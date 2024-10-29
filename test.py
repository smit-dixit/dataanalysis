import os
import pandas as pd
import numpy as np
from io import BytesIO
import matplotlib.pyplot as plt
from pandas import json_normalize
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import base64
import requests
import random
import hashlib
from datetime import datetime,timedelta,date
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet
import smtplib
from email.mime.text import MIMEText



# Load configuration from YAML file
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

# Set page configuration
st.set_page_config(page_title="Dashboard", page_icon=":bar_chart:", layout="wide")

st.markdown("""
        <style>
               .block-container {
                    padding-top: 1rem;
                    padding-bottom: 0rem;
                    padding-left: 5rem;
                    padding-right: 5rem;
                }
        </style>
        """, unsafe_allow_html=True)

# Authentication
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
    config['preauthorized']
)

# Read Excel file or create an empty DataFrame if it doesn't exist
try:
    df = pd.read_pickle('employee.pkl')
except FileNotFoundError:
    df = pd.DataFrame()

# Display all columns
pd.set_option('display.max_columns', None)

def reset_password(username):
    st.title("Reset Password")
    new_password = st.text_input("Enter your new password", type="password")
    confirm_password = st.text_input("Confirm new password", type="password")
    if st.button("Reset"):
        if new_password == confirm_password:
            # Update password in database
            hashed_password = hashlib.sha256(new_password.encode()).hexdigest()  # Hash new password
            update_password(username, hashed_password)
            st.success("Password successfully reset.")
        else:
            st.error("Passwords do not match.")

# Login
name, authentication_status, username = authenticator.login()


def generate_pdf_report(start_date=None, end_date=None, summ=False):
    c_df = pd.read_pickle('coupon.pkl')
    
    c_df = c_df.drop(columns=['OTP'])

    c_df = c_df[c_df['Redeemed'] == True]

    if start_date and end_date:
        # Ensure 'Date' column is datetime type
        c_df['Date'] = pd.to_datetime(c_df['Date'])

        # Convert start_date and end_date to datetime if they are date objects
        if isinstance(start_date, date):
            start_date = datetime.combine(start_date, datetime.min.time())
        if isinstance(end_date, date):
            end_date = datetime.combine(end_date, datetime.max.time())

        c_df = c_df[(c_df['Date'] >= start_date) & (c_df['Date'] <= end_date)]
    
    if summ:
        title = "Madhur Dairy Coupon Summary from " + start_date.strftime('%B %d, %Y') + " to " + end_date.strftime('%B %d, %Y')
        summ_df = c_df.groupby('Type of dish').agg({'Type of dish':'count', 'Rupees of items':'sum'}).rename(columns={'Type of dish':'Count', 'Rupees of items':'Total Amount'}).reset_index()
    else:
        title = "Madhur Dairy Coupon Report from " + start_date.strftime('%B %d, %Y') + " to " + end_date.strftime('%B %d, %Y')

    # Prepare data for the table
    if summ:
        table_data = [[Paragraph(str(val), getSampleStyleSheet()["BodyText"]) for val in summ_df.columns]]  # Header row
        for _, row in summ_df.iterrows():
            table_data.append([Paragraph(str(val), getSampleStyleSheet()["BodyText"]) for val in row])
    else:
        table_data = [[Paragraph(str(val), getSampleStyleSheet()["BodyText"]) for val in c_df.columns]]  # Header row
        for _, row in c_df.iterrows():
            table_data.append([Paragraph(str(val), getSampleStyleSheet()["BodyText"]) for val in row])

    # Calculate totals
    price_total = c_df.iloc[:, -2].sum()  # Assuming 'Rupees of Item' is the second-last column
    total_row = ['Total:', '', '', '', '', '', price_total]  # Add empty strings for other columns

    # Add total row to table data
    table_data.append([Paragraph(str(val), getSampleStyleSheet()["BodyText"]) for val in total_row])

    # Create a PDF document
    pdf_buffer = BytesIO()
    pdf = SimpleDocTemplate(pdf_buffer, pagesize=letter)
    
    # Create title paragraph
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    title_paragraph = Paragraph(title, title_style)

    # Create the table
    table = Table(table_data)
    style = TableStyle([('BACKGROUND', (0,0), (-1,0), colors.grey),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('BOTTOMPADDING', (0,0), (-1,0), 12),
                        ('BACKGROUND', (0,1), (-1,-2), colors.beige),  # Exclude total row from background color
                        ('GRID', (0,0), (-1,-1), 1, colors.black)])
    table.setStyle(style)

    # Add title and table to PDF
    elements = [title_paragraph, Spacer(1, 20), table]
    pdf.build(elements)
    
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    
    return pdf_bytes

