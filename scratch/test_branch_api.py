import requests
import jwt
from datetime import datetime, timedelta

# Create a valid token for A100
token = jwt.encode({
    "compony_code": "A100",
    "is_admin": True,
    "exp": datetime.utcnow() + timedelta(days=1)
}, "your_secret_key_here", algorithm="HS256") # wait I don't know the secret

