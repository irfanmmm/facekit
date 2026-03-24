from flask import Blueprint, render_template, request, jsonify, Response
from admin.admin_service.login import login_user, ADMIN_PASSWORD, ADMIN_USERNAME
from admin.admin_service.componys import list_componys
from admin.admin_service.settings import list_settings
from middleware.auth_middleware import jwt_required
from utility.jwt_utils import verify_token
import os
import time


admin = Blueprint('admin', __name__)


@admin.route('/login', methods=['POST'])
def admin_login():
    data = request.get_json()

    username = data.get("username")
    password = data.get("password")
    if ADMIN_PASSWORD != password or ADMIN_USERNAME != username:
        return jsonify({"message": "Invalid username or password"}), 401
    token = login_user(username, password)
    return jsonify({"token": token})

@admin.route('/componys', defaults={'id': None})
@admin.route('/componys/<id>')
@jwt_required
def list_compon(id):
    print("List componys called with id:", id)
    return jsonify({"componys": list_componys(id)})


@admin.route('/list-settings', methods=['POST'])
@jwt_required
def list_setting():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 415
    compony_code = data.get("compony_code")
    return jsonify({"settings": list_settings(compony_code)})


@admin.route('/update-settings', methods=['POST'])
def update_settings():
    data = request.get_json()
    compony_code = data.get("compony_code")
    new_settings = data.get("settings")
    value = data.get("value")
    from admin.admin_service.settings import update_settings
    update_settings(compony_code, new_settings , value)
    return jsonify({"message": "success"})


@admin.route('/update-client-status', methods=['POST'])
@jwt_required
def update_status():
    data = request.get_json()
    compony_code = data.get("compony_code")
    status = data.get("status")
    from admin.admin_service.componys import update_client_status
    update_client_status(compony_code, status)
    return jsonify({"message": "success"})


@admin.route('/dashboard')
def dashboard():
    return render_template('admin_template.html')

@admin.route('/dashboard-stats', methods=['GET'])
@jwt_required
def dashboard_stats():
    from admin.admin_service.dashboard import get_dashboard_stats
    return jsonify(get_dashboard_stats())

@admin.route('/fech-client-details', methods=['POST'])
@jwt_required
def fech_client_details():
    data = request.get_json()
    compony_code = data.get("compony_code")
    limit = data.get("limit", 10)
    offset = data.get("offset", 0)
    from admin.admin_service.componys import fech_client_details
    return jsonify({"client_details": fech_client_details(compony_code, limit, offset)})

@admin.route('/fech-client-details-search', methods=['POST'])
@jwt_required
def fech_client_details_search_route():
    data = request.get_json()
    compony_code = data.get("compony_code")
    search = data.get("search")
    limit = data.get("limit", 10)
    offset = data.get("offset", 0)
    from admin.admin_service.componys import fech_client_details_search
    return jsonify({"client_details": fech_client_details_search(compony_code, search, limit, offset)})





@admin.route('/live-logs')
def live_logs():
    # Since EventSource (SSE in Javascript) doesn't support Authorization headers easily, 
    # we verify the JWT token via query parameter.
    token = request.args.get("token")
    if not token or not verify_token(token):
        return jsonify({"error": "Invalid or expired token"}), 401

    def generate():
        log_file = "logs/facekit.log"
        if not os.path.exists(log_file):
            yield "data: Log file not found\n\n"
            return
            
        import collections
        with open(log_file, "r") as f:
            # Read the file and keep only the last 10 lines in memory
            last_lines = collections.deque(f, maxlen=100)
            
            for line in last_lines:
                # Yield the last 10 lines to the frontend for immediate context
                yield f"data: {line}\n\n"
                
            # Ensure the pointer is at the absolute end to begin tailing live
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    # Sleep slightly if nothing is newly written, then try again
                    time.sleep(0.5)
                    continue
                # SSE Event structure must be "data: <message>\n\n"
                yield f"data: {line}\n\n"

    # Set the mimetype to text/event-stream which activates SSE logic on the client browser
    return Response(generate(), mimetype='text/event-stream')
