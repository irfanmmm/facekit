import re
from functools import lru_cache
from datetime import datetime
from dateutil.relativedelta import relativedelta
import os
import base64
import math
from connection.db_officekit import get_db

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
with open("static/images/photo.png", "rb") as f:
    image_bytes = f.read()
    BASE_64_IMAGE = base64.b64encode(image_bytes).decode("utf-8")


class OnboardingOfficekit:
    def __init__(self, company_code=None):
        self.company_code = company_code
        self.conn = get_db(company_code)

    @lru_cache(maxsize=256)
    def get_employee_org(self, employee_code):
        """Look up an employee's actual branch/agency straight from OfficeKit via their
        entity assignment (HR_EMP_MASTER.LastEntity -> HighLevelViewTable.LastEntityID),
        for use when the local Mongo record was never synced with a branch/agency value."""
        if not self.conn or not employee_code:
            return None

        cursor = self.conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT h.LevelFourId AS BranchID, h.LevelFourDescription AS BranchName,
                   h.LevelFiveId AS AgencyID, h.LevelFiveDescription AS AgencyName
            FROM HR_EMP_MASTER e
            JOIN HighLevelViewTable h ON h.LastEntityID = e.LastEntity
            WHERE e.Emp_Code = %s
        """, (employee_code,))
        return cursor.fetchone()

    @lru_cache(maxsize=128)
    def get_agency(self, branch_id=None, search=None):
        if not self.conn:
            return []
        
        query = """
            SELECT LevelFiveId, LevelFiveDescription
            FROM HighLevelViewTable
        """
        conditions = []
        params = []
        if branch_id is not None:
            conditions.append("LevelFourId = %s")
            params.append(branch_id)
            
        if search:
            if type(search) == int or re.match(r'^\d+$', str(search)):
                conditions.append("LevelFiveId = %s")
                params.append(search)
            else:
                conditions.append("LevelFiveDescription LIKE %s")
                params.append(f"%{search}%")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += """
            GROUP BY LevelFiveId, LevelFiveDescription
            ORDER BY LevelFiveDescription
        """
        count_cursor = self.conn.cursor(as_dict=True)
        count_cursor.execute(query, tuple(params))
        rows = count_cursor.fetchall()
        mapped_response = []
        for row in rows:
            mapped_response.append({
                "_id": row["LevelFiveId"],
                "agent_name": row["LevelFiveDescription"],
            })
        return mapped_response
    
    @lru_cache(maxsize=128)
    def get_agency_byid(self, branch_id=None, search=None):
        if not self.conn:
            return []
        
        query = """
            SELECT LevelFiveId, LevelFiveDescription
            FROM HighLevelViewTable
        """
        conditions = []
        params = []
        if branch_id is not None:
            conditions.append("LevelFourId = %s")
            params.append(branch_id)
            
        if search:
            if type(search) == int or re.match(r'^\d+$', str(search)):
                conditions.append("LevelFiveId = %s")
                params.append(search)
            else:
                conditions.append("LevelFiveDescription LIKE %s")
                params.append(f"%{search}%")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += """
            GROUP BY LevelFiveId, LevelFiveDescription
            ORDER BY LevelFiveDescription
        """
        count_cursor = self.conn.cursor(as_dict=True)
        count_cursor.execute(query, tuple(params))
        rows = count_cursor.fetchall()
        mapped_response = []
        for row in rows:
            mapped_response.append({
                "_id": row["LevelFiveId"],
                "agent_name": row["LevelFiveDescription"],
            })
        return mapped_response

    @staticmethod
    def _minutes_to_hhmm(minutes):
        """HR_SHIFT01's *TimeMinutes columns are minutes-since-midnight - convert
        to HH:MM for the API response."""
        if minutes is None:
            return None
        try:
            total = int(round(float(minutes))) % (24 * 60)
            return f"{total // 60:02d}:{total % 60:02d}"
        except (TypeError, ValueError):
            return None

    @lru_cache(maxsize=128)
    def get_shift(self, search=None):
        """Shift master data straight from OfficeKit (HR_SHIFT00, timed via
        HR_SHIFT01) - used to populate the app's shift dropdown. A split shift
        has multiple HR_SHIFT01 rows (one per segment); we only surface the
        first segment's timing here since the dropdown just needs a name."""
        if not self.conn:
            return []

        query = """
            SELECT s0.ShiftID, s0.ShiftCode, s0.ShiftName, s0.ShiftType,
                   s1.StartTimeMinutes, s1.EndTimeMinutes
            FROM HR_SHIFT00 s0
            OUTER APPLY (
                SELECT TOP 1 StartTimeMinutes, EndTimeMinutes
                FROM HR_SHIFT01
                WHERE ShiftID = s0.ShiftID
                ORDER BY Shift01ID
            ) s1
        """
        params = []
        if search:
            if type(search) == int or re.match(r'^\d+$', str(search)):
                query += " WHERE s0.ShiftID = %s"
                params.append(search)
            else:
                query += " WHERE s0.ShiftName LIKE %s"
                params.append(f"%{search}%")
        query += " ORDER BY s0.ShiftName"

        cursor = self.conn.cursor(as_dict=True)
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        mapped_response = []
        for row in rows:
            mapped_response.append({
                "_id": row["ShiftID"],
                "shift_code": row["ShiftCode"],
                "shift_name": row["ShiftName"],
                "shift_type": row["ShiftType"],
                "start_time": self._minutes_to_hhmm(row.get("StartTimeMinutes")),
                "end_time": self._minutes_to_hhmm(row.get("EndTimeMinutes")),
            })
        return mapped_response

    def _resolve_policy_for_shift(self, shift_id):
        """Auto-pick an attendance policy from the chosen shift instead of making
        the app select one: a ~24-hour shift gets whichever policy looks like the
        tenant's round-the-clock/guard policy (if it has one), everything else
        gets the tenant's lowest-numbered (default) policy. Policies vary a lot
        per tenant with no universal "default" flag in OfficeKit, so this is the
        safest generic rule - myG has an explicit "Guard Policy" this matches
        exactly; tenants without one just always get their default policy."""
        if not self.conn or not shift_id:
            return None

        cursor = self.conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT s0.ShiftCode, s0.ShiftName, COALESCE(SUM(s1.TotalMinutes), 0) AS TotalMinutes
            FROM HR_SHIFT00 s0
            LEFT JOIN HR_SHIFT01 s1 ON s1.ShiftID = s0.ShiftID
            WHERE s0.ShiftID = %s
            GROUP BY s0.ShiftCode, s0.ShiftName
        """, (shift_id,))
        shift_row = cursor.fetchone()
        if not shift_row:
            return None

        name_blob = f"{shift_row.get('ShiftCode') or ''} {shift_row.get('ShiftName') or ''}".lower()
        is_24_hour = "24" in name_blob or (shift_row.get("TotalMinutes") or 0) >= 20 * 60

        cursor.execute("SELECT AttendancePolicyID, PolicyName FROM ATTENDANCEPOLICY00")
        policies = cursor.fetchall()
        if not policies:
            return None

        if is_24_hour:
            for p in policies:
                if "guard" in (p.get("PolicyName") or "").lower():
                    return p["AttendancePolicyID"]

        return min(p["AttendancePolicyID"] for p in policies)

    @lru_cache(maxsize=128)
    def get_branch(self, search=None, page=1, limit=10):
        page = max(1, int(page))
        limit = max(1, int(limit))
        offset = (page - 1) * limit

        if not self.conn:
            return {
                "data": [],
                "pagination": {
                    "totalRecords": 0,
                    "totalPages": 0,
                    "currentPage": page,
                    "limit": limit
                }
            }

        count_cursor = self.conn.cursor(as_dict=True)

        if self.company_code == 'A860':
            id_col = "LevelTwoId"
            desc_col = "LevelTwoDescription"
            table_name = "EntityLevelTwo"
        else:
            id_col = "LinkID"
            desc_col = "Branch"
            table_name = "BranchDetails"

        if search:
            if type(search) == int or re.match(r'^\d+$', str(search)):
                count_query = f"""
                    SELECT COUNT(DISTINCT {id_col}) AS total
                    FROM {table_name}
                    WHERE {id_col} = %s
                """
                count_cursor.execute(count_query, (search,))
            else:
                count_query = f"""
                    SELECT COUNT(DISTINCT {id_col}) AS total
                    FROM {table_name}
                    WHERE {desc_col} LIKE %s
                """
                count_cursor.execute(count_query, (f"%{search}%",))
        else:
            count_query = f"""
                SELECT COUNT(DISTINCT {id_col}) AS total
                FROM {table_name}
            """
            count_cursor.execute(count_query)

        total_records = count_cursor.fetchone()["total"]

        data_query = f"""
            SELECT {id_col}, {desc_col}
            FROM {table_name}
        """
        data_params = []

        if search:
            if type(search) == int or re.match(r'^\d+$', str(search)):
                data_query += f" WHERE {id_col} = %s"
                data_params.append(search)
            else:
                data_query += f" WHERE {desc_col} LIKE %s"
                data_params.append(f"%{search}%")

        data_query += f"""
            GROUP BY {id_col}, {desc_col}
            ORDER BY {desc_col}, {id_col}
            OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
        """
        data_params.extend([offset, limit])

        count_cursor.execute(data_query, tuple(data_params))
        rows = count_cursor.fetchall()

        mapped_response = [
            {
                "_id": row[id_col],
                "branch_name": row[desc_col],
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

    def _get_current_entity(self, employee_code):
        """Look up an already-onboarded employee's current org-entity chain
        (branch/agency/staff-level/grade/designation), keyed off
        HR_EMP_MASTER.LastEntity - the anchor a branch/agency switch needs so
        it can preserve everything except the one piece being changed."""
        cursor = self.conn.cursor(as_dict=True)
        cursor.execute("SELECT Emp_ID, LastEntity FROM HR_EMP_MASTER WHERE Emp_Code = %s", (employee_code,))
        emp = cursor.fetchone()
        if not emp:
            return None
        cursor.execute("SELECT * FROM HighLevelViewTable WHERE LastEntityID = %s", (emp["LastEntity"],))
        entity = cursor.fetchone()
        if not entity:
            return None
        entity["Emp_ID"] = emp["Emp_ID"]
        return entity

    def _resolve_entity(self, level_four_id=None, level_five_id=None, level_five_desc=None,
                         level_six_desc=None, level_seven_desc=None, level_eight_desc=None):
        """Find the HighLevelViewTable row for a target branch/agency,
        preferring one that keeps the given designation-level descriptions
        (staff-level/grade/designation) so a branch or agency switch doesn't
        silently reset an employee's designation. Falls back to any row under
        that branch/agency if no exact designation match exists."""
        cursor = self.conn.cursor(as_dict=True)

        def _rows(with_designation):
            conditions = []
            params = []
            if level_four_id is not None:
                conditions.append("LevelFourId = %s")
                params.append(level_four_id)
            if level_five_id is not None:
                conditions.append("LevelFiveId = %s")
                params.append(level_five_id)
            elif level_five_desc is not None:
                conditions.append("LevelFiveDescription = %s")
                params.append(level_five_desc)
            if with_designation:
                if level_six_desc is not None:
                    conditions.append("LevelSixDescription = %s")
                    params.append(level_six_desc)
                if level_seven_desc is not None:
                    conditions.append("LevelSevenDescription = %s")
                    params.append(level_seven_desc)
                if level_eight_desc is not None:
                    conditions.append("LevelEightDescription = %s")
                    params.append(level_eight_desc)
            query = "SELECT * FROM HighLevelViewTable"
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            cursor.execute(query, tuple(params))
            return cursor.fetchall()

        rows = _rows(with_designation=True)
        if rows:
            return rows[0], "exact"

        rows = _rows(with_designation=False)
        if rows:
            return rows[0], "fallback"

        return None, None

    def _apply_entity(self, emp_id, entity_row):
        cursor = self.conn.cursor(as_dict=True)
        emp_entity = ",".join(str(entity_row[k]) for k in (
            "LevelOneId", "LevelTwoId", "LevelThreeId", "LevelFourId",
            "LevelFiveId", "LevelSixId", "LevelSevenId", "LevelEightId"
        ))
        try:
            cursor.execute("""
                UPDATE HR_EMP_MASTER
                SET BranchID = %s, DepId = %s, BandID = %s, GradeID = %s, DesigId = %s,
                    LastEntity = %s, EmpEntity = %s
                WHERE Emp_ID = %s
            """, (
                entity_row["LevelFourId"], entity_row["LevelFiveId"], entity_row["LevelSixId"],
                entity_row["LevelSevenId"], entity_row["LevelEightId"], entity_row["LevelEightId"],
                emp_entity, emp_id
            ))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _entity_summary(self, target, match_type):
        return {
            "match_type": match_type,
            "branch_id": target["LevelFourId"], "branch_name": target["LevelFourDescription"],
            "agency_id": target["LevelFiveId"], "agency_name": target["LevelFiveDescription"],
        }

    def switch_branch(self, employee_code, new_branch_id):
        """Move an already-onboarded employee to a different branch in
        OfficeKit, keeping their current agency/staff-level/grade/designation
        if an equivalent org-entity exists under the new branch."""
        if not self.conn:
            raise ValueError("Officekit database connection is not available")

        current = self._get_current_entity(employee_code)
        if not current:
            raise ValueError(f"Employee {employee_code} not found in Officekit")

        target, match_type = self._resolve_entity(
            level_four_id=new_branch_id,
            level_five_desc=current.get("LevelFiveDescription"),
            level_six_desc=current.get("LevelSixDescription"),
            level_seven_desc=current.get("LevelSevenDescription"),
            level_eight_desc=current.get("LevelEightDescription"),
        )
        if not target:
            raise ValueError(f"No matching Officekit org entity found for branch {new_branch_id}")

        self._apply_entity(current["Emp_ID"], target)
        return self._entity_summary(target, match_type)

    def switch_agency(self, employee_code, new_agency_id):
        """Move an already-onboarded employee to a different agency in
        OfficeKit (same branch), keeping their current staff-level/grade/
        designation if an equivalent org-entity exists under that agency."""
        if not self.conn:
            raise ValueError("Officekit database connection is not available")

        current = self._get_current_entity(employee_code)
        if not current:
            raise ValueError(f"Employee {employee_code} not found in Officekit")

        target, match_type = self._resolve_entity(
            level_four_id=current.get("LevelFourId"),
            level_five_id=new_agency_id,
            level_six_desc=current.get("LevelSixDescription"),
            level_seven_desc=current.get("LevelSevenDescription"),
            level_eight_desc=current.get("LevelEightDescription"),
        )
        if not target:
            raise ValueError(f"No matching Officekit org entity found for agency {new_agency_id}")

        self._apply_entity(current["Emp_ID"], target)
        return self._entity_summary(target, match_type)

    def add_user(self, employee_code: str, branch, agency, _, fullname, gender, shift=None):
        if not self.conn:
            raise ValueError("Officekit database connection is not available")
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

            """tabele 7"""
            insert_emp_sql7 = """
                INSERT INTO BIOMETRICS_DTL (
                    CompanyID, 
                    EmployeeID,
                    DeviceID,
                    UserID,
                    EntryBy,
                    EntryDt
                )
                VALUES (    
                  %s,%s,%s,%s,%s,%s
                )
            """
            count_cursor.execute(insert_emp_sql7, (
                1, emp_id, 0, employee_code, 1, now
            ))

            """ table 8: shift assignment - without this the employee has no
            shift in OfficeKit until an admin assigns one by hand there """
            if shift:
                insert_shift_sql = """
                    INSERT INTO SHIFT_MASTER_ACCESS (
                        EmployeeID, ShiftID, IsCompanyLevel, CreatedBy, CreatedDate,
                        Active, ValidDatefrom, ValidDateTo, WeekEndMasterID,
                        ShiftApprovalID, ApprovalStatus, ProjectID
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s
                    )
                """
                count_cursor.execute(insert_shift_sql, (
                    emp_id, shift, 1, 1, now,
                    'Y', join_date, None, 0,
                    0, 'A', 0
                ))

            """ table 9: attendance policy assignment - auto-picked from the
            shift rather than app-selected (24-hour shift -> guard/round-the-
            clock policy if the tenant has one, else the tenant's default) """
            policy = self._resolve_policy_for_shift(shift) if shift else None
            if policy:
                insert_policy_sql = """
                    INSERT INTO ATTENDANCEPOLICY_MASTER_ACCESS (
                        EmployeeID, PolicyID, IsCompanyLevel, CreatedBy, CreatedDate,
                        Active, ValidDatefrom, ValidDateTo, IsExcludeBreakHours
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                """
                count_cursor.execute(insert_policy_sql, (
                    emp_id, policy, 1, 1, now,
                    'Y', join_date, None, None
                ))

            self.conn.commit()

            return emp_id
        except Exception as e:
            self.conn.rollback()
            raise e
