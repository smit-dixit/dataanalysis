from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import random

import pandas as pd
import streamlit as st
import requests
from email.mime.text import MIMEText
import smtplib

import db as app_db
from reports import generate_pdf, generate_pdf_report, generate_summary_pdf


def company_header():
    st.markdown(
        """
        <div style='background-color: #f0f0f0; padding: 12px; border-radius: 8px;'>
            <div style='display: flex; align-items: center; justify-content: space-between;'>
                <h2 style='color: #333333; margin: 0;'>Madhur Dairy Canteen Management System</h2>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.image("logo.png", width=250)


def _sidebar_report_controls(conn):
    st.sidebar.title("Generate Report")
    start_date = st.sidebar.date_input("Start Date")
    end_date = st.sidebar.date_input("End Date")

    if st.sidebar.button("Generate Full Report"):
        with st.spinner("Generating PDF..."):
            pdf_bytes = generate_pdf_report(conn, start_date=start_date, end_date=end_date, summ=False)
        st.sidebar.download_button(
            label="Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf"
        )

    if st.sidebar.button("Generate Summary"):
        with st.spinner("Generating PDF..."):
            pdf_bytes = generate_pdf_report(conn, start_date=start_date, end_date=end_date, summ=True)
        st.sidebar.download_button(
            label="Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf"
        )


def plot_line_graph(data: pd.DataFrame):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))
    data = data.copy()
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")

    end_date = data["Date"].max()
    start_date = end_date - timedelta(days=6)
    data_last_week = data[(data["Date"] >= start_date) & (data["Date"] <= end_date)]

    # Redeemed is stored as bool/int.
    redeemed_counts = data_last_week.groupby("Date")["Redeemed"].sum().reset_index()
    generated_counts = data_last_week.groupby("Date").size().reset_index(name="Generated")

    ax.plot(redeemed_counts["Date"], redeemed_counts["Redeemed"], marker="o", linestyle="-", label="Redeemed")
    ax.plot(generated_counts["Date"], generated_counts["Generated"], marker="o", linestyle="-", label="Generated")

    ax.set_title("Daily Coupons Generated and Redeemed (Last Week)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Number of Coupons")
    ax.grid(True)
    ax.legend()
    ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()
    return fig


def admin_dashboard_home(conn):
    st.title("Home")

    coupons_df = app_db.load_coupon_df(conn, include_id=False)
    coupons_df["Date"] = pd.to_datetime(coupons_df["Date"], errors="coerce")

    col1, col2 = st.columns([0.25, 1])
    with col1:
        st.write("## Coupons Overview")
        end_date = coupons_df["Date"].max()
        start_date = end_date - timedelta(days=6)
        last_week_data = coupons_df[(coupons_df["Date"] >= start_date) & (coupons_df["Date"] <= end_date)]

        generated_total = int(last_week_data.shape[0])
        redeemed_total = float(last_week_data["Redeemed"].sum()) if "Redeemed" in last_week_data.columns else 0.0

        st.metric(label="Coupons Generated", value=generated_total)
        st.metric(label="Coupons Redeemed", value=redeemed_total)
        st.metric(label="No. of Employees", value=3)

    with col2:
        st.write("## Daily Coupons Redeemed (Past Week)")
        fig = plot_line_graph(coupons_df)
        st.pyplot(fig)


def admin_dashboard(conn, config):
    st.sidebar.write("Welcome to the Admin Dashboard")
    page = st.sidebar.radio(
        "Select Page", ["Home", "User Management", "Employee Management", "Menu Management", "Support"]
    )

    # Common report area
    st.sidebar.divider()
    _sidebar_report_controls(conn)

    footer_html = """<div style='text-align: center;'><p>© 2024 Madhur Dairy | All Rights Reserved</p></div>"""
    st.sidebar.markdown(footer_html, unsafe_allow_html=True)

    if page == "Home":
        admin_dashboard_home(conn)
        return

    if page == "User Management":
        st.title("User Management")
        if "usernames" not in st.session_state:
            st.session_state.usernames = pd.DataFrame(config["credentials"]["usernames"]).T

        edited_users = st.data_editor(st.session_state.usernames, num_rows="dynamic")

        def hash_password(password):
            return hashlib.sha256(password.encode()).hexdigest()

        if st.button("Save", key="unique5"):
            for index, row in edited_users.iterrows():
                if row["password"] != edited_users.loc[index, "password"]:
                    row["password"] = hash_password(row["password"])

            new_users = edited_users.index.difference(st.session_state.usernames.index)
            if not new_users.empty:
                for user in new_users:
                    config["credentials"]["usernames"][user] = edited_users.loc[user].to_dict()

            config["credentials"]["usernames"] = edited_users.to_dict(orient="index")
            # Persist config.yaml (auth remains YAML-based)
            import yaml

            with open("config.yaml", "w") as f:
                yaml.dump(config, f)

            st.success("Users saved.")
        return

    if page == "Employee Management":
        st.title("Employee Management")
        dfm = app_db.load_employee_df(conn, include_id=False)
        edited_df = st.data_editor(
            dfm,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Mobile No.": st.column_config.NumberColumn(format="%f"),
                "Employee Code": st.column_config.NumberColumn(format="%f"),
            },
        )
        if st.button("Save", key="unique4"):
            app_db.replace_table_from_df(conn, "employee", edited_df)
            st.success("Changes Saved")

        df_menu = app_db.load_email_df(conn, include_id=False)
        edited_menu = st.data_editor(
            df_menu,
            num_rows="dynamic",
            use_container_width=True,
            column_config={"Personal No": st.column_config.NumberColumn(format="%f")},
        )
        if st.button("Save", key="unique5"):
            app_db.replace_table_from_df(conn, "email", edited_menu)
            st.success("Email details saved.")

        st.info("Upload controls were removed in this refactor; edit & save updates persist to SQLite.")
        return

    if page == "Menu Management":
        st.title("Canteen Menu")
        df_menu = app_db.load_menu_df(conn, include_id=False)
        edited_menu = st.data_editor(df_menu, num_rows="dynamic")
        if st.button("Save", key="unique3"):
            app_db.replace_table_from_df(conn, "menu", edited_menu)
            st.success("Menu saved.")

        df_price = app_db.load_price_df(conn, include_id=False)
        edited_price = st.data_editor(df_price, num_rows="dynamic")
        if st.button("Save", key="unique4"):
            app_db.replace_table_from_df(conn, "price", edited_price)
            st.success("Price list saved.")
        return

    if page == "Support":
        st.title("Support")
        issue_name = st.text_input("Name:")
        issue_email = st.text_input("Contact Email:")
        issue_number = st.text_input("Phone number:")
        issue = st.text_area("Describe your issue:")

        if st.button("Submit"):
            if issue and issue_name and issue_email and issue_number:
                st.success("Your request has been submitted successfully!")
            else:
                st.error("Please fill in both issue description and contact information.")


def user_dashboard(conn):
    st.write("Welcome to the Timekeeper Dashboard")

    st.sidebar.title("Generate Report")
    start_date = st.sidebar.date_input("Start Date")
    end_date = st.sidebar.date_input("End Date")

    if st.sidebar.button("Generate Full Report"):
        with st.spinner("Generating PDF..."):
            pdf_bytes = generate_pdf_report(conn, start_date=start_date, end_date=end_date, summ=False)
        st.sidebar.download_button(label="Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf")

    if st.sidebar.button("Generate Summary"):
        with st.spinner("Generating PDF..."):
            pdf_bytes = generate_pdf_report(conn, start_date=start_date, end_date=end_date, summ=True)
        st.sidebar.download_button(label="Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf")

    menu_df = app_db.load_menu_df(conn, include_id=False)
    employee_df = app_db.load_employee_df(conn, include_id=False)

    def safe_phone_to_str(value):
        if value is None:
            return None
        phone_num = pd.to_numeric(value, errors="coerce")
        if pd.isna(phone_num):
            return None
        return str(int(phone_num))

    employee_codes = (
        pd.to_numeric(employee_df["Employee Code"], errors="coerce").dropna().astype(int).tolist()
    )
    if not employee_codes:
        st.error("No valid employee codes found in employee table.")
        return

    selected_employee_code = st.selectbox("Select Employee Code:", employee_codes)
    employee_info = employee_df[employee_df["Employee Code"] == selected_employee_code]
    if employee_info.empty:
        st.error("Employee details not found.")
        return

    employee_name = employee_info.iloc[0]["Employee Name"]
    employee_mobile = employee_info.iloc[0]["Mobile No."]

    current_date = datetime.now().strftime("%Y-%m-%d")

    coupon_df = app_db.load_coupon_df(conn, include_id=False)
    if not coupon_df.empty:
        ordered_items_today = coupon_df[
            (coupon_df["Employee code"] == selected_employee_code) & (coupon_df["Date"] == current_date)
        ]["Type of dish"].tolist()
    else:
        ordered_items_today = []

    menu_items = menu_df[~menu_df["Item"].isin(ordered_items_today)]["Item"].tolist()
    if not menu_items:
        st.warning("No menu items available for the selected employee today.")
        return

    selected_items = st.selectbox("Select items from the menu:", menu_items)

    item_data = menu_df.loc[menu_df["Item"] == selected_items]
    if item_data.empty:
        st.error("Selected menu item not found.")
        return

    price = float(item_data["Price"].iloc[0])
    discount = float(item_data["Discount"].iloc[0])
    total_price = price - discount

    st.subheader("Bill")
    st.write(f"**Selected Item:** {selected_items}")
    st.write(f"**Employee Name:** {employee_name}")
    st.write(f"**Total Price:** ₹{total_price:.2f}")

    if st.button("Generate OTP"):
        mobile_str = safe_phone_to_str(employee_mobile)
        if not mobile_str:
            st.error("Selected employee has an invalid/missing mobile number. Update employee table and try again.")
            return

        otp = "".join(str(random.randint(0, 9)) for _ in range(6))
        redeemed = False

        new_entry = {
            "Coupon unique code no.": "".join(str(random.randint(0, 9)) for _ in range(5)),
            "Date": current_date,
            "Time": datetime.now().strftime("%H:%M:%S"),
            "Employee code": selected_employee_code,
            "Employee name": employee_name,
            "Type of dish": selected_items,
            "Rupees of items": total_price,
            "OTP": otp,
            "Redeemed": redeemed,
        }

        app_db.insert_coupon_row(conn, new_entry)

        variable = str(employee_name) + "|" + str(otp)
        url = "https://www.fast2sms.com/dev/bulkV2"
        querystring = {
            "authorization": "pPAR7SgKnuwyOvcxzUN3BhFfsaILJG142HWYjle8Zd6tXoVkDigXoLnctFQWVZI0PAUjDx31rl2SfhkJ",
            "sender_id": "GDCCMS",
            "message": "169006",
            "variables_values": f"{str(variable)}",
            "route": "dlt",
            "numbers": mobile_str,
        }
        headers = {"cache-control": "no-cache"}
        with st.spinner("Sending OTP..."):
            requests.request("GET", url, headers=headers, params=querystring)

        st.success("OTP sent to Employee.")


def user2_dashboard(conn):
    sweet_records_df = app_db.load_sweet_records_df(conn, include_id=True)
    coupons_df = app_db.load_coupon_df(conn, include_id=True)

    st.write("Welcome to the Operator Dashboard")
    st.sidebar.title("Generate Report")
    start_date = st.sidebar.date_input("Start Date")
    end_date = st.sidebar.date_input("End Date")

    if st.sidebar.button("Generate Full Report"):
        with st.spinner("Generating PDF..."):
            pdf_bytes = generate_pdf_report(conn, start_date=start_date, end_date=end_date, summ=False)
        st.sidebar.download_button(label="Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf")

    if st.sidebar.button("Generate Summary"):
        with st.spinner("Generating PDF..."):
            pdf_bytes = generate_pdf_report(conn, start_date=start_date, end_date=end_date, summ=True)
        st.sidebar.download_button(label="Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf")

    otp_input = st.text_input("Enter OTP/Temporary Code")

    if st.button("Redeem", key="unique8"):
        otp_input_str = str(otp_input).strip()

        # First: sweet_records redemption
        sweet_filtered = sweet_records_df[sweet_records_df["otp"].astype(str) == otp_input_str]
        if not sweet_filtered.empty:
            otp_details = sweet_filtered.iloc[0]
            redeemed_status = bool(int(otp_details["redeemed"])) if pd.notna(otp_details["redeemed"]) else False
            if redeemed_status:
                st.warning("Coupon already redeemed from sweet_records.")
            else:
                sweet_id = int(otp_details["id"])
                st.write(f"Employee Name: {otp_details['Employee Name']}")
                st.write(f"Bill Details: {otp_details['Bill Items']}")
                st.write(f"Total Price: {otp_details['Total Price']}")
                app_db.redeem_sweet_record_by_id(conn, sweet_id)
                st.success("Coupon Redeemed")
            return

        # Second: coupon redemption
        coupons_df["Date_dt"] = pd.to_datetime(coupons_df["Date"], errors="coerce")
        today = datetime.now()
        last_week_start = today - timedelta(days=7)

        last_week_coupons = coupons_df[coupons_df["Date_dt"] >= last_week_start]
        coupon_filtered = last_week_coupons[
            (last_week_coupons["OTP"].astype(str) == otp_input_str)
            | (last_week_coupons["Coupon unique code no."].astype(str) == otp_input_str)
        ]

        if coupon_filtered.empty:
            st.error("Invalid OTP. Please try again.")
            return

        otp_details = coupon_filtered.iloc[0]
        redeemed_status = bool(int(otp_details["Redeemed"])) if pd.notna(otp_details["Redeemed"]) else False
        if redeemed_status:
            st.warning("Coupon already redeemed from coupons.")
            return

        coupon_id = int(otp_details["id"])
        st.write(f"Employee Name: {otp_details['Employee name']}")
        st.write(f"Type of Dish: {otp_details['Type of dish']}")
        st.write(f"Amount: {otp_details['Rupees of items']}")
        app_db.redeem_coupon_by_id(conn, coupon_id)
        st.success("Coupon Redeemed")


def send_email(recipient_email, otp, employee_name, bill_details):
    smtp_server = "madhurdairy.icewarpcloud.in"
    smtp_port = 587
    sender_email = "sales@madhurdairy.org"
    sender_password = "Madhur@123"

    subject = "Madhur Dairy Sweets OTP"
    body = f"""
Hello {employee_name},

Your OTP for Madhur Dairy Sweets is: {otp}

Bill Details:
{bill_details}

Thank you!
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = recipient_email

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)


