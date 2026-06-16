from connection.db_officekit import get_db
from functools import lru_cache


class OfficeKitPunching:
    def __init__(self, company_code):
        self.conn = get_db(company_code)
        self.company_code = company_code

    def retrieve_branch_by_user(self, emp_code):
        if not self.conn:
            return {"branchId": None}
        cursor = self.conn.cursor(as_dict=True)
        try:
            query = """
                SELECT BranchID
                FROM HR_EMP_MASTER
                WHERE Emp_Code = %s
            """
            cursor.execute(query, (emp_code,))
            employee = cursor.fetchone()

            return {
                "branchId": employee["BranchID"] if employee else None
            }

        except Exception:
            raise

    @lru_cache(maxsize=128)
    def retreve_codinates(self, branch_id):
        if not self.conn:
            return None
        cursor = self.conn.cursor(as_dict=True)
        try:
            query1 = """
                SELECT GeoEntityID
                FROM Geotagging01
                WHERE LinkID = %s
            """
            cursor.execute(query1, (branch_id,))
            geo_main = cursor.fetchone()

            if not geo_main:
                return None

            query2 = """
                SELECT Latitude, Longitude, Radius
                FROM Geotagging01A
                WHERE GeoEntityID = %s
            """
            cursor.execute(query2, (geo_main["GeoEntityID"],))
            geo_details = cursor.fetchone()

            if not geo_details:
                return None

            return {
                "latitude": float(geo_details["Latitude"]),
                "longitude": float(geo_details["Longitude"]),
                "radius": float(geo_details["Radius"])
            }

        except Exception:
            raise

    def punchin_punchout(self, direction, emp_code):
        if direction not in ("in", "out"):
            raise ValueError("Invalid punch direction")

        if not self.conn:
            raise ValueError("Officekit database connection is not available")

        cursor = self.conn.cursor(as_dict=True)

        query = """
            INSERT INTO ATTENDANCELOG_STAGING
            (DownloadDate, UserId, LogDate, Direction)
            VALUES (
                SYSDATETIMEOFFSET() AT TIME ZONE 'India Standard Time',
                %s,
                SYSDATETIMEOFFSET() AT TIME ZONE 'India Standard Time',
                %s
            )
        """

        try:
            cursor.execute(query, (emp_code, direction))
            self.conn.commit()
            return {"status": "success"}

        except Exception as e:
            self.conn.rollback()
            print(
                f"Error during punch {direction} for emp_code {emp_code}: {e}")
            raise e

    def retreve_working_hours(self, emp_code):
        if not self.conn:
            return "00:00:00"
        cursor = self.conn.cursor(as_dict=True)
        try:
            query = """
                SELECT 
                    MIN(CASE WHEN Direction = 'in' THEN LogDate END) as FirstIn,
                    MAX(CASE WHEN Direction = 'out' THEN LogDate END) as LastOut
                FROM ATTENDANCELOG_STAGING
                WHERE UserId = %s 
                AND CAST(LogDate AS DATE) = CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'India Standard Time' AS DATE)
            """

            cursor.execute(query, (emp_code,))
            result = cursor.fetchone()
            self.conn.commit()
            
            if result and result.get("FirstIn"):
                from datetime import datetime, timedelta
                first_in = result["FirstIn"]
                
                # Use LastOut if it exists, otherwise use current time (IST)
                if result.get("LastOut") and result["LastOut"] > first_in:
                    end_time = result["LastOut"]
                else:
                    end_time = datetime.utcnow() + timedelta(hours=5, minutes=30)
                
                diff = end_time - first_in
                total_seconds = max(0, int(diff.total_seconds()))
                
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                return f"{hours:02}:{minutes:02}:{seconds:02}"
            return "00:00:00"
        except Exception:
            raise