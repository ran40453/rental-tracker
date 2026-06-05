#!/usr/bin/env python3
"""
591 租屋爬蟲 v3 - DOM 解析版
新北市藍線捷運站附近套房（土城區 section=39 + 板橋區 section=26）
預算：≤ 15,000 元
"""

import os, sys, re, time
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ── 設定區 ──────────────────────────────────────────────────
OUTPUT_DIR = os.path.expanduser("~/Desktop")
MAX_PRICE  = 15000
MIN_AREA   = 6       # 坪

# 591 section IDs（2026年確認）
SECTIONS = [
    {"id": "39", "name": "土城區"},
    {"id": "26", "name": "板橋區"},
]
# kind: 2=獨立套房, 3=分租套房
KINDS = [
    {"id": "2", "label": "獨立套房"},
    {"id": "3", "label": "分租套房"},
]

# 捷運站優先評分（越近頂埔越高）
STATION_SCORE = {
    "頂埔": 20, "永寧": 18, "土城": 16, "海山": 14,
    "亞東": 12, "新埔": 10, "板橋": 8, "府中": 6, "江子翠": 4,
}
NEW_BUILDING_KW = ["大樓", "電梯", "社區", "新建", "捷運宅"]
REJECT_KW       = ["頂樓加蓋", "鐵皮加蓋", "限女"]
# ────────────────────────────────────────────────────────────

KIND_LABEL = {"2": "獨立套房", "3": "分租套房", "1": "整層住家", "4": "雅房"}
KIND_COLOR = {"2": "#2196F3", "3": "#FF9800", "1": "#4CAF50", "4": "#9C27B0"}


def parse_listing_item(item_el, section_name, kind_id):
    """解析單筆房源 BeautifulSoup element"""
    # 標題
    title_el = item_el.find(class_="item-info-title")
    title = title_el.get_text(strip=True) if title_el else ""

    # 價格（抓數字）
    price_el = item_el.find(class_="item-info-price")
    price_text = price_el.get_text(" ", strip=True) if price_el else ""
    price_m = re.search(r"([\d,]+)", price_text.replace(",", ""))
    price = int(price_m.group(1).replace(",", "")) if price_m else 0

    # Info 文字（坪數 / 樓層 / 類型）
    txt_el  = item_el.find(class_="item-info-txt")
    txt_raw = txt_el.get_text(" | ", strip=True) if txt_el else ""

    # 坪數
    area_m = re.search(r"([\d.]+)\s*坪", txt_raw)
    area   = float(area_m.group(1)) if area_m else 0

    # 樓層
    floor_m = re.search(r"(\d+)F/(\d+)F", txt_raw)
    floor       = floor_m.group(1) if floor_m else ""
    total_floor = floor_m.group(2) if floor_m else ""

    # 地址 / 區域
    addr_el = item_el.find(class_="address")
    address = addr_el.get_text(" ", strip=True) if addr_el else section_name

    # 捷運距離
    metro_el = item_el.find(class_="house-metro")
    metro    = metro_el.get_text(" ", strip=True) if metro_el else ""

    # 標籤（近捷運、可開伙等）
    tag_els = item_el.find_all(class_="item-info-tag")
    tags    = [t.get_text(strip=True) for t in tag_els if t.get_text(strip=True)]

    # 連結
    link_el = item_el.find("a", href=True)
    link    = link_el["href"] if link_el else ""
    # ID from link
    pid_m = re.search(r"/(\d+)$", link)
    pid   = pid_m.group(1) if pid_m else ""

    # 圖片（data-src for lazy load）
    img_el = item_el.find("img")
    img    = ""
    if img_el:
        img = img_el.get("data-src") or img_el.get("data-original") or ""
        # skip SVG placeholders
        if img.startswith("data:"):
            img = ""

    return {
        "id":          pid,
        "title":       title,
        "address":     address,
        "section":     section_name,
        "price":       price,
        "area_ping":   area,
        "kind":        kind_id,
        "floor":       floor,
        "total_floor": total_floor,
        "metro":       metro,
        "tags":        tags,
        "url":         link if link.startswith("http") else f"https://rent.591.com.tw{link}",
        "img":         img,
    }


def score_listing(item):
    title = item["title"] + " " + item["address"] + " " + item["metro"]

    for bad in REJECT_KW:
        if bad in title:
            return -1

    score = 0
    kind  = item.get("kind", "0")

    if kind == "2":   score += 30
    elif kind == "3": score += 10

    for station, pts in STATION_SCORE.items():
        if station in title:
            score += pts
            break

    for kw in NEW_BUILDING_KW:
        if kw in title:
            score += 5
            break

    area = item.get("area_ping", 0)
    if area >= 10:   score += 10
    elif area >= 8:  score += 7
    elif area >= 7:  score += 5
    elif area >= 6:  score += 3

    price = item.get("price", 99999)
    if price <= 13500:   score += 10
    elif price <= 14000: score += 7
    elif price <= 14500: score += 5

    if "近捷運" in " ".join(item.get("tags", [])):
        score += 3

    return score


