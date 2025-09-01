# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import gdown
import tempfile, os, io, csv, re
from pathlib import Path
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="進階股票市場分析系統", layout="wide", initial_sidebar_state="expanded")

# ----------------------------
# 樣式設定
# ----------------------------
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-container {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #667eea;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
    .trend-positive { color: #e74c3c; font-weight: bold; }
    .trend-negative { color: #27ae60; font-weight: bold; }
    .trend-neutral { color: #7f8c8d; font-weight: bold; }
    .concept-tag {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 0.2rem 0.5rem;
        border-radius: 12px;
        font-size: 0.8rem;
        margin: 0.1rem;
        display: inline-block;
    }
    .filter-container {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ----------------------------
# 工具函數
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
    out = gdown.download(url, str(out_path), quiet=True, fuzzy=True)
    if out is None:
        raise RuntimeError("下載失敗（可能是權限非『知道連結者可檢視』，或 ID 不正確）。")
    p = Path(out)
    if not p.exists() or p.stat().st_size == 0:
        raise RuntimeError("下載到的檔案為空。請確認檔案權限與大小。")
    return str(p)

def sniff_and_read_table(path: str) -> pd.DataFrame:
    """嘗試 CSV（含自動分隔符）→ XLSX 兩種讀法；並作更明確錯誤訊息"""
    with open(path, "rb") as f:
        head = f.read(4096)
    
    if head.startswith(b"PK\x03\x04"):
        try:
            return pd.read_excel(path, engine="openpyxl")
        except Exception as e:
            raise RuntimeError(f"讀取 Excel 失敗：{e}")

    last_err = None
    encodings = ["cp950", "big5", "utf-8-sig", "utf-8"]
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="ignore") as f:
                sample = f.read(4096)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                    sep = dialect.delimiter
                except Exception:
                    sep = ","
            return pd.read_csv(path, encoding=enc, sep=sep, engine="python", low_memory=False)
        except Exception as e:
            last_err = e
    raise RuntimeError(f"讀取 CSV 失敗。最後錯誤：{last_err}")

@st.cache_data(ttl=3600, show_spinner=False)
def load_data(input_text: str) -> pd.DataFrame:
    local_path = download_file(input_text)
    df = sniff_and_read_table(local_path)

    if "日期" not in df.columns:
        raise RuntimeError("缺少『日期』欄位。請確認檔案含有台股日期（YYYYMMDD）欄。")
    df["日期"] = pd.to_datetime(df["日期"].astype(str), format="%Y%m%d", errors="coerce")

    if "代碼" not in df.columns:
        raise RuntimeError("缺少『代碼』欄位。")
    df["代碼"] = df["代碼"].astype(str)
    if "商品" not in df.columns:
        df["商品"] = ""

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

def generate_concept_data():
    """生成概念股範例資料"""
    concepts = {
        "AI人工智慧": [
            {"代碼": "2330", "商品": "台積電", "權重": 0.3, "概念": "AI晶片,半導體"},
            {"代碼": "2454", "商品": "聯發科", "權重": 0.25, "概念": "AI晶片,處理器"},
            {"代碼": "3034", "商品": "聯詠", "權重": 0.2, "概念": "顯示驅動IC,AI邊緣運算"},
            {"代碼": "2379", "商品": "瑞昱", "權重": 0.15, "概念": "網路晶片,AI處理"},
            {"代碼": "3661", "商品": "世芯-KY", "權重": 0.1, "概念": "ASIC設計,AI晶片"}
        ],
        "電動車": [
            {"代碼": "2317", "商品": "鴻海", "權重": 0.35, "概念": "電動車代工,MIH聯盟"},
            {"代碼": "1513", "商品": "中興電", "權重": 0.2, "概念": "電動車馬達,充電樁"},
            {"代碼": "6116", "商品": "彩晶", "權重": 0.15, "概念": "車用面板,儀表板"},
            {"代碼": "1102", "商品": "亞泥", "權重": 0.15, "概念": "鋰電池材料"},
            {"代碼": "5871", "商品": "中租-KY", "權重": 0.15, "概念": "電動車租賃"}
        ],
        "5G通訊": [
            {"代碼": "2454", "商品": "聯發科", "權重": 0.3, "概念": "5G晶片,基頻晶片"},
            {"代碼": "8996", "商品": "高力", "權重": 0.25, "概念": "5G基站,射頻"},
            {"代碼": "3029", "商品": "零壹", "權重": 0.2, "概念": "5G小基站"},
            {"代碼": "6269", "商品": "台郡", "權重": 0.15, "概念": "5G軟板,天線"},
            {"代碼": "4958", "商品": "臻鼎-KY", "權重": 0.1, "概念": "5G PCB,高頻板"}
        ]
    }
    return concepts

def format_trend_value(value, is_percent=True):
    """格式化趨勢數值並加上顏色"""
    if pd.isna(value):
        return ""
    if is_percent:
        if value > 0:
            return f'<span class="trend-positive">+{value:.1f}%</span>'
        elif value < 0:
            return f'<span class="trend-negative">{value:.1f}%</span>'
        else:
            return f'<span class="trend-neutral">{value:.1f}%</span>'
    else:
        if value > 0:
            return f'<span class="trend-positive">+{value:.2f}</span>'
        elif value < 0:
            return f'<span class="trend-negative">{value:.2f}</span>'
        else:
            return f'<span class="trend-neutral">{value:.2f}</span>'

# ----------------------------
# 主要應用程式
# ----------------------------

# 頁面標題
st.markdown("""
<div class="main-header">
    <h1>🚀 進階股票市場分析系統</h1>
    <p>專業投資決策支援平台 - 整合漲停分析、概念股追蹤、成交數據與投資組合管理</p>
</div>
""", unsafe_allow_html=True)

# 側邊欄 - 資料來源設定
st.sidebar.header("📦 資料來源設定")
user_input = st.sidebar.text_input(
    "Google Drive 檔案連結或 ID",
    value="",
    help="貼上檔案分享連結或直接貼 FILE_ID"
)

# 載入資料
if user_input:
    try:
        with st.spinner("載入資料中..."):
            df = load_data(user_input)
            df = calc_abnormal_volume(df, lookback=5)
        st.sidebar.success(f"✅ 資料載入成功！共 {len(df)} 筆記錄")
        
        # 日期選擇
        py_dates = df["日期"].dropna().sort_values().dt.date.unique()
        default_date_py = py_dates[-1] if len(py_dates) else None
        selected_date = st.sidebar.date_input("選擇分析日期", value=default_date_py)
        
    except Exception as e:
        st.sidebar.error(f"❌ 資料載入失敗：{str(e)}")
        st.stop()
else:
    st.info("👈 請在左側輸入Google Drive檔案連結或ID開始分析")
    st.stop()

# 主要內容區域 - 模組選擇
tab1, tab2, tab3, tab4 = st.tabs(["📈 漲停股分析", "🎯 概念股追蹤", "📊 成交紀錄分析", "💼 投資組合管理"])

# 取得當日資料
day_data = df[df["日期"].dt.date == selected_date].copy()

# ----------------------------
# 模組 1: 漲停股分析
# ----------------------------
with tab1:
    st.header("📈 漲停股分析模組")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        limit_up_threshold = st.number_input("漲停門檻 (%)", 0.0, 20.0, 9.9, 0.1)
    with col2:
        industry_filter = st.selectbox("產業篩選", ["全部"] + list(day_data["商品"].str[:2].unique()) if "商品" in day_data.columns else ["全部"])
    with col3:
        sort_by = st.selectbox("排序方式", ["漲跌幅", "成交量", "週轉率"])
    
    if "漲跌幅" in day_data.columns:
        limit_up_stocks = day_data[day_data["漲跌幅"] >= limit_up_threshold].copy()
        
        if not limit_up_stocks.empty:
            # 統計資訊
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("漲停股數量", len(limit_up_stocks))
            with col2:
                avg_volume = limit_up_stocks["成交量"].mean() / 1000 if "成交量" in limit_up_stocks.columns else 0
                st.metric("平均成交量", f"{avg_volume:.1f}萬股")
            with col3:
                avg_return = limit_up_stocks["漲跌幅"].mean()
                st.metric("平均漲幅", f"{avg_return:.2f}%")
            with col4:
                if "週轉率" in limit_up_stocks.columns:
                    avg_turnover = limit_up_stocks["週轉率"].mean()
                    st.metric("平均週轉率", f"{avg_turnover:.2f}%")
            
            # 漲停股列表
            st.subheader("漲停股詳細列表")
            display_cols = ["代碼", "商品", "收盤價", "漲跌幅", "成交量"]
            if "週轉率" in limit_up_stocks.columns:
                display_cols.append("週轉率")
            
            # 排序
            if sort_by in limit_up_stocks.columns:
                limit_up_stocks = limit_up_stocks.sort_values(sort_by, ascending=False)
            
            st.dataframe(
                limit_up_stocks[display_cols].style.format({
                    "收盤價": "{:.2f}",
                    "漲跌幅": "{:.2f}%",
                    "成交量": "{:,.0f}",
                    "週轉率": "{:.2f}%" if "週轉率" in display_cols else None
                }),
                use_container_width=True
            )
            
            # 漲停股分布圖表
            if len(limit_up_stocks) > 1:
                st.subheader("漲停股分析圖表")
                
                fig = make_subplots(
                    rows=2, cols=2,
                    subplot_titles=("漲幅分布", "成交量分布", "產業分布", "價位分布"),
                    specs=[[{"type": "histogram"}, {"type": "histogram"}],
                           [{"type": "pie"}, {"type": "histogram"}]]
                )
                
                # 漲幅分布
                fig.add_trace(
                    go.Histogram(x=limit_up_stocks["漲跌幅"], name="漲幅分布", nbinsx=10),
                    row=1, col=1
                )
                
                # 成交量分布
                if "成交量" in limit_up_stocks.columns:
                    fig.add_trace(
                        go.Histogram(x=limit_up_stocks["成交量"], name="成交量分布", nbinsx=10),
                        row=1, col=2
                    )
                
                # 產業分布 (簡化版)
                if "商品" in limit_up_stocks.columns:
                    industry_dist = limit_up_stocks["商品"].str[:2].value_counts()
                    fig.add_trace(
                        go.Pie(labels=industry_dist.index, values=industry_dist.values, name="產業"),
                        row=2, col=1
                    )
                
                # 價位分布
                if "收盤價" in limit_up_stocks.columns:
                    fig.add_trace(
                        go.Histogram(x=limit_up_stocks["收盤價"], name="價位分布", nbinsx=10),
                        row=2, col=2
                    )
                
                fig.update_layout(height=800, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("當日沒有符合條件的漲停股")
    else:
        st.warning("資料中缺少『漲跌幅』欄位，無法進行漲停股分析")

# ----------------------------
# 模組 2: 概念股追蹤
# ----------------------------
with tab2:
    st.header("🎯 概念股追蹤模組")
    
    concept_data = generate_concept_data()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        selected_concept = st.selectbox("概念股主題", list(concept_data.keys()))
    with col2:
        period = st.selectbox("分析期間", ["當日", "一週", "一月", "三月"])
    with col3:
        sort_method = st.selectbox("排序依據", ["權重", "報酬率", "成交量"])
    
    if selected_concept:
        concept_stocks = concept_data[selected_concept]
        concept_codes = [stock["代碼"] for stock in concept_stocks]
        
        # 篩選概念股資料
        concept_df = day_data[day_data["代碼"].isin(concept_codes)].copy()
        
        if not concept_df.empty:
            # 統計資訊
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("概念股數量", len(concept_df))
            with col2:
                if "漲跌幅" in concept_df.columns:
                    avg_return = concept_df["漲跌幅"].mean()
                    st.metric("平均報酬率", f"{avg_return:.2f}%")
            with col3:
                if "漲跌幅" in concept_df.columns:
                    best_performer = concept_df.loc[concept_df["漲跌幅"].idxmax(), "商品"]
                    st.metric("領漲股票", best_performer)
            with col4:
                if "成交金額" in concept_df.columns:
                    total_value = concept_df["成交金額"].sum() / 100000000
                    st.metric("總成交值", f"{total_value:.1f}億")
            
            # 概念股詳細資料
            st.subheader(f"{selected_concept} 概念股表現")
            
            # 合併概念標籤
            concept_info = {stock["代碼"]: stock for stock in concept_stocks}
            concept_df["概念標籤"] = concept_df["代碼"].map(lambda x: concept_info.get(x, {}).get("概念", ""))
            concept_df["權重"] = concept_df["代碼"].map(lambda x: concept_info.get(x, {}).get("權重", 0))
            
            display_cols = ["代碼", "商品", "概念標籤", "權重", "收盤價"]
            if "漲跌幅" in concept_df.columns:
                display_cols.append("漲跌幅")
            if "成交量" in concept_df.columns:
                display_cols.append("成交量")
            
            # 格式化顯示
            styled_df = concept_df[display_cols].copy()
            styled_df["權重"] = styled_df["權重"].apply(lambda x: f"{x*100:.1f}%")
            
            st.dataframe(styled_df, use_container_width=True)
            
            # 概念股表現圖表
            if "漲跌幅" in concept_df.columns and len(concept_df) > 1:
                st.subheader("概念股表現視覺化")
                
                fig = px.bar(
                    concept_df, 
                    x="商品", 
                    y="漲跌幅",
                    title=f"{selected_concept} 概念股今日表現",
                    color="漲跌幅",
                    color_continuous_scale=["red", "gray", "green"]
                )
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)
                
                # 權重與表現散點圖
                if "成交量" in concept_df.columns:
                    fig2 = px.scatter(
                        concept_df,
                        x="權重",
                        y="漲跌幅",
                        size="成交量",
                        hover_name="商品",
                        title="權重vs表現分析",
                        labels={"權重": "概念股權重", "漲跌幅": "今日漲跌幅(%)"}
                    )
                    st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info(f"當日沒有 {selected_concept} 概念股的交易資料")

# ----------------------------
# 模組 3: 成交紀錄分析
# ----------------------------
with tab3:
    st.header("📊 成交紀錄分析模組")
    
    col1, col2 = st.columns(2)
    with col1:
        stock_code = st.text_input("股票代碼", value="2330" if "2330" in df["代碼"].values else df["代碼"].iloc[0])
    with col2:
        analysis_days = st.slider("分析天數", 5, 60, 20)
    
    if stock_code:
        # 取得該股票的歷史資料
        stock_data = df[df["代碼"] == stock_code].copy()
        
        if not stock_data.empty:
            # 最近N天資料
            recent_data = stock_data.tail(analysis_days)
            
            # 統計資訊
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("分析天數", len(recent_data))
            with col2:
                if "成交量" in recent_data.columns:
                    total_volume = recent_data["成交量"].sum() / 10000
                    st.metric("總成交量", f"{total_volume:.0f}萬股")
            with col3:
                if "收盤價" in recent_data.columns:
                    avg_price = recent_data["收盤價"].mean()
                    st.metric("平均價格", f"{avg_price:.2f}")
            with col4:
                if "收盤價" in recent_data.columns and len(recent_data) > 1:
                    period_return = ((recent_data["收盤價"].iloc[-1] / recent_data["收盤價"].iloc[0]) - 1) * 100
                    st.metric("期間報酬率", f"{period_return:.2f}%")
            
            # 成交明細表
            st.subheader("近期成交紀錄")
            display_cols = ["日期", "開盤價", "最高價", "最低價", "收盤價"]
            if "漲跌幅" in recent_data.columns:
                display_cols.append("漲跌幅")
            if "成交量" in recent_data.columns:
                display_cols.append("成交量")
            if "成交金額" in recent_data.columns:
                display_cols.append("成交金額")
            
            # 反向排序（最新在前）
            display_data = recent_data[display_cols].sort_values("日期", ascending=False)
            st.dataframe(display_data, use_container_width=True)
            
            # 技術分析圖表
            st.subheader("技術分析圖表")
            
            if "收盤價" in recent_data.columns:
                # 價格與成交量圖表
                fig = make_subplots(
                    rows=2, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.1,
                    subplot_titles=('股價走勢', '成交量'),
                    row_width=[0.7, 0.3]
                )
                
                # 股價線圖
                fig.add_trace(
                    go.Scatter(
                        x=recent_data["日期"],
                        y=recent_data["收盤價"],
                        name="收盤價",
                        line=dict(color="blue")
                    ),
                    row=1, col=1
                )
                
                # 移動平均線
                if len(recent_data) >= 5:
                    ma5 = recent_data["收盤價"].rolling(5).mean()
                    fig.add_trace(
                        go.Scatter(
                            x=recent_data["日期"],
                            y=ma5,
                            name="MA5",
                            line=dict(color="orange", dash="dash")
                        ),
                        row=1, col=1
                    )
                
                if len(recent_data) >= 10:
                    ma10 = recent_data["收盤價"].rolling(10).mean()
                    fig.add_trace(
                        go.Scatter(
                            x=recent_data["日期"],
                            y=ma10,
                            name="MA10",
                            line=dict(color="red", dash="dash")
                        ),
                        row=1, col=1
                    )
                
                # 成交量柱狀圖
                if "成交量" in recent_data.columns:
                    colors = ['red' if row["漲跌幅"] >= 0 else 'green' 
                             for _, row in recent_data.iterrows()] if "漲跌幅" in recent_data.columns else 'blue'
                    
                    fig.add_trace(
                        go.Bar(
                            x=recent_data["日期"],
                            y=recent_data["成交量"],
                            name="成交量",
                            marker_color=colors
                        ),
                        row=2, col=1
                    )
                
                fig.update_layout(height=600, title=f"{stock_code} 技術分析")
                fig.update_xaxes(title_text="日期", row=2, col=1)
                fig.update_yaxes(title_text="價格", row=1, col=1)
                fig.update_yaxes(title_text="成交量", row=2, col=1)
                
                st.plotly_chart(fig, use_container_width=True)
                
                # 量能分析
                if "成交量" in recent_data.columns:
                    st.subheader("量能分析")
                    vol_data = calc_abnormal_volume(recent_data, lookback=5)
                    
                    # 量能異常日
                    abnormal_vol = vol_data[vol_data["量能倍數"] >= 2.0]
                    if not abnormal_vol.empty:
                        st.write("📊 量能異常交易日：")
                        st.dataframe(
                            abnormal_vol[["日期", "成交量", "均量5", "量能倍數"]].sort_values("日期", ascending=False),
                            use_container_width=True
                        )
        else:
            st.warning(f"找不到股票代碼 {stock_code} 的資料")

# ----------------------------
# 模組 4: 投資組合管理
# ----------------------------
with tab4:
    st.header("💼 投資組合管理模組")
    
    st.info("🚧 此模組需要額外的持股資料，目前顯示模擬功能")
    
    # 模擬投資組合
    col1, col2 = st.columns(2)
    with col1:
        portfolio_name = st.text_input("投資組合名稱", value="我的投資組合")
    with col2:
        benchmark = st.selectbox("比較基準", ["台股加權指數", "標普500", "那斯達克"])
    
    # 模擬持股
    st.subheader("投資組合組成")
    
    sample_portfolio = [
        {"代碼": "2330", "商品": "台積電", "權重": 30.0, "持股成本": 580, "損益": "+5.2%"},
        {"代碼": "2454", "商品": "聯發科", "權重": 20.0, "持股成本": 750, "損益": "+12.3%"},
        {"代碼": "2317", "商品": "鴻海", "權重": 15.0, "持股成本": 105, "損益": "+8.7%"},
        {"代碼": "2382", "商品": "廣達", "權重": 15.0, "持股成本": 190, "損益": "-2.1%"},
        {"代碼": "2308", "商品": "台達電", "權重": 20.0, "持股成本": 280, "損益": "+15.6%"}
    ]
    
    portfolio_df = pd.DataFrame(sample_portfolio)
    
    # 投資組合統計
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("組合報酬率", "+7.8%", "+1.2%")
    with col2:
        st.metric("年化波動率", "18.5%")
    with col3:
        st.metric("夏普比率", "1.25")
    with col4:
        st.metric("最大回檔", "-8.3%")
    
    # 持股明細
    st.dataframe(portfolio_df, use_container_width=True)
    
    # 組合分析圖表
    col1, col2 = st.columns(2)
    
    with col1:
        # 權重分布
        fig_pie = px.pie(
            portfolio_df, 
            values="權重", 
            names="商品",
            title="投資組合權重分布"
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        # 損益表現
        portfolio_df["損益數值"] = portfolio_df["損益"].str.replace("%", "").str.replace("+", "").astype(float)
        fig_bar = px.bar(
            portfolio_df,
            x="商品",
            y="損益數值",
            title="個股損益表現",
            color="損益數值",
            color_continuous_scale=["red", "gray", "green"]
        )
        st.plotly_chart(fig_bar, use_container_width=True)

# ----------------------------
# 全域個股查詢
# ----------------------------
st.sidebar.header("🔍 個股查詢")
if st.sidebar.button("開啟個股分析"):
    st.sidebar.info("個股分析功能已整合在各模組中")

# 頁腳
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: gray; padding: 20px;'>
    <p>📊 進階股票市場分析系統 | 整合Google Drive資料載入 | 支援多維度分析</p>
    <p>💡 提示：確認檔案權限設為『知道連結者可檢視』，檔案包含日期(YYYYMMDD)與代碼欄位</p>
</div>
""", unsafe_allow_html=True)