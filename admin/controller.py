from flask import Blueprint, render_template, request, jsonify, Response
from admin.admin_service.login import login_user, ADMIN_PASSWORD, ADMIN_USERNAME
from admin.admin_service.componys import list_componys
from admin.admin_service.settings import list_settings
from middleware.auth_middleware import jwt_required, super_admin_required, resolve_compony_code
from utility.jwt_utils import verify_token
import os
import time


admin = Blueprint('admin', __name__)


@admin.route('/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    username = data.get("username")
    password = data.get("password")
    if not all([username, password]):
        return jsonify({"message": "username and password are required"}), 400

    token = login_user(username, password)
    if not token:
        return jsonify({"message": "Invalid username or password"}), 401
    return jsonify({"token": token})

@admin.route('/componys', defaults={'id': None})
@admin.route('/componys/<id>')
@jwt_required
@super_admin_required
def list_compon(id):
    print("List componys called with id:", id)
    return jsonify({"componys": list_componys(id)})


@admin.route('/list-settings', methods=['POST'])
@jwt_required
@super_admin_required
def list_setting():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 415
    compony_code = data.get("compony_code")
    return jsonify({"settings": list_settings(compony_code)})


@admin.route('/set-portal-credentials', methods=['POST'])
@jwt_required
@super_admin_required
def set_portal_credentials_route():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    compony_code = data.get("compony_code")
    admin_username = data.get("admin_username")
    admin_password = data.get("admin_password")

    if not all([compony_code, admin_username, admin_password]):
        return jsonify({"message": "compony_code, admin_username and admin_password are required"}), 400

    from admin.admin_service.componys import set_portal_credentials
    result = set_portal_credentials(compony_code, admin_username, admin_password)

    if result.get("error"):
        return jsonify({"message": result["error"]}), 400

    return jsonify({"message": "success"})


@admin.route('/update-client-status', methods=['POST'])
@jwt_required
@super_admin_required
def update_status():
    data = request.get_json()
    compony_code = data.get("compony_code")
    status = data.get("status")
    from admin.admin_service.componys import update_client_status
    update_client_status(compony_code, status)
    return jsonify({"message": "success"})


@admin.route('/dashboard-stats', methods=['GET'])
@jwt_required
@super_admin_required
def dashboard_stats():
    from admin.admin_service.dashboard import get_dashboard_stats
    return jsonify(get_dashboard_stats())

@admin.route('/fech-client-details', methods=['POST'])
@jwt_required
def fech_client_details():
    data = request.get_json()
    compony_code = resolve_compony_code(request.user, data.get("compony_code"))
    limit = data.get("limit", 10)
    offset = data.get("offset", 0)
    date = data.get("date")
    from admin.admin_service.componys import fech_client_details
    return jsonify({"client_details": fech_client_details(compony_code, limit, offset, date)})

@admin.route('/fech-client-details-search', methods=['POST'])
@jwt_required
def fech_client_details_search_route():
    data = request.get_json()
    compony_code = resolve_compony_code(request.user, data.get("compony_code"))
    search = data.get("search")
    branch = data.get("branch")
    agency = data.get("agency")
    name = data.get("name")
    employee_code = data.get("employee_code")
    limit = data.get("limit", 10)
    offset = data.get("offset", 0)
    date = data.get("date")
    from admin.admin_service.componys import fech_client_details_search
    return jsonify({"client_details": fech_client_details_search(compony_code, search, limit, offset, date, branch, agency, name, employee_code)})

@admin.route('/register', methods=['POST'])
@jwt_required
@super_admin_required
def register():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 415
    from admin.admin_service.componys import create_company
    response = create_company(data)
    return jsonify({"response": response})


@admin.route('/get-settings', methods=['GET'])
@jwt_required
@super_admin_required
def get_settings_route():
    compony_code = request.args.get("compony_code")
    if not compony_code:
        return jsonify({"message": "compony_code is required"}), 400
    from admin.admin_service.settings import list_settings
    return jsonify({"settings": list_settings(compony_code)})


@admin.route('/update-settings', methods=['POST'])
@jwt_required
@super_admin_required
def update_settings_route():
    data = request.get_json()
    compony_code = data.get("compony_code")
    setting_name = data.get("setting_name")
    value = data.get("value")

    if not all([compony_code, setting_name]) or value is None:
        return jsonify({"message": "Missing required fields"}), 400

    from admin.admin_service.settings import update_settings
    update_settings(compony_code, setting_name, value)
    return jsonify({"message": "success"})


@admin.route('/attendance-list', methods=['GET'])
@jwt_required
def attendance_list_route():
    starting_date = request.args.get("starting_date")
    ending_date = request.args.get("ending_date")
    compony_code = resolve_compony_code(request.user, request.args.get("compony_code"))
    employee_code = request.args.get("employee_code")

    if not all([compony_code, employee_code]):
        return jsonify({"message": "compony_code and employee_code are required"}), 400

    from admin.admin_service.attendance import get_all_attendance
    result = get_all_attendance(starting_date, ending_date, compony_code, employee_code)
    return jsonify({"message": "success", "data": result})

@admin.route('/download/attandance', methods=['GET'])
@jwt_required
def download_attendance():
    starting_date = request.args.get("starting_date")
    ending_date = request.args.get("ending_date")
    compony_code = resolve_compony_code(request.user, request.args.get("compony_code"))

    if not all([compony_code]):
        return jsonify({"message": "compony_code required"}), 400

    from admin.admin_service.download import download_attendance
    result = download_attendance(starting_date, ending_date, compony_code)

    import pandas as pd
    from io import BytesIO
    
    df = pd.DataFrame(result)
    
    csv_buffer = BytesIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)
    from flask import send_file
    
    # Create a response with the CSV data
    return send_file(
        csv_buffer,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'attendance_{compony_code}_{starting_date}_to_{ending_date}.csv'
    )
    

