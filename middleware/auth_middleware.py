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


def super_admin_required(f):
    """Must be stacked below @jwt_required so request.user is already populated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.user.get("role") != "super_admin":
            return jsonify({"message": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated


def resolve_compony_code(user, requested_code=None):
    """Client admins are locked to their own company regardless of what the request asks for."""
    if user.get("role") == "client_admin":
        return user.get("compony_code")
    return requested_code
