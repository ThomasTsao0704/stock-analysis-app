
# 股票篩選器（Streamlit · Google Drive 版）

這個專案提供「漲停個股 / 融券增減最多 / 成交量異常」三大每日篩選，以及個股走勢圖。資料來源為你上傳到 **Google Drive** 的 `XQ.csv`。

## 使用方式（本地或 Streamlit Cloud）
1. 將此資料夾推到 GitHub（建議 repo 名稱：`stock-screener-gdrive`）。
2. 進入 [Streamlit Community Cloud](https://share.streamlit.io) → New app → 指定此 repo 與 `streamlit_app.py`。
3. App 啟動後，在左側輸入你的 **Google Drive FILE_ID**（來自分享連結的 `/d/FILE_ID/`）。

> 你的 Google Drive 檔案需設為「知道連結的對象皆可檢視」。

## Google Drive 連結說明
- 分享連結長這樣：`https://drive.google.com/file/d/FILE_ID/view?usp=sharing`
- 將 `FILE_ID` 貼進側欄輸入框即可載入資料。

## 檔案說明
- `streamlit_app.py`：主應用程式
- `requirements.txt`：套件需求（Streamlit Cloud 會自動安裝）

## 主要功能
- 日期選擇（預設抓資料中最後一天）
- 漲停個股（門檻可調，預設 9.9%）
- 融券增減 Top N（預設 10）
- 成交量異常（今日量 ÷ 歷史均量，視窗 5/10/20 可選，倍數門檻可調）
- 個股走勢圖（價格線 + 量能/均量）

## 常見問題
- 若 CSV 使用 Big5/cp950 編碼，本程式會自動嘗試處理。
- 若讀取失敗，請確認 Drive 檔案權限與 FILE_ID 是否正確。