def fetch_page(page, url, max_wait=45000):
    page.goto(url, wait_until="networkidle", timeout=max_wait)
    page.wait_for_timeout(3000)
    return page.content()


def scrape_listings(page, section_id, section_name, kind_id, kind_label):
    """爬取單一區域 + 種類的所有頁面"""
    items  = []
    page_n = 1

    while True:
        first_row = (page_n - 1) * 30
        url = (
            f"https://rent.591.com.tw/list"
            f"?region=3&kind={kind_id}&section={section_id}"
            f"&price=0_{MAX_PRICE}&area={MIN_AREA}_"
            f"&order=posttime&firstRow={first_row}"
        )
        print(f"    p{page_n} → {section_name} {kind_label}...", end="", flush=True)

        html  = fetch_page(page, url)
        soup  = BeautifulSoup(html, "html.parser")

        # 取得總筆數
        if page_n == 1:
            cnt_m = re.search(r"已為你找到([\d,]+)間", soup.get_text())
            total = int(cnt_m.group(1).replace(",", "")) if cnt_m else 0
            print(f" 共{total}筆", end="")

        wrapper = soup.find(class_="list-wrapper")
        if not wrapper:
            print(" [無 list-wrapper]")
            break

        card_els = wrapper.find_all(class_="item")
        if not card_els:
            print(" [0筆]")
            break

        print(f" {len(card_els)}筆")
        for el in card_els:
            parsed = parse_listing_item(el, section_name, kind_id)
            if parsed["price"] > 0:   # skip empty
                items.append(parsed)

        # 是否還有下一頁
        if len(items) >= total or page_n >= 5 or len(card_els) < 30:
            break

        page_n += 1
        time.sleep(1)

    return items


def fetch_all():
    print("🔍 啟動 Playwright 瀏覽器...")
    all_items = []
    seen_ids  = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="zh-TW",
        )
        pg = ctx.new_page()

        # warm up session
        pg.goto("https://rent.591.com.tw/", wait_until="domcontentloaded", timeout=30000)
        pg.wait_for_timeout(1500)

        for sec in SECTIONS:
            print(f"\n  📍 {sec['name']}")
            for kind in KINDS:
                raw = scrape_listings(pg, sec["id"], sec["name"], kind["id"], kind["label"])
                for item in raw:
                    pid = item["id"] or item["url"]
                    if pid not in seen_ids:
                        seen_ids.add(pid)
                        item["score"] = score_listing(item)
                        if item["score"] >= 0:
                            all_items.append(item)

        browser.close()

    all_items.sort(key=lambda x: x["score"], reverse=True)
    print(f"\n✅ 共 {len(all_items)} 筆有效房源（排除限女、頂加）")
    return all_items


def classify_building(item):
    """判斷大樓 or 公寓 or 其他"""
    text = item["title"] + " " + item["address"] + " " + " ".join(item.get("tags", []))
    if any(k in text for k in ["大樓", "電梯", "社區", "華廈", "捷運宅", "新建", "大廈"]):
        return "大樓"
    if any(k in text for k in ["公寓", "透天", "平房"]):
        return "公寓"
    return "未知"


