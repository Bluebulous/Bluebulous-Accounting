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
SHEET_ID = "1AEj8yFnrvzm7p2IQQeGe5PdBgRJLLtZd1Lx55SNvn40"

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
        elif os.environ.get("GCP_JSON"):
            key_dict = json.loads(os.environ.get("GCP_JSON"))
            creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, SCOPE)
        else:
            st.error("找不到 Google Sheets 金鑰！")
            st.stop()

        client = gspread.authorize(creds)
        return client.open_by_key(SHEET_ID)
    except Exception as e:
        st.error(f"❌ 無法連接 Google Sheets: {e}")
        st.stop()


def load_data():
    spreadsheet = connect_to_gsheets()
    sheet = spreadsheet.sheet1

    expected_columns = [
        "Date", "Category", "Amount", "Note", "User",
        "Status", "CreatedAt", "UpdatedAt", "VoidedAt", "VoidedBy"
    ]

    try:
        all_values = sheet.get_all_values()

        if len(all_values) < 2:
            return pd.DataFrame(columns=expected_columns + ["row_id"])

        header = all_values[0]
        data = all_values[1:]
        df = pd.DataFrame(data, columns=header)
        df["row_id"] = range(2, len(df) + 2)

        for col in expected_columns:
            if col not in df.columns:
                if col == "Status":
                    df[col] = "正常"
                else:
                    df[col] = ""

        df["Status"] = df["Status"].replace("", "正常").fillna("正常")

        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

        if "Amount" in df.columns:
            df["Amount"] = (
                df["Amount"]
                .astype(str)
                .str.replace(",", "", regex=False)
                .apply(pd.to_numeric, errors="coerce")
                .fillna(0)
            )

        return df

    except Exception:
        return pd.DataFrame(columns=expected_columns + ["row_id"])


@st.cache_data
def load_categories():
    spreadsheet = connect_to_gsheets()
    default_cats = [
        "進貨成本", "運費", "行銷廣告", "交通差旅", "辦公雜項", "水電等硬體費用",
        "租金貸款", "營業稅＆其他稅務", "交際費", "軟體系統使用費", "薪資人事費"
    ]

    try:
        cat_sheet = spreadsheet.worksheet("Categories")
        cats = cat_sheet.col_values(1)
        cats = [c.strip() for c in cats if c.strip()]

        if not cats:
            cat_sheet.append_rows([[c] for c in default_cats])
            return default_cats

        return cats

    except Exception as e:
        if "WorksheetNotFound" in str(type(e).__name__):
            try:
                cat_sheet = spreadsheet.add_worksheet(title="Categories", rows="100", cols="1")
                cat_sheet.append_rows([[c] for c in default_cats])
                return default_cats
            except Exception:
                return default_cats

        return default_cats


def add_category_to_cloud(new_cat):
    spreadsheet = connect_to_gsheets()
    cat_sheet = spreadsheet.worksheet("Categories")
    cat_sheet.append_row([new_cat.strip()])


def save_entry_to_cloud(date, category, amount, note, user):
    spreadsheet = connect_to_gsheets()
    sheet = spreadsheet.sheet1

    date_str = date.strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sheet.append_row([
        date_str,
        category,
        amount,
        note,
        user,
        "正常",
        now_str,
        now_str,
        "",
        ""
    ])


def update_entry_in_cloud(row_id, date, category, amount, note, user):
    spreadsheet = connect_to_gsheets()
    sheet = spreadsheet.sheet1

    date_str = date.strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cell_list = sheet.range(f"A{row_id}:E{row_id}")
    values = [date_str, category, amount, note, user]

    for i, val in enumerate(values):
        cell_list[i].value = val

    sheet.update_cells(cell_list)
    sheet.update_cell(int(row_id), 8, now_str)


