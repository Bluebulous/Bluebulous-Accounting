import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json

# --- 1. 設定區 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SHEET_NAME = "accounting_db" 

st.set_page_config(page_title="Bluebulous財務戰情室", page_icon="🏢", layout="wide")

# --- 2. 連線與資料處理 ---
@st.cache_resource
def connect_to_gsheets():
    try:
        if os.path.exists("credentials.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
        elif "gcp_service_account" in st.secrets:
            key_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, SCOPE)
        else:
            st.error("找不到金鑰！")
            st.stop()
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1
        return sheet
    except Exception as e:
        st.error(f"❌ 無法連接 Google Sheets: {e}")
        st.stop()

def load_data():
    sheet = connect_to_gsheets()
    try:
        all_values = sheet.get_all_values()
        
        if len(all_values) < 2:
            return pd.DataFrame(columns=["Date", "Category", "Amount", "Note", "User", "row_id"])
        
        header = all_values[0]
        data = all_values[1:]
        
        df = pd.DataFrame(data, columns=header)
        df['row_id'] = range(2, len(df) + 2) 

        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        if 'Amount' in df.columns:
             df['Amount'] = df['Amount'].astype(str).str.replace(',', '').apply(pd.to_numeric, errors='coerce').fillna(0)
             
        return df
    except Exception as e:
        return pd.DataFrame(columns=["Date", "Category", "Amount", "Note", "User", "row_id"])

def save_entry_to_cloud(date, category, amount, note, user):
    sheet = connect_to_gsheets()
    date_str = date.strftime("%Y-%m-%d")
    sheet.append_row([date_str, category, amount, note, user])

def delete_entry_from_cloud(row_id):
    sheet = connect_to_gsheets()
    sheet.delete_rows(int(row_id))

# --- 3. 初始化資料 ---
df = load_data()
categories = ["進貨成本", "運費", "行銷廣告", "交通差旅", "辦公雜項", "租金貸款", "營業稅＆其他稅務", "交際費", "軟體系統使用費", "薪資人事費"]
employees = ["選擇您的名字...", "Yuri", "YT", "NiNi"]

# ==========================================
# 🔐 側邊欄：身份與權限設定
# ==========================================
with st.sidebar:
    st.title("👤 身份設定")
    current_user = st.selectbox("請問您是哪一位？", employees)
    st.markdown("---")
    
    st.subheader("🔐 管理員專區")
    if "admin_password" in st.secrets:
        correct_password = st.secrets["admin_password"]
    else:
        correct_password = "admin" 
    
    admin_input = st.text_input("輸入密碼解鎖總報表", type="password")
    
    is_admin = False
    if admin_input == correct_password:
        is_admin = True
        st.success("✅ 管理員模式已啟動")
        if st.button("🔄 強制重新整理資料"):
            st.cache_data.clear()
            st.rerun()
    elif admin_input: 
        st.error("❌ 密碼錯誤") 

# --- 4. 主畫面顯示邏輯 ---

st.title("🏢 Bluebulous 記帳系統")

if current_user == "選擇您的名字...":
    st.info("👈 請先在左側選單選擇您的名字，才能開始記帳。")
    st.stop() 

st.write(f"👋 您好，**{current_user}**！")

tab1, tab2, tab3, tab4 = st.tabs(["➕ 新增支出", "📝 我的紀錄 (可修改)", "📈 總報表 (限)", "📋 總明細 (限)"])

# --- TAB 1: 新增支出 ---
with tab1:
    st.header("新增一筆紀錄")
    with st.form("cloud_entry", clear_on_submit=True):
        d = st.date_input("日期", datetime.today())
        a = st.number_input("金額", min_value=0, step=100)
        c = st.selectbox("類別", categories)
        n = st.text_input("備註")
        
        submitted = st.form_submit_button("☁️ 上傳資料")
        if submitted:
            if a > 0:
                with st.spinner("正在寫入雲端..."):
                    save_entry_to_cloud(d, c, a, n, current_user)
                st.success("✅ 資料已儲存！")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("金額必須大於 0")

