import logging
import os
import time
import schedule
import json
from flask import Flask, render_template, request, jsonify, g, send_from_directory
from flask_cors import CORS

from admin.controller import admin
from auth.controller import auth
from attandance.controller import attandance
from blueprints.branch_bp import branch_bp
from blueprints.employee_bp import employee_bp
from blueprints.attendance_bp import attendance_bp

from face_match import init_faiss_indexes
from datetime import datetime, timezone, timedelta
from model.database import get_database

IST = timezone(timedelta(hours=5, minutes=30))

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, template_folder='public/templates',
            static_folder='static', static_url_path='/static')

# Enable CORS specifically for frontend running on port 3000
CORS(app, resources={
     r"/*": {"origins": ["http://localhost:3000", "http://127.0.0.1:3000"]}})

app.register_blueprint(admin, url_prefix="/admin")
app.register_blueprint(auth, url_prefix="/auth")
app.register_blueprint(attandance, url_prefix="/attandance")
app.register_blueprint(branch_bp, url_prefix="")
app.register_blueprint(employee_bp, url_prefix="")
app.register_blueprint(attendance_bp, url_prefix="")

log_path = "logs/facekit.log"
os.makedirs(os.path.dirname(log_path), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

app_logger = app.logger
app_logger.setLevel(logging.INFO)


@app.before_request
def log_request_body():
    ip = request.access_route[0] if request.access_route else request.remote_addr
    g.start_time = time.time()

    content_type = request.headers.get("Content-Type", "").lower()
    if "multipart/form-data" in content_type:
        app.logger.info(
            f"REQUEST | {request.method} USER_IP | {ip} {request.path} | BODY: <FORM-DATA SKIPPED>"
        )
        return

    raw_body = request.get_data(as_text=True)

    try:
        data = request.get_json(silent=True)

        if isinstance(data, dict) and "base64" in data:
            masked = data.copy()
            masked["base64"] = "<BASE64_CONTENT_REMOVED>"
            app.logger.info(
                f"REQUEST | {request.method} USER_IP | {ip} {request.path} | BODY: {masked}"
            )
        else:
            app.logger.info(
                f"REQUEST | {request.method} USER_IP | {ip} {request.path} | BODY: {raw_body}"
            )

    except Exception:
        app.logger.info(
            f"REQUEST | {request.method} USER_IP | {ip} {request.path} | BODY: {raw_body}"
        )


@app.after_request
def after_request(response):
    try:
        start_time = g.start_time
        duration = time.time() - start_time
    except Exception:
        duration = 0
    try:
        ip = request.access_route[0] if request.access_route else request.remote_addr

        # Calling get_data() on streams blocks Server-Sent Events from executing
        if response.is_streamed:
            response_data = "<STREAMED_RESPONSE>"
        else:
            response_data = response.get_data(as_text=True)

        app.logger.info(
            f"REQUEST | {request.method} USER_IP | {ip} {request.path} | BODY: {response_data}")
    except Exception:
        pass
    return response


OFFICE_KIT_API_KEY = "wba1kit5p900egc12weblo2385"
OFFICE_KIT_PRIMERY_URL = "http://appteam.officekithr.net/api/AjaxAPI/MobileUrl"


@app.route("/app-version", methods=['GET'])
def app_version():
    db = get_database("AppVersion")

    if "appversion" not in db.list_collection_names():
        db.create_collection("appversion")

    collection = db["appversion"]

    version = collection.find_one({}, {"_id": 0})
    return jsonify({"message": "success", "version": version})


@app.route('/')
def home():
    return jsonify({"message": "Welcome to AttendEase API", "status": "success"})


@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory('face_match/uploads', filename)


if __name__ == "__main__":
    init_faiss_indexes()
    app.run(debug=True, port=5001, host="0.0.0.0")
