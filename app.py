        st.markdown("---")
        st.subheader("管理細分類與付款對象")

        st.caption("這裡新增後，員工記帳時會出現在對應類別的下拉選單。")

        if not options_df.empty:
            st.dataframe(options_df, use_container_width=True)

        with st.form("add_option_form", clear_on_submit=True):
            o1, o2, o3 = st.columns(3)

            with o1:
                option_category = st.selectbox("主類別", categories, key="option_category")

            existing_subcategories = sorted([
                v for v in options_df[
                    options_df["Category"] == option_category
                ]["SubCategory"].dropna().astype(str).str.strip().unique()
                if v
            ])

            subcategory_choices = ["新增細分類"] + existing_subcategories

            with o2:
                subcategory_mode = st.selectbox(
                    "細分類",
                    subcategory_choices,
                    key="subcategory_mode"
                )

                if subcategory_mode == "新增細分類":
                    option_subcategory = st.text_input(
                        "新增細分類名稱",
                        placeholder="例如：貸款、廣告投放、包材"
                    )
                else:
                    option_subcategory = subcategory_mode
                    st.caption(f"已選擇：{option_subcategory}")

            with o3:
                option_vendor = st.text_input(
                    "付款對象 / 廠商",
                    placeholder="例如：國泰世華銀行、Meta、某供應商"
                )

            submit_option = st.form_submit_button("新增選項")

            if submit_option:
                option_category_clean = option_category.strip()
                option_subcategory_clean = option_subcategory.strip()
                option_vendor_clean = option_vendor.strip()

                if not option_category_clean:
                    st.error("請選擇主類別。")
                elif not option_subcategory_clean and not option_vendor_clean:
                    st.error("細分類與付款對象至少要填一個。")
                else:
                    duplicate_option = options_df[
                        (options_df["Category"] == option_category_clean) &
                        (options_df["SubCategory"] == option_subcategory_clean) &
                        (options_df["Vendor"] == option_vendor_clean)
                    ]

                    if not duplicate_option.empty:
                        st.error("這組選項已經存在。")
                    else:
                        with st.spinner("正在新增選項..."):
                            add_category_option_to_cloud(
                                option_category_clean,
                                option_subcategory_clean,
                                option_vendor_clean
                            )

                        st.success("選項已新增。")
                        st.cache_data.clear()
                        st.rerun()