def void_entry_in_cloud(row_id, current_user):
    spreadsheet = connect_to_gsheets()
    sheet = spreadsheet.sheet1

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sheet.update_cell(int(row_id), 6, "作廢")
    sheet.update_cell(int(row_id), 8, now_str)
    sheet.update_cell(int(row_id), 9, now_str)
    sheet.update_cell(int(row_id), 10, current_user)


def find_duplicate_entries(df, date, category, amount, user):
    if df.empty or "Date" not in df.columns:
        return pd.DataFrame()

    active_df = df[df["Status"] != "作廢"].copy()

    if active_df.empty:
        return pd.DataFrame()

    date_str = date.strftime("%Y-%m-%d")
    active_df["DateStr"] = active_df["Date"].dt.strftime("%Y-%m-%d")

    return active_df[
        (active_df["DateStr"] == date_str) &
        (active_df["Category"] == category) &
        (active_df["Amount"] == amount) &
        (active_df["User"] == user)
    ]


def get_duplicate_groups(df):
    if df.empty:
        return pd.DataFrame()

    active_df = df[df["Status"] != "作廢"].copy()

    if active_df.empty:
        return pd.DataFrame()

    active_df["DateStr"] = active_df["Date"].dt.strftime("%Y-%m-%d")

    dup_cols = ["DateStr", "User", "Category", "Amount"]
    dup_mask = active_df.duplicated(subset=dup_cols, keep=False)

    return active_df[dup_mask].sort_values(by=["Date", "User", "Category", "Amount"])


# --- 3. 初始化資料 ---
df = load_data()
categories = load_categories()
employees = ["選擇您的名字...", "Yuri", "YT", "NiNi"]

if "pending_entry" not in st.session_state:
    st.session_state.pending_entry = None

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
    elif os.environ.get("admin_password"):
        correct_password = os.environ.get("admin_password")
    else:
        correct_password = None
        st.warning("尚未設定管理員密碼。請在 Streamlit Secrets 或環境變數設定 admin_password。")

    admin_input = st.text_input("輸入密碼解鎖總報表", type="password")

    is_admin = False

    if correct_password and admin_input == correct_password:
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

tab1, tab2, tab3, tab4 = st.tabs([
    "➕ 新增支出",
    "📝 我的紀錄 (點擊修改)",
    "📈 總報表 (限)",
    "📋 總明細與管理 (限)"
])

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
            if a <= 0:
                st.error("金額必須大於 0")
            else:
                duplicates = find_duplicate_entries(df, d, c, a, current_user)

                if not duplicates.empty:
                    st.session_state.pending_entry = {
                        "date": d,
                        "category": c,
                        "amount": a,
                        "note": n,
                        "user": current_user
                    }
                    st.warning("⚠️ 可能已有相同紀錄，請確認是否仍要新增。")
                else:
                    with st.spinner("正在寫入雲端..."):
                        save_entry_to_cloud(d, c, a, n, current_user)

                    st.success("✅ 資料已儲存！")
                    st.cache_data.clear()
                    st.rerun()

    if st.session_state.pending_entry:
        pending = st.session_state.pending_entry
        duplicates = find_duplicate_entries(
            df,
            pending["date"],
            pending["category"],
            pending["amount"],
            pending["user"]
        )

        st.markdown("---")
        st.warning("⚠️ 系統找到可能重複的紀錄：")

        if not duplicates.empty:
            st.dataframe(
                duplicates[["Date", "Category", "Amount", "Note", "User"]],
                use_container_width=True
            )

        c1, c2 = st.columns(2)

        with c1:
            if st.button("✅ 確認仍要新增", type="primary", use_container_width=True):
                with st.spinner("正在寫入雲端..."):
                    save_entry_to_cloud(
                        pending["date"],
                        pending["category"],
                        pending["amount"],
                        pending["note"],
                        pending["user"]
                    )

                st.session_state.pending_entry = None
                st.success("✅ 資料已儲存！")
                st.cache_data.clear()
                st.rerun()

        with c2:
            if st.button("取消新增", use_container_width=True):
                st.session_state.pending_entry = None
                st.info("已取消新增。")
                st.rerun()


