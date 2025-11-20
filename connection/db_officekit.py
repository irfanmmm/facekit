# import mysql.connector
from dotenv import load_dotenv
import os
import pymssql

load_dotenv()  # Load env variables

server = os.getenv("OFFICEKIT_DB")
database = os.getenv("OFFICEKIT_DATABASE_NAME")
username = os.getenv("OFFICEKIT_USERNAME")
password = os.getenv("OFFICEKIT_PASS")
port = int(os.getenv("OFFICEKIT_DB_PORT", "1433"))
# host = os.getenv("OFFICEKIT_DB_HOST")


def get_db():
    return pymssql.connect(
        server=server,
        user=username,
        password=password,
        database=database,
        port=port,
        # host=host,
        tds_version='7.4'
    )
conn = get_db()
cursor = conn.cursor()

