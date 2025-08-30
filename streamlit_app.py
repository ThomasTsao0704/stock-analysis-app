
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import gdown
import tempfile, os, io, csv, re
from pathlib import Path

st.set_page_config(page_title="每日股票篩選器 · GDrive 版（強化容錯）", layout="wide")

# ----------------------------
# Helpers
# ----------------------------
def is_drive_file_url(s: str) -> bool:
    return "drive.google.com/file/d/" in s or "drive.google.com/uc?" in s

def extract_file_id(s: str) -> str:
    """從 file URL 或 ID 回傳 ID；若已是 ID 直接回傳"""
    if re.fullmatch(r"[A-Za-z0-9_\-]{20,}", s):
        return s
    m = re.search(r"/d/([A-Za-z0-9_\-]+)", s)
    if m: return m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_\-]+)", s)
    if m: return m.group(1)
    return ""

def direct_url_from_id(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=download&id={file_id}"

@st.cache_data(ttl=3600, show_spinner="下載資料中…")
def download_file(input_text: str) -> str:
    """支援填入 FILE_ID 或完整 file 連結；下載到暫存，回傳路徑"""
    file_id = extract_file_id(input_text) if not is_drive_file_url(input_text) else extract_file_id(input_text)
    if not file_id:
        raise RuntimeError("辨識不到 Google Drive 檔案 ID。請貼『檔案分享連結』或直接貼 ID。")
    url = direct_url_from_id(file_id)
    out_path = Path(tempfile.gettempdir()) / f"xq_{file_id}"
    # gdown 會自動加副檔名（若有），因此用 without suffix 先指定，再由 gdown 決定
    out = gdown.download(url, str(out_path), quiet=True, fuzzy=True)
    if out is None:
        raise RuntimeError("下載失敗（可能是權限非『知道連結者可檢視』，或 ID 不正確）。")
    p = Path(out)
    if not p.exists() or p.stat().st_size == 0:
        raise RuntimeError("下載到的檔案為空。請確認檔案權限與大小。")
    return str(p)

def sniff_and_read_table(path: str) -> pd.DataFrame:
    """嘗試 CSV（含自動分隔符）→ XLSX 兩種讀法；並作更明確錯誤訊息"""
    # 先試 CSV with sniffer
    with open(path, "rb") as f:
        head = f.read(4096)
    # 嘗試偵測是否是ZIP（xlsx）
    if head.startswith(b"PK\x03\x04"):
        # Excel
        try:
            return pd.read_excel(path, engine="openpyxl")
        except Exception as e:
            raise RuntimeError(f"讀取 Excel 失敗：{e}")

    # CSV 路徑
    # 先用二進位探頭，再開文字（不確定編碼）
    last_err = None
    encodings = ["cp950", "big5", "utf-8-sig", "utf-8"]
    for enc in encodings:
        try:
            # auto delimiter
            with open(path, "r", encoding=enc, errors="ignore") as f:
                sample = f.read(4096)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                    sep = dialect.delimiter
                except Exception:
                    # fallback: 逗號
                    sep = ","
            return pd.read_csv(path, encoding=enc, sep=sep, engine="python", low_memory=False)
        except Exception as e:
            last_err = e
    raise RuntimeError(f"讀取 CSV 失敗（可能不是 CSV/XLSX，或內容受保護）。最後錯誤：{last_err}")

@st.cache_data(ttl=3600, show_spinner=False)
def load_data(input_text: str) -> pd.DataFrame:
    local_path = download_file(input_text)
    df = sniff_and_read_table(local_path)

    # 日期欄位
    if "日期" not in df.columns:
        raise RuntimeError("缺少『日期』欄位。請確認檔案含有台股日期（YYYYMMDD）欄。")
    df["日期"] = pd.to_datetime(df["日期"].astype(str), format="%Y%m%d", errors="coerce")

    # 代碼/商品欄位
    if "代碼" not in df.columns:
        raise RuntimeError("缺少『代碼』欄位。")
    df["代碼"] = df["代碼"].astype(str)
    if "商品" not in df.columns:
        df["商品"] = ""

    # 數值清理
    def to_numeric(series):
        return pd.to_numeric(
            series.astype(str)
                  .str.replace(",", "", regex=False)
                  .str.replace("(", "-", regex=False)
                  .str.replace(")", "", regex=False),
            errors="coerce"
        )
    for c in [
        "開盤價","最高價","最低價","收盤價","漲跌幅","振幅","成交量","內盤量","外盤量","開盤量",
        "當日沖銷張數","52H價","均價","均價[0+1]","均價[1+2]","均價[1+2+3]","均價[0+1+2]",
        "融券餘額張數","融券增減張數","成交金額","週轉率"
    ]:
        if c in df.columns:
            df[c] = to_numeric(df[c])

    return df.sort_values(["代碼","日期"]).reset_index(drop=True)

def calc_abnormal_volume(df: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    if "成交量" not in df.columns:
        raise RuntimeError("缺少『成交量』欄位")
    df = df.copy()
    df[f"均量{lookback}"] = (
        df.groupby("代碼")["成交量"]
          .transform(lambda s: s.shift(1).rolling(window=lookback, min_periods=max(1, lookback//2)).mean())
    )
    df["量能倍數"] = df["成交量"] / df[f"均量{lookback}"]
    return df

def section_title(title: str, help_text: str = ""):
    cols = st.columns([1, 0.06])
    with cols[0]:
        st.subheader(title)
    with cols[1]:
        if help_text:
            st.caption(help_text)

# ----------------------------
# UI
# ----------------------------
st.sidebar.header("📦 資料來源（Google Drive 檔案連結或 ID）")
user_input = st.sidebar.text_input(
    "貼上『檔案分享連結』或直接貼 FILE_ID",
    value="",
    help="範例連結： https://drive.google.com/file/d/FILE_ID/view?usp=sharing"
)
if not user_input:
    st.info("請在左側貼上檔案分享連結或 FILE_ID 後開始。")
    st.stop()

# 載入
df = load_data(user_input)
df = calc_abnormal_volume(df, lookback=5)

st.sidebar.header("⚙️ 篩選條件")
py_dates = df["日期"].dropna().sort_values().dt.date.unique()
default_date_py = py_dates[-1] if len(py_dates) else None
sel_date = st.sidebar.date_input("選擇日期", value=default_date_py)
if isinstance(sel_date, (list, tuple)):
    sel_date = sel_date[0] if len(sel_date) else default_date_py

top_n = st.sidebar.slider("Top N（融券增減 / 量能異常）", 5, 50, 10, 5)
limit_up_threshold = st.sidebar.number_input("漲停門檻（%）", 0.0, 20.0, 9.9, 0.1)
vol_lookback = st.sidebar.selectbox("量能均量視窗", options=[5, 10, 20], index=0)
vol_multiple = st.sidebar.number_input("量能倍數門檻（≥）", 1.0, 20.0, 2.0, 0.5)

df = calc_abnormal_volume(df, lookback=int(vol_lookback))
day = df.loc[df["日期"].dt.date == sel_date].copy()

# 1) 漲停
section_title("1）漲停個股", "條件：漲跌幅 ≥ 門檻")
if "漲跌幅" not in day.columns:
    st.warning("找不到『漲跌幅』欄位")
else:
    g = day.loc[day["漲跌幅"] >= limit_up_threshold].copy()
    cols = ["代碼","商品","收盤價","漲跌幅","成交量","週轉率"]
    st.dataframe(g[[c for c in cols if c in g.columns]].sort_values(["漲跌幅","成交量"], ascending=[False,False]), use_container_width=True)

# 2) 融券增減
section_title("2）融券增減最多個股", "依『融券增減張數』排序，取 Top N")
if "融券增減張數" not in day.columns:
    st.warning("找不到『融券增減張數』欄位")
else:
    cols = ["代碼","商品","收盤價","融券增減張數","融券餘額張數","成交量"]
    r = day.dropna(subset=["融券增減張數"]).sort_values("融券增減張數", ascending=False).head(top_n)
    st.dataframe(r[[c for c in cols if c in r.columns]], use_container_width=True)

# 3) 量能異常
section_title("3）成交量異常個股", "條件：量能倍數 ≥ 門檻（今日量 ÷ 歷史均量）")
need_cols = {"成交量", f"均量{vol_lookback}", "量能倍數"}
if not need_cols.issubset(set(day.columns)):
    miss = ", ".join(sorted(need_cols - set(day.columns)))
    st.warning(f"缺少欄位：{miss}")
else:
    cols = ["代碼","商品","成交量",f"均量{vol_lookback}","量能倍數","收盤價","漲跌幅"]
    v = day[(day["量能倍數"] >= float(vol_multiple)) & day[f"均量{vol_lookback}"].notna()].copy()
    v = v.sort_values("量能倍數", ascending=False).head(top_n)
    st.dataframe(v[[c for c in cols if c in v.columns]], use_container_width=True)

# 個股走勢
section_title("個股走勢（互動）", "輸入代碼")
codes_today = sorted(day["代碼"].dropna().unique().tolist())
sel_code = st.text_input("輸入股票代碼", value=(codes_today[0] if codes_today else ""))

if sel_code:
    hist = df[df["代碼"] == sel_code].copy()
    if hist.empty:
        st.info("查無此代碼的歷史資料")
    else:
        st.markdown(f"**{sel_code} · {hist['商品'].iloc[-1] if '商品' in hist.columns else ''}**")
        base = alt.Chart(hist).encode(x="日期:T")
        price_cols = [c for c in ["收盤價","開盤價","最高價","最低價"] if c in hist.columns]
        vol_cols = [c for c in ["成交量", f"均量{vol_lookback}"] if c in hist.columns]

        if price_cols:
            st.altair_chart(
                base.mark_line().transform_fold(price_cols, as_=["指標","數值"]).encode(
                    y=alt.Y("數值:Q", title="價格"), color="指標:N"
                ).properties(height=260),
                use_container_width=True
            )
        if vol_cols:
            st.altair_chart(
                base.transform_fold(vol_cols, as_=["量種","數值"]).mark_bar().encode(
                    y=alt.Y("數值:Q", title="成交量 / 均量"), color="量種:N"
                ).properties(height=180),
                use_container_width=True
            )

st.caption("若仍出錯：確認檔案權限（任何知道連結者可檢視）、確定是 CSV 或 Excel，並包含『日期（YYYYMMDD）』與『代碼』欄。")
