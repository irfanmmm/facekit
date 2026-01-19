from datetime import datetime
from dateutil.relativedelta import relativedelta
import os
import base64
import math
from connection.db_officekit import conn

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
with open("static/images/photo.png", "rb") as f:
    image_bytes = f.read()
    BASE_64_IMAGE = base64.b64encode(image_bytes).decode("utf-8")


class OnboardingOfficekit:
    def __init__(self):

        self.conn = conn

    def get_agency(self, branch_id):
        query = """
            SELECT LevelFiveId, LevelFiveDescription
            FROM HighLevelViewTable
            WHERE LevelFourId = %s
            GROUP BY LevelFiveId, LevelFiveDescription
            ORDER BY LevelFiveDescription
        """
        count_cursor = self.conn.cursor(as_dict=True)
        count_cursor.execute(query, (branch_id,))
        rows = count_cursor.fetchall()
        mapped_response = []
        for row in rows:
            mapped_response.append({
                "_id": row["LevelFiveId"],
                "agent_name": row["LevelFiveDescription"],
            })
        return mapped_response

    def get_branch(self, search=None, page=1, limit=10):
        page = max(1, int(page))
        limit = max(1, int(limit))
        offset = (page - 1) * limit

        count_cursor = self.conn.cursor(as_dict=True)

        if search:
            count_query = """
                SELECT COUNT(DISTINCT LinkID) AS total
                FROM BranchDetails
                WHERE Branch LIKE %s
            """
            count_cursor.execute(count_query, (f"%{search}%",))
        else:
            count_query = """
                SELECT COUNT(DISTINCT LinkID) AS total
                FROM BranchDetails
            """
            count_cursor.execute(count_query)

        total_records = count_cursor.fetchone()["total"]

        data_query = """
            SELECT LinkID, Branch
            FROM BranchDetails
        """
        data_params = []

        if search:
            data_query += " WHERE Branch LIKE %s"
            data_params.append(f"%{search}%")

        data_query += """
            GROUP BY LinkID, Branch
            ORDER BY Branch, LinkID
            OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
        """
        data_params.extend([offset, limit])

        count_cursor.execute(data_query, tuple(data_params))
        rows = count_cursor.fetchall()

        mapped_response = [
            {
                "_id": row["LinkID"],
                "branch_name": row["Branch"],
            }
            for row in rows
        ]

        return {
            "data": mapped_response,
            "pagination": {
                "totalRecords": total_records,
                "totalPages": math.ceil(total_records / limit),
                "currentPage": page,
                "limit": limit
            }
        }

    def add_user(self, employee_code: str, branch, agency, _, fullname, gender):
        try:
            now = datetime.now()
            join_date = now
            probation_date = join_date + relativedelta(months=3)
            insert_emp_sql = """
                INSERT INTO HR_EMP_MASTER (
                    Emp_Code,First_Name,DateOfBirth,Gender,Join_Dt,
                    emp_status,Probation_Dt,Is_probation,Notice_period,
                    BranchID,DepId,BandID,GradeID,DesigId,
                    Entry_By,Entry_Dt,CompanyID,LastEntity,CurrentStatus,
                    EmpFirstEntity,EmpEntity,IsVerified,SeperationStatus,
                    ISHRA,CountryOfBirth,FirstEntryDate,PublicHoliday,IsExpat,
                    CompanyConveyance,CompanyVehicle,InitialDate,ModifiedDate,
                    MealAllowanceDeduct,InitialPaymentPending,IsDelete,IsSave,
                    UpdatedBy,UpdatedDate,EmpFileNumber,CanteenRequest,Inst_Id
                )
                OUTPUT INSERTED.Emp_ID
                VALUES (
                    %s,%s,%s,%s,%s,
                    %s,%s,%s,%s,
                    %s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,
                    %s,%s,%s,%s,
                    %s,%s,%s,%s,%s,
                    %s,%s,%s,%s,
                    %s,%s,%s,%s,
                    %s,%s,%s,%s,%s
                )
            """

            find_branch_id_query = """
                SELECT *
                FROM HighLevelViewTable
                WHERE LevelFourId = %s
                AND LevelFiveId = %s
                """
            count_cursor = self.conn.cursor(as_dict=True)
            count_cursor.execute(find_branch_id_query, (branch, agency))
            firt_row = count_cursor.fetchone()

            level1 = firt_row.get("LevelOneId")
            level2 = firt_row.get("LevelTwoId")
            level3 = firt_row.get("LevelThreeId")
            level4 = firt_row.get("LevelFourId")
            level5 = firt_row.get("LevelFiveId")
            level6 = firt_row.get("LevelSixId")
            level7 = firt_row.get("LevelSevenId")
            level8 = firt_row.get("LevelEightId")
            emp_entity = f"{level1},{level2},{level3},{level4},{level5},{level6},{level7},{level8}"

            count_cursor.execute(insert_emp_sql, (
                employee_code, fullname, "1995-01-01", gender, join_date,
                1, probation_date, 0, 30,
                level4, level5, level6, level7, level8,
                1, now, 1, level8, 7,
                level1, emp_entity, 0, 0,
                0, 71, now, 0, 0,
                0, 0, now, now,
                0, 0, 0, 0,
                1, now, "", 0, 1
            ))

            emp_id = count_cursor.fetchone()['Emp_ID']

            # self.conn.commit()

            """ tabele 2 """
            insert_emp_sql2 = """
                INSERT INTO ADM_User_Master (
                    UserName,
                    DetailedName,
                    Password,
                    EntryDate,
                    active,
                    status,
                    Email,
                    need_app
                )
                OUTPUT INSERTED.UserID
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """
            count_cursor.execute(insert_emp_sql2, (
                employee_code,                  # UserName
                fullname,                       # DetailedName
                'kohNZpjfnsZdZdiqvYllow==',      # Password
                datetime.now(),                 # EntryDate
                'Y',                            # active
                'Y',                            # status
                'NIL',                          # Email
                0                               # need_app
            ))

            user_id = count_cursor.fetchone()["UserID"]
            # self.conn.commit()

            """ tabele 3 """
            insert_emp_sql3 = """
                INSERT INTO HR_EMPLOYEE_USER_RELATION (
                    UserId,
                    Emp_Id,
                    Entry_By,
                    Entry_Dt,
                    inst_Id
                )
                VALUES (
                    %s, %s, %s, %s, %s
                )
                """
            count_cursor.execute(insert_emp_sql3, (
                user_id, emp_id, 1, now, 1
            ))

            """ tabele 4 """
            insert_emp_sql4 = """
                INSERT INTO ADM_UserRoleMaster (
                    Role_Id, 
                    User_Id,
                    Acess,
                    inst_Id
                )
                VALUES (
                    %s,%s,%s,%s
                )
            """
            count_cursor.execute(insert_emp_sql4, (
                1, user_id, 1, 1
            ))

            """ tabele 5 """
            insert_emp_sql5 = """
                INSERT INTO HR_EMP_IMAGES (
                    inst_Id, 
                    emp_id,
                    image_url,
                    active,
                    finger_url,
                    Emp_image
                )
                VALUES ( 
                    %s, %s,%s,%s,%s,%s
                )
            """

            count_cursor.execute(insert_emp_sql5, (
                1, emp_id, 'default.jpg', 'Y', 'default.jpg', BASE_64_IMAGE
            ))

            """ tabele 6 """
            insert_emp_sql6 = """
                INSERT INTO HR_EMP_ADDRESS (
                    inst_Id, 
                    Emp_Id,
                    Add_Type,
                    Entry_By,
                    Entry_Dt
                )
                VALUES (
                  %s,%s,%s,%s,%s
                )
            """
            count_cursor.execute(insert_emp_sql6, (
                1, emp_id, 1, 1, now
            ))
            self.conn.commit()

            return emp_id
        except Exception as e:
            self.conn.rollback()
            raise e
