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

# --- 2. 視覺風格 ---
st.markdown("""
<style>
.stApp {
    background: #eef4f1;
}
.block-container {
    padding-top: 2rem;
}
[data-testid="stSidebar"] {
    background: #f8fbf8;
}
div[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #edf1ee;
    border-radius: 18px;
    padding: 18px 20px;
    box-shadow: 0 8px 28px rgba(36, 54, 44, 0.06);
}
div[data-testid="stMetric"] label {
    color: #6b756f;
}
div[data-testid="stMetricValue"] {
    color: #141a17;
}
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
}
.stTabs [data-baseweb="tab"] {
    background: #ffffff;
    border-radius: 999px;
    padding: 10px 18px;
}
.stTabs [aria-selected="true"] {
    background: #dff56f;
}
div[data-testid="stExpander"] {
    background: #ffffff;
    border: 1px solid #edf1ee;
    border-radius: 16px;
}
</style>
""", unsafe_allow_html=True)

PLOTLY_TEMPLATE = "plotly_white"
COLOR_SEQUENCE = ["#c8f7df", "#dff56f", "#9bd8c6", "#f7d774", "#b8c8ff", "#ffc6d0", "#c9b8ff", "#a8e6cf"]

# --- 3. 連線與資料處理 ---
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


def style_fig(fig, height=380):
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial", color="#18201b"),
        margin=dict(l=20, r=20, t=50, b=30),
        colorway=COLOR_SEQUENCE,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e7eee9")
    return fig


def get_or_create_worksheet(spreadsheet, title, rows="200", cols="10"):
    try:
        return spreadsheet.worksheet(title)
    except Exception:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def load_data():
    spreadsheet = connect_to_gsheets()
    sheet = spreadsheet.sheet1

    expected_columns = [
        "Date", "Category", "SubCategory", "Vendor", "Amount", "Note", "User",
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
                df[col] = "正常" if col == "Status" else ""

        df["Status"] = df["Status"].replace("", "正常").fillna("正常")
        df["SubCategory"] = df["SubCategory"].fillna("").astype(str)
        df["Vendor"] = df["Vendor"].fillna("").astype(str)
        df["Note"] = df["Note"].fillna("").astype(str)

        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
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
        "進貨成本", "運費", "行銷廣告", "交通差旅", "辦公雜項",
        "租金貸款", "營業稅＆其他稅務", "交際費", "軟體系統使用費", "薪資人事費"
    ]

    try:
        cat_sheet = spreadsheet.worksheet("Categories")
        cats = cat_sheet.col_values(1)
        cats = [c.strip() for c in cats if c.strip()]
        return cats if cats else default_cats
    except Exception:
        try:
            cat_sheet = spreadsheet.add_worksheet(title="Categories", rows="100", cols="1")
            cat_sheet.append_rows([[c] for c in default_cats])
        except Exception:
            pass
        return default_cats


@st.cache_data
def load_category_options():
    spreadsheet = connect_to_gsheets()
    default_rows = [
        ["行銷廣告", "印刷製作", "春聯製作"],
        ["行銷廣告", "廣告投放", "Meta"],
        ["行銷廣告", "廣告投放", "Google"],
        ["進貨成本", "商品進貨", ""],
        ["進貨成本", "包材", ""],
        ["租金貸款", "貸款", ""],
        ["租金貸款", "房租", ""],
        ["運費", "郵寄", "郵局"],
        ["運費", "快遞", "黑貓宅急便"],
        ["軟體系統使用費", "設計工具", "Canva"],
    ]

    try:
        opt_sheet = get_or_create_worksheet(spreadsheet, "CategoryOptions", rows="300", cols="3")
        values = opt_sheet.get_all_values()

        if not values:
            opt_sheet.append_row(["Category", "SubCategory", "Vendor"])
            opt_sheet.append_rows(default_rows)
            values = opt_sheet.get_all_values()

        header = values[0]
        data = values[1:]

        df_opt = pd.DataFrame(data, columns=header)

        for col in ["Category", "SubCategory", "Vendor"]:
            if col not in df_opt.columns:
                df_opt[col] = ""

        df_opt = df_opt[["Category", "SubCategory", "Vendor"]].fillna("")
        df_opt = df_opt.apply(lambda col: col.astype(str).str.strip())
        df_opt = df_opt[df_opt["Category"] != ""]

        return df_opt

    except Exception:
        return pd.DataFrame(default_rows, columns=["Category", "SubCategory", "Vendor"])


