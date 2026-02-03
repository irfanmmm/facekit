from connection.db_officekit import conn
from functools import lru_cache


class OfficeKitPunching:
    def __init__(self):
        self.conn = conn

    def retrieve_branch_by_user(self, emp_code):
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