def generate_html(items, output_path):
    import json as _json
    now = datetime.now().strftime("%Y/%m/%d %H:%M")

    # Attach building type
    for item in items:
        item["building_type"] = classify_building(item)

    # Serialize to JSON for JS
    items_json = _json.dumps(items, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>租屋搜尋 {now}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--blue:#1565C0;--blue-lt:#42A5F5;--green:#2E7D32;--orange:#E65100;--red:#C62828;--gray:#757575}}
body{{font-family:-apple-system,'PingFang TC',sans-serif;background:#f0f4f8;color:#222;min-height:100vh}}

/* HEADER */
.header{{background:linear-gradient(135deg,var(--blue),var(--blue-lt));color:#fff;padding:20px 24px 16px}}
.header h1{{font-size:20px;font-weight:700;display:flex;align-items:center;gap:8px}}
.header-sub{{font-size:12px;opacity:.8;margin-top:4px}}

/* STATS BAR */
.stats-bar{{display:flex;gap:10px;padding:12px 24px;background:#fff;border-bottom:1px solid #dde3ea;flex-wrap:wrap;align-items:center}}
.stat{{background:#f0f4ff;border-radius:8px;padding:6px 14px;text-align:center;min-width:70px}}
.stat .n{{font-size:18px;font-weight:700;color:var(--blue);line-height:1}}
.stat .l{{font-size:10px;color:#666;margin-top:2px}}
.stat-spacer{{flex:1}}
.btn{{display:inline-flex;align-items:center;gap:5px;padding:7px 14px;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;border:none;transition:.15s}}
.btn-primary{{background:var(--blue);color:#fff}}
.btn-primary:hover{{background:#1976D2}}
.btn-outline{{background:#fff;color:var(--blue);border:1.5px solid var(--blue)}}
.btn-outline:hover{{background:#f0f4ff}}
.btn-danger{{background:#fff;color:var(--red);border:1.5px solid #ffcdd2}}
.btn-danger:hover{{background:#ffebee}}

/* FILTER PANEL */
.filter-panel{{background:#fff;border-bottom:1px solid #dde3ea;padding:10px 24px;display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}}
.filter-group{{display:flex;flex-direction:column;gap:3px}}
.filter-group label{{font-size:11px;color:#888;font-weight:500}}
.filter-group select, .filter-group input[type=number]{{
  padding:5px 10px;border:1.5px solid #dde3ea;border-radius:7px;
  font-size:13px;color:#333;background:#fff;outline:none;
  appearance:none;-webkit-appearance:none;min-width:110px}}
.filter-group select:focus, .filter-group input:focus{{border-color:var(--blue)}}
.budget-wrap{{display:flex;flex-direction:column;gap:3px}}
.budget-row{{display:flex;align-items:center;gap:6px}}
.budget-row input[type=range]{{width:130px;accent-color:var(--blue)}}
.budget-val{{font-size:13px;font-weight:600;color:var(--blue);min-width:58px}}
.chip-group{{display:flex;gap:5px;flex-wrap:wrap;align-items:center}}
.chip{{padding:4px 10px;border-radius:20px;font-size:12px;cursor:pointer;border:1.5px solid #dde3ea;background:#fff;color:#555;transition:.12s;user-select:none}}
.chip.active{{background:var(--blue);color:#fff;border-color:var(--blue)}}
.chip:hover:not(.active){{background:#f0f4ff;border-color:var(--blue-lt)}}
.divider{{width:1px;height:28px;background:#e0e0e0;align-self:center}}

/* ACTIVE FILTERS STRIP */
.active-filters{{padding:6px 24px;background:#f8f9ff;border-bottom:1px solid #e8ecf4;display:none;gap:6px;flex-wrap:wrap;align-items:center;font-size:12px}}
.af-chip{{background:#e3f2fd;color:#1565C0;padding:2px 8px;border-radius:12px;display:flex;align-items:center;gap:4px}}
.af-chip span{{cursor:pointer;opacity:.7}}
.af-chip span:hover{{opacity:1}}

/* TABLE */
.table-wrap{{padding:16px 24px;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 6px rgba(0,0,0,.07)}}
th{{background:var(--blue);color:#fff;padding:10px 8px;font-size:12px;font-weight:600;white-space:nowrap;cursor:pointer;user-select:none;position:sticky;top:0}}
th:hover{{background:#1976D2}}
th .sort-icon{{margin-left:4px;opacity:.6;font-size:10px}}
td{{padding:9px 8px;font-size:13px;border-bottom:1px solid #f0f2f5;vertical-align:middle}}
tr:hover td{{background:#f7f9ff}}
tr.fav-row td{{background:#fffbf0 !important}}
tr.hidden-row{{display:none}}

/* CELLS */
.listing-title{{color:var(--blue);text-decoration:none;font-weight:500;font-size:13px;line-height:1.3}}
.listing-title:hover{{text-decoration:underline}}
.meta{{color:#999;font-size:11px;margin-top:2px}}
.metro-txt{{color:#1976D2;font-size:11px;margin-top:2px}}
.kind-badge{{display:inline-block;padding:2px 8px;border-radius:10px;color:#fff;font-size:11px;font-weight:600;white-space:nowrap}}
.btype-badge{{display:inline-block;padding:2px 7px;border-radius:8px;font-size:11px;font-weight:500}}
.btype-大樓{{background:#E8F5E9;color:#2E7D32}}
.btype-公寓{{background:#FFF3E0;color:#E65100}}
.btype-未知{{background:#F5F5F5;color:#9E9E9E}}
.badge{{display:inline-block;padding:1px 6px;border-radius:8px;font-size:10px;margin-right:2px}}
.badge-new{{background:#E8F5E9;color:#2E7D32}}
.badge-cheap{{background:#E3F2FD;color:var(--blue)}}
.tag{{display:inline-block;background:#f0f0f0;color:#555;padding:1px 5px;border-radius:4px;font-size:10px;margin:1px}}
.price-val{{font-weight:700;font-size:14px}}
.price-ok{{color:var(--green)}}
.price-hi{{color:var(--red)}}
.stars{{letter-spacing:-1px}}

/* ACTION BUTTONS */
.act-btn{{background:none;border:none;cursor:pointer;padding:3px 5px;border-radius:5px;font-size:15px;transition:.1s;opacity:.5}}
.act-btn:hover{{opacity:1;background:#f0f0f0}}
.act-btn.fav-on{{opacity:1;color:#E91E63}}
.act-btn.del-btn:hover{{background:#ffebee}}

/* EMPTY STATE */
.empty{{text-align:center;padding:60px 20px;color:#aaa}}
.empty .e-icon{{font-size:48px;margin-bottom:12px}}

/* TOAST */
.toast{{position:fixed;bottom:24px;right:24px;background:#323232;color:#fff;padding:10px 18px;border-radius:8px;font-size:13px;z-index:9999;opacity:0;transition:.3s;pointer-events:none}}
.toast.show{{opacity:1}}

/* FOOTER */
.footer{{text-align:center;padding:16px;color:#bbb;font-size:11px}}

@media(max-width:768px){{
  .filter-panel{{padding:10px 12px}}
  .table-wrap{{padding:10px 8px}}
  th,td{{padding:7px 5px;font-size:12px}}
}}
</style>
</head>
<body>

<div class="header">
  <h1>🏠 租屋搜尋</h1>
  <div class="header-sub">更新：{now} ｜ 來源：591 租屋網 ｜ 新北市土城區 + 板橋區</div>
</div>

<!-- STATS -->
<div class="stats-bar" id="statsBar">
  <div class="stat"><div class="n" id="statTotal">0</div><div class="l">顯示</div></div>
  <div class="stat"><div class="n" id="statSuite">0</div><div class="l">獨立套房</div></div>
  <div class="stat"><div class="n" id="statShare">0</div><div class="l">分租套房</div></div>
  <div class="stat"><div class="n" id="statCheap">0</div><div class="l">≤13,500</div></div>
  <div class="stat"><div class="n" id="statBldg">0</div><div class="l">大樓</div></div>
  <div class="stat"><div class="n" id="statFav">0</div><div class="l">我的最愛</div></div>
  <div class="stat-spacer"></div>
  <button class="btn btn-outline" onclick="showOnlyFav()" id="favBtn">❤️ 只看最愛</button>
  <button class="btn btn-outline" onclick="showDeletedModal()" id="deletedBtn">🗑️ 已隱藏 (<span id="deletedCount">0</span>)</button>
  <button class="btn btn-outline" onclick="exportFav()">📥 匯出最愛</button>
</div>

<!-- FILTERS -->
<div class="filter-panel">
  <!-- 區域 -->
  <div class="filter-group">
    <label>區域</label>
    <select id="fRegion" onchange="applyFilters()">
      <option value="">全部</option>
      <option value="土城區">土城區</option>
      <option value="板橋區">板橋區</option>
    </select>
  </div>

  <!-- 類型 -->
  <div class="filter-group">
    <label>房型</label>
    <select id="fKind" onchange="applyFilters()">
      <option value="">全部</option>
      <option value="2">獨立套房</option>
      <option value="3">分租套房</option>
    </select>
  </div>

  <!-- 建物類型 -->
  <div class="filter-group">
    <label>建物</label>
    <select id="fBtype" onchange="applyFilters()">
      <option value="">全部</option>
      <option value="大樓">大樓/電梯</option>
      <option value="公寓">公寓</option>
    </select>
  </div>

  <!-- 排序 -->
  <div class="filter-group">
    <label>排序</label>
    <select id="fSort" onchange="applyFilters()">
      <option value="score">評分（高→低）</option>
      <option value="price_asc">月租（低→高）</option>
      <option value="price_desc">月租（高→低）</option>
      <option value="area_desc">坪數（大→小）</option>
      <option value="area_asc">坪數（小→大）</option>
    </select>
  </div>

  <div class="divider"></div>

  <!-- 預算滑桿 -->
  <div class="budget-wrap">
    <label style="font-size:11px;color:#888;font-weight:500">最高月租預算</label>
    <div class="budget-row">
      <input type="range" id="budgetSlider" min="5000" max="25000" step="500" value="{MAX_PRICE}"
             oninput="updateBudget(this.value)" onchange="applyFilters()">
      <span class="budget-val" id="budgetVal">NT${MAX_PRICE:,}</span>
    </div>
  </div>

  <!-- 坪數下限 -->
  <div class="filter-group">
    <label>最小坪數</label>
    <div style="display:flex;align-items:center;gap:4px">
      <input type="number" id="fMinArea" value="{MIN_AREA}" min="1" max="30" step="1"
             style="width:70px" onchange="applyFilters()">
      <span style="font-size:12px;color:#888">坪</span>
    </div>
  </div>

  <div class="divider"></div>

  <!-- 快速篩選chips -->
  <div class="filter-group">
    <label>快速篩選</label>
    <div class="chip-group">
      <div class="chip" id="chip-elevator" onclick="toggleChip('elevator')">🛗 有電梯</div>
      <div class="chip" id="chip-metro"    onclick="toggleChip('metro')">🚇 近捷運</div>
      <div class="chip" id="chip-fav"      onclick="toggleChip('fav')">❤️ 最愛</div>
      <div class="chip" id="chip-budget"   onclick="toggleChip('budget')">💰 預算內</div>
    </div>
  </div>

  <div style="flex:1"></div>
  <button class="btn btn-outline" onclick="resetFilters()" style="align-self:flex-end">✕ 清除篩選</button>
</div>

<!-- ACTIVE FILTERS STRIP -->
<div class="active-filters" id="activeFilters"></div>

<!-- TABLE -->
<div class="table-wrap">
  <table id="mainTable">
    <thead>
      <tr>
        <th style="width:36px">#</th>
        <th style="width:70px">圖片</th>
        <th>地址 / 標題</th>
        <th style="width:80px" onclick="sortBy('kind')">房型 <span class="sort-icon">⇅</span></th>
        <th style="width:80px" onclick="sortBy('btype')">建物 <span class="sort-icon">⇅</span></th>
        <th style="width:90px" onclick="sortBy('price_asc')">月租(元) <span class="sort-icon">⇅</span></th>
        <th style="width:70px" onclick="sortBy('area_desc')">坪數 <span class="sort-icon">⇅</span></th>
        <th style="width:64px">樓層</th>
        <th style="width:70px" onclick="sortBy('score')">評分 <span class="sort-icon">⇅</span></th>
        <th style="width:72px">操作</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
  <div class="empty" id="emptyState" style="display:none">
    <div class="e-icon">🔍</div>
    <div>目前沒有符合條件的房源</div>
    <div style="font-size:12px;margin-top:6px;color:#ccc">試著放寬篩選條件</div>
  </div>
</div>

<div class="footer">
  ⭐ 評分：套房類型＋捷運（頂埔優先）＋新大樓＋坪數＋價格 ｜ 資料來源：591 租屋網 ｜ 僅供參考
</div>

<!-- DELETED MODAL -->
<div id="deletedModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:1000;align-items:center;justify-content:center">
  <div style="background:#fff;border-radius:14px;width:90%;max-width:560px;max-height:80vh;display:flex;flex-direction:column;box-shadow:0 8px 32px rgba(0,0,0,.2)">
    <div style="padding:16px 20px;border-bottom:1px solid #eee;display:flex;align-items:center;justify-content:space-between">
      <strong style="font-size:15px">🗑️ 已隱藏的房源</strong>
      <div style="display:flex;gap:8px">
        <button class="btn btn-danger" onclick="restoreAllDeleted()" style="font-size:12px;padding:5px 10px">全部還原</button>
        <button class="btn btn-outline" onclick="closeDeletedModal()" style="font-size:12px;padding:5px 10px">關閉</button>
      </div>
    </div>
    <div id="deletedList" style="overflow-y:auto;padding:12px 16px;flex:1;min-height:60px"></div>
    <div id="deletedEmpty" style="padding:32px;text-align:center;color:#aaa;display:none">沒有隱藏的房源</div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
// ── Raw data from Python ──────────────────────────────────────
const RAW = {items_json};

// ── Persistent state (localStorage) ──────────────────────────
const LS = {{
  get favs()    {{ try{{return JSON.parse(localStorage.getItem('rf_favs')||'[]')}}catch{{return[]}} }},
  get deleted() {{ try{{return JSON.parse(localStorage.getItem('rf_deleted')||'[]')}}catch{{return[]}} }},
  addFav(id)    {{ const s=new Set(this.favs); s.add(id); localStorage.setItem('rf_favs',JSON.stringify([...s])) }},
  removeFav(id) {{ const s=new Set(this.favs); s.delete(id); localStorage.setItem('rf_favs',JSON.stringify([...s])) }},
  addDel(id)    {{ const s=new Set(this.deleted); s.add(id); localStorage.setItem('rf_deleted',JSON.stringify([...s])) }},
  clearDel()    {{ localStorage.removeItem('rf_deleted') }},
  isFav(id)     {{ return this.favs.includes(id) }},
  isDel(id)     {{ return this.deleted.includes(id) }},
}};

const KIND_LABEL = {{"2":"獨立套房","3":"分租套房","1":"整層住家","4":"雅房"}};
const KIND_COLOR = {{"2":"#2196F3","3":"#FF9800","1":"#4CAF50","4":"#9C27B0"}};

let chips = {{}};
let sortKey = 'score';

// ── Chips ─────────────────────────────────────────────────────
function toggleChip(id) {{
  chips[id] = !chips[id];
  document.getElementById('chip-'+id).classList.toggle('active', !!chips[id]);
  applyFilters();
}}

// ── Budget ────────────────────────────────────────────────────
function updateBudget(v) {{
  document.getElementById('budgetVal').textContent = 'NT$' + Number(v).toLocaleString();
}}

// ── Sort ──────────────────────────────────────────────────────
function sortBy(key) {{
  // toggle asc/desc if same key
  if (key === sortKey && key === 'price_asc') key = 'price_desc';
  else if (key === sortKey && key === 'price_desc') key = 'price_asc';
  else if (key === sortKey && key === 'area_desc') key = 'area_asc';
  else if (key === sortKey && key === 'area_asc')  key = 'area_desc';
  sortKey = key;
  document.getElementById('fSort').value = key;
  applyFilters();
}}

// ── Core filter + render ──────────────────────────────────────
function applyFilters() {{
  const region   = document.getElementById('fRegion').value;
  const kind     = document.getElementById('fKind').value;
  const btype    = document.getElementById('fBtype').value;
  const budget   = parseInt(document.getElementById('budgetSlider').value);
  const minArea  = parseFloat(document.getElementById('fMinArea').value) || 0;
  const sk       = document.getElementById('fSort').value;
  sortKey = sk;

  const deleted = new Set(LS.deleted);
  const favs    = new Set(LS.favs);

  let data = RAW.filter(d => {{
    if (deleted.has(d.id)) return false;
    if (region   && d.section !== region)       return false;
    if (kind     && d.kind    !== kind)          return false;
    if (btype    && d.building_type !== btype)   return false;
    if (d.price  > budget)                       return false;
    if (d.area_ping < minArea)                   return false;
    if (chips.elevator && !['大樓'].includes(d.building_type)) return false;
    if (chips.metro    && !d.metro)              return false;
    if (chips.fav      && !favs.has(d.id))       return false;
    if (chips.budget   && d.price > 13500)       return false;
    return true;
  }});

  // sort
  data = [...data].sort((a,b) => {{
    if (sk==='price_asc')  return a.price - b.price;
    if (sk==='price_desc') return b.price - a.price;
    if (sk==='area_desc')  return b.area_ping - a.area_ping;
    if (sk==='area_asc')   return a.area_ping - b.area_ping;
    if (sk==='kind')       return a.kind.localeCompare(b.kind);
    if (sk==='btype')      return a.building_type.localeCompare(b.building_type);
    return b.score - a.score;  // default: score
  }});

  renderTable(data);
  renderStats(data, favs.size);
  renderActiveFilters({{region, kind, btype, budget, minArea, chips}});
}}

// ── Render table ──────────────────────────────────────────────
function renderTable(data) {{
  const tbody = document.getElementById('tbody');
  const favs  = new Set(LS.favs);

  if (!data.length) {{
    tbody.innerHTML = '';
    document.getElementById('emptyState').style.display = 'block';
    return;
  }}
  document.getElementById('emptyState').style.display = 'none';

  tbody.innerHTML = data.map((d, i) => {{
    const isFav = favs.has(d.id);
    const kColor = KIND_COLOR[d.kind] || '#999';
    const kLabel = KIND_LABEL[d.kind] || '?';
    const pClass = d.price > 14000 ? 'price-hi' : 'price-ok';
    const stars  = '⭐'.repeat(Math.min(5, Math.max(1, Math.floor(d.score/10))));

    const badges = [
      d.building_type==='大樓' ? '<span class="badge badge-new">🏢大樓</span>' : '',
      d.price<=13500 && d.price>0 ? '<span class="badge badge-cheap">💰預算內</span>' : '',
    ].join('');
    const tags = (d.tags||[]).slice(0,3).map(t=>`<span class="tag">${{t}}</span>`).join('');

    const imgHtml = d.img
      ? `<img src="${{d.img}}" style="width:70px;height:52px;object-fit:cover;border-radius:5px" onerror="this.style.display='none'">`
      : '<div style="width:70px;height:52px;background:#eee;border-radius:5px;display:flex;align-items:center;justify-content:center;color:#ccc;font-size:20px">🏠</div>';

    const floorTxt = (d.floor && d.total_floor) ? `${{d.floor}}/${{d.total_floor}}樓` : (d.floor||'-');
    const metroHtml = d.metro ? `<div class="metro-txt">🚇 ${{d.metro}}</div>` : '';

    const btypeClass = `btype-${{d.building_type}}`;

    return `<tr class="${{isFav?'fav-row':''}}" id="row-${{d.id}}">
      <td style="text-align:center;color:#aaa;font-size:12px">${{i+1}}</td>
      <td>${{imgHtml}}</td>
      <td>
        <a href="${{d.url}}" target="_blank" class="listing-title">${{d.title}}</a>
        <div style="margin-top:3px">${{badges}}${{tags}}</div>
        <div class="meta">${{d.section}} · ${{d.address}}</div>
        ${{metroHtml}}
      </td>
      <td style="text-align:center"><span class="kind-badge" style="background:${{kColor}}">${{kLabel}}</span></td>
      <td style="text-align:center"><span class="btype-badge ${{btypeClass}}">${{d.building_type}}</span></td>
      <td style="text-align:center"><span class="price-val ${{pClass}}">${{d.price.toLocaleString()}}</span></td>
      <td style="text-align:center">${{d.area_ping.toFixed(1)}} 坪</td>
      <td style="text-align:center;font-size:12px">${{floorTxt}}</td>
      <td style="text-align:center">${{stars}}<br><small style="color:#bbb">${{d.score}}分</small></td>
      <td style="text-align:center;white-space:nowrap">
        <button class="act-btn ${{isFav?'fav-on':''}}" onclick="toggleFav('${{d.id}}')" title="${{isFav?'取消最愛':'加入最愛'}}">${{isFav?'❤️':'🤍'}}</button>
        <button class="act-btn del-btn" onclick="deleteListing('${{d.id}}')" title="隱藏此房源">🗑️</button>
      </td>
    </tr>`;
  }}).join('');
}}

// ── Stats ─────────────────────────────────────────────────────
function renderStats(data, favCount) {{
  document.getElementById('statTotal').textContent = data.length;
  document.getElementById('statSuite').textContent = data.filter(d=>d.kind==='2').length;
  document.getElementById('statShare').textContent = data.filter(d=>d.kind==='3').length;
  document.getElementById('statCheap').textContent = data.filter(d=>d.price<=13500&&d.price>0).length;
  document.getElementById('statBldg').textContent  = data.filter(d=>d.building_type==='大樓').length;
  document.getElementById('statFav').textContent   = favCount;
}}

// ── Active filters strip ──────────────────────────────────────
function renderActiveFilters(f) {{
  const bar = document.getElementById('activeFilters');
  const pills = [];
  if (f.region)           pills.push([`區域：${{f.region}}`,   ()=>{{document.getElementById('fRegion').value='';applyFilters()}}]);
  if (f.kind)             pills.push([`房型：${{KIND_LABEL[f.kind]}}`, ()=>{{document.getElementById('fKind').value='';applyFilters()}}]);
  if (f.btype)            pills.push([`建物：${{f.btype}}`,    ()=>{{document.getElementById('fBtype').value='';applyFilters()}}]);
  if (f.budget<{MAX_PRICE}) pills.push([`預算≤${{f.budget.toLocaleString()}}`, ()=>{{document.getElementById('budgetSlider').value={MAX_PRICE};updateBudget({MAX_PRICE});applyFilters()}}]);
  if (f.minArea>6)        pills.push([`≥${{f.minArea}}坪`,    ()=>{{document.getElementById('fMinArea').value=6;applyFilters()}}]);
  Object.entries(f.chips).filter(([,v])=>v).forEach(([k])=>pills.push([`chip:${{k}}`, ()=>toggleChip(k)]));

  if (pills.length) {{
    bar.style.display='flex';
    bar.innerHTML = '🔍 目前篩選：' + pills.map(([label, fn], idx)=>
      `<span class="af-chip" id="af${{idx}}">${{label}} <span onclick="([${{pills.map((_,i)=>`window._afcb${{i}}`).join(',')}}])[${{idx}}]()">✕</span></span>`
    ).join('');
    pills.forEach(([,fn],i) => window[`_afcb${{i}}`] = fn);
  }} else {{
    bar.style.display='none';
  }}
}}

// ── Fav / Delete ──────────────────────────────────────────────
function toggleFav(id) {{
  if (LS.isFav(id)) {{
    LS.removeFav(id);
    showToast('已移除最愛');
  }} else {{
    LS.addFav(id);
    showToast('❤️ 已加入最愛');
  }}
  applyFilters();
}}

function deleteListing(id) {{
  LS.addDel(id);
  const row = document.getElementById('row-'+id);
  if (row) {{ row.style.transition='.3s'; row.style.opacity='0'; setTimeout(()=>applyFilters(),300); }}
  showToast('已隱藏，點「還原刪除」可復原');
}}

function restoreDeleted(id) {{
  const s = new Set(LS.deleted);
  s.delete(id);
  localStorage.setItem('rf_deleted', JSON.stringify([...s]));
  applyFilters();
  renderDeletedModal();
  showToast('已還原該房源');
}}

function restoreAllDeleted() {{
  LS.clearDel();
  applyFilters();
  renderDeletedModal();
  showToast('已還原所有隱藏房源');
}}

function showDeletedModal() {{
  document.getElementById('deletedModal').style.display = 'flex';
  renderDeletedModal();
}}

function closeDeletedModal() {{
  document.getElementById('deletedModal').style.display = 'none';
}}

function renderDeletedModal() {{
  const deleted = new Set(LS.deleted);
  const btn = document.getElementById('deletedBtn');
  document.getElementById('deletedCount').textContent = deleted.size;

  const list = document.getElementById('deletedList');
  const empty = document.getElementById('deletedEmpty');

  if (!deleted.size) {{
    list.innerHTML = '';
    list.style.display = 'none';
    empty.style.display = 'block';
    return;
  }}
  list.style.display = 'block';
  empty.style.display = 'none';

  const deletedItems = RAW.filter(d => deleted.has(d.id));
  const unknown = deleted.size - deletedItems.length;  // IDs from older scrapes

  list.innerHTML = deletedItems.map(d => `
    <div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #f5f5f5">
      <div style="flex:1">
        <a href="${{d.url}}" target="_blank" style="color:#1565C0;font-size:13px;text-decoration:none;font-weight:500">${{d.title}}</a>
        <div style="font-size:11px;color:#999;margin-top:2px">${{d.section}} · ${{d.price.toLocaleString()}}元/月 · ${{d.area_ping.toFixed(1)}}坪</div>
      </div>
      <button class="btn btn-outline" onclick="restoreDeleted('${{d.id}}')" style="font-size:11px;padding:4px 10px;white-space:nowrap">還原</button>
    </div>
  `).join('') + (unknown > 0 ? `<div style="font-size:11px;color:#bbb;padding:8px 0;text-align:center">另有 ${{unknown}} 筆來自舊報表的隱藏記錄（已不在本次搜尋結果中）</div>` : '');
}}

function showOnlyFav() {{
  const btn = document.getElementById('favBtn');
  chips.fav = !chips.fav;
  document.getElementById('chip-fav').classList.toggle('active', chips.fav);
  btn.textContent = chips.fav ? '❤️ 全部顯示' : '❤️ 只看最愛';
  applyFilters();
}}

// ── Export favs ───────────────────────────────────────────────
function exportFav() {{
  const favs = new Set(LS.favs);
  const data = RAW.filter(d=>favs.has(d.id));
  if (!data.length) {{ showToast('尚無最愛房源'); return; }}

  let csv = '標題,區域,類型,建物,月租,坪數,樓層,捷運,連結\\n';
  data.forEach(d=>{{
    csv += [d.title,d.section,KIND_LABEL[d.kind]||'',d.building_type,d.price,d.area_ping,
            d.floor?d.floor+'/'+d.total_floor+'樓':'',d.metro||'',d.url]
           .map(v=>`"${{String(v).replace(/"/g,'""')}}"`)
           .join(',') + '\\n';
  }});

  const blob = new Blob(['﻿'+csv], {{type:'text/csv;charset=utf-8'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = '我的最愛房源.csv';
  a.click();
  showToast(`已匯出 ${{data.length}} 筆最愛房源`);
}}

// ── Toast ─────────────────────────────────────────────────────
let toastTimer;
function showToast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=>t.classList.remove('show'), 2200);
}}

// ── Reset ─────────────────────────────────────────────────────
function resetFilters() {{
  document.getElementById('fRegion').value = '';
  document.getElementById('fKind').value   = '';
  document.getElementById('fBtype').value  = '';
  document.getElementById('fSort').value   = 'score';
  document.getElementById('budgetSlider').value = {MAX_PRICE};
  document.getElementById('fMinArea').value = {MIN_AREA};
  updateBudget({MAX_PRICE});
  chips = {{}};
  ['elevator','metro','fav','budget'].forEach(k=>document.getElementById('chip-'+k).classList.remove('active'));
  applyFilters();
}}

// ── Close modal on backdrop click ────────────────────────────
document.getElementById('deletedModal').addEventListener('click', function(e) {{
  if (e.target === this) closeDeletedModal();
}});

// ── Init ──────────────────────────────────────────────────────
applyFilters();
renderDeletedModal();
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"💾 已儲存：{output_path}")


def main():
    print("=" * 54)
    print("🏠 591 租屋爬蟲 v3  (Playwright DOM 解析)")
    print(f"   預算 ≤ {MAX_PRICE:,} 元｜坪數 ≥ {MIN_AREA} 坪")
    print(f"   地區：新北市土城區 + 板橋區")
    print("=" * 54)

    items    = fetch_all()
    date_str = datetime.now().strftime("%Y%m%d_%H%M")

    dated_path  = os.path.join(OUTPUT_DIR, f"rental_report_{date_str}.html")
    latest_path = os.path.join(OUTPUT_DIR, "rental_latest.html")

    generate_html(items, dated_path)
    generate_html(items, latest_path)

    print(f"\n📂 open '{latest_path}'")
    if sys.platform == "darwin":
        os.system(f"open '{latest_path}'")


if __name__ == "__main__":
    main()