def add_category_to_cloud(new_cat):
    spreadsheet = connect_to_gsheets()
    cat_sheet = get_or_create_worksheet(spreadsheet, "Categories", rows="100", cols="1")
    cat_sheet.append_row([new_cat.strip()])


def add_category_option_to_cloud(category, subcategory, vendor):
    spreadsheet = connect_to_gsheets()
    opt_sheet = get_or_create_worksheet(spreadsheet, "CategoryOptions", rows="300", cols="3")

    values = opt_sheet.get_all_values()
    if not values:
        opt_sheet.append_row(["Category", "SubCategory", "Vendor"])

    opt_sheet.append_row([category.strip(), subcategory.strip(), vendor.strip()])


def get_subcategory_options(options_df, category):
    values = options_df[options_df["Category"] == category]["SubCategory"].dropna().astype(str).str.strip()
    values = sorted([v for v in values.unique() if v])
    return ["未分類"] + values


def get_vendor_options(options_df, category, subcategory):
    filtered = options_df[options_df["Category"] == category].copy()

    if subcategory and subcategory != "未分類":
        filtered = filtered[filtered["SubCategory"] == subcategory]

    values = filtered["Vendor"].dropna().astype(str).str.strip()
    values = sorted([v for v in values.unique() if v])
    return ["未指定"] + values


def normalize_empty_choice(value):
    if value in ["未分類", "未指定"]:
        return ""
    return value


def save_entry_to_cloud(date, category, subcategory, vendor, amount, note, user):
    spreadsheet = connect_to_gsheets()
    sheet = spreadsheet.sheet1

    date_str = date.strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sheet.append_row([
        date_str,
        category,
        subcategory,
        vendor,
        amount,
        note,
        user,
        "正常",
        now_str,
        now_str,
        "",
        ""
    ])


def update_entry_in_cloud(row_id, date, category, subcategory, vendor, amount, note, user):
    spreadsheet = connect_to_gsheets()
    sheet = spreadsheet.sheet1

    date_str = date.strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cell_list = sheet.range(f"A{row_id}:G{row_id}")
    values = [date_str, category, subcategory, vendor, amount, note, user]

    for i, val in enumerate(values):
        cell_list[i].value = val

    sheet.update_cells(cell_list)
    sheet.update_cell(int(row_id), 10, now_str)


def void_entry_in_cloud(row_id, current_user):
    spreadsheet = connect_to_gsheets()
    sheet = spreadsheet.sheet1

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sheet.update_cell(int(row_id), 8, "作廢")
    sheet.update_cell(int(row_id), 10, now_str)
    sheet.update_cell(int(row_id), 11, now_str)
    sheet.update_cell(int(row_id), 12, current_user)


def find_duplicate_entries(df, date, category, subcategory, vendor, amount, user):
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
        (active_df["SubCategory"].fillna("") == subcategory) &
        (active_df["Vendor"].fillna("") == vendor) &
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
    dup_cols = ["DateStr", "User", "Category", "SubCategory", "Vendor", "Amount"]
    dup_mask = active_df.duplicated(subset=dup_cols, keep=False)

    return active_df[dup_mask].sort_values(by=["Date", "User", "Category", "Amount"])