# --- TAB 2: 我的紀錄 ---
with tab2:
    st.header(f"📝 {current_user} 的記帳紀錄")
    if not df.empty and "User" in df.columns:
        my_df = df[df["User"] == current_user].copy()
        if my_df.empty:
            st.info("您目前還沒有輸入過任何資料。")
        else:
            st.dataframe(my_df[["Date", "Category", "Amount", "Note", "User"]].sort_values(by="Date", ascending=False), use_container_width=True)
            st.markdown("---")
            st.subheader("❌ 刪除/修改資料")
            my_df['label'] = my_df['Date'].dt.strftime('%Y-%m-%d') + " | $" + my_df['Amount'].astype(int).astype(str) + " | " + my_df['Note']
            delete_target = st.selectbox("選擇要刪除的項目：", ["(請選擇)"] + my_df['label'].tolist())
            if delete_target != "(請選擇)":
                target_row = my_df[my_df['label'] == delete_target].iloc[0]
                row_id_to_delete = target_row['row_id']
                if st.button(f"🗑️ 確定刪除：{delete_target}"):
                    with st.spinner("正在刪除..."):
                        delete_entry_from_cloud(row_id_to_delete)
                    st.success("✅ 刪除成功！")
                    st.cache_data.clear()
                    st.rerun()
    else:
        st.warning("資料庫結構正在更新，或目前無資料。")

# --- TAB 3: 總報表 (修正：本月支出 & X軸分類) ---
with tab3:
    if is_admin:
        if df.empty:
            st.info("目前沒有資料，請先新增支出。")
        else:
            # 建立 'YearMonth' 欄位
            df['YearMonth'] = df['Date'].dt.strftime('%Y-%m') # 使用標準字串格式
            
            # --- 計算 KPI ---
            total_exp = df['Amount'].sum()
            unique_months = df['YearMonth'].nunique()
            avg_monthly = total_exp / unique_months if unique_months > 0 else total_exp
            
            # 🔥 計算「本月支出」 (使用現在真實時間)
            current_ym = datetime.now().strftime('%Y-%m')
            # 篩選出 YearMonth 等於 現在月份 的資料
            current_month_df = df[df['YearMonth'] == current_ym]
            current_month_total = current_month_df['Amount'].sum()
            
            st.markdown("### 📊 財務關鍵指標")
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("💰 歷史總支出", f"${total_exp:,.0f}")
            kpi2.metric("📅 平均月支出", f"${avg_monthly:,.0f}")
            # 修改這裡：顯示本月支出
            kpi3.metric(f"📆 本月支出 ({current_ym})", f"${current_month_total:,.0f}")
            
            st.markdown("---")

            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("1️⃣ 各類別支出佔比")
                cat_sum = df.groupby("Category")["Amount"].sum().reset_index()
                fig_pie = px.pie(cat_sum, values='Amount', names='Category', hole=0.4) 
                fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with col2:
                st.subheader("2️⃣ 每月總支出趨勢")
                monthly_total = df.groupby('YearMonth')['Amount'].sum().reset_index()
                fig_line = px.line(monthly_total, x='YearMonth', y='Amount', markers=True)
                # 🔥 關鍵修正：強制 X 軸為分類模式 (category)，避免被當成連續日期
                fig_line.update_xaxes(type='category')
                fig_line.update_layout(xaxis_title="月份", yaxis_title="金額")
                st.plotly_chart(fig_line, use_container_width=True)

            st.markdown("---")

            st.subheader("3️⃣ 各類別每月詳細分析")
            monthly_cat = df.groupby(['YearMonth', 'Category'])['Amount'].sum().reset_index()
            chart_type = st.radio("選擇圖表類型：", ["折線圖 (比較趨勢)", "堆疊長條圖 (比較結構)"], horizontal=True)
            
            if "折線圖" in chart_type:
                fig_multi = px.line(monthly_cat, x='YearMonth', y='Amount', color='Category', markers=True)
            else:
                fig_multi = px.bar(monthly_cat, x='YearMonth', y='Amount', color='Category')

            # 🔥 關鍵修正：這裡也要強制 X 軸為分類模式
            fig_multi.update_xaxes(type='category')
            fig_multi.update_layout(xaxis_title="月份", yaxis_title="金額")
            st.plotly_chart(fig_multi, use_container_width=True)

    else:
        st.warning("🔒 這是公司機密數據，請輸入管理員密碼解鎖。")

# --- TAB 4: 總明細 ---
with tab4:
    if is_admin:
        st.dataframe(df.sort_values(by="Date", ascending=False), use_container_width=True)
    else:
        st.warning("🔒 需要管理員權限")
