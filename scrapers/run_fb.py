#!/usr/bin/env python3
"""
run_fb.py — FB 租屋爬蟲每日執行腳本
1. 讀取 GitHub README 確認最新架構
2. 執行 scraper_fb.py
3. 推送結果至 data_fb.json
4. 發送 Telegram 日報

兩台設備均可執行：
  Mac:    python scrapers/run_fb.py
  NR200P: python scrapers/run_fb.py

必要環境變數（寫入 ~/.zshrc 或 ~/.bashrc，或執行前 export）：
  GITHUB_TOKEN   GitHub Personal Access Token（需有 repo 權限）
  TG_BOT_TOKEN   Telegram Bot Token
  TG_CHAT_ID     Telegram Chat ID
  FB_SESSION_DIR Playwright 持久化 session 目錄（預設 ~/fb_session）

快速設定（首次）：
  export GITHUB_TOKEN="你的token"
  export TG_BOT_TOKEN="你的bot_token"
  export TG_CHAT_ID="你的chat_id"
  python scrapers/run_fb.py
"""

import os, sys, json, base64, urllib.request
from datetime import datetime
from pathlib import Path

# ── 設定（全部從環境變數讀取，不在程式碼內硬編碼）──────────
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN")
TG_BOT_TOKEN   = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID     = os.environ.get("TG_CHAT_ID")
REPO           = "ran40453/rental-tracker"
FB_DATA_FILE   = "data_fb.json"
FB_SESSION_DIR = os.environ.get("FB_SESSION_DIR", os.path.expanduser("~/fb_session"))

def check_env():
    missing = [k for k in ["GITHUB_TOKEN","TG_BOT_TOKEN","TG_CHAT_ID"]
               if not os.environ.get(k)]
    if missing:
        print(f"❌ 缺少環境變數：{', '.join(missing)}", file=sys.stderr)
        print("請先 export 後再執行，詳見 scrapers/README_scrapers.md", file=sys.stderr)
        sys.exit(1)
# ────────────────────────────────────────────────────────────

GITHUB_API = "https://api.github.com"

def gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }

def gh_get(path):
    req = urllib.request.Request(f"{GITHUB_API}/{path}", headers=gh_headers())
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def gh_put(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{GITHUB_API}/{path}", data=data, headers=gh_headers(), method="PUT"
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def tg_send(text):
    """傳送 Telegram 訊息（自動分段 ≤ 4096 字）"""
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    results = []
    for chunk in chunks:
        payload = json.dumps({"chat_id": TG_CHAT_ID, "text": chunk}).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read())
                results.append(d.get("ok", False))
        except Exception as e:
            print(f"[Telegram error] {e}", file=sys.stderr)
            results.append(False)
    return all(results)

def read_readme():
    try:
        url = "https://raw.githubusercontent.com/ran40453/rental-tracker/main/README.md"
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read().decode("utf-8")
    except Exception:
        return ""

def get_existing_sha(filename):
    try:
        return gh_get(f"repos/{REPO}/contents/{filename}").get("sha", "")
    except Exception:
        return ""

def push_json(filename, data, message):
    sha = get_existing_sha(filename)
    content = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode()
    payload = {"message": message, "content": content}
    if sha:
        payload["sha"] = sha
    return gh_put(f"repos/{REPO}/contents/{filename}", payload)

def build_telegram_report(listings, today, errors):
    STATION_ORDER = ["頂埔","永寧","土城","海山","亞東醫院","府中","板橋","新埔","江子翠"]
    def sort_key(x):
        try: return STATION_ORDER.index(x["station"])
        except ValueError: return 99

    if not listings:
        lines = [
            f"🏠【租屋日報】{today}",
            "今日在板南線土城段（頂埔→江子翠）搜尋中未找到符合條件的新貼文。",
            "（已搜尋：5個社團 + 17個關鍵字搜尋）",
        ]
        if errors:
            lines.append(f"⚠️ 無法存取：{', '.join(errors[:3])}")
        lines.append("\n📱 https://ran40453.github.io/rental-tracker/")
        return "\n".join(lines)

    listings = sorted(listings, key=sort_key)
    lines = [f"🏠【租屋日報】{today} 找到 {len(listings)} 筆", ""]
    for i, l in enumerate(listings, 1):
        lines.append("━━━━━━━━━━━━━━━━")
        lines.append(f"{i}. {l['station']}站 | {l['price']:,}元/月")
        parts = [l['type']]
        if l['size']: parts.append(f"{l['size']}坪")
        if l['floor']: parts.append(l['floor'])
        lines.append(f"房型：{' | '.join(parts)}")
        stars = []
        if l['elevator']=='有': stars.append("電梯⭐")
        if l['wardrobe']: stars.append("衣櫃⭐")
        if l['parking']: stars.append("停車⭐")
        if stars: lines.append(f"加分：{' '.join(stars)}")
        lines.append(f"電費：{l['elec'] or '未提及'} | 押金：{l['deposit']}個月")
        note = l.get('note', '')
        if '貼文：' in note:
            lines.append(f"摘要：{note.split('貼文：',1)[1][:80]}")
        warnings = [n for n in note.split('。') if '未確認' in n or '放寬' in n]
        if warnings: lines.append(f"📌 {' | '.join(warnings)}")
        lines.append(f"🔗 {l['link'] or '請私訊房東'}")
    lines.append("━━━━━━━━━━━━━━━━")
    if errors:
        lines.append(f"⚠️ 部分頁面無法存取：{', '.join(errors[:3])}")
    lines.append("\n📱 https://ran40453.github.io/rental-tracker/")
    return "\n".join(lines)

def main():
    check_env()
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[{today}] FB 租屋爬蟲開始")

    # STEP 0：讀 README 確認架構
    print("STEP 0: 讀取 GitHub README...")
    readme = read_readme()
    for line in readme.splitlines():
        if any(k in line for k in ["data_fb","data_591","schema","FB爬蟲","NR200P"]):
            print(f"  {line.strip()}")

    # STEP 1-3：爬蟲
    print("STEP 1-3: 爬取 Facebook...")
    sys.path.insert(0, str(Path(__file__).parent))
    from scraper_fb import scrape_facebook
    try:
        listings, errors = scrape_facebook(FB_SESSION_DIR)
    except Exception as e:
        msg = f"❌ FB 爬蟲失敗：{e}"
        print(msg, file=sys.stderr)
        tg_send(msg)
        sys.exit(1)
    print(f"  找到 {len(listings)} 筆，{len(errors)} 個頁面錯誤")

    # STEP 4：Telegram
    print("STEP 4: 發送 Telegram...")
    ok = tg_send(build_telegram_report(listings, today, errors))
    print(f"  {'✅ 已送出' if ok else '❌ 發送失敗'}")

    # STEP 5：推送 GitHub
    if listings:
        print("STEP 5: 推送 data_fb.json...")
        try:
            r = push_json(FB_DATA_FILE, listings, f"🏠 {today} FB社團每日更新（{len(listings)}筆）")
            print(f"  ✅ commit: {r.get('commit',{}).get('sha','')[:7]}")
        except Exception as e:
            print(f"  ❌ 推送失敗：{e}", file=sys.stderr)
    else:
        print("STEP 5: 0筆，略過推送")
    print("完成。")

if __name__ == "__main__":
    main()
