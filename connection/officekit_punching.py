from connection.db_officekit import conn


class OfficeKitPunching:
    def __init__(self):
        self.cursor = conn.cursor(as_dict=True)
        self.conn = conn

    def retreve_branche_by_user(self,emp_code):
        query = """SELECT *  FROM HR_EMP_MASTER where Emp_Code  = %s"""
        self.cursor.execute(query, (emp_code,))
        employee_details = self.cursor.fetchone()
        if not employee_details:
            return {
                 "branchId":None
            }
        return {
            "branchId":employee_details.get("BranchID")
        }
    def retreve_codinates(self, branch):
        query1 = """
        SELECT *
        FROM Geotagging01
        WHERE LinkID = %s
        """
        self.cursor.execute(query1, (branch,))
        geo_main = self.cursor.fetchone()

        if not geo_main:
            return None

        geo_entity_id = geo_main.get("GeoEntityID")

        query2 = """
            SELECT *
            FROM Geotagging01A
            WHERE GeoEntityID = %s
        """
        self.cursor.execute(query2, (geo_entity_id,))
        geo_details = self.cursor.fetchone()

        return {
            "latitude": float(geo_details.get("Latitude")),
            "longitude": float(geo_details.get("Longitude")),
            "radius":float(geo_details.get("Radius"))
        }

    def punchin_punchout(self, direction, emp_code):
        query = """
            INSERT INTO ATTENDANCELOG_STAGING
            (DownloadDate, UserId, LogDate, Direction)
            VALUES (GETUTCDATE(), %s, GETUTCDATE(), %s)
        """

        self.cursor.execute(query, (emp_code, direction))
        self.conn.commit()
        return
