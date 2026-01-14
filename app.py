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
        # 使用 get_all_values 而不是 records，這樣才能確保我們掌握行數
        all_values = sheet.get_all_values()
        
        if len(all_values) < 2:
            return pd.DataFrame(columns=["Date", "Category", "Amount", "Note", "User", "row_id"])
        
        # 第一列是標題，後面是資料
        header = all_values[0]
        data = all_values[1:]
        
        df = pd.DataFrame(data, columns=header)
        
        # ⚠️ 關鍵：加上「行號 (row_id)」
        # Excel 表格中，標題是第1行，第一筆資料是第2行。
        # Python 的 index 是從 0 開始，所以第一筆資料 index 0 對應 Excel 的 Row 2
        df['row_id'] = range(2, len(df) + 2) 

        # 格式轉換
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        if 'Amount' in df.columns:
             # 清除逗號並轉數字
             df['Amount'] = df['Amount'].astype(str).str.replace(',', '').apply(pd.to_numeric, errors='coerce').fillna(0)
             
        return df
    except Exception as e:
        return pd.DataFrame(columns=["Date", "Category", "Amount", "Note", "User", "row_id"])

def save_entry_to_cloud(date, category, amount, note, user):
    sheet = connect_to_gsheets()
    date_str = date.strftime("%Y-%m-%d")
    # 把使用者名稱 (user) 也存進去
    sheet.append_row([date_str, category, amount, note, user])

def delete_entry_from_cloud(row_id):
    sheet = connect_to_gsheets()
    sheet.delete_rows(int(row_id))

# --- 3. 初始化資料 ---
df = load_data()
categories = ["進貨成本", "運費", "行銷廣告", "交通差旅", "辦公雜項", "租金貸款", "營業稅＆其他稅務", "交際費", "軟體系統使用費", "薪資人事費"]
# 定義員工名單 (您可以隨時在這裡增加名字)
employees = ["選擇您的名字...", "Yuri", "YT", "NiNi"]

# ==========================================
# 🔐 側邊欄：身份與權限設定
# ==========================================
with st.sidebar:
    st.title("👤 身份設定")
    
    # 1. 選擇我是誰
    current_user = st.selectbox("請問您是哪一位？", employees)
    
    st.markdown("---")
    
    # 2. 管理員登入 (只有老闆要用)
    st.subheader("🔐 管理員專區")
    
    if "admin_password" in st.secrets:
        correct_password = st.secrets["admin_password"]
    else:
        correct_password = "admin" 
    
    # ... (前面的程式碼) ...
    
    admin_input = st.text_input("輸入密碼解鎖總報表", type="password")
    
    is_admin = False
    if admin_input == correct_password:
        is_admin = True
        st.success("✅ 管理員模式已啟動") # <--- 如果成功，會出現這個
        if st.button("🔄 強制重新整理資料"):
            st.cache_data.clear()
            st.rerun()
    elif admin_input: # <--- 新增這一段：如果有輸入內容，但上面沒通過
        st.error("❌ 密碼錯誤，請檢查 Secrets 設定") # <--- 跳出錯誤提示

# --- 4. 主畫面顯示邏輯 ---

st.title("🏢 Bluebulous 記帳系統")

if current_user == "選擇您的名字...":
    st.info("👈 請先在左側選單選擇您的名字，才能開始記帳。")
    st.stop() # 暫停執行下面的程式，直到選了名字

st.write(f"👋 您好，**{current_user}**！")

# 分頁設定
tab1, tab2, tab3, tab4 = st.tabs(["➕ 新增支出", "📝 我的紀錄 (可修改)", "📈 總報表 (限)", "📋 總明細 (限)"])

# --- TAB 1: 新增支出 (自動帶入名字) ---
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
                    # 這裡把 current_user 傳進去
                    save_entry_to_cloud(d, c, a, n, current_user)
                st.success("✅ 資料已儲存！")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("金額必須大於 0")

# --- TAB 2: 我的紀錄 (只看得到自己的，且可刪除) ---
with tab2:
    st.header(f"📝 {current_user} 的記帳紀錄")
    
    if not df.empty and "User" in df.columns:
        # 篩選：只抓出 User 欄位等於 current_user 的資料
        my_df = df[df["User"] == current_user].copy()
        
        if my_df.empty:
            st.info("您目前還沒有輸入過任何資料。")
        else:
            # 顯示表格
            st.dataframe(my_df[["Date", "Category", "Amount", "Note"]].sort_values(by="Date", ascending=False), use_container_width=True)
            
            st.markdown("---")
            st.subheader("❌ 刪除/修改資料")
            st.caption("如果您輸入錯誤，請在這裡選取該筆資料並刪除，然後再去「新增支出」重新輸入正確的。")
            
            # 製作一個選單，讓使用者選擇要刪除哪一筆 (顯示 日期-金額-備註)
            # 這裡我們把 row_id 藏在選項的 key 裡
            my_df['label'] = my_df['Date'].dt.strftime('%Y-%m-%d') + " | $" + my_df['Amount'].astype(int).astype(str) + " | " + my_df['Note']
            
            delete_target = st.selectbox("選擇要刪除的項目：", ["(請選擇)"] + my_df['label'].tolist())
            
            if delete_target != "(請選擇)":
                # 找出那筆資料的 row_id
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

# --- TAB 3: 總報表 (管理員限定) ---
with tab3:
    if is_admin:
        # (這裡放原本的報表程式碼，稍微簡化顯示)
        if df.empty:
            st.info("無資料")
        else:
            total = df['Amount'].sum()
            c1, c2 = st.columns(2)
            c1.metric("公司總支出", f"${total:,.0f}")
            # 依員工統計
            if "User" in df.columns:
                st.subheader("各員工申報總額")
                user_sum = df.groupby("User")["Amount"].sum().reset_index()
                st.bar_chart(user_sum, x="User", y="Amount")
    else:
        st.warning("🔒 需要管理員權限")

# --- TAB 4: 總明細 (管理員限定) ---
with tab4:
    if is_admin:
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("🔒 需要管理員權限")