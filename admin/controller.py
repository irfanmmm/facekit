from flask import Blueprint, render_template, request, jsonify
from admin.admin_service.login import login_user, ADMIN_PASSWORD, ADMIN_USERNAME
from admin.admin_service.componys import list_componys
from admin.admin_service.settings import list_settings
from middleware.auth_middleware import jwt_required


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