@admin.route('/download/employee_details', methods=['GET'])
@jwt_required
def download_employee_details_route():
    compony_code = resolve_compony_code(request.user, request.args.get("compony_code"))
    branch = request.args.get("branch")
    employee_id = request.args.get("employee_id")
    
    if not all([compony_code]):
        return jsonify({"message": "compony_code required"}), 400
    
    from admin.admin_service.download import download_employee_details
    pdf_path = download_employee_details(compony_code, branch, employee_id)

    from flask import send_file
    import os
    
    if not pdf_path or not os.path.exists(pdf_path):
        return jsonify({"message": "No data found or error generating PDF"}), 404
    
    return send_file(
        pdf_path,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'employee_details_{compony_code}.pdf'
    )
    





@admin.route('/list-duplicate-faces', methods=['POST'])
@jwt_required
@super_admin_required
def list_duplicate_faces_route():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    compony_code = data.get("compony_code")
    threshold = data.get("threshold", 0.85)

    if not compony_code:
        return jsonify({"message": "compony_code is required"}), 400

    from admin.admin_service.duplicates import list_duplicate_faces
    result = list_duplicate_faces(compony_code, threshold)

    if result.get("error"):
        return jsonify({"message": result["error"]}), 400

    return jsonify(result)


@admin.route('/list-bad-face-records', methods=['POST'])
@jwt_required
@super_admin_required
def list_bad_face_records_route():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    compony_code = data.get("compony_code")
    threshold = data.get("threshold", 0.85)

    if not compony_code:
        return jsonify({"message": "compony_code is required"}), 400

    from admin.admin_service.duplicates import list_bad_face_records
    result = list_bad_face_records(compony_code, threshold)

    if result.get("error"):
        return jsonify({"message": result["error"]}), 400

    return jsonify(result)


@admin.route('/merge-duplicate-employees', methods=['POST'])
@jwt_required
@super_admin_required
def merge_duplicate_employees_route():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    compony_code = data.get("compony_code")
    primary_employee_code = data.get("primary_employee_code")
    duplicate_employee_code = data.get("duplicate_employee_code")

    if not all([compony_code, primary_employee_code, duplicate_employee_code]):
        return jsonify({"message": "compony_code, primary_employee_code and duplicate_employee_code are required"}), 400

    from admin.admin_service.duplicates import merge_duplicate_employees
    result = merge_duplicate_employees(compony_code, primary_employee_code, duplicate_employee_code)

    if result.get("error"):
        return jsonify({"message": result["error"]}), 400

    return jsonify({"message": "success"})


@admin.route('/force-delete-employee', methods=['POST'])
@jwt_required
@super_admin_required
def force_delete_employee_route():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    compony_code = data.get("compony_code")
    employee_code = data.get("employee_code")

    if not all([compony_code, employee_code]):
        return jsonify({"message": "compony_code and employee_code are required"}), 400

    from admin.admin_service.componys import force_delete_employee
    result = force_delete_employee(compony_code, employee_code)

    if result.get("error"):
        return jsonify({"message": result["error"]}), 400

    return jsonify({"message": "success"})


@admin.route('/delete-employee', methods=['POST'])
@jwt_required
@super_admin_required
def delete_employee_route():
    """Facekit-only delete: removes the employee from Facekit's own database
    without touching Officekit. See /force-delete-employee for the variant
    that also removes the employee from Officekit."""
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    compony_code = data.get("compony_code")
    employee_code = data.get("employee_code")

    if not all([compony_code, employee_code]):
        return jsonify({"message": "compony_code and employee_code are required"}), 400

    from admin.admin_service.componys import delete_employee_facekit_only
    result = delete_employee_facekit_only(compony_code, employee_code)

    if result.get("error"):
        return jsonify({"message": result["error"]}), 400

    return jsonify({"message": "success"})