# --- TAB 2: 我的紀錄 ---
with tab2:
    st.header(f"📝 {current_user} 的記帳紀錄")

    if not df.empty and "User" in df.columns:
        my_df = df[
            (df["User"] == current_user) &
            (df["Status"] != "作廢")
        ].copy()

        if my_df.empty:
            st.info("您目前還沒有輸入過任何資料。")
        else:
            st.write("👇 **請直接在下方表格中，點擊您要修改的那一列：**")

            my_df_sorted = my_df.sort_values(by="Date", ascending=False).reset_index(drop=True)

            event = st.dataframe(
                my_df_sorted[["Date", "Category", "Amount", "Note"]],
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row"
            )

            selected_rows = event.selection.rows

            if selected_rows:
                st.markdown("---")
                st.subheader("✏️ 編輯選取的資料")

                selected_index = selected_rows[0]
                target_row = my_df_sorted.iloc[selected_index]
                row_id = target_row["row_id"]

                c1, c2 = st.columns(2)

                with c1:
                    edit_date = st.date_input("修改日期", target_row["Date"], key="u_date")
                    cat_idx = categories.index(target_row["Category"]) if target_row["Category"] in categories else 0
                    edit_category = st.selectbox("修改類別", categories, index=cat_idx, key="u_cat")

                with c2:
                    edit_amount = st.number_input(
                        "修改金額",
                        min_value=0,
                        step=100,
                        value=int(target_row["Amount"]),
                        key="u_amt"
                    )
                    edit_note = st.text_input("修改備註", str(target_row["Note"]), key="u_note")

                btn1, btn2 = st.columns(2)

                with btn1:
                    if st.button("💾 儲存修改內容", use_container_width=True, type="primary"):
                        if edit_amount <= 0:
                            st.error("金額必須大於 0")
                        else:
                            with st.spinner("正在更新雲端資料庫..."):
                                update_entry_in_cloud(
                                    row_id,
                                    edit_date,
                                    edit_category,
                                    edit_amount,
                                    edit_note,
                                    current_user
                                )

                            st.success("✅ 修改成功！")
                            st.cache_data.clear()
                            st.rerun()

                with btn2:
                    if st.button("作廢此筆", use_container_width=True):
                        with st.spinner("正在作廢..."):
                            void_entry_in_cloud(row_id, current_user)

                        st.success("✅ 此筆資料已作廢！")
                        st.cache_data.clear()
                        st.rerun()

            else:
                st.info("👆 點擊上方表格中的任意一筆紀錄，即可展開修改選單。")
    else:
        st.warning("資料庫結構正在更新，或目前無資料。")


