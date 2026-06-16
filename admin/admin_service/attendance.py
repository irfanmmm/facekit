from model.database import get_database, exclude
from datetime import datetime, timedelta

def get_all_attendance(starting_date=None, ending_date=None, compony_code=None, employee_code=None):
    """
    Service to retrieve attendance records for all companies and employees.
    Supports filtering by date range, specific company, and specific employee.
    """
    client = get_database()
    
    # Default to current date if not provided
    now = datetime.utcnow()
    if not starting_date:
        starting_date = now.strftime("%Y-%m-%d")
    if not ending_date:
        ending_date = now.strftime("%Y-%m-%d")
        
    try:
        start_dt = datetime.strptime(starting_date, "%Y-%m-%d")
        end_dt = datetime.strptime(ending_date, "%Y-%m-%d")
    except ValueError:
        # Fallback if date format is invalid
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = start_dt
        
    end_dt_query = end_dt + timedelta(days=1)
    
    # Determine companies to check
    companies = []
    if compony_code:
        companies = [compony_code]
    else:
        all_dbs = client.list_database_names()
        companies = [db for db in all_dbs if db not in exclude]
        
    # Dictionary to group by employee_id
    employee_wise_attendance = {}
    
    for company in companies:
        db = client[company]
        
        # Get relevant months for the query
        months = set()
        current = start_dt
        while current < end_dt_query:
            months.add(current.strftime("%Y-%m"))
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1, day=1)
            else:
                current = current.replace(month=current.month + 1, day=1)
        
        for month in months:
            coll_name = f"attandance_{company}_{month}"
            if coll_name in db.list_collection_names():
                collection = db[coll_name]
                
                # Build query
                query = {
                    "date": {"$gte": start_dt, "$lt": end_dt_query}
                }
                if employee_code:
                    query["employee_id"] = employee_code
                    
                records = list(collection.find(query, {"_id": 0}))
                
                for rec in records:
                    emp_id = rec.get("employee_id")
                    if not emp_id:
                        continue
                        
                    # Initialize employee entry if not exists
                    if emp_id not in employee_wise_attendance:
                        employee_wise_attendance[emp_id] = {
                            "employee_id": emp_id,
                            "fullname": rec.get("fullname"),
                            "compony_code": company,
                            "attendance_records": []
                        }
                    
                    # Format log_details
                    formatted_logs = []
                    for log in rec.get("log_details", []):
                        log_time = log.get("time")
                        time_str = log_time.strftime("%Y-%m-%d %H:%M:%S") if isinstance(log_time, datetime) else str(log_time)
                        formatted_logs.append({
                            "direction": log.get("direction"),
                            "time": time_str
                        })
                    
                    # Format record date
                    date_str = rec.get("date").strftime("%Y-%m-%d") if isinstance(rec.get("date"), datetime) else str(rec.get("date"))
                    
                    employee_wise_attendance[emp_id]["attendance_records"].append({
                        "date": date_str,
                        "present": rec.get("present"),
                        "total_working_time": rec.get("total_working_time"),
                        "logs": formatted_logs
                    })
                    
    # Return as a list of employees for easier frontend iteration
    return list(employee_wise_attendance.values())


