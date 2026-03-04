from connection.db_officekit import get_db
from model.database import get_database


class Validate():
    def __init__(self, compony_code, employee_code, isAdmin=False):
        self.db = get_database(compony_code)
        self.collection = self.db['compony_details']
        self.compony_code = compony_code
        self.employee_code = employee_code
        self.user_details = None
        self.isAdmin = isAdmin
        self.conn = get_db(compony_code)
        self.cursor = self.conn.cursor()

    def validate_employee(self):
        if self.collection.find_one({"compony_code": self.compony_code, "officekit": True}):
            query = """
                SELECT *
                FROM HR_EMP_MASTER
                WHERE emp_code = %s
            """
            self.cursor.execute(query, (self.employee_code))
            result = self.cursor.fetchone()
            if result:
                columns = [col[0] for col in self.cursor.description]
                row_dict = dict(zip(columns, result))
                self.user_details = row_dict
                return True, row_dict
            return False, None
        elif self.collection.find_one({"compony_code": self.compony_code, "officekit": False}):
            if self.collection.find_one({"employee_code": self.employee_code}):
                return True, None
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
        self.cursor.execute(query, (user_id, direction))
        self.conn.commit()

    def log_user(self, direction):
        query = """
                SELECT *
                FROM ATTENDANCELOG_STAGING
                WHERE employee_code = %s
            """