def render_category_deep_dive(active_df, category_name):
    target_df = active_df[active_df["Category"] == category_name].copy()

    st.subheader(f"{category_name}分析")

    if target_df.empty:
        st.info(f"目前沒有「{category_name}」資料。")
        return

    total = target_df["Amount"].sum()
    all_total = active_df["Amount"].sum()
    ratio = total / all_total if all_total else 0

    m1, m2, m3 = st.columns(3)
    m1.metric(f"{category_name}總支出", f"${total:,.0f}")
    m2.metric("佔總支出比例", f"{ratio:.1%}")
    m3.metric("資料筆數", f"{len(target_df)} 筆")

    c1, c2 = st.columns(2)

    with c1:
        sub_df = target_df.copy()
        sub_df["SubCategoryDisplay"] = sub_df["SubCategory"].replace("", "未分類")
        sub_sum = sub_df.groupby("SubCategoryDisplay")["Amount"].sum().reset_index().sort_values("Amount", ascending=False)

        fig = px.pie(
            sub_sum,
            names="SubCategoryDisplay",
            values="Amount",
            hole=0.55,
            title=f"{category_name}細分類佔比",
            color_discrete_sequence=COLOR_SEQUENCE
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(style_fig(fig), use_container_width=True)

    with c2:
        vendor_df = target_df.copy()
        vendor_df["VendorDisplay"] = vendor_df["Vendor"].replace("", "未指定")
        vendor_sum = vendor_df.groupby("VendorDisplay")["Amount"].sum().reset_index().sort_values("Amount", ascending=False).head(12)

        fig = px.bar(
            vendor_sum,
            x="Amount",
            y="VendorDisplay",
            orientation="h",
            title=f"{category_name}付款對象 / 廠商排行",
            color="Amount",
            color_continuous_scale=["#c8f7df", "#dff56f"]
        )
        fig.update_layout(yaxis=dict(categoryorder="total ascending"), coloraxis_showscale=False)
        st.plotly_chart(style_fig(fig), use_container_width=True)

    monthly = target_df.copy()
    monthly["YearMonth"] = monthly["Date"].dt.strftime("%Y-%m")
    monthly_sum = monthly.groupby("YearMonth")["Amount"].sum().reset_index()

    fig = px.line(
        monthly_sum,
        x="YearMonth",
        y="Amount",
        markers=True,
        title=f"{category_name}每月趨勢",
        color_discrete_sequence=["#9bd8c6"]
    )
    fig.update_xaxes(type="category")
    st.plotly_chart(style_fig(fig, height=340), use_container_width=True)


# --- 4. 初始化資料 ---
df = load_data()
categories = load_categories()
options_df = load_category_options()

option_categories = sorted(options_df["Category"].dropna().astype(str).str.strip().unique().tolist())
categories = sorted(list(dict.fromkeys(categories + option_categories)))

employees = ["選擇您的名字...", "Yuri", "YT", "NiNi"]

if "pending_entry" not in st.session_state:
    st.session_state.pending_entry = None

# --- 5. 側邊欄 ---
with st.sidebar:
    st.title("Bluebulous")
    st.caption("財務戰情室")

    current_user = st.selectbox("請問您是哪一位？", employees)

    st.markdown("---")
    st.subheader("管理員專區")

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
        st.success("管理員模式已啟動")

        if st.button("強制重新整理資料"):
            st.cache_data.clear()
            st.rerun()
    elif admin_input:
        st.error("密碼錯誤")

# --- 6. 主畫面 ---
st.title("Bluebulous 記帳系統")

if current_user == "選擇您的名字...":
    st.info("請先在左側選單選擇您的名字，才能開始記帳。")
    st.stop()

st.write(f"您好，**{current_user}**。")

tab1, tab2, tab3, tab4 = st.tabs([
    "新增支出",
    "我的紀錄",
    "總報表",
    "總明細與管理"
])

# --- TAB 1: 新增支出 ---
with tab1:
    st.header("新增一筆紀錄")

    with st.form("cloud_entry", clear_on_submit=True):
        d = st.date_input("日期", datetime.today())
        c = st.selectbox("類別", categories)

        sub_options = get_subcategory_options(options_df, c)
        sub_choice = st.selectbox("細分類", sub_options)

        vendor_options = get_vendor_options(options_df, c, sub_choice)
        vendor_choice = st.selectbox("付款對象 / 廠商", vendor_options)

        a = st.number_input("金額", min_value=0, step=100)
        n = st.text_input("備註")

        submitted = st.form_submit_button("上傳資料")

        if submitted:
            sub_value = normalize_empty_choice(sub_choice)
            vendor_value = normalize_empty_choice(vendor_choice)

            if a <= 0:
                st.error("金額必須大於 0")
            else:
                duplicates = find_duplicate_entries(df, d, c, sub_value, vendor_value, a, current_user)

                if not duplicates.empty:
                    st.session_state.pending_entry = {
                        "date": d,
                        "category": c,
                        "subcategory": sub_value,
                        "vendor": vendor_value,
                        "amount": a,
                        "note": n,
                        "user": current_user
                    }
                    st.warning("可能已有相同紀錄，請確認是否仍要新增。")
                else:
                    with st.spinner("正在寫入雲端..."):
                        save_entry_to_cloud(d, c, sub_value, vendor_value, a, n, current_user)

                    st.success("資料已儲存。")
                    st.cache_data.clear()
                    st.rerun()

    if st.session_state.pending_entry:
        pending = st.session_state.pending_entry
        duplicates = find_duplicate_entries(
            df,
            pending["date"],
            pending["category"],
            pending["subcategory"],
            pending["vendor"],
            pending["amount"],
            pending["user"]
        )

        st.markdown("---")
        st.warning("系統找到可能重複的紀錄：")

        if not duplicates.empty:
            st.dataframe(
                duplicates[["Date", "Category", "SubCategory", "Vendor", "Amount", "Note", "User"]],
                use_container_width=True
            )

        c1, c2 = st.columns(2)

        with c1:
            if st.button("確認仍要新增", type="primary", use_container_width=True):
                with st.spinner("正在寫入雲端..."):
                    save_entry_to_cloud(
                        pending["date"],
                        pending["category"],
                        pending["subcategory"],
                        pending["vendor"],
                        pending["amount"],
                        pending["note"],
                        pending["user"]
                    )

                st.session_state.pending_entry = None
                st.success("資料已儲存。")
                st.cache_data.clear()
                st.rerun()

        with c2:
            if st.button("取消新增", use_container_width=True):
                st.session_state.pending_entry = None
                st.rerun()

# --- TAB 2: 我的紀錄 ---
with tab2:
    st.header(f"{current_user} 的記帳紀錄")

    if not df.empty and "User" in df.columns:
        my_df = df[
            (df["User"] == current_user) &
            (df["Status"] != "作廢")
        ].copy()

        if my_df.empty:
            st.info("您目前還沒有輸入過任何資料。")
        else:
            my_df_sorted = my_df.sort_values(by="Date", ascending=False).reset_index(drop=True)

            event = st.dataframe(
                my_df_sorted[["Date", "Category", "SubCategory", "Vendor", "Amount", "Note"]],
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row"
            )

            selected_rows = event.selection.rows

            if selected_rows:
                st.markdown("---")
                st.subheader("編輯選取的資料")

                target_row = my_df_sorted.iloc[selected_rows[0]]
                row_id = target_row["row_id"]

                c1, c2 = st.columns(2)

                with c1:
                    edit_date = st.date_input("修改日期", target_row["Date"], key="u_date")
                    cat_idx = categories.index(target_row["Category"]) if target_row["Category"] in categories else 0
                    edit_category = st.selectbox("修改類別", categories, index=cat_idx, key="u_cat")

                    edit_sub_options = get_subcategory_options(options_df, edit_category)
                    current_sub = target_row["SubCategory"] if target_row["SubCategory"] else "未分類"
                    sub_idx = edit_sub_options.index(current_sub) if current_sub in edit_sub_options else 0
                    edit_subcategory_choice = st.selectbox("修改細分類", edit_sub_options, index=sub_idx, key="u_sub")

                    edit_vendor_options = get_vendor_options(options_df, edit_category, edit_subcategory_choice)
                    current_vendor = target_row["Vendor"] if target_row["Vendor"] else "未指定"
                    vendor_idx = edit_vendor_options.index(current_vendor) if current_vendor in edit_vendor_options else 0
                    edit_vendor_choice = st.selectbox("修改付款對象 / 廠商", edit_vendor_options, index=vendor_idx, key="u_vendor")

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
                    if st.button("儲存修改內容", use_container_width=True, type="primary"):
                        if edit_amount <= 0:
                            st.error("金額必須大於 0")
                        else:
                            with st.spinner("正在更新雲端資料庫..."):
                                update_entry_in_cloud(
                                    row_id,
                                    edit_date,
                                    edit_category,
                                    normalize_empty_choice(edit_subcategory_choice),
                                    normalize_empty_choice(edit_vendor_choice),
                                    edit_amount,
                                    edit_note,
                                    current_user
                                )

                            st.success("修改成功。")
                            st.cache_data.clear()
                            st.rerun()

                with btn2:
                    if st.button("作廢此筆", use_container_width=True):
                        with st.spinner("正在作廢..."):
                            void_entry_in_cloud(row_id, current_user)

                        st.success("此筆資料已作廢。")
                        st.cache_data.clear()
                        st.rerun()
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
            active_df["Year"] = active_df["Date"].dt.year

            now = datetime.now()
            current_year = now.year
            current_ym = now.strftime("%Y-%m")
            last_month = (pd.Timestamp(now) - pd.DateOffset(months=1)).strftime("%Y-%m")

            current_year_df = active_df[active_df["Year"] == current_year].copy()
            current_month_df = active_df[active_df["YearMonth"] == current_ym].copy()

            total_exp = active_df["Amount"].sum()
            current_year_total = current_year_df["Amount"].sum()
            year_months = current_year_df["YearMonth"].nunique()
            current_year_avg = current_year_total / year_months if year_months > 0 else 0

            current_month_total = current_month_df["Amount"].sum()
            last_month_total = active_df[active_df["YearMonth"] == last_month]["Amount"].sum()
            month_delta = current_month_total - last_month_total

            category_this_month = current_month_df.groupby("Category")["Amount"].sum().reset_index()
            if not category_this_month.empty:
                top_month_category = category_this_month.sort_values("Amount", ascending=False).iloc[0]
                top_category_text = f"{top_month_category['Category']} ${top_month_category['Amount']:,.0f}"
            else:
                top_category_text = "無資料"

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("歷史總支出", f"${total_exp:,.0f}")
            kpi2.metric(f"{current_year} 年總支出", f"${current_year_total:,.0f}")
            kpi3.metric("今年平均月支出", f"${current_year_avg:,.0f}")
            kpi4.metric("本月支出", f"${current_month_total:,.0f}", delta=f"{month_delta:,.0f} vs 上月")

            st.caption(f"本月最大支出類別：{top_category_text}")

            st.markdown("---")

            col1, col2 = st.columns(2)

            with col1:
                cat_sum = active_df.groupby("Category")["Amount"].sum().reset_index().sort_values("Amount", ascending=False)
                fig = px.bar(
                    cat_sum,
                    x="Amount",
                    y="Category",
                    orientation="h",
                    title="類別支出排行",
                    color="Amount",
                    color_continuous_scale=["#c8f7df", "#dff56f"]
                )
                fig.update_layout(yaxis=dict(categoryorder="total ascending"), coloraxis_showscale=False)
                st.plotly_chart(style_fig(fig), use_container_width=True)

            with col2:
                fig = px.pie(
                    cat_sum,
                    values="Amount",
                    names="Category",
                    hole=0.55,
                    title="類別支出佔比",
                    color_discrete_sequence=COLOR_SEQUENCE
                )
                fig.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(style_fig(fig), use_container_width=True)

            col3, col4 = st.columns(2)

            with col3:
                monthly_total = active_df.groupby("YearMonth")["Amount"].sum().reset_index()
                fig = px.line(
                    monthly_total,
                    x="YearMonth",
                    y="Amount",
                    markers=True,
                    title="每月總支出趨勢",
                    color_discrete_sequence=["#9bd8c6"]
                )
                fig.update_xaxes(type="category")
                st.plotly_chart(style_fig(fig), use_container_width=True)

            with col4:
                sub_df = active_df.copy()
                sub_df["SubCategoryDisplay"] = sub_df["SubCategory"].replace("", "未分類")
                sub_sum = sub_df.groupby("SubCategoryDisplay")["Amount"].sum().reset_index().sort_values("Amount", ascending=False).head(12)

                fig = px.bar(
                    sub_sum,
                    x="Amount",
                    y="SubCategoryDisplay",
                    orientation="h",
                    title="細分類支出排行",
                    color="Amount",
                    color_continuous_scale=["#c8f7df", "#dff56f"]
                )
                fig.update_layout(yaxis=dict(categoryorder="total ascending"), coloraxis_showscale=False)
                st.plotly_chart(style_fig(fig), use_container_width=True)

            st.markdown("---")

            selected_deep_category = st.selectbox(
                "選擇一個類別查看細部分析",
                categories,
                index=categories.index("行銷廣告") if "行銷廣告" in categories else 0
            )
            render_category_deep_dive(active_df, selected_deep_category)

            st.markdown("---")
            st.subheader("常用類別快速分析")

            quick1, quick2 = st.columns(2)

            with quick1:
                render_category_deep_dive(active_df, "行銷廣告")

            with quick2:
                render_category_deep_dive(active_df, "進貨成本")

            quick3, quick4 = st.columns(2)

            with quick3:
                render_category_deep_dive(active_df, "租金貸款")

            with quick4:
                render_category_deep_dive(active_df, "軟體系統使用費")

            st.markdown("---")
            st.subheader("異常與提醒")

            dup_df = get_duplicate_groups(active_df)
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
                        dup_df[["Date", "User", "Category", "SubCategory", "Vendor", "Amount", "Note"]],
                        use_container_width=True
                    )

            with st.expander("查看本月大額支出"):
                if large_df.empty:
                    st.info("本月沒有超過 10,000 的支出。")
                else:
                    st.dataframe(
                        large_df[["Date", "User", "Category", "SubCategory", "Vendor", "Amount", "Note"]],
                        use_container_width=True
                    )

            with st.expander("查看備註空白紀錄"):
                if empty_note_df.empty:
                    st.info("目前沒有備註空白紀錄。")
                else:
                    st.dataframe(
                        empty_note_df[["Date", "User", "Category", "SubCategory", "Vendor", "Amount", "Note"]],
                        use_container_width=True
                    )

    else:
        st.warning("這是公司機密數據，請輸入管理員密碼解鎖。")

