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


def get_db(company_code=None):
    if company_code == 'A100':
        db_name = database
    else:
        db_name = os.getenv(f"EMPIRE_OFFICEKIT_DATABASE_NAME", database)

    return pymssql.connect(
        server=server,
        user=username,
        password=password,
        database=db_name,
        port=port,
        tds_version='7.4'
    )


conn = get_db()
cursor = conn.cursor()
