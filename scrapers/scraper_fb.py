#!/usr/bin/env python3
"""
Facebook 租屋爬蟲 v1 - Playwright 版
板南線土城段（頂埔 → 江子翠）FB 社團 + 全站關鍵字搜尋
產出格式與 scraper_591.py 相同（data_fb.json schema）
"""

import re, time, json
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── 設定區 ──────────────────────────────────────────────────
MAX_PRICE   = 14000
PRICE_FLEX  = 15000   # 條件優異時放寬上限
MIN_FLOOR   = 2       # 排除一樓
FB_ID_START = 10001   # data_fb.json id 起始值

# 目標社團（每個搜尋套房出租）
GROUP_URLS = [
    ("我是土城人（頂埔大小事）", "https://www.facebook.com/groups/115901595712321/search/?q=出租+套房"),
    ("我是土城人",               "https://www.facebook.com/groups/iTuChengm/search/?q=出租+套房"),
    ("板橋租屋網 我是好房東",    "https://www.facebook.com/groups/3140810842843485/search/?q=套房+出租"),
    ("台北租屋出租專屬社團",     "https://www.facebook.com/groups/464870710346711/search/?q=板橋+套房"),
    ("台北租屋出租專屬平台2.0",  "https://www.facebook.com/groups/459966811445588/search/?q=板橋+套房"),
]

# 全站關鍵字搜尋（覆蓋板南線全9站）
SEARCH_QUERIES = [
    ("頂埔", "頂埔站+出租+套房"),
    ("頂埔", "土城頂埔+出租"),
    ("土城", "土城站+出租+套房"),
    ("土城", "新北市土城+出租+套房"),
    ("海山", "海山站+出租+套房"),
    ("府中", "府中站+出租+套房"),
    ("府中", "板橋府中+出租+套房"),
    ("亞東醫院", "亞東醫院站+出租+套房"),
    ("亞東醫院", "板橋亞東+出租+套房"),
    ("永寧", "永寧站+出租+套房"),
    ("永寧", "板橋永寧+出租+套房"),
    ("板橋", "板橋站+出租+套房"),
    ("板橋", "板橋區+出租+套房"),
    ("新埔", "新埔站+出租+套房"),
    ("新埔", "板橋新埔+出租+套房"),
    ("江子翠", "江子翠站+出租+套房"),
    ("江子翠", "板橋江子翠+出租+套房"),
]

# 站名對應 station 欄位值
STATION_MAP = {
    "頂埔": "頂埔", "土城": "土城", "海山": "海山",
    "府中": "府中", "亞東醫院": "亞東醫院", "永寧": "永寧",
    "板橋": "板橋", "新埔": "新埔", "江子翠": "江子翠",
}

# 排除關鍵字
REJECT_KW = ["頂樓加蓋", "鐵皮加蓋", "限女", "純女", "一樓出租", "店面"]
# ────────────────────────────────────────────────────────────


def scroll_and_expand(page, scrolls=3):
    """捲動頁面並展開「顯示更多」"""
    for _ in range(scrolls):
        page.evaluate("""
            Array.from(document.querySelectorAll('div[role=\"button\"],span[role=\"button\"]'))
                .filter(el => ['顯示更多','查看更多'].includes(el.textContent.trim()))
                .forEach(b => b.click());
        """)
        time.sleep(1.5)
        page.evaluate("window.scrollBy(0, 3000)")
        time.sleep(1.5)


def is_recent(text):
    """判斷貼文是否在24小時內（基於頁面文字）"""
    if re.search(r'\d+s*(分鐘|小時)前', text):
        return True
    if '剛剛' in text:
        return True
    # 「昨天」需判斷：若現在是早上，昨天下午可能超過24小時；保守起見納入
    if '昨天' in text:
        return True
    return False


