# import mysql.connector
from dotenv import load_dotenv
import os
import pymssql

load_dotenv()  # Load primary env variables

server = os.getenv("OFFICEKIT_DB")
database = os.getenv("OFFICEKIT_DATABASE_NAME")
username = os.getenv("OFFICEKIT_USERNAME")
password = os.getenv("OFFICEKIT_PASS")
port = int(os.getenv("OFFICEKIT_DB_PORT", "1433"))
host = os.getenv("OFFICEKIT_HOST")


def get_db(company_code=None):
    # Start with default credentials from .env
    current_host = host
    current_server = os.getenv("OFFICEKIT_SERVER") or server
    current_user = username
    current_pass = password
    current_db = database

    # Switch to Empire credentials if it's NOT A100 (and not None)
    # If you want Empire to be the default, you can adjust this logic
    if company_code and company_code == 'A102':
        current_db = os.getenv("EMPIRE_OFFICEKIT_DATABASE_NAME")
        current_host = os.getenv("EMPIRE_OFFICEKIT_IP")
        current_user = os.getenv("EMPIRE_OFFICEKIT_USER")
        current_pass = os.getenv("EMPIRE_OFFICEKIT_PASS")
        current_server = os.getenv("EMPIRE_OFFICEKIT_SERVER")

    try:
        return pymssql.connect(
            host=current_host,
            server=current_server,
            user=current_user,
            password=current_pass,
            database=current_db,
            port=port,
            login_timeout=5,
            tds_version='7.4'
        )
    except Exception as e:
        print(f"Database connection failed for company {company_code} on {current_host or current_server}: {e}")
        return None