def generate_pdf(start_date=None, end_date=None):
    # Load the DataFrame from the pickle file
    s_df = pd.read_pickle('sweet_records2.pkl')

    # Convert the input start and end dates to datetime
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)

    # Convert the "Date" column to datetime and filter between start_date and end_date
    s_df['Date'] = pd.to_datetime(s_df['Date'], errors='coerce')
    s_df = s_df[(s_df['Date'] >= start_date) & (s_df['Date'] <= end_date)]

    # Remove the 'otp' column and filter for redeemed records only
    s_df = s_df.drop(columns=['otp'])
    s_df = s_df[s_df['redeemed'] == True]
    s_df = s_df.drop(columns=['redeemed'])

    # Convert "Employee Number" to integer and remove rows with Employee Number 101
    s_df['Employee Number'] = s_df['Employee Number'].astype(int)
    s_df = s_df[s_df['Employee Number'] != 101]

    # Adjust "Time" column by adding 5 hours and 30 minutes
    time_delta = pd.to_timedelta('5:30:00')
    s_df['Time'] = (pd.to_datetime(s_df['Time'], format='%H:%M:%S') + time_delta).dt.time

    s_df['Discount'] = s_df['Discount'].round()

    # Format "Bill Items" as sub-rows by joining items with line breaks
    s_df['Bill Items'] = s_df['Bill Items'].str.split(',').apply(lambda items: '\n'.join([item.strip() for item in items]))

    # Define title for the report
    title = "Madhur Dairy Sweet Report"

    # Prepare data for the table
    table_data = [[Paragraph(str(val), getSampleStyleSheet()["BodyText"]) for val in s_df.columns]]  # Header row
    for _, row in s_df.iterrows():
        table_data.append([Paragraph(str(val), getSampleStyleSheet()["BodyText"]) for val in row])

    # Calculate totals for the 'Total Price' column
    total_price = s_df['Total Price'].sum()
    total_row = ['Total:', '', '', '', '', '', '', total_price]  # Add empty strings for other columns

    # Add total row to table data
    table_data.append([Paragraph(str(val), getSampleStyleSheet()["BodyText"]) for val in total_row])

    # Create a PDF document
    pdf_buffer = BytesIO()
    pdf = SimpleDocTemplate(pdf_buffer, pagesize=letter)

    # Create title paragraph
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    title_paragraph = Paragraph(title, title_style)

    # Create the table with styling
    table = Table(table_data)
    style = TableStyle([('BACKGROUND', (0,0), (-1,0), colors.grey),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('BOTTOMPADDING', (0,0), (-1,0), 12),
                        ('BACKGROUND', (0,1), (-1,-2), colors.beige),  # Exclude total row from background color
                        ('GRID', (0,0), (-1,-1), 1, colors.black),
                        ('FONTSIZE', (0, 0), (-1, -1), 6),  # Set font size to 8 for all cells
                        ('WORDWRAP', (0, 0), (-1, -1), 'ON')])  # Enable word wrap
    table.setStyle(style)

    # Add title and table to PDF elements
    elements = [title_paragraph, Spacer(1, 20), table]
    pdf.build(elements)
    
    # Get PDF bytes and close the buffer
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    
    return pdf_bytes

coupons_df = pd.read_pickle('coupon.pkl')