def parse_price(text):
    """從貼文萃取月租金"""
    patterns = [
        r'租金[：:＄$]?s*$?s*(d[d,]+)s*元?',
        r'$s*(d[d,]+)s*/?s*月',
        r'(d[d,]+)s*元s*/s*月',
        r'月租[：:]?s*$?s*(d[d,]+)',
        r'(d{4,5})s*元/月',
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return int(m.group(1).replace(',', ''))
    return 0


def parse_size(text):
    """坪數"""
    m = re.search(r'(d+(?:.d+)?)s*坪', text)
    return float(m.group(1)) if m else 0.0


def parse_floor(text):
    """樓層"""
    m = re.search(r'(d+)s*樓', text)
    if m:
        return f"{m.group(1)}F"
    patterns_hi = ['高樓', '頂樓']
    if any(k in text for k in patterns_hi):
        return "高樓"
    return ""


def parse_deposit(text):
    m = re.search(r'押金[：:]?s*(d+)s*個?月', text)
    return int(m.group(1)) if m else 2


def parse_elec(text):
    if '獨立電' in text or '獨立電錶' in text:
        m = re.search(r'(d+(?:.d+)?)s*元?s*/?s*度', text)
        rate = m.group(1) if m else ''
        return f"獨立電錶{rate+'元/度' if rate else ''}"
    if '包水電' in text or '含水電' in text:
        return "包含水電"
    if '台電' in text:
        return "台電（需確認分攤方式）"
    if re.search(r'一?度s*$?s*(d+)', text):
        m = re.search(r'一?度s*$?s*(d+)', text)
        return f"獨立電錶{m.group(1)}元/度"
    return ""


def parse_station(text):
    """推斷最近捷運站"""
    for station in ["頂埔", "永寧", "土城", "海山", "亞東醫院", "亞東", "府中",
                    "新埔民生", "新埔", "板橋", "江子翠"]:
        if station in text:
            key = "亞東醫院" if station == "亞東" else station
            return STATION_MAP.get(key, station)
    return "板橋"


def parse_type(text):
    if "分租套房" in text:
        return "分租套房"
    if "獨立套房" in text or "套房" in text:
        return "獨立套房"
    if "雅房" in text:
        return "雅房"
    return "套房"


def parse_link(text):
    """萃取聯絡方式"""
    # 手機號碼
    m = re.search(r'(09\d{2}[-\s]?\d{3}[-\s]?\d{3})', text)
    if m:
        return m.group(1).replace(' ', '-')
    # LINE ID
    m = re.search(r'LINE\s*[：:iIdD]*\s*([A-Za-z0-9_.-]{3,30})', text)
    if m:
        return f"LINE: {m.group(1)}"
    # 私訊
    if '私訊' in text:
        return "FB私訊房東"
    return ""


def passes_filter(post):
    """篩選條件"""
    text = post.get('raw', '')
    price = post.get('price', 0)

    # 必要：有效租金
    if price <= 0:
        return False, "無法解析租金"
    if price > PRICE_FLEX:
        return False, f"租金 {price} 超出上限"

    # 必要：排除關鍵字
    for kw in REJECT_KW:
        if kw in text:
            return False, f"含排除關鍵字：{kw}"

    # 必要：非一樓
    floor = post.get('floor', '')
    if floor in ('1F', '1'):
        return False, "一樓"

    # 必要：電費非統一台電分攤
    elec = post.get('elec', '')
    if '台電' in elec and '獨立' not in elec:
        return False, "台電統一分攤（需確認）"

    return True, ""


def build_title(text, station):
    """從貼文建構標題"""
    # 試圖萃取地址片段
    m = re.search(r'(土城|板橋)[^
，。]{0,15}(路|街|巷|里|區)', text)
    if m:
        return f"{station}站 {m.group(0)[:20].strip()} 套房"
    return f"{station}站 套房出租"


def build_note(post, passed, flex_price=False):
    """組成 note 欄位"""
    parts = []
    text = post.get('raw', '')
    if '網路' not in text and '光纖' not in text:
        parts.append("網路未確認")
    if not re.search(r'(對外窗|採光|窗戶)', text):
        parts.append("窗戶未確認")
    if not re.search(r'(屋齡|民國|興建|年份|新建)', text):
        parts.append("屋齡未確認")
    if flex_price:
        parts.append("條件放寬（租金超14000）")
    # 加分項
    stars = []
    if post.get('elevator') == '有':
        stars.append("電梯⭐")
    if post.get('parking'):
        stars.append("停車⭐")
    if post.get('wardrobe'):
        stars.append("衣櫃⭐")
    if stars:
        parts.insert(0, "加分：" + " ".join(stars))
    return "。".join(parts)


def extract_posts(page):
    """從已載入頁面抽取所有貼文文字"""
    return page.evaluate("""
        () => {
            const posts = [];
            // FB 貼文通常在 div[data-pagelet] 或 role=article 下
            const articles = document.querySelectorAll('div[role="article"]');
            articles.forEach(a => {
                const text = a.innerText || '';
                if (text.length > 50) posts.push(text);
            });
            return posts;
        }
    """)


def scrape_facebook(user_data_dir=None):
    """
    主爬蟲函式
    user_data_dir: Chromium 持久化資料夾路徑，用於保留 FB 登入狀態
                   預設 ~/fb_session
    回傳: list of dict（符合 schema 的物件）
    """
    import os
    if user_data_dir is None:
        user_data_dir = os.path.expanduser("~/fb_session")

    today = datetime.now().strftime("%Y-%m-%d")
    seen_contacts = set()   # 去重用
    results = []
    errors = []

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,          # 首次需手動登入；登入後可改 True
            args=["--lang=zh-TW"],
            locale="zh-TW",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()

        def process_page(url, hint_station=""):
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(2.5)
                scroll_and_expand(page, scrolls=3)
                posts_text = extract_posts(page)
                return posts_text, hint_station
            except PWTimeout:
                errors.append(f"Timeout: {url}")
                return [], hint_station
            except Exception as e:
                errors.append(f"Error {url}: {e}")
                return [], hint_station

        all_raw_posts = []

        # 策略A：社團搜尋
        for group_name, url in GROUP_URLS:
            posts, station = process_page(url)
            for p in posts:
                all_raw_posts.append({"raw": p, "source_hint": "", "group": group_name})

        # 策略B：全站關鍵字搜尋
        for station_hint, query in SEARCH_QUERIES:
            url = f"https://www.facebook.com/search/posts/?q={query}"
            posts, _ = process_page(url, station_hint)
            for p in posts:
                all_raw_posts.append({"raw": p, "source_hint": station_hint, "group": "FB全站搜尋"})

        ctx.close()

    # 解析 + 篩選
    next_id = FB_ID_START
    for item in all_raw_posts:
        raw = item["raw"]

        # 時間過濾
        if not is_recent(raw):
            continue

        price = parse_price(raw)
        size  = parse_size(raw)
        floor = parse_floor(raw)
        deposit = parse_deposit(raw)
        elec  = parse_elec(raw)
        station = item["source_hint"] or parse_station(raw)
        rtype = parse_type(raw)
        link  = parse_link(raw)
        elev  = "有" if re.search(r'電梯|有電梯', raw) else ""
        wardrobe = bool(re.search(r'衣櫃|衣櫥', raw))
        parking  = bool(re.search(r'停車|車位|機車位|汽車位', raw))
        pets     = bool(re.search(r'可養寵|可帶寵|寵物可', raw))
        net      = bool(re.search(r'網路|光纖|WiFi', raw, re.I))
        window   = bool(re.search(r'對外窗|採光窗', raw))

        post_data = {
            "raw": raw, "price": price, "size": size, "floor": floor,
            "deposit": deposit, "elec": elec, "station": station,
            "type": rtype, "link": link, "elevator": elev,
            "wardrobe": wardrobe, "parking": parking, "pets": pets,
            "net": net, "window": window,
        }

        ok, reason = passes_filter(post_data)
        if not ok:
            continue

        # 去重（同一聯絡方式視為同一物件）
        dedup_key = link or raw[:80]
        if dedup_key in seen_contacts:
            continue
        seen_contacts.add(dedup_key)

        flex = price > MAX_PRICE
        note_parts = []
        if not net:    note_parts.append("網路未確認")
        if not window: note_parts.append("窗戶未確認")
        if not re.search(r'屋齡|民國|年份|新建', raw): note_parts.append("屋齡未確認")
        if flex:       note_parts.append("條件放寬（租金超14000）")
        if elev == "有":  note_parts.insert(0, "電梯⭐")
        if wardrobe:      note_parts.insert(0, "衣櫃⭐")
        if parking:       note_parts.insert(0, "停車⭐")

        title = build_title(raw, station)
        note  = "。".join(note_parts)
        # 貼文摘要（前100字，去除換行）
        summary = re.sub(r'\s+', ' ', raw[:120]).strip()
        if note:
            note = note + "。貼文：" + summary
        else:
            note = "貼文：" + summary

        results.append({
            "id":        next_id,
            "title":     title,
            "price":     price,
            "size":      size,
            "floor":     floor,
            "type":      rtype,
            "station":   station,
            "elec":      elec,
            "elevator":  elev,
            "window":    window,
            "net":       net,
            "parking":   parking,
            "wardrobe":  wardrobe,
            "pets":      pets,
            "deposit":   deposit,
            "link":      link,
            "note":      note,
            "source":    "FB社團",
            "date":      today,
            "pinned":    False,
            "dismissed": False,
            "score":     0,
        })
        next_id += 1

    return results, errors


if __name__ == "__main__":
    import sys
    user_data = sys.argv[1] if len(sys.argv) > 1 else None
    listings, errs = scrape_facebook(user_data)
    print(json.dumps(listings, ensure_ascii=False, indent=2))
    if errs:
        print("\n[錯誤]", "\n".join(errs), file=sys.stderr)