# --- TAB 3: 總報表 ---
with tab3:
    if is_admin:
        active_df = df[df["Status"] != "作廢"].copy()

        if active_df.empty:
            st.info("目前沒有正常資料。")
        else:
            active_df["YearMonth"] = active_df["Date"].dt.strftime("%Y-%m")

            total_exp = active_df["Amount"].sum()
            unique_months = active_df["YearMonth"].nunique()
            avg_monthly = total_exp / unique_months if unique_months > 0 else total_exp

            current_ym = datetime.now().strftime("%Y-%m")
            last_month = (pd.Timestamp(datetime.now()) - pd.DateOffset(months=1)).strftime("%Y-%m")

            current_month_total = active_df[active_df["YearMonth"] == current_ym]["Amount"].sum()
            last_month_total = active_df[active_df["YearMonth"] == last_month]["Amount"].sum()
            month_delta = current_month_total - last_month_total

            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("💰 歷史總支出", f"${total_exp:,.0f}")
            kpi2.metric("📅 平均月支出", f"${avg_monthly:,.0f}")
            kpi3.metric(
                f"📆 本月支出 ({current_ym})",
                f"${current_month_total:,.0f}",
                delta=f"{month_delta:,.0f} vs 上月"
            )

            st.markdown("---")

            col1, col2 = st.columns(2)

            with col1:
                cat_sum = active_df.groupby("Category")["Amount"].sum().reset_index()
                fig_pie = px.pie(cat_sum, values="Amount", names="Category", hole=0.4)
                fig_pie.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(fig_pie, use_container_width=True)

            with col2:
                monthly_total = active_df.groupby("YearMonth")["Amount"].sum().reset_index()
                fig_line = px.line(monthly_total, x="YearMonth", y="Amount", markers=True)
                fig_line.update_xaxes(type="category")
                st.plotly_chart(fig_line, use_container_width=True)

            st.markdown("---")

            monthly_cat = active_df.groupby(["YearMonth", "Category"])["Amount"].sum().reset_index()
            chart_type = st.radio(
                "圖表類型：",
                ["折線圖 (比較趨勢)", "堆疊長條圖 (比較結構)"],
                horizontal=True
            )

            if "折線圖" in chart_type:
                fig_multi = px.line(monthly_cat, x="YearMonth", y="Amount", color="Category", markers=True)
            else:
                fig_multi = px.bar(monthly_cat, x="YearMonth", y="Amount", color="Category")

            fig_multi.update_xaxes(type="category")
            st.plotly_chart(fig_multi, use_container_width=True)

            st.markdown("---")
            st.subheader("異常與提醒")

            dup_df = get_duplicate_groups(active_df)
            current_month_df = active_df[active_df["YearMonth"] == current_ym].copy()
            large_df = current_month_df[current_month_df["Amount"] >= 10000].sort_values(by="Amount", ascending=False)
            empty_note_df = active_df[active_df["Note"].astype(str).str.strip() == ""].sort_values(by="Date", ascending=False)

            r1, r2, r3 = st.columns(3)
            r1.metric("可能重複紀錄", f"{len(dup_df)} 筆")
            r2.metric("本月大額支出", f"{len(large_df)} 筆")
            r3.metric("備註空白紀錄", f"{len(empty_note_df)} 筆")

            with st.expander("查看可能重複紀錄"):
                if dup_df.empty:
                    st.info("目前沒有偵測到可能重複紀錄。")
                else:
                    st.dataframe(
                        dup_df[["Date", "User", "Category", "Amount", "Note"]],
                        use_container_width=True
                    )

            with st.expander("查看本月大額支出"):
                if large_df.empty:
                    st.info("本月沒有超過 10,000 的支出。")
                else:
                    st.dataframe(
                        large_df[["Date", "User", "Category", "Amount", "Note"]],
                        use_container_width=True
                    )

            with st.expander("查看備註空白紀錄"):
                if empty_note_df.empty:
                    st.info("目前沒有備註空白紀錄。")
                else:
                    st.dataframe(
                        empty_note_df[["Date", "User", "Category", "Amount", "Note"]],
                        use_container_width=True
                    )

    else:
        st.warning("🔒 這是公司機密數據，請輸入管理員密碼解鎖。")


