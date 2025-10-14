import threading
import time
import schedule
import json
from flask import Flask, request, jsonify
from face_match.face_ml import FaceAttendance, job
from model.compony_model import ComponyModel
from model.user_model import UserModel
from helper.trigger_mail import send_mail_with_template

app = Flask(__name__)

OFFICE_KIT_API_KEY = "wba1kit5p900egc12weblo2385"
OFFICE_KIT_PRIMERY_URL = "http://appteam.officekithr.net/api/AjaxAPI/MobileUrl"

# ---------------- DB Connection ----------------

attendance = FaceAttendance()  # initialize once
componyCode = ComponyModel()  # initialize once
userdetails = UserModel()


""" Register user """


@app.route('/signup', methods=['POST'])
def sighnup():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body received"}), 400

    compony_name = data.get("compony_name")
    _name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    mobile_no = data.get("mobile_no")
    emp_count = data.get("emp_count")

    if not all([compony_name, _name, email, password, mobile_no, emp_count]):
        return jsonify({"error": "Missing required fields"})
    message, company_code = componyCode._set(
        compony_name, _name, email, password, mobile_no, emp_count)
    if message == "faild":
        return jsonify({"message": company_code})
    status = send_mail_with_template(email, email, password, company_code, '')
    if status:
        return jsonify({"message": message})
    else:
        return jsonify({"message": "somthing went wrong"})


@app.route("/verify-compony-code", methods=['POST'])
def verify_compony_code():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    compony_code = data.get("code")
    if not compony_code:
        return jsonify({"message": "compony code is requerd"})
    message = componyCode._verify(compony_code)
    if message == "success":
        return jsonify({"message": message})

    return jsonify({"message": message})


@app.route("/verify-admin", methods=['POST'])
def verify_admin():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    username = data.get("username")
    password = data.get("password")
    compony_code = data.get("compony_code")

    if not all([username, password, compony_code]):
        return jsonify({"message": "Missing required fields"})

    message = componyCode._verify_admin(compony_code, username, password)
    return jsonify({"message": message})


@app.route("/add-branch", methods=['POST'])
def add_branch():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = data.get('compony_code')
    branch_name = data.get('branch_name')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    radius = data.get("radius")
    if not all([branch_name, latitude, longitude, compony_code, radius]):
        return jsonify({"error": "Missing required fields"})
    status = componyCode._branch_set(
        compony_code, branch_name, latitude, longitude, radius)
    if status:
        return jsonify({"message": "success"})
    return jsonify({"message": "Falid"})


@app.route("/get-branch", methods=['POST'])
def get_branches():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = data.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    branches = componyCode._get_branch(
        compony_code)
    if branches:
        return jsonify({"message": "success", "details": branches})
    return jsonify({"message": "Falid"})


@app.route("/add-employee-face", methods=['POST'])
def add_employee_face():
    if 'file' in request.files:
        data = request.form
        file = request.files.get('file')
        fullname = data.get('fullname')
        employeecode = data.get('employeecode')
        compony_code = data.get('compony_code')
        branch = data.get('branch')
        if not all([fullname, employeecode, compony_code, branch]):
            return jsonify({"error": "Missing required fields"})

        status = attendance.update_face(
            employee_code=employeecode, branch=branch, add_img=file, company_code=compony_code, fullname=fullname)
        if status:
            return jsonify({"message": "success"})
        return jsonify({"message": "Faild"})

    return jsonify({"message": "file is missing"})


@app.route("/compare-face", methods=['POST'])
def comare_face():
    if 'file' in request.files:
        file = request.files.get('file')
        data = request.form
        compony_code = data.get('compony_code')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        if not all([compony_code, latitude, longitude]):
            return jsonify({"message": "fill requerd fileds"})
        match, message = attendance.compare_faces(
            file, compony_code, latitude, longitude)
        if match:
            return jsonify({"message": "success" if isinstance(message, dict) else (message or "success"), "details": match})
        else:
            return jsonify({"message": "Faild" if isinstance(message, dict) else (message or "Faild")})
        # return jsonify({"message": "Faild"})
    return jsonify({"message": "file is missing"})


@app.route("/all-employees", methods=['POST'])
def all_employees():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = data.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    data = userdetails.get_all_users(compony_code=compony_code)
    return jsonify({"message": "success", "data": data})


@app.route("/attandance-report", methods=['POST'])
def attandance_report():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = data.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    employee_code = data.get('employee_code')
    if not employee_code:
        return jsonify({"message": "employee_code is requerd"})

    starting_date = data.get('starting_date')
    if not starting_date:
        return jsonify({"message": "starting_date is requerd"})

    ending_date = data.get('ending_date')
    if not ending_date:
        return jsonify({"message": "ending_date is requerd"})

    data = userdetails.get_attandance_report(
        compony_code=compony_code, employee_code=employee_code, starting_date=starting_date, ending_date=ending_date)
    return jsonify({"message": "success", "data": data})


@app.route("/attandance-report-all", methods=['POST'])
def attandance_report_all():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = data.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})

    date = data.get("date")
    if not date:
        return jsonify({"message": "date is requerd"})

    data = userdetails.get_attandance_report_all(
        compony_code=compony_code, date=date)
    return jsonify({"message": "success", "data": data})


@app.route("/edit-attandance", methods=['POST'])
def edit_attandance():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = data.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    # employee_code = data.get('employee_code')

    """ [{'employee_id':'1','action':'P' | 'PL' | 'UL' | 'H'}] """
    editable_details = data.get("editable_details")
    if not editable_details:
        return jsonify({"message": "editable_details is requerd"})

    editad_date = data.get("date")
    if not editad_date:
        return jsonify({"message": "editad_date is requerd"})

    message = userdetails.edit_attandance_report(
        compony_code=compony_code, emploee_list_with_action=editable_details, editad_date=editad_date)
    if message:
        return jsonify({"message": message})
    return jsonify({"message": "Faild"})


@app.route("/edit-user", methods=['POST'])
def edit_user():
    data = request.form
    compony_code = data.get("compony_code")
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    editable_details_raw = data.get("editable_details")
    editable_details = json.loads(
        editable_details_raw) if editable_details_raw else []
    editable_details_files = []
    for i, emp in enumerate(editable_details):
        editable_details_files.append({
            "employee_id": emp['employee_id'],
            "branch": emp["branch"],
            "action": emp['action'],
            "full_name": emp['full_name'] if emp['full_name'] else None,
            "file": request.files.get(f"file_{i}") if request.files.get(f"file_{i}") else None
        })
    if editable_details_files:
        message = userdetails.edit_user_details(
            compony_code, editable_details_files)
        return jsonify({"message": message})
    return jsonify({"message": "Faild"})


@app.route("/logs", methods=['POST'])
def get_logs():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = data.get("compony_code")
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    from_date = data.get("from_date")
    to_date = data.get("to_date")
    page = data.get("page")
    limit = data.get("limit")
    counts, data = attendance.get_logs(
        compony_code, from_date, to_date, page=page, limit=limit)
    return jsonify({"message": "success", "counts": counts, "data": data})


@app.route('/')
def home():
    return 'AttendEase APP API'


def run_scheduler():
    schedule.every(1).hours.do(job)
    while True:
        schedule.run_pending()
        time.sleep(1)


threading.Thread(target=run_scheduler, daemon=True).start()

if __name__ == "__main__":
    app.run(debug=True, port=5001, host="0.0.0.0")
