
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

st.set_page_config(page_title="每日股票篩選器 · GDrive 版", layout="wide")

# ----------------------------
# Utils
# ----------------------------
def gdrive_file_url(file_id: str) -> str:
    """轉換 Google Drive FILE_ID 為可讀取的直連 URL"""
    return f"https://drive.google.com/uc?export=download&id={file_id}"

@st.cache_data(ttl=1800, show_spinner="讀取資料中…")
def load_data_from_gdrive(file_id: str) -> pd.DataFrame:
    url = gdrive_file_url(file_id)
    # 嘗試多種常見編碼
    last_err = None
    for enc in ["cp950", "big5", "utf-8"]:
        try:
            df = pd.read_csv(url, encoding=enc, low_memory=False)
            break
        except Exception as e:
            last_err = e
            df = None
    if df is None:
        raise RuntimeError(f"讀取失敗：{last_err}")

    # 日期轉換
    if "日期" not in df.columns:
        raise RuntimeError("缺少『日期』欄位")
    df["日期"] = pd.to_datetime(df["日期"].astype(str), format="%Y%m%d", errors="coerce")

    # 代碼/商品欄位
    if "代碼" not in df.columns:
        raise RuntimeError("缺少『代碼』欄位")
    df["代碼"] = df["代碼"].astype(str)
    if "商品" not in df.columns:
        df["商品"] = ""

    # 將可能含逗號或字串的數值欄轉為數值
    def to_numeric(series):
        return pd.to_numeric(
            series.astype(str)
                  .str.replace(",", "", regex=False)
                  .str.replace("(", "-", regex=False)
                  .str.replace(")", "", regex=False),
            errors="coerce"
        )

    numeric_cols = [
        "開盤價","最高價","最低價","收盤價","漲跌幅","振幅","成交量","內盤量","外盤量","開盤量",
        "當日沖銷張數","52H價","均價","均價[0+1]","均價[1+2]","均價[1+2+3]","均價[0+1+2]",
        "融券餘額張數","融券增減張數","成交金額","週轉率"
    ]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = to_numeric(df[c])

    # 排序
    df = df.sort_values(["代碼","日期"]).reset_index(drop=True)
    return df