@admin.route('/get-branch', methods=['POST'])
@jwt_required
@super_admin_required
def admin_get_branch_route():
    data = request.get_json() or {}
    compony_code = data.get("compony_code")
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"}), 400

    from admin.admin_service.componys import list_branches
    result = list_branches(
        compony_code,
        search=data.get("search"),
        offset=data.get("offset") or 1,
        limit=data.get("limit") or 1000,
    )

    if result.get("error"):
        return jsonify({"message": result["error"]}), 400

    return jsonify({"message": "success", "details": result["data"]})


@admin.route('/get-agency', methods=['POST'])
@jwt_required
@super_admin_required
def admin_get_agency_route():
    data = request.get_json() or {}
    compony_code = data.get("compony_code")
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"}), 400

    from admin.admin_service.componys import list_agencies
    result = list_agencies(compony_code, branch_id=data.get("branch_id"), search=data.get("search"))

    if result.get("error"):
        return jsonify({"message": result["error"]}), 400

    return jsonify({"message": "success", "details": result["data"]})


@admin.route('/switch-branch', methods=['POST'])
@jwt_required
@super_admin_required
def switch_branch_route():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    compony_code = data.get("compony_code")
    employee_code = data.get("employee_code")
    branch_id = data.get("branch_id")

    if not all([compony_code, employee_code]) or branch_id is None:
        return jsonify({"message": "compony_code, employee_code and branch_id are required"}), 400

    from admin.admin_service.componys import switch_employee_branch
    result = switch_employee_branch(compony_code, employee_code, branch_id)

    if result.get("error"):
        return jsonify({"message": result["error"]}), 400

    return jsonify({"message": "success", "details": result.get("officekit")})


@admin.route('/switch-agency', methods=['POST'])
@jwt_required
@super_admin_required
def switch_agency_route():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    compony_code = data.get("compony_code")
    employee_code = data.get("employee_code")
    agency_id = data.get("agency_id")

    if not all([compony_code, employee_code]) or agency_id is None:
        return jsonify({"message": "compony_code, employee_code and agency_id are required"}), 400

    from admin.admin_service.componys import switch_employee_agency
    result = switch_employee_agency(compony_code, employee_code, agency_id)

    if result.get("error"):
        return jsonify({"message": result["error"]}), 400

    return jsonify({"message": "success", "details": result.get("officekit")})

    if result.get("error"):
        return jsonify({"message": result["error"]}), 404

    return jsonify({"message": "success"})


@admin.route('/live-logs')
def live_logs():
    # Since EventSource (SSE in Javascript) doesn't support Authorization headers easily, 
    # we verify the JWT token via query parameter.
    token = request.args.get("token")
    token_data = verify_token(token) if token else None
    if not token_data or token_data.get("role") != "super_admin":
        return jsonify({"error": "Invalid or expired token"}), 401

    def generate():
        log_file = "logs/facekit.log"
        import collections
        
        # 1. Provide Initial Context (Last 100 lines)
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    last_lines = collections.deque(f, maxlen=100)
                    for line in last_lines:
                        yield f"data: {line}\n\n"
            except Exception as e:
                yield f"data: Error reading initial logs: {str(e)}\n\n"

        # 2. Enter Live Tailing Loop
        last_pos = os.path.getsize(log_file) if os.path.exists(log_file) else 0
        last_heartbeat = time.time()
        
        while True:
            # Detect if file was rotated or truncated
            if os.path.exists(log_file):
                try:
                    curr_size = os.path.getsize(log_file)
                    if curr_size < last_pos:
                        # File was truncated or rotated (replaced with smaller file)
                        last_pos = 0 
                    
                    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_pos)
                        while True:
                            line = f.readline()
                            if not line:
                                last_pos = f.tell()
                                break
                            yield f"data: {line}\n\n"
                            last_heartbeat = time.time() # Reset heartbeat on data
                except Exception:
                    # Ignore temporary file access errors
                    pass
            
            # 3. Internal Keep-Alive Heartbeat (every 15s)
            if time.time() - last_heartbeat > 5:
                yield ": heartbeat\n\n"
                last_heartbeat = time.time()
            
            # Small sleep to prevent CPU spiking, but low enough for "fully live" feel
            time.sleep(0.1)

    # Set the mimetype to text/event-stream which activates SSE logic on the client browser
    return Response(generate(), mimetype='text/event-stream')
