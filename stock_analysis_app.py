
import streamlit as st
import pandas as pd
from datetime import datetime, date
import os

from utils.twse_api import fetch_twse_stock_data

# 設定頁面樣式
st.set_page_config(page_title="股票紀錄分析", layout="wide")
st.title("📈 股票紀錄分析工具")

# 初始化 CSV 檔案
CSV_FILE = "data/notes.csv"
def initialize_csv():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(CSV_FILE):
        columns = [
            '日期', '股票代號', '股票名稱', '分析內容', '預判', 
            '目標價', '停損價', '信心度', '策略標籤', '市場情緒', '備註'
        ]
        df_empty = pd.DataFrame(columns=columns)
        df_empty.to_csv(CSV_FILE, index=False, encoding='utf-8-sig')
initialize_csv()

@st.cache_data
def load_data():
    if os.path.exists(CSV_FILE):
        return pd.read_csv(CSV_FILE, encoding='utf-8-sig')
    return pd.DataFrame()

def save_record(record):
    df = load_data()
    new_df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
    new_df.to_csv(CSV_FILE, index=False, encoding='utf-8-sig')
    st.cache_data.clear()

# 側邊欄功能選單
st.sidebar.title("功能選單")
function = st.sidebar.radio(
    "選擇功能",
    ["新增分析記錄", "瀏覽與篩選記錄", "📊 多股比較分析"]
)

if function == "新增分析記錄":
    st.header("📝 新增股票分析記錄")

    col1, col2 = st.columns(2)
    with col1:
        record_date = st.date_input("📅 分析日期", value=date.today())
        stock_code = st.text_input("🏷️ 股票代號", placeholder="例：2330")
        stock_name = st.text_input("📋 股票名稱", placeholder="例：台積電")
        target_price = st.number_input("🎯 目標價", min_value=0.0, step=0.01)
        stop_loss = st.number_input("🛡️ 停損價", min_value=0.0, step=0.01)

    with col2:
        confidence = st.slider("📊 信心度", 1, 10, 5)
        strategy_tags = st.multiselect(
            "🏃 策略標籤",
            ["技術分析", "基本面分析", "消息面", "長線投資", "短線交易", "波段操作", "價值投資", "成長股"]
        )
        market_sentiment = st.selectbox(
            "😊 市場情緒",
            ["非常樂觀", "樂觀", "中性", "悲觀", "非常悲觀"]
        )

    analysis_content = st.text_area("📖 分析內容", height=100)
    prediction = st.text_area("🔮 預判與理由", height=100)
    notes = st.text_area("📝 額外備註", height=80)

    if st.button("💾 新增記錄", type="primary"):
        if stock_code and analysis_content and prediction:
            record = {
                '日期': record_date.strftime('%Y-%m-%d'),
                '股票代號': stock_code.upper(),
                '股票名稱': stock_name,
                '分析內容': analysis_content,
                '預判': prediction,
                '目標價': target_price if target_price > 0 else '',
                '停損價': stop_loss if stop_loss > 0 else '',
                '信心度': confidence,
                '策略標籤': ', '.join(strategy_tags) if strategy_tags else '',
                '市場情緒': market_sentiment,
                '備註': notes
            }
            save_record(record)
            st.success("✅ 記錄已成功新增！")
            st.balloons()
        else:
            st.error("❌ 請填寫必要欄位：股票代號、分析內容、預判")

elif function == "瀏覽與篩選記錄":
    st.header("📚 瀏覽分析記錄")
    df = load_data()
    if df.empty:
        st.info("📝 尚無任何記錄，請先新增分析記錄。")
    else:
        st.dataframe(df)

elif function == "📊 多股比較分析":
    st.header("📊 多股收盤價與主觀分析比較")

    df_notes = load_data()
    if "股票代號" in df_notes.columns:
        stock_choices = df_notes["股票代號"].unique().tolist()[:20]
    else:
        stock_choices = []
        st.warning("⚠️ 資料中找不到『股票代號』欄位，請先建立分析記錄。")

    selected_stocks = st.multiselect("選擇最多 5 檔股票進行比較", stock_choices, max_selections=5)

    if selected_stocks:
        all_data = []
        for code in selected_stocks:
            with st.spinner(f"抓取 {code} 收盤資料..."):
                monthly_data = []
                today = datetime.today()
                for i in range(3):
                    y = today.year
                    m = today.month - i
                    if m <= 0:
                        m += 12
                        y -= 1
                    df_price = fetch_twse_stock_data(code, y, m)
                    if not df_price.empty:
                        df_price["股票代號"] = code
                        monthly_data.append(df_price)
                if monthly_data:
                    df_all = pd.concat(monthly_data)
                    all_data.append(df_all)

        if all_data:
            price_df = pd.concat(all_data)
            pivot_df = price_df.pivot(index="日期", columns="股票代號", values="收盤價")
            st.line_chart(pivot_df)

        st.subheader("📋 主觀分析比較")
        filtered_notes = df_notes[df_notes["股票代號"].isin(selected_stocks)]
        st.dataframe(filtered_notes[["日期", "股票代號", "目標價", "信心度", "策略標籤"]])
