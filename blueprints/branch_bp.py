from flask import Blueprint, request, jsonify
from middleware.auth_middleware import jwt_required
from model.compony_model import ComponyModel

branch_bp = Blueprint('branch', __name__)

@branch_bp.route("/add-branch", methods=['POST'])
@jwt_required
def add_branch():
    user = request.user
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = user.get('compony_code')
    branch_name = data.get('branch_name')

    for setting in user.get("settings"):
        if setting.get("setting_name") == "Location Tracking":
            if setting.get("value", False):
                if not data.get('latitude') or not data.get('longitude') or not data.get('radius'):
                    return jsonify({"message": "latitude, longitude and radius are required"})

            latitude = data.get('latitude', None)
            longitude = data.get('longitude', None)
            radius = data.get("radius", None)

    componyCode = ComponyModel(compony_code)
    status = componyCode._branch_set(
        compony_code, branch_name, latitude, longitude, radius)
    if status:
        return jsonify({"message": "success"})
    return jsonify({"message": "Failed"})

@branch_bp.route("/get-branch",  methods=['POST'])
@jwt_required
def get_branches():
    user = request.user
    compony_code = user.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})

    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    offset = data.get("offset")
    limit = data.get("limit")
    search = data.get("search")

    componyCode = ComponyModel(compony_code)
    branches = componyCode._get_branch(
        compony_code, offset, limit, search)
    if branches:
        return jsonify({"message": "success", "details": branches})
    return jsonify({"message": "Failed"})

@branch_bp.route("/get-agency", methods=['POST'])
@jwt_required
def get_agencys():
    user = request.user
    compony_code = user.get('compony_code')
    data = request.get_json()
    branch_id = data.get('_id')

    if not data or not branch_id:
        return jsonify({"message": "No JSON body received"}), 400

    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    componyCode = ComponyModel(compony_code)
    agencys = componyCode._get_agents(
        compony_code, branch_id)
    if agencys:
        return jsonify({"message": "success", "details": agencys})
    return jsonify({"message": "Failed"})

@branch_bp.route("/set-agency", methods=['POST'])
@jwt_required
def set_branches():
    user = request.user
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    agency = data.get('agency')
    if not agency:
        return jsonify({"message": "agency is requerd"})
    compony_code = user.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    componyCode = ComponyModel(compony_code)
    agencys = componyCode._set_agents(
        compony_code, agency)
    if agencys:
        return jsonify({"message": "success"})
    return jsonify({"message": "Failed"})