# --- TAB 4: 總明細與管理 ---
with tab4:
    if is_admin:
        st.subheader("管理員專用：修改 / 作廢歷史資料")

        if not df.empty:
            st.write("篩選條件設定")

            c_filter1, c_filter2, c_filter3, c_filter4 = st.columns(4)

            with c_filter1:
                filter_cat = st.selectbox("依類別篩選", ["全部"] + categories)

            with c_filter2:
                valid_users = employees[1:]
                filter_user = st.selectbox("依填表人篩選", ["全部"] + valid_users)

            with c_filter3:
                filter_status = st.selectbox("狀態篩選", ["正常", "作廢", "全部"])

            with c_filter4:
                vendor_values = sorted([v for v in df["Vendor"].dropna().astype(str).str.strip().unique() if v])
                filter_vendor = st.selectbox("依付款對象 / 廠商篩選", ["全部"] + vendor_values)

            admin_df_filtered = df.copy()

            if filter_cat != "全部":
                admin_df_filtered = admin_df_filtered[admin_df_filtered["Category"] == filter_cat]

            if filter_user != "全部":
                admin_df_filtered = admin_df_filtered[admin_df_filtered["User"] == filter_user]

            if filter_status != "全部":
                admin_df_filtered = admin_df_filtered[admin_df_filtered["Status"] == filter_status]

            if filter_vendor != "全部":
                admin_df_filtered = admin_df_filtered[admin_df_filtered["Vendor"] == filter_vendor]

            admin_df_sorted = admin_df_filtered.sort_values(by="Date", ascending=False).reset_index(drop=True)

            st.markdown("---")

            if admin_df_sorted.empty:
                st.info("找不到符合此篩選條件的紀錄。")
            else:
                admin_event = st.dataframe(
                    admin_df_sorted[["Date", "User", "Category", "SubCategory", "Vendor", "Amount", "Note", "Status"]],
                    use_container_width=True,
                    on_select="rerun",
                    selection_mode="single-row"
                )

                admin_selected_rows = admin_event.selection.rows

                if admin_selected_rows:
                    st.markdown("---")
                    st.subheader("編輯選取的資料")

                    target_row = admin_df_sorted.iloc[admin_selected_rows[0]]
                    row_id = target_row["row_id"]

                    c1, c2 = st.columns(2)

                    with c1:
                        edit_date = st.date_input("日期", target_row["Date"], key="a_date")

                        cat_idx = categories.index(target_row["Category"]) if target_row["Category"] in categories else 0
                        edit_category = st.selectbox("類別", categories, index=cat_idx, key="a_cat")

                        edit_sub_options = get_subcategory_options(options_df, edit_category)
                        current_sub = target_row["SubCategory"] if target_row["SubCategory"] else "未分類"
                        sub_idx = edit_sub_options.index(current_sub) if current_sub in edit_sub_options else 0
                        edit_subcategory_choice = st.selectbox("細分類", edit_sub_options, index=sub_idx, key="a_sub")

                        edit_vendor_options = get_vendor_options(options_df, edit_category, edit_subcategory_choice)
                        current_vendor = target_row["Vendor"] if target_row["Vendor"] else "未指定"
                        vendor_idx = edit_vendor_options.index(current_vendor) if current_vendor in edit_vendor_options else 0
                        edit_vendor_choice = st.selectbox("付款對象 / 廠商", edit_vendor_options, index=vendor_idx, key="a_vendor")

                    with c2:
                        user_idx = valid_users.index(target_row["User"]) if target_row["User"] in valid_users else 0
                        edit_user = st.selectbox("填表人", valid_users, index=user_idx, key="a_user")

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
                        if st.button("強制儲存修改", use_container_width=True, type="primary"):
                            if edit_amount <= 0:
                                st.error("金額必須大於 0")
                            else:
                                with st.spinner("正在更新..."):
                                    update_entry_in_cloud(
                                        row_id,
                                        edit_date,
                                        edit_category,
                                        normalize_empty_choice(edit_subcategory_choice),
                                        normalize_empty_choice(edit_vendor_choice),
                                        edit_amount,
                                        edit_note,
                                        edit_user
                                    )

                                st.success("修改成功。")
                                st.cache_data.clear()
                                st.rerun()

                    with btn2:
                        if target_row["Status"] == "作廢":
                            st.info("此筆資料已作廢。")
                        else:
                            if st.button("作廢此筆", use_container_width=True):
                                with st.spinner("正在作廢..."):
                                    void_entry_in_cloud(row_id, current_user)

                                st.success("此筆資料已作廢。")
                                st.cache_data.clear()
                                st.rerun()
        else:
            st.info("目前沒有資料。")

        st.markdown("---")
        st.subheader("管理主類別")

        st.write(f"目前共有 {len(categories)} 個類別：")
        st.write("、".join(categories))

        with st.form("add_cat_form", clear_on_submit=True):
            new_cat = st.text_input("新增類別名稱", placeholder="例如：教育訓練費")
            submit_cat = st.form_submit_button("新增類別")

            if submit_cat:
                if not new_cat.strip():
                    st.error("類別名稱不能為空。")
                elif new_cat.strip() in categories:
                    st.error("此類別已經存在。")
                else:
                    with st.spinner("正在將類別同步至雲端..."):
                        add_category_to_cloud(new_cat)

                    st.success(f"成功新增類別：{new_cat.strip()}")
                    st.cache_data.clear()
                    st.rerun()

        st.markdown("---")
        st.subheader("管理細分類與付款對象")

        st.caption("這裡新增後，員工記帳時會出現在對應類別的下拉選單。")

        if not options_df.empty:
            st.dataframe(options_df, use_container_width=True)

        with st.form("add_option_form", clear_on_submit=True):
            o1, o2, o3 = st.columns(3)

            with o1:
                option_category = st.selectbox("主類別", categories, key="option_category")

            with o2:
                option_subcategory = st.text_input("細分類", placeholder="例如：貸款、廣告投放、包材")

            with o3:
                option_vendor = st.text_input("付款對象 / 廠商", placeholder="例如：國泰世華銀行、Meta、某供應商")

            submit_option = st.form_submit_button("新增選項")

            if submit_option:
                if not option_category.strip():
                    st.error("請選擇主類別。")
                elif not option_subcategory.strip() and not option_vendor.strip():
                    st.error("細分類與付款對象至少要填一個。")
                else:
                    duplicate_option = options_df[
                        (options_df["Category"] == option_category.strip()) &
                        (options_df["SubCategory"] == option_subcategory.strip()) &
                        (options_df["Vendor"] == option_vendor.strip())
                    ]

                    if not duplicate_option.empty:
                        st.error("這組選項已經存在。")
                    else:
                        with st.spinner("正在新增選項..."):
                            add_category_option_to_cloud(option_category, option_subcategory, option_vendor)

                        st.success("選項已新增。")
                        st.cache_data.clear()
                        st.rerun()

    else:
        st.warning("需要管理員權限。")
