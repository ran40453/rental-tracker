#!/usr/bin/env python3
"""
rental_tracker — 每日執行腳本
執行流程：
  1. 從 GitHub 讀取 README.md，理解目前架構（此機器負責哪個 JSON 檔、資料格式）
  2. 執行 591 爬蟲（rental_finder.py）
  3. 將爬蟲產出轉換為 README 指定的 JSON 格式
  4. 推送至 GitHub

若架構有變更，請先更新 GitHub README，本腳本下次執行時會自動適應。
"""

import subprocess, sys, json, re, os, datetime, base64
from pathlib import Path

REPO        = "ran40453/rental-tracker"
THIS_DIR    = Path(__file__).parent
FINDER_PY   = THIS_DIR / "rental_finder.py"
REPO_DIR    = THIS_DIR / "repo_clone"
TODAY       = datetime.date.today().isoformat()

# ── 1. 從 GitHub 讀取 README，理解架構 ──────────────────────────
def fetch_readme() -> str:
    r = subprocess.run(
        ["gh", "api", f"repos/{REPO}/contents/README.md", "--jq", ".content"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        raise RuntimeError(f"無法取得 README: {r.stderr}")
    return base64.b64decode(r.stdout.strip()).decode()

def parse_architecture(readme: str) -> dict:
    """
    從 README 解析此機器的設定。
    README 表格格式：| 來源 | 爬蟲機器 | 輸出檔 | 說明 |
    回傳 dict，例如：{ "output_file": "data_591.json", "source_label": "591租屋網" }
    """
    arch = {"output_file": "data_591.json", "source_label": "591租屋網"}

    for line in readme.splitlines():
        if "Mac" in line or "mac" in line:
            m = re.search(r'(data_\S+\.json)', line)
            if m:
                arch["output_file"] = m.group(1)
            m2 = re.search(r'\*\*(.+?)\*\*', line)
            if m2:
                arch["source_label"] = m2.group(1)
            break

    print(f"[架構] 輸出檔：{arch['output_file']}，來源標籤：{arch['source_label']}")
    return arch

# ── 2. 執行爬蟲 ─────────────────────────────────────────────────
def run_crawler() -> Path:
    html_out = Path.home() / "Desktop" / "rental_latest.html"
    print(f"[爬蟲] 執行 {FINDER_PY} …")
    r = subprocess.run([sys.executable, str(FINDER_PY)])
    if r.returncode != 0:
        raise RuntimeError("爬蟲執行失敗")
    if not html_out.exists():
        raise FileNotFoundError(f"找不到爬蟲輸出：{html_out}")
    return html_out

# ── 3. 將 HTML 報表轉換為 JSON ──────────────────────────────────
STATION_MAP = {
    '永寧': '永寧', '頂埔': '頂埔', '土城': '土城', '海山': '海山',
    '府中': '府中', '亞東': '亞東醫院', '板橋': '板橋',
    '新埔': '新埔', '江子翠': '江子翠',
}
KIND_MAP = {'1': '分租套房', '2': '套房'}

def guess_station(r: dict) -> str:
    for kw, st in STATION_MAP.items():
        if any(kw in str(r.get(f, '')) for f in ('metro', 'title', 'address')):
            return st
    for kw, st in STATION_MAP.items():
        if kw in r.get('section', ''):
            return st
    return ''

def has_tag(r: dict, kw: str) -> bool:
    return any(kw in t for t in r.get('tags', []))

def convert_to_json(html_path: Path, source_label: str) -> list:
    content = html_path.read_text(encoding='utf-8')
    m = re.search(r'const RAW\s*=\s*(\[.*?\]);', content, re.DOTALL)
    if not m:
        raise ValueError("找不到 RAW 資料陣列")
    raw = json.loads(m.group(1))

    out = []
    for i, r in enumerate(raw):
        fl, tfl = r.get('floor', ''), r.get('total_floor', '')
        floor_str = f"{fl}F/{tfl}F" if fl and tfl else (f"{fl}F" if fl else '')
        note = '標籤：' + '、'.join(r['tags']) if r.get('tags') else ''

        out.append({
            'id':       i + 1,
            'title':    r.get('title', ''),
            'price':    r.get('price', 0),
            'size':     r.get('area_ping', 0),
            'floor':    floor_str,
            'type':     KIND_MAP.get(str(r.get('kind', '')), '套房'),
            'station':  guess_station(r),
            'elec':     '',
            'elevator': '有' if has_tag(r, '電梯') else '',
            'window':   has_tag(r, '對外窗') or has_tag(r, '外窗'),
            'net':      has_tag(r, '網路') or has_tag(r, 'wifi') or has_tag(r, 'WiFi'),
            'parking':  has_tag(r, '機車') or has_tag(r, '停車'),
            'wardrobe': has_tag(r, '衣櫃'),
            'pets':     has_tag(r, '寵物'),
            'deposit':  2,
            'link':     f"https://rent.591.com.tw/rent-detail-{r['id']}.html",
            'note':     note,
            'source':   source_label,
            'date':     TODAY,
            'pinned':   False,
            'dismissed':False,
            'score':    r.get('score', 0),
        })
    print(f"[轉換] 共 {len(out)} 筆房源")
    return out

# ── 4. 推送至 GitHub ─────────────────────────────────────────────
def push_to_github(data: list, output_file: str):
    if REPO_DIR.exists():
        print("[Git] 更新本地 clone …")
        subprocess.run(["git", "-C", str(REPO_DIR), "pull", "--rebase"],
                       check=True, capture_output=True)
    else:
        print("[Git] Clone repo …")
        subprocess.run(["gh", "repo", "clone", REPO, str(REPO_DIR)], check=True)

    out_path = REPO_DIR / output_file
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"[Git] 寫入 {output_file}（{out_path.stat().st_size // 1024} KB）")

    subprocess.run(["git", "-C", str(REPO_DIR), "config", "user.email", "ran40453@gmail.com"], check=True)
    subprocess.run(["git", "-C", str(REPO_DIR), "config", "user.name", "ran40453"], check=True)
    subprocess.run(["git", "-C", str(REPO_DIR), "add", output_file], check=True)

    diff = subprocess.run(["git", "-C", str(REPO_DIR), "diff", "--cached", "--stat"],
                          capture_output=True, text=True).stdout.strip()
    if not diff:
        print("[Git] 無變更，略過推送")
        return

    commit_msg = (
        f"data(591): 更新 {output_file} — {TODAY}\n\n"
        f"共 {len(data)} 筆（土城區 + 板橋區，≤15000元，≥6坪）"
    )
    subprocess.run(["git", "-C", str(REPO_DIR), "commit", "-m", commit_msg], check=True)
    subprocess.run(["git", "-C", str(REPO_DIR), "push", "origin", "main"], check=True)
    print(f"[Git] ✅ 已推送 {output_file}")

# ── 主流程 ───────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print(f"🏠 rental_tracker 每日執行  {TODAY}")
    print("=" * 55)

    print("\n[Step 1] 讀取 GitHub README，確認目前架構 …")
    try:
        readme = fetch_readme()
        arch = parse_architecture(readme)
    except Exception as e:
        print(f"  ⚠️  無法取得 README（{e}），使用預設架構")
        arch = {"output_file": "data_591.json", "source_label": "591租屋網"}

    print("\n[Step 2] 執行 591 爬蟲 …")
    html_path = run_crawler()

    print("\n[Step 3] 轉換為 JSON …")
    data = convert_to_json(html_path, arch["source_label"])

    print("\n[Step 4] 推送至 GitHub …")
    push_to_github(data, arch["output_file"])

    print(f"\n✅ 完成！{arch['output_file']} 已更新")
    print(f"   🌐 https://ran40453.github.io/rental-tracker")

if __name__ == "__main__":
    main()