def save_email_details(conn, employee_number, employee_name, bill_items, mrp, discount, total_price, otp):
    current_date = datetime.today().strftime("%Y-%m-%d")
    current_time = datetime.now().strftime("%H:%M:%S")

    try:
        employee_number_int = int(employee_number)
    except Exception:
        employee_number_int = 0

    row = {
        "Date": current_date,
        "Time": current_time,
        "Employee Number": employee_number_int,
        "Employee Name": employee_name,
        "Bill Items": bill_items,
        "MRP": float(mrp) if mrp is not None else 0.0,
        "Discount": float(discount) if discount is not None else 0.0,
        "Total Price": float(total_price) if total_price is not None else 0.0,
        "otp": str(otp),
        "redeemed": False,
    }
    app_db.insert_sweet_record_row(conn, row)


def user_dashboard3(conn):
    st.write("Welcome to the Operator POS Dashboard")

    st.sidebar.title("Generate Report")
    start_date = st.sidebar.date_input("Start Date")
    end_date = st.sidebar.date_input("End Date")

    if st.sidebar.button("Generate Full Report"):
        with st.spinner("Generating PDF..."):
            pdf_bytes = generate_pdf_report(conn, start_date=start_date, end_date=end_date, summ=False)
        st.sidebar.download_button(label="Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf")

    if st.sidebar.button("Generate Summary"):
        with st.spinner("Generating PDF..."):
            pdf_bytes = generate_pdf_report(conn, start_date=start_date, end_date=end_date, summ=True)
        st.sidebar.download_button(label="Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf")

    menu_df = app_db.load_price_df(conn, include_id=False)
    employee_df = app_db.load_email_df(conn, include_id=False)

    employee_codes = (
        pd.to_numeric(employee_df["Personal No"], errors="coerce").dropna().astype(int).tolist()
    )
    if not employee_codes:
        st.error("No valid employee codes in email table.")
        return

    selected_employee_code = st.selectbox("Select Employee Code:", employee_codes)
    employee_info = employee_df[employee_df["Personal No"] == selected_employee_code]

    if employee_info.empty:
        st.error("Employee details not found.")
        return

    employee_name = employee_info.iloc[0]["EMPLOYEE NAME."]
    recipient_email = employee_info.iloc[0]["Email Id "]
    employee_number = employee_info.iloc[0]["Personal No"]

    selected_items = st.selectbox("Select items from the menu:", menu_df["Material Description"].tolist())

    st.subheader("Bill Builder")
    quantity = st.number_input("Quantity: ", min_value=1, value=1)

    if "bill" not in st.session_state:
        st.session_state.bill = []

    def reset_bill():
        st.session_state.bill = []

    if st.button("Add to Bill"):
        item_data = menu_df.loc[menu_df["Material Description"] == selected_items]
        if item_data.empty:
            st.error("Menu item not found.")
            return

        discounted_price = float(item_data["Price"].iloc[0])
        mrp_price = float(item_data["MRP"].iloc[0])
        weight = float(item_data["Weight"].iloc[0])

        total_price = discounted_price * quantity
        total_weight = sum(x["weight"] * x["quantity"] for x in st.session_state.bill)
        if total_weight + (weight * quantity) > 10000:
            st.error("Adding this item would exceed the weight limit of 10kgs.")
            return

        st.session_state.bill.append(
            {
                "item": selected_items,
                "quantity": quantity,
                "total_price": total_price,
                "mrp": mrp_price,
                "discounted": discounted_price,
                "weight": weight,
            }
        )

    if st.session_state.bill:
        bill_details_lines = []
        total_mrp = 0.0
        total_discount = 0.0

        for idx, bill_item in enumerate(st.session_state.bill):
            total_mrp += bill_item["mrp"] * bill_item["quantity"]
            total_discount += (bill_item["mrp"] - bill_item["discounted"]) * bill_item["quantity"]
            bill_details_lines.append(
                f"- {bill_item['quantity']} x {bill_item['item']}: ~~₹{bill_item['mrp']:.2f}~~ ₹{bill_item['discounted']:.2f} (Total: ₹{bill_item['total_price']:.2f})"
            )

            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.markdown(
                    f"- {bill_item['quantity']} x **{bill_item['item']}**: ~~₹{bill_item['mrp']:.2f}~~ ₹{bill_item['discounted']:.2f} (Total: ₹{bill_item['total_price']:.2f})"
                )
            with col_b:
                if st.button("🗑️", key=f"remove_{idx}", help="Remove item"):
                    st.session_state.bill.pop(idx)
                    st.experimental_rerun()

        st.write(f"**Employee Name:** {employee_name}")
        st.write("".join(bill_details_lines))
        total_bill_price = sum(x["total_price"] for x in st.session_state.bill)
        st.write(f"**Total Price:** ₹{total_bill_price:.2f}")
        if st.button("Clear Bill"):
            reset_bill()
            st.experimental_rerun()

        bill_items_str = ", ".join([f"{x['quantity']}x {x['item']}" for x in st.session_state.bill])
    else:
        st.info("No items added to the bill.")
        bill_items_str = ""
        total_bill_price = 0.0
        total_mrp = 0.0
        total_discount = 0.0

    if st.button("Generate OTP"):
        if not recipient_email or pd.isna(recipient_email):
            st.error("No email address found for the selected employee.")
            return
        if not st.session_state.bill:
            st.error("Please add at least one item to the bill.")
            return

        otp = random.randint(1000000, 9999999)
        send_email(recipient_email, otp, employee_name, "\n".join(bill_details_lines))
        save_email_details(conn, employee_number, employee_name, bill_items_str, total_mrp, total_discount, total_bill_price, otp)
        st.success("OTP has been sent.")

