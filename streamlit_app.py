# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import gdown
import tempfile, os, io, csv, re
from pathlib import Path
from datetime import datetime, timedelta, date

st.set_page_config(page_title="整合股票分析系統", layout="wide", initial_sidebar_state="expanded")

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
    .record-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #28a745;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ----------------------------
# 工具函數 - Google Drive 相關
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
def load_market_data(input_text: str) -> pd.DataFrame:
    local_path = download_file(input_text)
    df = sniff_and_read_table(local_path)

    if "日期" not in df.columns:
        raise RuntimeError("缺少『日期』欄位。請確認檔案含有對股日期（YYYYMMDD）欄。")
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

# ----------------------------
# 工具函數 - 個人紀錄相關
# ----------------------------
CSV_FILE = "data/notes.csv"

def initialize_csv() -> None:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(CSV_FILE):
        columns = [
            "日期", "股票代號", "股票名稱", "分析內容", "預判", "目標價", "停損價",
            "信心度", "策略標籤", "市場情緒", "備註", "參考指標"
        ]
        pd.DataFrame(columns=columns).to_csv(CSV_FILE, index=False, encoding="utf-8-sig")

initialize_csv()

@st.cache_data(show_spinner=False)
def load_personal_records() -> pd.DataFrame:
    if os.path.exists(CSV_FILE):
        try:
            return pd.read_csv(CSV_FILE, encoding="utf-8-sig")
        except Exception:
            return pd.read_csv(CSV_FILE)
    return pd.DataFrame()

def save_record(record: dict) -> None:
    df = load_personal_records()
    new_df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
    new_df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")
    st.cache_data.clear()

# ----------------------------
# 分析功能函數
# ----------------------------
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
    <h1>🚀 整合股票市場分析與紀錄系統</h1>
    <p>專業投資決策支援平台 - 整合漲跌分析、概念股追蹤、成交數據與個人分析紀錄管理</p>
