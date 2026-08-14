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

# Thread-local connection storage. pymssql's C extension (_mssql) is not
# thread-safe for concurrent use of a single connection object — the previous
# implementation cached one shared pymssql connection per company across all
# threads, protected only during the cache lookup, not during actual query
# execution. Under gunicorn's threads=2 gthread workers, two threads (e.g. a
# foreground punch request and the background OfficeKit sync thread spawned
# per successful match) could run queries on the same shared connection at
# the same time, which reliably segfaults the C extension. Giving each thread
# its own connection per (host, server, user, db) key removes the shared
# mutable state entirely, so no connection is ever touched by more than one
# thread.
_thread_local = threading.local()


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

    if not hasattr(_thread_local, "connections"):
        _thread_local.connections = {}

    conn = _thread_local.connections.get(key)
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
            _thread_local.connections.pop(key, None)

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
        _thread_local.connections[key] = conn
        return conn
    except Exception as e:
        print(f"Database connection failed for company {company_code} on {current_host or current_server}: {e}")
        return None
