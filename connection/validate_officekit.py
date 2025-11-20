from connection.db_officekit import cursor, conn
from model.database import get_database


class Validate():
    def __init__(self, compony_code, employee_code):
        self.db = get_database()
        self.collection = self.db['compony_details']
        self.compony_code = compony_code
        self.employee_code = employee_code
        self.user_details = None

    def validate_employee(self):
        if self.collection.find_one({"compony_code": self.compony_code, "officekit": True}):
            query = """
                SELECT *
                FROM HR_EMP_MASTER
                WHERE emp_code = %s
            """
            cursor.execute(query, (self.employee_code))
            result = cursor.fetchone()
            if result:
                columns = [col[0] for col in cursor.description]
                row_dict = dict(zip(columns, result))
                self.user_details  = row_dict
                return True, row_dict
            return False, None
        elif self.collection.find_one({"compony_code": self.compony_code, "officekit": False}):
            if self.collection.find_one({"employee_id": self.employee_code}):
                return False, None
            else:
                return False, None
        return False, None

    def insert_log(self, direction):
        query = """
            INSERT INTO ATTENDANCELOG_STAGING
            (DownloadDate, UserId, LogDate, Direction)
            VALUES (GETUTCDATE(), %s, GETUTCDATE(), %s)
        """
        user_id = self.user_details['Emp_Code']
        cursor.execute(query, (user_id, direction))
        conn.commit()

    def log_user(self, direction):
        query = """
                SELECT *
                FROM ATTENDANCELOG_STAGING
                WHERE employee_code = %s
            """
