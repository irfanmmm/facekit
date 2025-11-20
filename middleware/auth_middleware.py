from functools import wraps
from flask import request, jsonify
from utility.jwt_utils import verify_token

def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")

        if not token:
            return jsonify({"error": "Token missing"}), 401
        
        # If token contains "Bearer "
        if token.startswith("Bearer "):
            token = token.split(" ")[1]

        data = verify_token(token)
        if not data:
            return jsonify({"error": "Invalid or expired token"}), 401
        
        request.user = data
        return f(*args, **kwargs)
    return decorated
