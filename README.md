
# 股票篩選器（Streamlit · Google Drive 版 · 穩定下載）

此版本透過 `gdown` 先把 Google Drive 的 CSV 下載到暫存資料夾，再用 pandas 讀取，能處理大型檔案的 confirm token/403 等問題。

## 使用（Streamlit Cloud）
1. 推這個資料夾到 GitHub。
2. 在 Streamlit Cloud 建立 App，`Main file path` 指向 `streamlit_app.py`。
3. App 啟動後，側欄填入你的 **Google Drive FILE_ID**（分享連結 `/d/FILE_ID/` 中間那段）。
4. 確認 Google Drive 檔案權限為「知道連結者可檢視」。

## 檔案
- `streamlit_app.py`：主程式
- `requirements.txt`：包含 `gdown` 以支援穩定下載
