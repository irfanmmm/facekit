import jwt
from datetime import datetime, timedelta
import os

def get_secret_key():
    return os.getenv("SECRET_KEY") or "facekit_secret_key_super_secret_secure_2026_32bytes"

def create_token(payload):
    payload["exp"] = datetime.utcnow() + timedelta(days=180)
    return jwt.encode(payload, get_secret_key(), algorithm="HS256")

def verify_token(token):
    try:
        return jwt.decode(token, get_secret_key(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
