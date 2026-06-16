from datetime import datetime, timedelta
from model.database import get_database

def download_attendance(starting_date=None, ending_date=None, compony_code=None, branch=None, employee_id=None):
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
                if employee_id:
                    query["employee_id"] = employee_id
                
                if branch:
                    query["branch"] = branch
                    
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
                            "first_in": "",
                            "last_out": "",
                            "fist_in_last": ""
                        }
                    
                    if rec.get("log_details"):
                        if not employee_wise_attendance[emp_id]["first_in"]:
                            employee_wise_attendance[emp_id]["first_in"] = rec.get("log_details")[0]["time"]
                        employee_wise_attendance[emp_id]["last_out"] = rec.get("log_details")[-1]["time"]

                    # Format log_details and calculate working time
                    # formatted_logs = []
                    valid_logs_for_calc = []
                    for log in rec.get("log_details", []):
                        log_time = log.get("time")
                        time_str = log_time.strftime("%Y-%m-%d %H:%M:%S") if isinstance(log_time, datetime) else str(log_time)
                        # formatted_logs.append({
                        #     "direction": log.get("direction"),
                        #     "time": time_str
                        # })
                        
                        # Prepare for calculation
                        calc_time = log_time
                        if isinstance(calc_time, str):
                            try:
                                calc_time = datetime.strptime(calc_time, "%Y-%m-%d %H:%M:%S")
                            except ValueError:
                                pass
                                
                        if isinstance(calc_time, datetime):
                            valid_logs_for_calc.append({"direction": log.get("direction"), "time": calc_time})

                    # Calculate total working time
                    valid_logs_for_calc.sort(key=lambda x: x["time"])
                    
                    total_seconds_normal = 0
                    last_in_time = None
                    first_in_time = None
                    last_out_time = None
                    
                    for log in valid_logs_for_calc:
                        direction = log.get("direction")
                        if isinstance(direction, str):
                            direction = direction.upper()
                            
                        if direction == "IN":
                            if first_in_time is None:
                                first_in_time = log["time"]
                            last_in_time = log["time"]
                        elif direction == "OUT":
                            last_out_time = log["time"]
                            if last_in_time is not None:
                                total_seconds_normal += (log["time"] - last_in_time).total_seconds()
                                last_in_time = None
                                
                    def format_seconds(secs):
                        if secs < 0:
                            secs = 0
                        hours = int(secs // 3600)
                        minutes = int((secs % 3600) // 60)
                        seconds = int(secs % 60)
                        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                        
                    total_working_time_normal = format_seconds(total_seconds_normal)
                    
                    total_working_time_filo = "00:00:00"
                    if first_in_time and last_out_time and last_out_time >= first_in_time:
                        total_working_time_filo = format_seconds((last_out_time - first_in_time).total_seconds())
                    
    return list(employee_wise_attendance.values())

def download_employee_details(compony_code, branch=None, employee_id=None):
    from model.database import get_database
    import os
    import glob
    from fpdf import FPDF
    
    db = get_database(compony_code)
    collection = db[f'encodings_{compony_code}']
    
    query = {}
    if branch:
        query["branch"] = branch
    if employee_id:
        query["employee_code"] = employee_id
        
    users = list(collection.find(query, {"_id": 0, "encodings": 0}))
    
    class PDF(FPDF):
        def header(self):
            self.set_font('helvetica', 'B', 15)
            self.cell(0, 10, 'Employee Details Report', border=0, align='C', new_x="LMARGIN", new_y="NEXT")
            self.ln(5)

    pdf = PDF()
    pdf.set_auto_page_break(auto=False)
    
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    uploads_path = os.path.join(BASE_DIR, "face_match", "uploads")
    
    margin_x = 10
    margin_y = 25
    item_width = 38
    item_height = 31.5
    items_per_page = 40
    
    from PIL import Image
    
    for idx, user in enumerate(users):
        if idx % items_per_page == 0:
            pdf.add_page()
            
        page_idx = idx % items_per_page
        col = page_idx % 5
        row = page_idx // 5
        
        start_x = margin_x + (col * item_width)
        start_y = margin_y + (row * item_height)
        
        emp_code = user.get("employee_code", "")
        fullname = user.get("fullname", "")
        branch_name = user.get("branch", "N/A")
        agency = user.get("agency", "N/A")
        
        # Border
        pdf.rect(start_x, start_y, item_width - 2, item_height - 2)
        
        # Determine image path
        pattern = os.path.join(uploads_path, f"user_{emp_code}*")
        matching_files = glob.glob(pattern)
        img_path = None
        for mf in matching_files:
            if mf.endswith('.jpg') or mf.endswith('.png') or mf.endswith('.jpeg'):
                img_path = mf
                break
                
        # Image rendering with compression
        img_size = 15
        if img_path and os.path.exists(img_path):
            try:
                temp_img_path = f"/tmp/res_{emp_code}.jpg"
                with Image.open(img_path) as im:
                    # Convert to RGB to avoid issues saving as JPEG
                    if im.mode != 'RGB':
                        im = im.convert('RGB')
                    im.thumbnail((100, 100))
                    im.save(temp_img_path, format="JPEG", quality=75)
                
                img_x = start_x + (item_width - 2 - img_size) / 2
                pdf.image(temp_img_path, x=img_x, y=start_y + 1, w=img_size, h=img_size)
            except Exception:
                pass
                
        # Details rendering
        text_y = start_y + 1 + img_size + 1
        pdf.set_font("helvetica", "", 5)
        
        pdf.set_xy(start_x + 1, text_y)
        pdf.cell(item_width - 4, 3, f"Code: {str(emp_code)[:20]}", border=0, align='C')
        
        pdf.set_xy(start_x + 1, text_y + 3)
        pdf.cell(item_width - 4, 3, f"Name: {str(fullname)[:20]}", border=0, align='C')
        
        pdf.set_xy(start_x + 1, text_y + 6)
        pdf.cell(item_width - 4, 3, f"Branch: {str(branch_name)[:20]}", border=0, align='C')
        
        pdf.set_xy(start_x + 1, text_y + 9)
        pdf.cell(item_width - 4, 3, f"Agency: {str(agency)[:20]}", border=0, align='C')
        
    if not users:
        pdf.add_page()
        pdf.set_font("helvetica", "", 12)
        pdf.cell(0, 10, "No users found.", border=0, align='C', new_x="LMARGIN", new_y="NEXT")
        
    temp_pdf_path = f"/tmp/employee_details_{compony_code}.pdf"
    pdf.output(temp_pdf_path)
    
    return temp_pdf_path