def calc_abnormal_volume(df: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    """計算每檔的歷史均量（排除當日，用 shift(1)），新增欄位 '均量N'、'量能倍數'。"""
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
# Sidebar · Settings
# ----------------------------
st.sidebar.header("📦 資料來源（Google Drive）")
default_file_id = st.sidebar.text_input(
    "Google Drive FILE_ID",
    value="",
    help=(
        "上傳 XQ.csv 到 Google Drive → 取得分享連結，形如 "
        "'https://drive.google.com/file/d/FILE_ID/view?usp=sharing'，把 FILE_ID 貼到這裡。"
    )
)

if not default_file_id:
    st.info("請在左側輸入 Google Drive 的 FILE_ID 後開始。")
    st.stop()

df = load_data_from_gdrive(default_file_id)

# 先計算一次量能異常（預設 5 日）
df = calc_abnormal_volume(df, lookback=5)

st.sidebar.header("⚙️ 篩選條件")
# 日期選擇（轉 Python date，避免 numpy.datetime64 型別問題）
py_dates = df["日期"].dropna().sort_values().dt.date.unique()
default_date_py = py_dates[-1] if len(py_dates) else None
sel_date = st.sidebar.date_input("選擇日期", value=default_date_py)
if isinstance(sel_date, (list, tuple)):
    sel_date = sel_date[0] if len(sel_date) else default_date_py

top_n = st.sidebar.slider("Top N（融券增減 / 量能異常）", 5, 50, 10, 5)
limit_up_threshold = st.sidebar.number_input("漲停門檻（%）", 0.0, 20.0, 9.9, 0.1)
vol_lookback = st.sidebar.selectbox("量能均量視窗", options=[5, 10, 20], index=0)
vol_multiple = st.sidebar.number_input("量能倍數門檻（≥）", 1.0, 20.0, 2.0, 0.5)

# 依選擇重算量能視窗
df = calc_abnormal_volume(df, lookback=int(vol_lookback))

# 取當日資料
mask_day = df["日期"].dt.date == sel_date
day = df.loc[mask_day].copy()

# ----------------------------
# 1) 漲停個股
# ----------------------------
section_title("1）漲停個股", "條件：漲跌幅 ≥ 門檻")
if "漲跌幅" not in day.columns:
    st.warning("找不到『漲跌幅』欄位，無法計算漲停")
else:
    g_limit = day.loc[day["漲跌幅"] >= limit_up_threshold].copy()
    show_cols = ["代碼", "商品", "收盤價", "漲跌幅", "成交量", "週轉率"]
    table = g_limit[[c for c in show_cols if c in g_limit.columns]].sort_values(
        ["漲跌幅","成交量"], ascending=[False, False]
    )
    st.dataframe(table, use_container_width=True)

# ----------------------------
# 2) 融券增減最多個股
# ----------------------------
section_title("2）融券增減最多個股", "依『融券增減張數』排序，取 Top N")
if "融券增減張數" not in day.columns:
    st.warning("找不到『融券增減張數』欄位，無法產生排行榜")
else:
    rq_cols = ["代碼", "商品", "收盤價", "融券增減張數", "融券餘額張數", "成交量"]
    g_rq = (
        day.dropna(subset=["融券增減張數"])
           .sort_values("融券增減張數", ascending=False)
           .head(top_n)
    )
    st.dataframe(g_rq[[c for c in rq_cols if c in g_rq.columns]], use_container_width=True)

# ----------------------------
# 3) 成交量異常個股
# ----------------------------
section_title("3）成交量異常個股", "條件：量能倍數 ≥ 門檻（今日量 ÷ 歷史均量）")
if not set(["成交量", "量能倍數"]).issubset(day.columns):
    st.warning("缺少『成交量』或『量能倍數』欄位")
else:
    vol_cols = ["代碼", "商品", "成交量", f"均量{vol_lookback}", "量能倍數", "收盤價", "漲跌幅"]
    g_vol = (
        day[(day["量能倍數"] >= float(vol_multiple)) & day[f"均量{vol_lookback}"].notna()]
        .copy()
        .sort_values("量能倍數", ascending=False)
        .head(top_n)
    )
    st.dataframe(g_vol[[c for c in vol_cols if c in g_vol.columns]], use_container_width=True)

# ----------------------------
# 個股走勢（互動）
# ----------------------------
section_title("個股走勢（互動）", "從上面的表格挑股票或直接輸入代碼")
codes_today = sorted(day["代碼"].dropna().unique().tolist())
col_a, col_b = st.columns([1,1])
with col_a:
    sel_code = st.text_input("輸入股票代碼", value=(codes_today[0] if codes_today else ""))

if sel_code:
    hist = df[df["代碼"] == sel_code].copy()
    if hist.empty:
        st.info("查無此代碼的歷史資料")
    else:
        st.markdown(f"**{sel_code} · {hist['商品'].iloc[-1] if '商品' in hist.columns else ''}**")

        price_cols = [c for c in ["收盤價","開盤價","最高價","最低價"] if c in hist.columns]
        vol_cols = [c for c in ["成交量", f"均量{vol_lookback}"] if c in hist.columns]

        base = alt.Chart(hist).encode(x="日期:T")

        if price_cols:
            chart_price = base.mark_line().transform_fold(
                price_cols, as_=["指標","數值"]
            ).encode(
                y=alt.Y("數值:Q", title="價格"),
                color="指標:N"
            ).properties(height=260)
            st.altair_chart(chart_price, use_container_width=True)

        if vol_cols:
            chart_vol = base.transform_fold(
                vol_cols, as_=["量種","數值"]
            ).mark_bar().encode(
                y=alt.Y("數值:Q", title="成交量 / 均量"),
                color="量種:N"
            ).properties(height=180)
            st.altair_chart(chart_vol, use_container_width=True)

st.caption("資料來源：Google Drive XQ.csv（公開共享連結）。建議每日更新後重新整理頁面。")