</div>
""", unsafe_allow_html=True)

# 側邊欄 - 資料來源設定
st.sidebar.header("📦 資料來源設定")
user_input = st.sidebar.text_input(
    "Google Drive 檔案連結或 ID",
    value="",
    help="貼上檔案分享連結或直接貼 FILE_ID"
)

# 載入市場數據
market_data_loaded = False
df_market = pd.DataFrame()

if user_input:
    try:
        with st.spinner("載入市場資料中..."):
            df_market = load_market_data(user_input)
            df_market = calc_abnormal_volume(df_market, lookback=5)
        st.sidebar.success(f"✅ 市場資料載入成功！共 {len(df_market)} 筆記錄")
        market_data_loaded = True
        
        # 日期選擇
        py_dates = df_market["日期"].dropna().sort_values().dt.date.unique()
        default_date_py = py_dates[-1] if len(py_dates) else None
        selected_date = st.sidebar.date_input("選擇分析日期", value=default_date_py)
        
    except Exception as e:
        st.sidebar.error(f"❌ 市場資料載入失敗：{str(e)}")

# 載入個人紀錄
df_records = load_personal_records()

# 主要內容區域 - 模組選擇
if market_data_loaded:
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📈 漲跌股分析", "🎯 概念股追蹤", "📊 成交紀錄分析", 
        "📝 新增分析紀錄", "📚 瀏覽分析紀錄", "📋 整合分析視圖"
    ])
else:
    tab4, tab5, tab6 = st.tabs(["📝 新增分析紀錄", "📚 瀏覽分析紀錄", "📋 整合分析視圖"])

# 取得當日資料
if market_data_loaded:
    day_data = df_market[df_market["日期"].dt.date == selected_date].copy()

# ----------------------------
# 模組 1: 漲跌股分析 (僅在有市場數據時顯示)
# ----------------------------
if market_data_loaded:
    with tab1:
        st.header("📈 漲跌股分析模組")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            limit_up_threshold = st.number_input("漲停門檻 (%)", 0.0, 20.0, 9.9, 0.1)
        with col2:
            industry_filter = st.selectbox("產業篩選", ["全部"] + list(day_data["商品"].str[:2].unique()) if "商品" in day_data.columns else ["全部"])
        with col3:
            sort_by = st.selectbox("排序方式", ["漲跌幅", "成交量", "週轉率"])
        
        # 快速添加紀錄按鈕
        if st.button("💡 將漲停股加入我的觀察清單"):
            st.session_state.show_quick_add = True
        
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
                
                # 添加選擇框讓用戶快速添加到觀察清單
                selected_stocks_for_record = st.multiselect(
                    "選擇要加入觀察清單的股票：",
                    options=limit_up_stocks["代碼"].tolist(),
                    format_func=lambda x: f"{x} - {limit_up_stocks[limit_up_stocks['代碼']==x]['商品'].iloc[0] if not limit_up_stocks[limit_up_stocks['代碼']==x].empty else x}"
                )
                
                if selected_stocks_for_record and st.button("加入觀察清單"):
                    for stock_code in selected_stocks_for_record:
                        stock_row = limit_up_stocks[limit_up_stocks["代碼"] == stock_code].iloc[0]
                        record = {
                            "日期": selected_date.strftime("%Y-%m-%d"),
                            "股票代號": stock_code,
                            "股票名稱": stock_row["商品"] if "商品" in stock_row else "",
                            "分析內容": f"漲停股觀察 - 漲幅{stock_row['漲跌幅']:.2f}%",
                            "預判": "觀察中",
                            "目標價": "",
                            "停損價": "",
                            "信心度": 5,
                            "策略標籤": "漲停股觀察",
                            "市場情緒": "樂觀",
                            "備註": f"從漲停股分析中添加，成交量：{stock_row['成交量']:,.0f}",
                            "參考指標": "漲停股"
                        }
                        save_record(record)
                    st.success(f"已將 {len(selected_stocks_for_record)} 檔股票加入觀察清單！")
                    st.cache_data.clear()
                
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
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        # 漲幅分布
                        st.write("📊 漲幅分布")
                        st.bar_chart(limit_up_stocks["漲跌幅"])
                    
                    with col2:
                        # 成交量分布
                        if "成交量" in limit_up_stocks.columns:
                            st.write("📈 成交量分布")
                            chart_data = limit_up_stocks[["代碼", "成交量"]].set_index("代碼")
                            st.bar_chart(chart_data)
            else:
                st.info("當日沒有符合條件的漲停股")
        else:
            st.warning("資料中缺少『漲跌幅』欄位，無法進行漲停股分析")

# ----------------------------
# 模組 2: 概念股追蹤 (僅在有市場數據時顯示)
# ----------------------------
if market_data_loaded:
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
                
                # 添加到觀察清單的選擇
                selected_concept_stocks = st.multiselect(
                    "選擇概念股加入觀察清單：",
                    options=concept_df["代碼"].tolist(),
                    format_func=lambda x: f"{x} - {concept_df[concept_df['代碼']==x]['商品'].iloc[0] if not concept_df[concept_df['代碼']==x].empty else x}"
                )
                
                if selected_concept_stocks and st.button("加入概念股觀察清單"):
                    for stock_code in selected_concept_stocks:
                        stock_row = concept_df[concept_df["代碼"] == stock_code].iloc[0]
                        record = {
                            "日期": selected_date.strftime("%Y-%m-%d"),
                            "股票代號": stock_code,
                            "股票名稱": stock_row["商品"] if "商品" in stock_row else "",
                            "分析內容": f"{selected_concept}概念股觀察",
                            "預判": "關注概念股發展",
                            "目標價": "",
                            "停損價": "",
                            "信心度": 6,
                            "策略標籤": f"{selected_concept},概念股",
                            "市場情緒": "中性",
                            "備註": f"概念標籤：{stock_row['概念標籤']}",
                            "參考指標": selected_concept
                        }
                        save_record(record)
                    st.success(f"已將 {len(selected_concept_stocks)} 檔概念股加入觀察清單！")
                    st.cache_data.clear()
                
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
                    
                    # 概念股表現柱狀圖
                    chart_data = concept_df[["商品", "漲跌幅"]].set_index("商品")
                    st.bar_chart(chart_data)
                    
                    # 權重與表現散點圖
                    if "成交量" in concept_df.columns:
                        st.write("權重vs表現分析")
                        scatter_chart = alt.Chart(concept_df).mark_circle(size=60).encode(
                            x=alt.X("權重:Q", title="概念股權重"),
                            y=alt.Y("漲跌幅:Q", title="今日漲跌幅(%)"),
                            size=alt.Size("成交量:Q", scale=alt.Scale(range=[100, 400])),
                            color=alt.Color("漲跌幅:Q", scale=alt.Scale(scheme="redyellowgreen")),
                            tooltip=["商品", "權重", "漲跌幅", "成交量"]
                        ).properties(height=400)
                        st.altair_chart(scatter_chart, use_container_width=True)
            else:
                st.info(f"當日沒有 {selected_concept} 概念股的交易資料")

# ----------------------------
# 模組 3: 成交紀錄分析 (僅在有市場數據時顯示)
# ----------------------------
if market_data_loaded:
    with tab3:
        st.header("📊 成交紀錄分析模組")
        
        col1, col2 = st.columns(2)
        with col1:
            stock_code = st.text_input("股票代碼", value="2330" if "2330" in df_market["代碼"].values else df_market["代碼"].iloc[0])
        with col2:
            analysis_days = st.slider("分析天數", 5, 60, 20)
        
        if stock_code:
            # 取得該股票的歷史資料
            stock_data = df_market[df_market["代碼"] == stock_code].copy()
            
            if not stock_data.empty:
                # 最近N天資料
                recent_data = stock_data.tail(analysis_days)
                
                # 快速添加該股票到紀錄
                if st.button(f"📝 快速添加 {stock_code} 的分析紀錄"):
                    st.session_state.quick_add_stock = stock_code
                    st.session_state.quick_add_name = recent_data["商品"].iloc[-1] if "商品" in recent_data.columns else ""
                
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
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("股價走勢圖")
                        # 創建價格走勢圖
                        price_chart = alt.Chart(recent_data).mark_line(point=True).encode(
                            x=alt.X("日期:T", title="日期"),
                            y=alt.Y("收盤價:Q", title="收盤價"),
                            tooltip=["日期", "收盤價"]
                        ).properties(height=300)
                        
                        # 如果有足夠資料，添加移動平均線
                        if len(recent_data) >= 5:
                            recent_data["MA5"] = recent_data["收盤價"].rolling(5).mean()
                            ma5_chart = alt.Chart(recent_data).mark_line(color="orange", strokeDash=[5, 5]).encode(
                                x="日期:T",
                                y="MA5:Q"
                            )
                            price_chart = price_chart + ma5_chart
                        
                        if len(recent_data) >= 10:
                            recent_data["MA10"] = recent_data["收盤價"].rolling(10).mean()
                            ma10_chart = alt.Chart(recent_data).mark_line(color="red", strokeDash=[10, 5]).encode(
                                x="日期:T",
                                y="MA10:Q"
                            )
                            price_chart = price_chart + ma10_chart
                        
                        st.altair_chart(price_chart, use_container_width=True)
                    
                    with col2:
                        # 成交量柱狀圖
                        if "成交量" in recent_data.columns:
                            st.write("成交量分析")
                            volume_chart = alt.Chart(recent_data).mark_bar().encode(
                                x=alt.X("日期:T", title="日期"),
                                y=alt.Y("成交量:Q", title="成交量"),
                                color=alt.condition(
                                    alt.datum["漲跌幅"] >= 0,
                                    alt.value("red"),
                                    alt.value("green")
                                ) if "漲跌幅" in recent_data.columns else alt.value("blue"),
                                tooltip=["日期", "成交量", "漲跌幅"]
                            ).properties(height=300)
                            st.altair_chart(volume_chart, use_container_width=True)
                    
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
# 模組 4: 新增分析紀錄
# ----------------------------
with tab4:
    st.header("📝 新增股票分析紀錄")
    
    # 檢查是否有快速添加的股票
    default_code = ""
    default_name = ""
    if 'quick_add_stock' in st.session_state:
        default_code = st.session_state.quick_add_stock
        default_name = st.session_state.quick_add_name
    
    col1, col2 = st.columns(2)
    with col1:
        record_date = st.date_input("📅 分析日期", value=date.today())
        stock_code = st.text_input("🏷️ 股票代號", value=default_code, placeholder="例：2330")
        stock_name = st.text_input("📋 股票名稱", value=default_name, placeholder="例：台積電")
        target_price = st.number_input("🎯 目標價", min_value=0.0, step=0.01)
        stop_loss = st.number_input("🛡️ 停損價", min_value=0.0, step=0.01)

    with col2:
        confidence = st.slider("📊 信心度", 1, 10, 5)
        strategy_tags = st.multiselect(
            "🏃 策略標籤",
            ["技術分析", "基本面分析", "消息面", "長線投資", "短線交易", "波段操作", "價值投資", "成長股", "漲停股觀察", "概念股"],
        )
        market_sentiment = st.selectbox(
            "😊 市場情緒", ["非常樂觀", "樂觀", "中性", "悲觀", "非常悲觀"]
        )
        ref_index = st.multiselect(
            "📍 參考指標",
            ["籌碼差", "今日出關", "52H高點", "三均價", "融券張數多", "借券張數多", "漲停股", "AI人工智慧", "電動車", "5G通訊"],
        )

    prediction = st.text_area("🔮 預判方向與進場理由", height=100)
    analysis_content = st.text_area("📖 分析內容", height=100)
    notes = st.text_area("📝 額外備註", height=80)

    if st.button("💾 新增記錄", type="primary"):
        if stock_code and analysis_content and prediction:
            record = {
                "日期": record_date.strftime("%Y-%m-%d"),
                "股票代號": stock_code.upper(),
                "股票名稱": stock_name,
                "分析內容": analysis_content,
                "預判": prediction,
                "目標價": target_price if target_price > 0 else "",
                "停損價": stop_loss if stop_loss > 0 else "",
                "信心度": confidence,
                "策略標籤": ", ".join(strategy_tags) if strategy_tags else "",
                "市場情緒": market_sentiment,
                "備註": notes,
                "參考指標": ", ".join(ref_index) if isinstance(ref_index, list) else ref_index,
            }
            save_record(record)
            st.success("✅ 記錄已成功新增！")
            st.balloons()
            
            # 清除快速添加的session state
            if 'quick_add_stock' in st.session_state:
                del st.session_state.quick_add_stock
            if 'quick_add_name' in st.session_state:
                del st.session_state.quick_add_name
        else:
            st.error("❌ 請填寫必要欄位：股票代號、分析內容、預判")

# ----------------------------
# 模組 5: 瀏覽分析紀錄
# ----------------------------
with tab5:
    st.header("📚 瀏覽分析紀錄")
    
    if df_records.empty:
        st.info("📝 尚無任何記錄，請先新增分析記錄。")
    else:
        # 篩選功能
        col1, col2, col3 = st.columns(3)
        with col1:
            # 股票代號篩選
            all_stocks = ["全部"] + sorted(df_records["股票代號"].dropna().unique().tolist())
            selected_stock = st.selectbox("股票代號篩選", all_stocks)
        
        with col2:
            # 策略標籤篩選
            all_tags = ["全部"]
            for tags_str in df_records["策略標籤"].dropna():
                if tags_str:
                    all_tags.extend([tag.strip() for tag in str(tags_str).split(",")])
            unique_tags = ["全部"] + sorted(list(set(all_tags) - {"全部"}))
            selected_tag = st.selectbox("策略標籤篩選", unique_tags)
        
        with col3:
            # 信心度篩選
            min_confidence = st.slider("最低信心度", 1, 10, 1)
        
        # 套用篩選
        filtered_records = df_records.copy()
        if selected_stock != "全部":
            filtered_records = filtered_records[filtered_records["股票代號"] == selected_stock]
        if selected_tag != "全部":
            filtered_records = filtered_records[filtered_records["策略標籤"].str.contains(selected_tag, na=False)]
        filtered_records = filtered_records[filtered_records["信心度"] >= min_confidence]
        
        # 排序
        filtered_records = filtered_records.sort_values("日期", ascending=False)
        
        st.write(f"共找到 {len(filtered_records)} 筆記錄")
        
        # 顯示紀錄
        for idx, record in filtered_records.iterrows():
            with st.expander(f"📋 {record['股票代號']} - {record['股票名稱']} ({record['日期']})"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**分析內容：** {record['分析內容']}")
                    st.write(f"**預判：** {record['預判']}")
                    st.write(f"**備註：** {record['備註']}")
                with col2:
                    st.write(f"**目標價：** {record['目標價']}")
                    st.write(f"**停損價：** {record['停損價']}")
                    st.write(f"**信心度：** {record['信心度']}/10")
                    st.write(f"**策略標籤：** {record['策略標籤']}")
                    st.write(f"**市場情緒：** {record['市場情緒']}")
                    st.write(f"**參考指標：** {record['參考指標']}")
        
        # 完整表格檢視
        if st.checkbox("顯示完整表格"):
            st.dataframe(filtered_records, use_container_width=True)
        
        # 統計分析
        if len(filtered_records) > 0:
            st.subheader("📊 紀錄統計分析")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                # 信心度分布
                st.write("信心度分布")
                confidence_dist = filtered_records["信心度"].value_counts().sort_index()
                st.bar_chart(confidence_dist)
            
            with col2:
                # 策略標籤分布
                st.write("策略標籤分布")
                tag_counts = {}
                for tags_str in filtered_records["策略標籤"].dropna():
                    if tags_str:
                        for tag in str(tags_str).split(","):
                            tag = tag.strip()
                            tag_counts[tag] = tag_counts.get(tag, 0) + 1
                if tag_counts:
                    tag_df = pd.DataFrame(list(tag_counts.items()), columns=["標籤", "數量"])
                    st.bar_chart(tag_df.set_index("標籤"))
            
            with col3:
                # 市場情緒分布
                st.write("市場情緒分布")
                sentiment_dist = filtered_records["市場情緒"].value_counts()
                st.bar_chart(sentiment_dist)

# ----------------------------
# 模組 6: 整合分析視圖
# ----------------------------
with tab6:
    st.header("📋 整合分析視圖")
    
    if market_data_loaded and not df_records.empty:
        st.subheader("🔗 市場數據與個人紀錄整合分析")
        
        # 找出有紀錄的股票在當日的表現
        recorded_stocks = df_records["股票代號"].unique()
        market_recorded = day_data[day_data["代碼"].isin(recorded_stocks)].copy()
        
        if not market_recorded.empty:
            # 合併市場數據與個人紀錄
            latest_records = df_records.groupby("股票代號").last().reset_index()
            merged_data = market_recorded.merge(
                latest_records[["股票代號", "策略標籤", "信心度", "市場情緒", "預判"]],
                left_on="代碼", right_on="股票代號", how="left"
            )
            
            st.subheader("📊 觀察清單今日表現")
            
            # 表現統計
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("觀察股票數", len(merged_data))
            with col2:
                if "漲跌幅" in merged_data.columns:
                    positive_count = (merged_data["漲跌幅"] > 0).sum()
                    st.metric("上漲股票數", positive_count)
            with col3:
                if "漲跌幅" in merged_data.columns:
                    avg_return = merged_data["漲跌幅"].mean()
                    st.metric("平均報酬", f"{avg_return:.2f}%")
            with col4:
                if "信心度" in merged_data.columns:
                    avg_confidence = merged_data["信心度"].mean()
                    st.metric("平均信心度", f"{avg_confidence:.1f}")
            
            # 詳細表格
            display_cols = ["代碼", "商品", "收盤價", "漲跌幅", "成交量", "策略標籤", "信心度", "預判"]
            available_cols = [col for col in display_cols if col in merged_data.columns]
            
            styled_merged = merged_data[available_cols].copy()
            if "漲跌幅" in styled_merged.columns:
                styled_merged = styled_merged.sort_values("漲跌幅", ascending=False)
            
            st.dataframe(styled_merged, use_container_width=True)
            
            # 視覺化分析
            if "漲跌幅" in merged_data.columns and "信心度" in merged_data.columns:
                st.subheader("📈 信心度 vs 實際表現分析")
                
                # 散點圖：信心度 vs 報酬率
                scatter_chart = alt.Chart(merged_data).mark_circle(size=100).encode(
                    x=alt.X("信心度:Q", title="信心度", scale=alt.Scale(domain=[1, 10])),
                    y=alt.Y("漲跌幅:Q", title="今日漲跌幅(%)"),
                    color=alt.Color("漲跌幅:Q", scale=alt.Scale(scheme="redyellowgreen")),
                    size=alt.Size("成交量:Q", scale=alt.Scale(range=[50, 300])) if "成交量" in merged_data.columns else alt.value(100),
                    tooltip=["代碼", "商品", "信心度", "漲跌幅", "策略標籤"]
                ).properties(
                    height=400,
                    title="信心度與實際表現關係圖"
                )
                st.altair_chart(scatter_chart, use_container_width=True)
                
                # 策略標籤表現分析
                if "策略標籤" in merged_data.columns:
                    st.subheader("📊 策略標籤表現分析")
                    
                    # 計算各策略標籤的平均表現
                    strategy_performance = []
                    for idx, row in merged_data.iterrows():
                        if pd.notna(row["策略標籤"]) and pd.notna(row["漲跌幅"]):
                            tags = [tag.strip() for tag in str(row["策略標籤"]).split(",")]
                            for tag in tags:
                                strategy_performance.append({"策略": tag, "報酬率": row["漲跌幅"]})
                    
                    if strategy_performance:
                        strategy_df = pd.DataFrame(strategy_performance)
                        strategy_avg = strategy_df.groupby("策略")["報酬率"].agg(["mean", "count"]).reset_index()
                        strategy_avg.columns = ["策略", "平均報酬率", "樣本數"]
                        strategy_avg = strategy_avg[strategy_avg["樣本數"] >= 1].sort_values("平均報酬率", ascending=False)
                        
                        st.dataframe(strategy_avg, use_container_width=True)
                        
                        # 策略表現圖
                        strategy_chart = alt.Chart(strategy_avg).mark_bar().encode(
                            x=alt.X("策略:N", sort="-y"),
                            y=alt.Y("平均報酬率:Q", title="平均報酬率(%)"),
                            color=alt.condition(
                                alt.datum["平均報酬率"] >= 0,
                                alt.value("green"),
                                alt.value("red")
                            ),
                            tooltip=["策略", "平均報酬率", "樣本數"]
                        ).properties(height=300, title="各策略標籤平均表現")
                        st.altair_chart(strategy_chart, use_container_width=True)
        else:
            st.info("觀察清單中的股票在當日沒有交易數據")
    
    elif market_data_loaded:
        st.info("請先建立一些分析紀錄，然後就能看到市場數據與個人紀錄的整合分析")
    
    elif not df_records.empty:
        st.info("載入市場數據後，就能看到更豐富的整合分析")
        
        # 僅顯示個人紀錄的統計
        st.subheader("📊 個人分析紀錄統計")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("總紀錄數", len(df_records))
        with col2:
            st.metric("觀察股票數", df_records["股票代號"].nunique())
        with col3:
            avg_confidence = df_records["信心度"].mean()
            st.metric("平均信心度", f"{avg_confidence:.1f}")
        
        # 最近的分析紀錄
        st.subheader("📝 最近的分析紀錄")
        recent_records = df_records.sort_values("日期", ascending=False).head(5)
        st.dataframe(recent_records[["日期", "股票代號", "股票名稱", "策略標籤", "信心度"]], use_container_width=True)
    
    else:
        st.info("👈 請先載入市場資料或建立分析紀錄來使用整合分析功能")

# 如果沒有載入市場數據，顯示提示
if not market_data_loaded:
    st.info("💡 載入 Google Drive 的市場數據檔案後，就能使用完整的市場分析功能（漲跌股分析、概念股追蹤、成交紀錄分析）")

# 頁腳
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: gray; padding: 20px;'>
    <p> 1iYzALB8Gt7yu1tTUgtJMtpQS9mgWvLrxhw8lGEYHxAA </p>
    <p>📊 整合股票市場分析與紀錄系統 | 結合市場數據載入與個人分析紀錄管理</p>
    <p>💡 提示：確認檔案權限設為『知道連結者可檢視』，檔案包含日期(YYYYMMDD)與代碼欄位</p>
    <p>🔗 支援功能：漲跌股分析 ➤ 概念股追蹤 ➤ 技術分析 ➤ 個人紀錄管理 ➤ 整合分析視圖</p>
</div>
""", unsafe_allow_html=True)
