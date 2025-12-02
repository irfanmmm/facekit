
import csv
import io
from flask import Blueprint, app, jsonify, request, Response
from datetime import datetime, timedelta
from model.database import get_database
from middleware.auth_middleware import jwt_required
from helper.format_duration import format_duration

attandance = Blueprint('attandance', __name__)
IST_OFFSET = timedelta(hours=5, minutes=30)


@attandance.route('/download-report')
def download_report():
    compony_code = request.args.get("compony_code")
    starting_at = request.args.get("starting_at")
    ending_at = request.args.get("ending_at")

    # Validate
    if not compony_code or not starting_at or not ending_at:
        return jsonify({"error": "Missing required URL parameters"}), 400
    db = get_database(compony_code)
    """ attandance_150_2025-11 """
    year_month = starting_at[:7]
    collection = db[f'attandance_{compony_code}_{year_month}']
    usercollection = db[f'encodings_{compony_code}']
    start_date = datetime.strptime(starting_at, "%Y-%m-%d")
    end_date = datetime.strptime(ending_at, "%Y-%m-%d") + timedelta(days=1)
    records = list(collection.find({
        "date": {
            "$gte": start_date,
            "$lt": end_date
        }
    }, {"_id": 0}))

    if not records:
        return jsonify({"message": "No records found"})

    """ Process records and generate report (e.g., CSV or Excel) """
    # For demonstration, we'll just return the records as JSON
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Employee ID", "Full Name", "Branch", "Agency", "Date", "First In", "Last Out",
                    "Total Working Time", "Present"])

    for record in records:
        log_details = record.get("log_details", [])

        if not log_details:
            continue

        # Convert log times to IST and sort
        logs_ist = [
            {
                "direction": log.get("direction"),
                "time": log.get("time") + IST_OFFSET
            }
            for log in log_details
        ]

        logs_ist.sort(key=lambda x: x["time"])

        # Extract First In & Last Out
        first_in = next((log["time"]
                        for log in logs_ist if log["direction"] == "in"), None)
        last_out = next((log["time"] for log in reversed(
            logs_ist) if log["direction"] == "out"), None)

        # Build logs string
        logs_string = "\n".join(
            f"{log['direction']} - {log['time'].strftime('%Y-%m-%d %H:%M:%S')}"
            for log in logs_ist
        )

        userdetails = usercollection.find_one(
            {"employee_code": record.get("employee_id")})
        writer.writerow([
            record.get("employee_id"),
            record.get("fullname"),
            userdetails.get("branch", "N/A"),
            userdetails.get("agency", "N/A"),
            (record.get("date") + IST_OFFSET).strftime('%Y-%m-%d') if record.get("date") else "",
            first_in.strftime('%Y-%m-%d %H:%M:%S') if first_in else "",
            last_out.strftime('%Y-%m-%d %H:%M:%S') if last_out else "",
            format_duration(record.get("total_working_time", 0)),
            record.get("present", "Working"),
        ])
    csv_data = output.getvalue()
    output.close()
    filename = f"attendance_report_{compony_code}_{starting_at}_to_{ending_at}.csv"

    import os
    save_dir = "./reports"  # You can change the path
    os.makedirs(save_dir, exist_ok=True)

    save_path = os.path.join(save_dir, filename)

    with open(save_path, "w", encoding="utf-8", newline="") as f:
        f.write(csv_data)

    print("File saved to:", save_path)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
