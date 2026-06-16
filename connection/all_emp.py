from connection.db_officekit import get_db
from model.database import get_database
from utility.settings import Settings

class AllEmp:
    def __init__(self, company_code):
        self.company_code = company_code
        self.conn = get_db(company_code)
        self.db = get_database(company_code)
        self.encoding_db = self.db[f"encodings_{company_code}"]
        
    def get_all_emp(self, offset=0, limit=10, search=None, branch_id=None):
        sm = Settings(self.company_code)
        enable_create_user = sm.get("Enable Create User")

        where_conditions = ["SeperationStatus = 0"]
        where_params = []
        
        if enable_create_user:
            existing_docs = list(self.encoding_db.find({}, {"employee_code": 1}))
            existing_codes_all = [doc['employee_code'] for doc in existing_docs if doc.get('employee_code')]
            
            if not existing_codes_all:
                return {"data": [], "total": 0, "offset": int(offset), "limit": int(limit)}
            
            # SQL Server parameter limit is 2100. Using 2000 for safety.
            if len(existing_codes_all) <= 2000:
                placeholders = ', '.join(['%s'] * len(existing_codes_all))
                where_conditions.append(f"Emp_Code IN ({placeholders})")
                where_params.extend(existing_codes_all)
            else:
                # If more than 2000, we use a subset to avoid SQL errors
                subset = existing_codes_all[:2000]
                placeholders = ', '.join(['%s'] * len(subset))
                where_conditions.append(f"Emp_Code IN ({placeholders})")
                where_params.extend(subset)
        
        if search:
            where_conditions.append("(Emp_Code LIKE %s OR First_Name LIKE %s)")
            search_param = f"%{search}%"
            where_params.extend([search_param, search_param])
            
        if branch_id:
            where_conditions.append("BranchID = %s")
            where_params.append(branch_id)
            
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        count_q = f"SELECT COUNT(*) as total FROM HR_EMP_MASTER {where_clause}"
        cursor = self.conn.cursor(as_dict=True)
        cursor.execute(count_q, tuple(where_params))
        total_count = cursor.fetchone()['total']
        
        data_q = f"""
            SELECT First_Name, Last_Name, Emp_Code, Gender, BranchID FROM HR_EMP_MASTER
            {where_clause}
            ORDER BY Emp_Code
            OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
        """
        data_params = where_params + [int(offset), int(limit)]
        cursor.execute(data_q, tuple(data_params))
        rows = cursor.fetchall()
        cursor.close()

        for row in rows:
            if row.get('Emp_Code'):
                row['Emp_Code'] = str(row['Emp_Code']).strip()

        emp_codes = [row['Emp_Code'] for row in rows]
        existing_codes = set()
        if emp_codes:
            existing_docs = self.encoding_db.find(
                {"employee_code": {"$in": emp_codes}},
                {"employee_code": 1}
            )
            existing_codes = {doc['employee_code'] for doc in existing_docs}

        data = []
        for row in rows:
            is_exist = row['Emp_Code'] in existing_codes
            if enable_create_user and not is_exist:
                continue
                
            data.append({
                **row,
                "exist": is_exist
            })

        return {
            "data": data, 
            "total": total_count, 
            "offset": int(offset), 
            "limit": int(limit)
        }

    
