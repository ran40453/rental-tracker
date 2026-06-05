# rental-tracker

租屋追蹤器 — 板南線土城 / 板橋段每日自動爬蟲

🌐 **線上檢視：** https://ran40453.github.io/rental-tracker

---

## 架構概覽

```
rental-tracker/
├── index.html       # 前端展示頁，動態 fetch 兩個 JSON 檔合併顯示
├── data_591.json    # 591 租屋網資料（Mac 每日更新）
├── data_fb.json     # Facebook 社團資料（NR200P 每日更新）
└── README.md        # ← 本檔，為各爬蟲機器的架構說明來源
```

> ⚠️ **重要：** 每台機器的爬蟲腳本在執行前都會讀取此 README，
> 以確認自己負責的輸出檔名與資料格式。
> **若調整架構，請務必同步更新此 README。**

---

## 各機器分工

| 來源 | 爬蟲機器 | 輸出檔 | 說明 |
|------|----------|--------|------|
| **591租屋網** | Mac（本機） | `data_591.json` | 每日爬取：新北市土城區 + 板橋區，預算 ≤ 15,000 元，坪數 ≥ 6 坪，排除限女 / 頂加 |
| **FB社團** | NR200P | `data_fb.json` | 爬取土城 / 海山 / 長庚等相關租屋社團貼文 |

---

## 資料格式（JSON Schema）

每個 JSON 檔為陣列，每筆物件包含以下欄位：

```jsonc
{
  "id":        1,               // 整數，唯一識別碼（591: 1–9999, FB: 10001+）
  "title":     "捷運旁套房",    // 標題
  "price":     10000,           // 月租金（元），0 = 未知
  "size":      8.5,             // 坪數，0 = 未知
  "floor":     "3F/7F",         // 樓層/總樓，空字串 = 未知
  "type":      "套房",          // 套房 | 分租套房 | 雅房 | 整層
  "station":   "土城",          // 最近捷運站名，空字串 = 未知
  "elec":      "獨立電表",      // 電費方式，空字串 = 未知
  "elevator":  "有",            // 有 | 無 | 空字串(未知)
  "window":    false,           // 對外窗
  "net":       true,            // 含網路
  "parking":   false,           // 機車位
  "wardrobe":  false,           // 衣櫃
  "pets":      false,           // 可養寵物
  "deposit":   2,               // 押金（月數）
  "link":      "https://...",   // 來源連結
  "note":      "備註文字",      // 標籤或貼文摘要
  "source":    "591租屋網",     // "591租屋網" | "FB社團"
  "date":      "2026-06-05",    // 爬取日期 YYYY-MM-DD
  "pinned":    false,           // 前端釘選狀態（由 index.html 管理）
  "dismissed": false,           // 前端移除狀態（由 index.html 管理）
  "score":     71               // 爬蟲評分（591 專用，FB 填 0）
}
```

---

## Mac 爬蟲腳本位置

```
~/rental_tracker/
├── run_daily.py      # 主執行腳本（每日排程）
└── rental_finder.py  # 591 Playwright 爬蟲核心
```

**執行邏輯（`run_daily.py`）：**
1. 讀取此 README → 解析 Mac 對應的輸出檔名（目前：`data_591.json`）
2. 執行 `rental_finder.py` → 產出 `~/Desktop/rental_latest.html`
3. 解析 HTML 中的 `const RAW` 資料，轉換為上述 JSON 格式
4. `git push` 至 `data_591.json`

---

## NR200P 更新說明

- 只需更新 `data_fb.json`，不要動 `data_591.json`
- `id` 請使用 10001 起（避免與 591 的 id 衝突）
- `source` 欄位填 `"FB社團"`
- 推送後，GitHub Pages 自動反映（index.html 每次載入都 fetch 最新 JSON）

---

## 更新記錄

### 2026-06-05 — NR200P 架構重構
- 將資料從 index.html 拆出，分成 data_591.json + data_fb.json
- index.html 改為動態 fetch 兩個 JSON 合併顯示

### 2026-06-05 — Mac 首次加入 591 資料
- 加入 591 租屋網爬蟲資料（368 筆，土城區 + 板橋區）
- 新增來源篩選器（591租屋網 / FB社團）、評分排序
- 建立 `~/rental_tracker/run_daily.py` 主腳本（含 README 架構自動偵測）
