# scrapers/

各爬蟲腳本目錄。**兩台機器均可執行任一爬蟲**，腳本只依賴 Python + 已安裝套件，不綁定設備。

## 591 爬蟲

| 檔案 | 說明 |
|------|------|
| `scraper_591.py` | Playwright 核心爬蟲，爬取 591 租屋網 |
| `run_591.py` | 每日執行腳本（讀 README → 爬取 → 推送 `data_591.json`） |

**執行條件：**
```bash
pip install playwright
playwright install chromium
python scrapers/run_591.py
```

## FB 爬蟲

| 檔案 | 說明 |
|------|------|
| `scraper_fb.py` | ⚠️ 尚未上傳，請 NR200P 將此檔案 commit 至此目錄 |
| `run_fb.py` | ⚠️ 尚未上傳，請 NR200P 將此檔案 commit 至此目錄 |

**NR200P 待辦：** 請將 FB 爬蟲腳本 commit 到 `scrapers/` 後更新此說明及 repo 根目錄的 README.md。

**爬取社團（從 data_fb.json 推測）：**
- 土城 / 海山 / 長庚相關租屋社團（確切社團名稱請 NR200P 補充）

**注意事項：**
- FB 私人社團貼文沒有公開連結，`link` 欄位存放聯絡方式（電話 / LINE / FB 私訊）
- index.html 已處理此情況：非 URL 格式的 link 會顯示為聯絡方式圖示，不包成超連結
