import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json

# --- 1. 設定區 ---
# 定義權限範圍
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
# 指定您的試算表名稱 (需與 Google Drive 上的一模一樣)
SHEET_NAME = "accounting_db" 

# 設定頁面 (這行必須在最前面)
st.set_page_config(page_title="公司財務戰情室 (雲端版)", page_icon="☁️", layout="wide")

# --- 2. 核心函數：連接 Google Sheets (智慧切換模式) ---
@st.cache_resource
def connect_to_gsheets():
    try:
        # 情況 A: 如果電腦裡有 credentials.json (本機模式)
        if os.path.exists("credentials.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
        
        # 情況 B: 如果在雲端，讀取 Streamlit Secrets (雲端模式)
        elif "gcp_service_account" in st.secrets:
            # 將 Secrets 轉換為字典格式
            key_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, SCOPE)
        
        else:
            st.error("找不到金鑰！請確認本地有 credentials.json 或雲端已設定 Secrets。")
            st.stop()
            
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1  # 開啟第一個工作表
        return sheet
    except Exception as e:
        st.error(f"❌ 無法連接 Google Sheets: {e}")
        st.stop()

# --- 3. 資料讀取函數 ---
def load_data():
    sheet = connect_to_gsheets()
    try:
        # 讀取所有資料
        data = sheet.get_all_records()
        if not data:
            return pd.DataFrame(columns=["Date", "Category", "Amount", "Note"])
        
        df = pd.DataFrame(data)
        
        # 確保欄位名稱正確 (容錯處理)
        # 如果 Google Sheet 欄位是中文，確保 DataFrame 也能對應
        
        # 處理日期格式
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
        
        # 處理金額格式 (去除逗號轉數字)
        if 'Amount' in df.columns:
             if df['Amount'].dtype == 'object':
                 df['Amount'] = pd.to_numeric(df['Amount'].astype(str).str.replace(',',''), errors='coerce')
        
        return df
    except Exception as e:
        st.warning(f"讀取資料時發生錯誤或試算表為空: {e}")
        return pd.DataFrame(columns=["Date", "Category", "Amount", "Note"])

# --- 4. 資料寫入函數 ---
def save_entry_to_cloud(date, category, amount, note):
    sheet = connect_to_gsheets()
    # 將日期轉為字串儲存
    date_str = date.strftime("%Y-%m-%d")
    # 新增一列 (Append Row)
    sheet.append_row([date_str, category, amount, note])

# --- 5. 主程式邏輯 (UI 介面) ---

# 初始化資料
df = load_data()

# 類別選單
categories = ["薪資", "租金", "進貨成本", "行銷廣告", "交通差旅", "辦公雜項", "稅務", "交際費"]

# --- 側邊欄 ---
with st.sidebar:
    st.title("☁️ 雲端設定")
    if not df.empty and 'Date' in df.columns:
        min_year = int(df['Date'].dt.year.min())
        max_year = int(df['Date'].dt.year.max())
        years = list(range(max_year, min_year - 1, -1))
        selected_year = st.selectbox("📅 分析年份", ["所有年份"] + years)
    else:
        selected_year = "所有年份"

    if st.button("🔄 重新整理資料"):
        st.cache_data.clear()
        st.rerun()

# --- 主畫面標題 ---
st.title("☁️ Bluebulous 財務戰情室 (Cloud Version)")
st.caption(f"資料來源: Google Sheet [{SHEET_NAME}]")

# 分頁
tab1, tab2, tab3 = st.tabs(["📈 視覺化儀表板", "➕ 新增支出", "📋 詳細資料"])

# --- TAB 1: 視覺化 ---
with tab1:
    if df.empty:
        st.info("目前沒有資料，請至「新增支出」分頁輸入第一筆數據。")
    else:
        dashboard_df = df.copy()
        if selected_year != "所有年份":
            dashboard_df = dashboard_df[dashboard_df['Date'].dt.year == selected_year]
        
        if dashboard_df.empty:
            st.warning("該年份無資料")
        else:
            # KPI
            total = dashboard_df['Amount'].sum()
            avg = dashboard_df['Amount'].mean()
            
            c1, c2 = st.columns(2)
            c1.metric("總支出", f"${total:,.0f}")
            c2.metric("平均支出", f"${avg:,.0f}")
            
            st.markdown("---")
            
            # 圖表
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("類別佔比")
                if 'Category' in dashboard_df.columns:
                    cat_sum = dashboard_df.groupby("Category")["Amount"].sum().reset_index()
                    fig_pie = px.pie(cat_sum, values='Amount', names='Category', hole=0.4)
                    st.plotly_chart(fig_pie, use_container_width=True)
            
            with col2:
                st.subheader("月度趨勢")
                if 'Date' in dashboard_df.columns:
                    monthly = dashboard_df.set_index('Date').resample('ME')['Amount'].sum().reset_index()
                    fig_line = px.line(monthly, x='Date', y='Amount')
                    st.plotly_chart(fig_line, use_container_width=True)

# --- TAB 2: 新增支出 ---
with tab2:
    st.header("新增一筆紀錄")
    with st.form("cloud_entry", clear_on_submit=True):
        d = st.date_input("日期", datetime.today())
        a = st.number_input("金額", min_value=0, step=100)
        c = st.selectbox("類別", categories)
        n = st.text_input("備註")
        
        submitted = st.form_submit_button("☁️ 上傳至雲端")
        if submitted:
            if a > 0:
                with st.spinner("正在寫入 Google Sheets..."):
                    save_entry_to_cloud(d, c, a, n)
                st.success("✅ 資料已同步至 Google Sheets！")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("金額必須大於 0")

# --- TAB 3: 資料表 ---
with tab3:
    if not df.empty:
        st.dataframe(df.sort_values(by="Date", ascending=False), use_container_width=True)
        st.info("如需修改或刪除舊資料，請直接前往 Google Sheets 操作，完成後按側邊欄的「重新整理」。")
    else:
        st.write("尚無資料")