def company_header():
    st.markdown(
        """
        <div style='background-color: #f0f0f0; padding: 10px; display: flex; align-items: center; justify-content: space-between;'>
            <div style='display: flex; align-items: center;'>
                <h2 style='color: #333333; margin: 0;'>Madhur Dairy Canteen Management System</h2>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    
    
    st.sidebar.image('logo.png', width = 250)


        
        
# Function to plot line graph
def plot_line_graph(data):
    fig, ax = plt.subplots(figsize=(10, 6))
    
    data['Date'] = pd.to_datetime(data['Date'])
    
    # Filter data for last week
    end_date = data['Date'].max()
    start_date = end_date - timedelta(days=6)
    data_last_week = data[(data['Date'] >= start_date) & (data['Date'] <= end_date)]
    
    redeemed_counts = data_last_week.groupby('Date')['Redeemed'].sum().reset_index()
    generated_counts = data_last_week.groupby('Date').size().reset_index(name='Generated')
    
    ax.plot(redeemed_counts['Date'], redeemed_counts['Redeemed'], marker='o', linestyle='-', label='Redeemed')
    ax.plot(generated_counts['Date'], generated_counts['Generated'], marker='o', linestyle='-', label='Generated')
    
    ax.set_title('Daily Coupons Generated and Redeemed (Last Week)')
    ax.set_xlabel('Date')
    ax.set_ylabel('Number of Coupons')
    ax.grid(True)
    ax.legend()
    ax.tick_params(axis='x', rotation=45)
    plt.tight_layout()
    return fig

# Admin dashboard home page
def admin_dashboard_home():
    
    st.title('Home')
    # Layout for dividing the page into two parts
    col1, col2 = st.columns([0.25, 1])
    
    with col1:
        st.write("## Coupons Overview")
        coupons_df['Date'] = pd.to_datetime(coupons_df['Date'])

        # Calculate the start and end dates of the last week
        end_date = coupons_df['Date'].max()
        start_date = end_date - timedelta(days=6)

        # Filter the DataFrame for last week's data
        last_week_data = coupons_df[(coupons_df['Date'] >= start_date) & (coupons_df['Date'] <= end_date)]

        # Calculate total generated and redeemed coupons for last week
        generated_total = last_week_data.shape[0]  # Total number of rows
        redeemed_total = last_week_data['Redeemed'].sum()

        # Display coupons generated and redeemed with small green arrows
        st.metric(label='Coupons Generated', value = generated_total)
        st.metric(label='Coupons Redeemed', value = redeemed_total)
        st.metric(label='No. of Employees', value = 3)
        #st.write(f"**Coupons Generated:** {generated_total}")
        #st.write(f"**Coupons Redeemed:** {redeemed_total}")


 # Second part: Line graph of daily coupons redeemed for past week
    with col2:
        st.write("## Daily Coupons Redeemed (Past Week)")
        fig = plot_line_graph(coupons_df)
        st.pyplot(fig)
    

# Admin dashboard function
def admin_dashboard():
    
    st.sidebar.write("Welcome to the Admin Dashboard")
    page = st.sidebar.radio("Select Page", ["Home", "User Management", "Employee Management", "Menu Management", "Support"])
    
    # Add your user dashboard content here
    st.sidebar.title("Generate Report")
    start_date = st.sidebar.date_input("Start Date")
    end_date = st.sidebar.date_input("End Date")
    
    def hash_password(password):
      return hashlib.sha256(password.encode()).hexdigest()

    # Button to generate PDF report
    if st.sidebar.button("Generate Full Report"):
    
        pdf_bytes = generate_pdf_report(start_date=start_date, end_date=end_date, summ = False)
        st.sidebar.download_button(label="Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf")
        st.sidebar.success("PDF report generated successfully!")
        
    if st.sidebar.button("Generate Summary"):
    
        pdf_bytes = generate_pdf_report(start_date=start_date, end_date=end_date, summ = True)
        st.sidebar.download_button(label="Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf")
        st.sidebar.success("PDF report generated successfully!")
        
    if st.sidebar.button("Generate Sweets Report"):
    
        pdf_bytes = generate_pdf(start_date=start_date, end_date=end_date)
        st.sidebar.download_button(label="Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf")
        st.sidebar.success("PDF report generated successfully!")
    
    footer_html = """<div style='text-align: center;'>
                    <p>© 2024 Madhur Dairy | All Rights Reserved</p>
                    </div>"""
    st.sidebar.markdown(footer_html, unsafe_allow_html=True)
    
    if page == "Home":
        admin_dashboard_home()
        # Add content for the Home page
        
    elif page == "User Management":
        st.title("User Management")
        if 'usernames' not in st.session_state:
            st.session_state.usernames = pd.DataFrame(config['credentials']['usernames']).T
            
        edited_users = st.data_editor(st.session_state.usernames, num_rows="dynamic")
        
        if st.button('Save', key="unique5"):
        
            for index, row in edited_users.iterrows():
                if row['password'] != edited_users.loc[index, 'password']:  # Check for password change
                    row['password'] = hash_password(row['password'])  # Hash password if changed
            # Check if there are new users added
            new_users = edited_users.index.difference(st.session_state.usernames.index)
            
            # If there are new users, append them to the configuration
            if not new_users.empty:
                for user in new_users:
                    config['credentials']['usernames'][user] = edited_users.loc[user].to_dict()

            # Update the usernames in the configuration
            config['credentials']['usernames'] = edited_users.to_dict(orient='index')

            # Write the updated configuration back to the YAML file
            with open('config.yaml', 'w') as file:
                yaml.dump(config, file)
   
        
    elif page == "Employee Management":
        st.title("Employee Management")
        dfm = pd.read_pickle('employee.pkl')
        
        
        
        edited_df = st.data_editor(dfm, 
                           num_rows="dynamic", 
                           use_container_width=True, 
                           column_config={
                               "Mobile No.": st.column_config.NumberColumn(format="%f"),
                               "Employee Code": st.column_config.NumberColumn(format="%f")
                           })
        if st.button('Save', key="unique4"):
            edited_df.to_pickle('employee.pkl')
            st.success('Changes Saved')
            
        df_menu = pd.read_pickle('email.pkl')
        edited_menu = st.data_editor(df_menu, num_rows="dynamic", 
                           use_container_width=True, 
                           column_config={
                               "Personal No": st.column_config.NumberColumn(format="%f")
                           })
        if st.button('Save', key="unique5"):
            edited_menu.to_pickle('email.pkl')
        
        uploaded = st.file_uploader("Choose a file")
        
    elif page == "Menu Management":
        st.title("Canteen Menu")
        df_menu = pd.read_pickle('menu.pkl')
        edited_menu = st.data_editor(df_menu, num_rows="dynamic")
        if st.button('Save', key="unique3"):
            edited_menu.to_pickle('menu.pkl')
            
        df_menu = pd.read_pickle('price.pkl')
        edited_menu = st.data_editor(df_menu, num_rows="dynamic")
        if st.button('Save', key="unique4"):
            edited_menu.to_pickle('price.pkl')
            
    elif page == "Support":
        st.title('Support')
    
        # Input Fields
        issue_name = st.text_input('Name:')
        issue_email = st.text_input('Contact Email:')
        issue_number = st.text_input('Phone number:')
        issue = st.text_area('Describe your issue:')
        
        
        # Submit Button
        if st.button('Submit'):
            if issue and issue_name and issue_email and issue_number:
                #send_email(issue, contact_info)
                st.success('Your request has been submitted successfully!')
            else:
                st.error('Please fill in both issue description and contact information.')

# Regular user dashboard function
def user_dashboard():
    st.write("Welcome to the Timekeeper Dashboard")
    # Add your user dashboard content here
    st.sidebar.title("Generate Report")
    start_date = st.sidebar.date_input("Start Date")
    end_date = st.sidebar.date_input("End Date")

    # Button to generate PDF report
    if st.sidebar.button("Generate Full Report"):
    
        pdf_bytes = generate_pdf_report(start_date=start_date, end_date=end_date, summ = False)
        st.sidebar.download_button(label="Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf")
        st.sidebar.success("PDF report generated successfully!")
        
    if st.sidebar.button("Generate Summary"):
    
        pdf_bytes = generate_pdf_report(start_date=start_date, end_date=end_date, summ = True)
        st.sidebar.download_button(label="Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf")
        st.sidebar.success("PDF report generated successfully!")
    # Read menu data
    
    menu_df = pd.read_pickle('menu.pkl')

    # Read employee data
    employee_df = pd.read_pickle('employee.pkl')


    # Display employee dropdown to select employee code
    selected_employee_code = st.selectbox("Select Employee Code:", [int(code) for code in employee_df['Employee Code'].tolist()])

    # Get employee details based on selected employee code
    employee_info = employee_df[employee_df['Employee Code'] == selected_employee_code]
    if not employee_info.empty:
        employee_name = employee_info.iloc[0]['Employee Name']
        employee_mobile = employee_info.iloc[0]['Mobile No.']
        
    else:
        employee_name = "Not Found"
        employee_mobile = "Not Found"
        
    current_date = datetime.now().strftime('%Y-%m-%d')

    # Filter out items already ordered by the selected employee today
    ordered_items_today = []
    coupon_df = pd.read_pickle('coupon.pkl')
    if not coupon_df.empty:
        ordered_items_today = coupon_df[(coupon_df['Employee code'] == selected_employee_code) & (coupon_df['Date'] == current_date)]['Type of dish'].tolist()

    # Filter menu items not already ordered today
    menu_items = menu_df[~menu_df['Item'].isin(ordered_items_today)]['Item'].tolist()

    # Display menu items and allow user to select
    selected_items = st.selectbox("Select items from the menu:", menu_items)
    # Calculate total price based on selected items
    total_price = 0

    
    item_data = menu_df.loc[menu_df['Item'] == selected_items]
    if not item_data.empty:
        price = item_data['Price'].iloc[0]
        discount = item_data['Discount'].iloc[0]
        # Apply discount if available
        discounted_price = price - discount
        total_price += discounted_price

    # Display bill with selected items, employee details, and total price
    st.write("### Bill")
    st.write("**Selected Item:**")
    st.write(f"- {selected_items}")
    st.write(f"**Employee Name:** {employee_name}")
    st.write(f"**Total Price:** ₹{total_price:.2f}")
    button1 = st.button('Generate OTP', )
    if button1:
    
        c_df = pd.read_pickle('coupon.pkl')
        
        # Increment the coupon unique code number
        last_coupon_code = c_df['Coupon unique code no.'].iloc[-1]
        last_coupon_num = int(last_coupon_code[1:])
        new_coupon_num = last_coupon_num + 1
        new_coupon_code = ''.join(str(random.randint(0, 9)) for _ in range(5))
        
        # Get current date and time
        current_date = datetime.now().strftime('%Y-%m-%d')
        current_time = datetime.now().strftime('%H:%M:%S')

        # Generate 6-digit OTP
        
        otp = ''.join(str(random.randint(0, 9)) for _ in range(6))
        
        # Set redeemed to False
        redeemed = False

        # Create the new entry
        new_entry = {
            'Coupon unique code no.': new_coupon_code,
            'Date': current_date,
            'Time': current_time,
            'Employee code': selected_employee_code,
            'Employee name': employee_name,
            'Type of dish': selected_items,
            'Rupees of items': total_price,
            'OTP': otp,
            'Redeemed': redeemed
        }

        # Append the new entry to the DataFrame
        c_df = pd.concat([c_df, pd.DataFrame([new_entry])], ignore_index=True)
        c_df.to_pickle('coupon.pkl')
        
        variable = str(employee_name) + '|' + str(otp)
    
        url = "https://www.fast2sms.com/dev/bulkV2"

        querystring = {"authorization":"pPAR7SgKnuwyOvcxzUN3BhFfsaILJG142HWYjle8Zd6tXoVkDigXoLnctFQWVZI0PAUjDx31rl2SfhkJ","sender_id":"GDCCMS","message":"169006","variables_values":f"{str(variable)}","route":"dlt","numbers": str(int(employee_mobile))}

        headers = {
            'cache-control': "no-cache"
        }

        response = requests.request("GET", url, headers=headers, params=querystring)
        
        st.title("Temporary Code:" + new_coupon_code)
        st.success("OTP sent to Employee")

    
def user2_dashboard():
    sweet_records_df = pd.read_pickle('sweet_records2.pkl')
    coupons_df = pd.read_pickle('coupon.pkl')  # Load coupons DataFrame

    st.write("Welcome to Operator Dashboard")

    st.sidebar.title("Generate Report")
    start_date = st.sidebar.date_input("Start Date")
    end_date = st.sidebar.date_input("End Date")

    # Button to generate PDF report
    if st.sidebar.button("Generate Sweets Report"):
    
        pdf_bytes = generate_pdf(start_date=start_date, end_date=end_date)
        st.sidebar.download_button(label="Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf")
        st.sidebar.success("PDF report generated successfully!")

    otp_input = st.text_input("Enter OTP/Temporary Code")

    if st.button("Redeem", key="unique8"):
        otp_input_str = str(otp_input).strip()

        # Check for OTP in sweet_records_df
        sweet_filtered = sweet_records_df[sweet_records_df['otp'].astype(str) == otp_input_str]

        if not sweet_filtered.empty:
            otp_details = sweet_filtered.iloc[0]
            redeemed_status = otp_details['redeemed']

            if redeemed_status:
                st.warning("Coupon already redeemed from sweet_records.")
            else:
                sweet_index = sweet_filtered.index[0]
                st.write(f"Employee Name: {otp_details['Employee Name']}")
                st.write(f"Bill Details: {otp_details['Bill Items']}")
                sweet_records_df.at[sweet_index, 'redeemed'] = True
                sweet_records_df.to_pickle('sweet_records2.pkl')
                st.success('Coupon Redeemed')
            
            return  # Exit after handling the sweet_records case

        # Check for OTP in coupons_df
        coupon_filtered = coupons_df[(coupons_df['OTP'] == otp_input_str) | (coupons_df['Coupon unique code no.'] == otp_input_str)]

        if not coupon_filtered.empty:
            otp_details = coupon_filtered.iloc[0]
            redeemed_status = otp_details['Redeemed']

            if not redeemed_status:
                coupon_index = coupon_filtered.index[0]
                employee_name = otp_details['Employee name']
                dish_type = otp_details['Type of dish']
                amount = otp_details['Rupees of items']
                
                st.write(f"Employee Name: {employee_name}")
                st.write(f"Type of Dish: {dish_type}")
                st.write(f"Amount: {amount}")
                coupons_df.at[coupon_index, 'Redeemed'] = True
                coupons_df.to_pickle('coupon.pkl')
                st.success('Coupon Redeemed')
            else:
                st.warning("Coupon already redeemed from coupons.")
        else:
            st.error("Invalid OTP. Please try again.")
        
def send_email(recipient_email, otp, employee_name, bill_details):
    # Set your SMTP server details
    smtp_server = "madhurdairy.icewarpcloud.in"
    smtp_port = 587
    sender_email = "info@madhurdairy.org"
    sender_password = "Madhur@123"  # Use environment variables in production

    # Create email content
    subject = "Madhur Dairy Sweets OTP"
    body = f"""
    Hello {employee_name},

    Your OTP for Madhur Dairy Sweets is: {otp}

    Bill Details:
    {bill_details}

    Thank you!
    """
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = recipient_email

    # Sending the email
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()  # Use TLS
        server.login(sender_email, sender_password)
        server.send_message(msg)

def save_email_details(employee_number, employee_name, bill_items, mrp, discount, total_price, otp):
    filename = 'sweet_records2.pkl'
    
    # Check if the file exists
    if os.path.exists(filename):
        # Load existing records
        records_df = pd.read_pickle(filename)
    else:
        # Create a new DataFrame if the file doesn't exist
        records_df = pd.DataFrame(columns=['Date', 'Time', 'Employee Number', 'Employee Name', 
                                           'Bill Items', 'MRP', 'Discount', 'Total Price', 'otp', 'redeemed'])

    # Get the current date and time
    current_date = datetime.today().strftime('%Y-%m-%d')
    current_time = datetime.now().strftime('%H:%M:%S')

    # Create a new record
    new_record = pd.DataFrame({
        'Date': [current_date],
        'Time': [current_time],
        'Employee Number': [employee_number],
        'Employee Name': [employee_name],
        'Bill Items': [bill_items],  # List of items
        'MRP': [mrp],  # Total MRP for the items
        'Discount': [discount],  # Total discount applied
        'Total Price': [total_price],  # Total price after discount
        'otp': [otp],
        'redeemed': [False]# The generated OTP
    })

    # Append the new record
    records_df = pd.concat([records_df, new_record], ignore_index=True)

    # Save the updated DataFrame back to the pickle file
    records_df.to_pickle(filename)

def user_dashboard3():
    st.write("Welcome to the Timekeeper Dashboard")

    # Sidebar for report generation
    st.sidebar.title("Generate Report")
    start_date = st.sidebar.date_input("Start Date")
    end_date = st.sidebar.date_input("End Date")

    # Button to generate PDF report
    if st.sidebar.button("Generate Sweets Report"):
    
        pdf_bytes = generate_pdf(start_date=start_date, end_date=end_date)
        st.sidebar.download_button(label="Download PDF", data=pdf_bytes, file_name="report.pdf", mime="application/pdf")
        st.sidebar.success("PDF report generated successfully!")

    # Read menu data
    menu_df = pd.read_pickle('price.pkl')
    employee_df = pd.read_pickle('email.pkl')

    # Employee selection
    selected_employee_code = st.selectbox("Select Employee Code:", [int(code) for code in employee_df['Personal No'].tolist()])
    employee_info = employee_df[employee_df['Personal No'] == selected_employee_code]
    
    if not employee_info.empty:
        employee_name = employee_info.iloc[0]['EMPLOYEE NAME.']
        recipient_email = employee_info.iloc[0]['Email Id ']
        employee_number = employee_info.iloc[0]['Personal No']
    else:
        employee_name = "Not Found"
        employee_number = None

    # Menu items selection with quantity input
    selected_items = st.selectbox("Select items from the menu:", menu_df['Material Description'].tolist())
    
    # Enhanced layout for quantity input
    col1, col2 = st.columns([1, 2])
    with col1:
        quantity = st.number_input("Quantity: ", min_value=1, value=1)
        
    # Initialize bill in session state
    if 'bill' not in st.session_state:
        st.session_state.bill = []
    
    # Calculate total weight
    total_weight = sum(item['weight'] * item['quantity'] for item in st.session_state.bill)

    if st.button("Add to Bill"):
        item_data = menu_df.loc[menu_df['Material Description'] == selected_items]
        if not item_data.empty:
            discounted_price = item_data['Price'].iloc[0]
            mrp_price = item_data['MRP'].iloc[0]
            weight = item_data['Weight'].iloc[0]
            
            total_price = discounted_price * quantity
            
            # Check if adding this item exceeds the weight limit
            if total_weight + (weight * quantity) > 10000:
                st.error("Adding this item would exceed the weight limit of 10kgs.")
            else:
                st.session_state.bill.append({
                    'item': selected_items,
                    'quantity': quantity,
                    'total_price': total_price,
                    'mrp': mrp_price,
                    'discounted': discounted_price,
                    'weight': weight
                })

    # Display the bill
    st.write("### Bill")
    st.write(f"**Employee Name:** {employee_name}")  # Show the employee name
    if st.session_state.bill:
        bill_details = ""
        total_mrp = 0
        total_discount = 0
        for idx, bill_item in enumerate(st.session_state.bill):
            total_mrp += bill_item['mrp'] * bill_item['quantity']
            total_discount += (bill_item['mrp'] - bill_item['discounted']) * bill_item['quantity']
            bill_details += f"- {bill_item['quantity']} x **{bill_item['item']}**: ~~₹{bill_item['mrp']:.2f}~~ ₹{bill_item['discounted']:.2f} (Total: ₹{bill_item['total_price']:.2f})\n"
            col_a, col_b = st.columns([3, 1])  # Create two columns for item details and remove button
            with col_a:
                st.markdown(f"- {bill_item['quantity']} x **{bill_item['item']}**: ~~₹{bill_item['mrp']:.2f}~~ ₹{bill_item['discounted']:.2f} (Total: ₹{bill_item['total_price']:.2f})")
            with col_b:
                if st.button("🗑️", key=f"remove_{idx}", help="Remove item"):
                    st.session_state.bill.pop(idx)
                    st.experimental_rerun()    # Refresh the app to show updated bill
    else:
        st.write("No items added to the bill.")

    # Total price calculation
    total_bill_price = sum(item['total_price'] for item in st.session_state.bill)
    st.write(f"**Total Price:** ₹{total_bill_price:.2f}")

    # Generate OTP and Save Transaction
    if st.button('Generate OTP'):
        if not pd.isna(recipient_email) and recipient_email:
            otp = random.randint(1000000, 9999999)  # Generate a 7-digit OTP
            bill_items = ', '.join([f"{bill_item['quantity']}x {bill_item['item']}" for bill_item in st.session_state.bill])  # List of items
            send_email(recipient_email, otp, employee_name, bill_details)  # Send OTP via email
            
            # Save the bill details along with the OTP in the pickle file
            save_email_details(employee_number, employee_name, bill_items, total_mrp, total_discount, total_bill_price, otp)
            st.success(f"OTP has been sent.")
        else:
            st.error("No email address found for the selected employee.")
# Display dashboard if authenticated
if authentication_status:
    company_header()
    authenticator.logout('Logout', 'sidebar', 'my_crazy_random_signature_key')
      
    if username.startswith('ad'):
        admin_dashboard()
    elif username.startswith('op'):
        user2_dashboard()
    elif username.startswith('ti'):
        user_dashboard()
    elif username.startswith('po'):
        user_dashboard3()

st.markdown("""
    <style>
        .reportview-container {
            margin-top: -2em;
        }
        #MainMenu {visibility: hidden;}
        .stDeployButton {display:none;}
        footer {visibility: hidden;}
        #stDecoration {display:none;}
    </style>
""", unsafe_allow_html=True)

