from __future__ import annotations

from datetime import date, datetime
from io import BytesIO

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import re

import db as app_db


def parse_bill_items(bill_items_str: str):
    """
    Parse strings like:
      '2x MADHUR something, 1x MADHUR other'
    Returns list of (item_name, quantity).
    """
    items = (bill_items_str or "").split(",")
    parsed_items = []
    for item in items:
        match = re.match(r"(\d+)x\s+(MADHUR .+)", item.strip())
        if match:
            quantity = int(match.group(1))
            item_name = match.group(2).strip()
            parsed_items.append((item_name, quantity))
    return parsed_items


def _build_empty_pdf(title: str, body: str) -> bytes:
    pdf_buffer = BytesIO()
    pdf = SimpleDocTemplate(pdf_buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    title_paragraph = Paragraph(title, styles["Title"])
    body_paragraph = Paragraph(body, styles["BodyText"])
    pdf.build([title_paragraph, Spacer(1, 12), body_paragraph])
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    return pdf_bytes


def generate_pdf_report(conn, start_date=None, end_date=None, summ: bool = False) -> bytes:
    """
    Coupon PDF report (redeemed-only).
    """
    c_df = app_db.load_coupon_df(conn, include_id=False)
    c_df = c_df.drop(columns=["OTP"], errors="ignore")

    if "Redeemed" in c_df.columns:
        c_df["Redeemed"] = c_df["Redeemed"].apply(lambda x: bool(int(x)) if pd.notna(x) else False)
    c_df = c_df[c_df["Redeemed"] == True]

    available_min = None
    available_max = None

    if start_date and end_date:
        c_df["Date"] = pd.to_datetime(c_df["Date"], errors="coerce")
        available_min = c_df["Date"].min()
        available_max = c_df["Date"].max()

        if isinstance(start_date, date):
            start_date = datetime.combine(start_date, datetime.min.time())
        if isinstance(end_date, date):
            end_date = datetime.combine(end_date, datetime.max.time())

        c_df = c_df[(c_df["Date"] >= start_date) & (c_df["Date"] <= end_date)]

    if c_df.empty:
        title = "Madhur Dairy Coupon Summary" if summ else "Madhur Dairy Coupon Report"
        if available_min is not None and available_max is not None:
            msg = (
                "No redeemed coupon data found for the selected date range. "
                f"Available redeemed dates: {available_min.strftime('%Y-%m-%d')} to {available_max.strftime('%Y-%m-%d')}."
            )
        else:
            msg = "No redeemed coupon data found for the selected date range."
        return _build_empty_pdf(title, msg)

    styles = getSampleStyleSheet()

    if summ:
        if start_date and end_date:
            title = (
                "Madhur Dairy Coupon Summary from "
                + start_date.strftime("%B %d, %Y")
                + " to "
                + end_date.strftime("%B %d, %Y")
            )
        else:
            title = "Madhur Dairy Coupon Summary"

        summ_df = (
            c_df.groupby("Type of dish")
            .agg({"Type of dish": "count", "Rupees of items": "sum"})
            .rename(columns={"Type of dish": "Count", "Rupees of items": "Total Amount"})
            .reset_index()
        )

        if summ_df.empty:
            return _build_empty_pdf(title, "No summary rows to display.")

        table_data = [[Paragraph(str(val), styles["BodyText"]) for val in summ_df.columns]]
        for _, row in summ_df.iterrows():
            table_data.append([Paragraph(str(val), styles["BodyText"]) for val in row])

        total_amount = summ_df["Total Amount"].sum()
        table_data.append([Paragraph("Total:", styles["BodyText"]), Paragraph("", styles["BodyText"]), Paragraph(str(total_amount), styles["BodyText"])])
    else:
        if start_date and end_date:
            title = (
                "Madhur Dairy Coupon Report from "
                + start_date.strftime("%B %d, %Y")
                + " to "
                + end_date.strftime("%B %d, %Y")
            )
        else:
            title = "Madhur Dairy Coupon Report"

        table_data = [[Paragraph(str(val), styles["BodyText"]) for val in c_df.columns]]
        for _, row in c_df.iterrows():
            table_data.append([Paragraph(str(val), styles["BodyText"]) for val in row])

        total_price = c_df["Rupees of items"].sum() if "Rupees of items" in c_df.columns else 0
        total_row = [""] * len(c_df.columns)
        total_row[0] = "Total:"
        if "Rupees of items" in c_df.columns:
            total_row[c_df.columns.get_loc("Rupees of items")] = total_price
        table_data.append([Paragraph(str(val), styles["BodyText"]) for val in total_row])

    pdf_buffer = BytesIO()
    pdf = SimpleDocTemplate(pdf_buffer, pagesize=letter)
    title_paragraph = Paragraph(title, styles["Title"])

    table = Table(table_data)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -2), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]
        )
    )

    elements = [title_paragraph, Spacer(1, 20), table]
    pdf.build(elements)

    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    return pdf_bytes


