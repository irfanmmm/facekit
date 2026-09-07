from utility.jwt_utils import create_token
from model.database import get_database, exclude

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


def find_client_admin(username, password):
    """Scan every company DB for a matching portal admin_username/admin_password."""
    client = get_database()
    for db_name in client.list_database_names():
        if db_name in exclude:
            continue
        collection = client[db_name].get_collection("compony_details")
        company = collection.find_one({
            "admin_username": username,
            "admin_password": password
        })
        if company:
            return str(company.get("compony_code"))
    return None


def login_user(username, password):
    """Returns a JWT on success, or None on invalid credentials.

    Two kinds of admins:
    - super_admin: the single hardcoded platform account, full access to every company.
    - client_admin: a per-company portal account, scoped to only that company's data.
    """
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        return create_token({"username": username, "role": "super_admin"})

    compony_code = find_client_admin(username, password)
    if compony_code:
        return create_token({
            "username": username,
            "role": "client_admin",
            "compony_code": compony_code
        })

    return None