# --- TAB 4: 總明細與管理 ---
with tab4:
    if is_admin:
        st.subheader("👑 管理員專用：修改 / 作廢歷史資料")

        if not df.empty:
            st.write("📌 **篩選條件設定：**")

            c_filter1, c_filter2, c_filter3 = st.columns(3)

            with c_filter1:
                filter_cat = st.selectbox("📂 依類別篩選", ["全部"] + categories)

            with c_filter2:
                valid_users = employees[1:]
                filter_user = st.selectbox("👤 依填表人篩選", ["全部"] + valid_users)

            with c_filter3:
                filter_status = st.selectbox("狀態篩選", ["正常", "作廢", "全部"])

            admin_df_filtered = df.copy()

            if filter_cat != "全部":
                admin_df_filtered = admin_df_filtered[admin_df_filtered["Category"] == filter_cat]

            if filter_user != "全部":
                admin_df_filtered = admin_df_filtered[admin_df_filtered["User"] == filter_user]

            if filter_status != "全部":
                admin_df_filtered = admin_df_filtered[admin_df_filtered["Status"] == filter_status]

            admin_df_sorted = admin_df_filtered.sort_values(by="Date", ascending=False).reset_index(drop=True)

            st.markdown("---")

            if admin_df_sorted.empty:
                st.info("⚠️ 找不到符合此篩選條件的紀錄。")
            else:
                st.write("👇 **請直接在下方表格中，點擊您要修改的那一列：**")

                admin_event = st.dataframe(
                    admin_df_sorted[["Date", "User", "Category", "Amount", "Note", "Status"]],
                    use_container_width=True,
                    on_select="rerun",
                    selection_mode="single-row"
                )

                admin_selected_rows = admin_event.selection.rows

                if admin_selected_rows:
                    st.markdown("---")
                    st.subheader("✏️ 編輯選取的資料")

                    target_row = admin_df_sorted.iloc[admin_selected_rows[0]]
                    row_id = target_row["row_id"]

                    c1, c2 = st.columns(2)

                    with c1:
                        edit_date = st.date_input("日期", target_row["Date"], key="a_date")
                        cat_idx = categories.index(target_row["Category"]) if target_row["Category"] in categories else 0
                        edit_category = st.selectbox("類別", categories, index=cat_idx, key="a_cat")

                        user_idx = valid_users.index(target_row["User"]) if target_row["User"] in valid_users else 0
                        edit_user = st.selectbox("填表人", valid_users, index=user_idx, key="a_user")

                    with c2:
                        edit_amount = st.number_input(
                            "金額",
                            min_value=0,
                            step=100,
                            value=int(target_row["Amount"]),
                            key="a_amt"
                        )
                        edit_note = st.text_input("備註", str(target_row["Note"]), key="a_note")

                    btn1, btn2 = st.columns(2)

                    with btn1:
                        if st.button("💾 強制儲存修改", use_container_width=True, type="primary"):
                            if edit_amount <= 0:
                                st.error("金額必須大於 0")
                            else:
                                with st.spinner("正在更新..."):
                                    update_entry_in_cloud(
                                        row_id,
                                        edit_date,
                                        edit_category,
                                        edit_amount,
                                        edit_note,
                                        edit_user
                                    )

                                st.success("✅ 修改成功！")
                                st.cache_data.clear()
                                st.rerun()

                    with btn2:
                        if target_row["Status"] == "作廢":
                            st.info("此筆資料已作廢。")
                        else:
                            if st.button("作廢此筆", use_container_width=True):
                                with st.spinner("正在作廢..."):
                                    void_entry_in_cloud(row_id, current_user)

                                st.success("✅ 此筆資料已作廢！")
                                st.cache_data.clear()
                                st.rerun()
                else:
                    st.info("👆 點擊上方表格中的任意一筆紀錄，即可展開修改選單。")
        else:
            st.info("目前沒有資料。")

        st.markdown("---")
        st.subheader("🏷️ 管理支出類別")
        st.caption("在此新增的類別會永久保存於雲端，所有員工皆可選擇。")

        st.write(f"**目前共有 {len(categories)} 個類別：**")
        st.write("、".join(categories))

        with st.form("add_cat_form", clear_on_submit=True):
            c1, c2 = st.columns([3, 1])

            with c1:
                new_cat = st.text_input("新增類別名稱", placeholder="例如：教育訓練費")

            with c2:
                st.write("")
                st.write("")
                submit_cat = st.form_submit_button("➕ 新增類別", use_container_width=True)

            if submit_cat:
                if not new_cat.strip():
                    st.error("❌ 類別名稱不能為空！")
                elif new_cat.strip() in categories:
                    st.error("❌ 此類別已經存在了！")
                else:
                    with st.spinner("正在將類別同步至雲端..."):
                        add_category_to_cloud(new_cat)

                    st.success(f"✅ 成功新增類別：{new_cat.strip()}")
                    st.cache_data.clear()
                    st.rerun()

    else:
        st.warning("🔒 需要管理員權限")