def generate_summary_pdf(conn, start_date, end_date) -> bytes:
    """
    Sweets summary PDF from sweet_records (redeemed-only path in caller).
    """
    s_df = app_db.load_sweet_records_df(conn, include_id=False)
    price_df = app_db.load_price_df(conn, include_id=False)

    s_df["Date"] = pd.to_datetime(s_df["Date"], errors="coerce")
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)
    s_df = s_df[(s_df["Date"] >= start_date) & (s_df["Date"] <= end_date)]

    parsed_data = []
    for _, row in s_df.iterrows():
        bill_items = parse_bill_items(row.get("Bill Items"))
        for item_name, quantity in bill_items:
            item_price = price_df.loc[price_df["Material Description"] == item_name, "Price"].values
            item_amount = float(item_price[0]) if len(item_price) > 0 else 0.0
            parsed_data.append(
                {
                    "Type of Sweet": item_name,
                    "Box Count": quantity,
                    "Item Amount": item_amount,
                    "Total Amount": item_amount * quantity,
                }
            )

    if not parsed_data:
        title = "Madhur Dairy Sweet Report Summary"
        date_range_text = f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        return _build_empty_pdf(title, f"{date_range_text}<br/>No bill items found for this range.")

    summary_df = pd.DataFrame(parsed_data)
    summary_df = summary_df.groupby("Type of Sweet").agg(
        Box_Count=("Box Count", "sum"),
        Item_Amount=("Item Amount", "first"),
        Total_Amount=("Total Amount", "sum"),
    ).reset_index()

    grand_total = round(summary_df["Total_Amount"].sum(), 2)

    title = "Madhur Dairy Sweet Report Summary"
    date_range_text = f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"

    styles = getSampleStyleSheet()
    header = ["Type of sweet", "Box count", "Item amount", "Total Amount"]
    table_data = [[Paragraph(col, styles["BodyText"]) for col in header]]

    for _, row in summary_df.iterrows():
        table_data.append(
            [
                Paragraph(row["Type of Sweet"], styles["BodyText"]),
                Paragraph(str(row["Box_Count"]), styles["BodyText"]),
                Paragraph(str(row["Item_Amount"]), styles["BodyText"]),
                Paragraph(str(row["Total_Amount"]), styles["BodyText"]),
            ]
        )

    table_data.append(
        [
            Paragraph("Grand total", styles["BodyText"]),
            Paragraph("", styles["BodyText"]),
            Paragraph("", styles["BodyText"]),
            Paragraph(str(grand_total), styles["BodyText"]),
        ]
    )

    pdf_buffer = BytesIO()
    pdf = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=20,
    )

    title_paragraph = Paragraph(title, styles["Title"])
    date_range_paragraph = Paragraph(date_range_text, styles["BodyText"])

    summary_table = Table(table_data, colWidths=[200, 80, 80, 80])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("SPAN", (0, -1), (2, -1)),
                ("ALIGN", (0, -1), (0, -1), "RIGHT"),
            ]
        )
    )

    pdf.build([title_paragraph, Spacer(1, 10), date_range_paragraph, Spacer(1, 10), summary_table])

    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    return pdf_bytes


def generate_pdf(conn, start_date=None, end_date=None) -> bytes:
    """
    Sweets redemption PDF from sweet_records (redeemed-only path).
    """
    s_df = app_db.load_sweet_records_df(conn, include_id=False)

    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)

    s_df["Date"] = pd.to_datetime(s_df["Date"], errors="coerce")
    s_df = s_df[(s_df["Date"] >= start_date) & (s_df["Date"] <= end_date)]

    s_df = s_df.drop(columns=["otp"], errors="ignore")
    s_df["redeemed"] = s_df["redeemed"].astype(bool)
    s_df = s_df[s_df["redeemed"]]
    s_df = s_df.drop(columns=["redeemed"])

    s_df["Employee Number"] = pd.to_numeric(s_df["Employee Number"], errors="coerce").fillna(0).astype(int)
    s_df = s_df[s_df["Employee Number"] != 101]

    time_delta = pd.to_timedelta("5:30:00")
    s_df["Time"] = (pd.to_datetime(s_df["Time"], format="%H:%M:%S", errors="coerce") + time_delta).dt.time
    s_df["Discount"] = s_df["Discount"].round()

    styles = getSampleStyleSheet()
    title = "Madhur Dairy Sweet Report"

    table_data = [[Paragraph(str(val), styles["BodyText"]) for val in s_df.columns]]
    for _, row in s_df.iterrows():
        table_data.append([Paragraph(str(val), styles["BodyText"]) for val in row])

    total_price = s_df["Total Price"].sum()
    total_row = ["Total:", "", "", "", "", "", "", total_price]
    table_data.append([Paragraph(str(val), styles["BodyText"]) for val in total_row])

    pdf_buffer = BytesIO()
    pdf = SimpleDocTemplate(pdf_buffer, pagesize=letter)
    title_paragraph = Paragraph(title, styles["Title"])

    table = Table(table_data, colWidths=[50, 50, 80, 100, 180, 40, 40, 60])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -2), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("FONTSIZE", (0, 0), (-1, -1), 6),
                ("WORDWRAP", (0, 0), (-1, -1), "ON"),
            ]
        )
    )

    pdf.build([title_paragraph, Spacer(1, 20), table])
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    return pdf_bytes

