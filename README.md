# rental-tracker

租屋追蹤器 — 板南線土城 / 板橋段每日自動爬蟲

🌐 **線上檢視：** https://ran40453.github.io/rental-tracker

---

## 架構概覽

```
rental-tracker/
├── index.html          # 前端展示頁，動態 fetch 兩個 JSON 合併顯示
├── data_591.json       # 591 租屋網資料（每日更新）
├── data_fb.json        # Facebook 社團資料（每日更新）
├── scrapers/
│   ├── scraper_591.py  # 591 Playwright 爬蟲核心
│   ├── run_591.py      # 591 每日執行腳本
│   ├── scraper_fb.py   # ⚠️ FB 爬蟲（NR200P 待 commit）
│   └── run_fb.py       # ⚠️ FB 執行腳本（NR200P 待 commit）
└── README.md           # ← 架構說明來源，爬蟲腳本執行前必讀
```

> ⚠️ **重要：** 爬蟲腳本執行前會讀取此 README 確認輸出檔名與格式。
> **架構有任何變更，請務必先更新此 README。**

---

## 各機器分工（可互換）

兩台設備均可執行任一爬蟲，腳本不綁定設備。

| 來源 | 預設執行機器 | 輸出檔 | 執行腳本 |
|------|-------------|--------|---------|
| **591租屋網** | Mac（本機） | `data_591.json` | `scrapers/run_591.py` |
| **FB社團** | NR200P | `data_fb.json` | `scrapers/run_fb.py` |

### 在 Mac 上執行 591 爬蟲
```bash
cd ~/rental_tracker
python3 scrapers/run_591.py
# 或使用本地副本：
python3 run_daily.py
```

### 在 Mac 上執行 FB 爬蟲（需先確認 scraper_fb.py 已在 repo）
```bash
cd /tmp/rental-tracker   # 或任意 clone 目錄
git pull
python3 scrapers/run_fb.py
```

### 在 NR200P 上執行 591 爬蟲
```bash
cd <repo clone 目錄>
git pull
pip install playwright && playwright install chromium
python scrapers/run_591.py
```

### 在 NR200P 上執行 FB 爬蟲
```bash
cd <repo clone 目錄>
python scrapers/run_fb.py
```

---

## 資料格式（JSON Schema）

每個 JSON 檔為陣列，每筆物件欄位：

```jsonc
{
  "id":        1,               // 整數（591: 1–9999, FB: 10001+）
  "title":     "捷運旁套房",
  "price":     10000,           // 月租金（元），0 = 未知
  "size":      8.5,             // 坪數，0 = 未知
  "floor":     "3F/7F",         // 空字串 = 未知
  "type":      "套房",          // 套房 | 分租套房 | 雅房 | 整層
  "station":   "土城",          // 最近捷運站名
  "elec":      "獨立電表",      // 電費方式
  "elevator":  "有",            // 有 | 無 | ""(未知)
  "window":    false,
  "net":       true,
  "parking":   false,
  "wardrobe":  false,
  "pets":      false,
  "deposit":   2,               // 押金月數
  "link":      "https://...",   // 591 為 URL；FB 為聯絡方式文字（電話/LINE/FB私訊）
  "note":      "備註",
  "source":    "591租屋網",     // "591租屋網" | "FB社團"
  "date":      "2026-06-05",
  "pinned":    false,
  "dismissed": false,
  "score":     71               // 591 爬蟲評分，FB 填 0
}
```

> **FB link 欄位說明：** FB 私人社團貼文無法取得公開連結，改存聯絡方式文字。
> index.html 已判斷：非 `http://` 開頭的 link 顯示為 ☎ 聯絡方式，不跳轉連結。

---

## 爬取目標

### 591 租屋網
- 地區：新北市土城區 + 板橋區
- 條件：預算 ≤ 15,000 元，坪數 ≥ 6 坪，排除限女 / 頂加
- 爬蟲：Playwright DOM 解析

### Facebook 社團
- 爬取社團：⚠️ 請 NR200P 在此補充確切社團名稱
- 爬蟲方式：⚠️ 請 NR200P commit scraper_fb.py 後補充

---

## 更新記錄

### 2026-06-05 — 架構整合 + 跨機互換支援
- index.html 修正 FB 聯絡方式連結（非 URL 改顯示 ☎ 文字，不包成超連結）
- 新增 `scrapers/` 目錄，存放 591 爬蟲程式碼
- README 加入跨機執行說明，兩台設備均可執行任一爬蟲
- ⚠️ NR200P 待辦：commit `scraper_fb.py` + `run_fb.py` + 補充社團名稱

### 2026-06-05 — NR200P 架構重構
- 資料從 index.html 拆出，分成 data_591.json + data_fb.json
- index.html 改為動態 fetch 兩個 JSON 合併顯示

### 2026-06-05 — Mac 首次加入 591 資料
- 加入 591 租屋網爬蟲（368 筆，土城 + 板橋）
- 新增來源篩選、評分排序、來源標籤顯示
