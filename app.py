import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json

# --- 設定 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SHEET_NAME = "accounting_db" 

st.set_page_config(page_title="公司財務戰情室 (雲端版)", page_icon="☁️", layout="wide")

# --- 核心函數：連接 Google Sheets (智慧切換模式) ---
@st.cache_resource
def connect_to_gsheets():
    try:
        # 情況 A: 如果電腦裡有 credentials.json (本機模式)
        if os.path.exists("credentials.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
        
        # 情況 B: 如果在雲端，讀取 Streamlit Secrets (雲端模式)
        elif "gcp_service_account" in st.secrets:
            key_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, SCOPE)
        
        else:
            st.error("找不到金鑰！請確認本地有 credentials.json 或雲端已設定 Secrets。")
            st.stop()
            
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1
        return sheet
    except Exception as e:
        st.error(f"❌ 無法連接 Google Sheets: {e}")
        st.stop()

# --- (以下程式碼不需要改動，保持原樣) ---
# ... (請保留原本 load_data, save_entry_to_cloud 以及後面所有的 UI 程式碼)
# 為節省篇幅，請將原本 app.py 下半部 (從 def load_data 開始) 完整保留接在上面這段之後