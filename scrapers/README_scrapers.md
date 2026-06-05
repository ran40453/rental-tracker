# scrapers/

各爬蟲腳本目錄。**兩台機器（Mac / NR200P）均可執行任一爬蟲**，腳本只依賴 Python + 已安裝套件，不綁定設備。

---

## 環境變數設定（兩台機器均需）

在 `~/.zshrc` 或 `~/.bashrc` 加入：

```bash
export GITHUB_TOKEN="ghp_..."        # GitHub Personal Access Token（repo 權限）
export TG_BOT_TOKEN="123456:AAG..."  # Telegram Bot Token
export TG_CHAT_ID="8214988503"       # Telegram Chat ID
```

---

## 591 爬蟲

| 檔案 | 說明 |
|------|------|
| `scraper_591.py` | Playwright 核心爬蟲，爬取 591 租屋網 |
| `run_591.py`     | 每日執行腳本（讀 README → 爬取 → 推送 `data_591.json` → Telegram） |

**執行：**
```bash
pip install playwright beautifulsoup4
playwright install chromium
python scrapers/run_591.py
```

**爬取範圍：** 新北市土城區 + 板橋區，預算 ≤ 15,000，坪數 ≥ 6，排除限女 / 頂加

---

## FB 社團爬蟲

| 檔案 | 說明 |
|------|------|
| `scraper_fb.py` | Playwright 核心爬蟲，爬取 Facebook 社團 + 全站搜尋 |
| `run_fb.py`     | 每日執行腳本（讀 README → 爬取 → 推送 `data_fb.json` → Telegram） |

**執行：**
```bash
pip install playwright
playwright install chromium

# 首次執行需手動登入 Facebook（headless=False 模式）
# 登入完成後 session 會儲存於 ~/fb_session，之後可 headless 執行
export FB_SESSION_DIR=~/fb_session
python scrapers/run_fb.py
```

**爬取社團（策略A）：**
| 社團名稱 | 搜尋條件 |
|----------|----------|
| 我是土城人（頂埔大小事） | 出租 套房 |
| 我是土城人 | 出租 套房 |
| 板橋租屋網 我是好房東 | 套房 出租 |
| 台北租屋、出租專屬社團 | 板橋 套房 |
| 台北租屋、出租專屬平台 2.0 | 板橋 套房 |

**全站關鍵字搜尋（策略B）：** 板南線全9站關鍵字（頂埔 / 土城 / 海山 / 府中 / 亞東醫院 / 永寧 / 板橋 / 新埔 / 江子翠）× 2種查詢 = 17組

**篩選條件：** 租金 ≤ 14,000（優異條件放寬至 15,000）、獨立套房、非限女、非一樓、非頂加

---

## 備注

- FB 私人社團貼文沒有公開連結，`link` 欄位存聯絡方式（電話 / LINE / FB私訊）
- index.html 已處理：非 URL 格式的 link 顯示為聯絡方式圖示，不包成超連結
- FB session 需定期重新登入（Facebook 約每 30–90 天失效）
- 兩個爬蟲各自覆蓋自己的 JSON，不互相干擾
