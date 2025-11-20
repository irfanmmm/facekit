from utility.jwt_utils import create_token

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
def login_user(username, password):
    return create_token({"username": username, "role": "admin", "password": password})
    
