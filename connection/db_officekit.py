from dotenv import load_dotenv
import os
import pymssql
import threading

load_dotenv()  # Load primary env variables

server = os.getenv("OFFICEKIT_DB")
database = os.getenv("OFFICEKIT_DATABASE_NAME")
username = os.getenv("OFFICEKIT_USERNAME")
password = os.getenv("OFFICEKIT_PASS")
port = int(os.getenv("OFFICEKIT_DB_PORT", "1433"))
host = os.getenv("OFFICEKIT_HOST")

_connection_pool = {}
_pool_lock = threading.Lock()


def get_db(company_code=None):
    current_host = host
    current_server = os.getenv("OFFICEKIT_SERVER") or server
    current_user = username
    current_pass = password
    current_db = database

    if company_code and company_code == 'A102':
        current_db = os.getenv("EMPIRE_OFFICEKIT_DATABASE_NAME")
        current_host = os.getenv("EMPIRE_OFFICEKIT_IP")
        current_user = os.getenv("EMPIRE_OFFICEKIT_USER")
        current_pass = os.getenv("EMPIRE_OFFICEKIT_PASS")
        current_server = os.getenv("EMPIRE_OFFICEKIT_SERVER")
    if company_code and company_code == 'A860':
        current_db = os.getenv("ANJUMAN_OFFICEKIT_DATABASE_NAME")
        current_host = os.getenv("ANJUMAN_OFFICEKIT_IP")
        current_user = os.getenv("ANJUMAN_OFFICEKIT_USER")
        current_pass = os.getenv("ANJUMAN_OFFICEKIT_PASS")
        current_server = os.getenv("ANJUMAN_OFFICEKIT_SERVER")

    key = (current_host, current_server, current_user, current_db)

    with _pool_lock:
        conn = _connection_pool.get(key)
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                return conn
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                _connection_pool.pop(key, None)

        try:
            conn = pymssql.connect(
                host=current_host,
                server=current_server,
                user=current_user,
                password=current_pass,
                database=current_db,
                port=port,
                login_timeout=5,
                tds_version='7.4',
                autocommit=True
            )
            _connection_pool[key] = conn
            return conn
        except Exception as e:
            print(f"Database connection failed for company {company_code} on {current_host or current_server}: {e}")
            return None
