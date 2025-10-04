from model.database import get_database 
from datetime import datetime, timedelta
from face_match.face_ml import FaceAttendance
# import datetime

# def is_sunday(year):
#     sundays = []
#     # Start from January 1st
#     date = datetime.date(year, 1, 1)
#     # Loop through each day of the year
#     while date.year == year:
#         if date.weekday() == 6:  # Sunday is 6
#             sundays.append(date)
#         date += datetime.timedelta(days=1)
#     return sundays


class UserModel():
    def __init__(self):
        self.db = get_database()
        
    def get_all_users(self, compony_code):
        collection = self.db[f'encodings_{compony_code}']
        return collection.find({},{"_id":0,"encodings":0}).to_list()
    
    def edit_user_details(self,compony_code, editable_details):
        available_actions = ['E', 'D']

        if not isinstance(editable_details, list) or not editable_details:
            return "editable_details must be a non-empty list"
        for details in editable_details:
            try:
                if available_actions not in details['action']:
                    return "action not available"

                if details['action'] == 'E':
                    required_fields = ['employee_id', 'full_name', 'file']
                    missing_fields = [f for f in required_fields if not details.get(f)]
                    if missing_fields:
                        return f"Missing fields: {', '.join(missing_fields)}"
                    # if not all(details['employee_id'], details['full_name'], details['file']):
                    #     return "full detials not available"
                    
                    face_details = FaceAttendance()
                    status = face_details.update_face(
                        details['employee_id'],
                        details['file'],
                        compony_code,
                        details['full_name'],
                    )
                    if status:
                        return "Faild"
                    
                elif details['action'] == 'D':
                    colloction = self.db[f"encodings_{compony_code}"]
                    _filter = {
                        "employee_code":details['employee_id']
                    }
                    result  = colloction.delete_one(_filter)
                    if result.deleted_count > 0:
                        pass
                    else:
                        return "Employee not found for deletion"
            except Exception as e:
                return f"Exception occurred: {str(e)}"
            
        return "success"

    
    def edit_attandance_report(self, compony_code,emploee_list_with_action,editad_date):
        """ [{'employee_id':'1','action':'P' | 'PL' | 'UL' | 'H'}] """
        # action

        remarks = ['P' , 'PL' ,'UL' , 'H']
        for emploee_dict in emploee_list_with_action:
            if remarks not in emploee_dict['action']:
                return "action not available"
            colloction = self.db[f"attandance_{compony_code}_{datetime.utcnow().strftime('%Y-%m')}"]
            starting_at=datetime.strptime(editad_date, "%Y-%m-%d")
            ending_at=datetime.strptime(editad_date, "%Y-%m-%d")  + timedelta(days=1)
            _filter = {"employee_id":emploee_dict['employee_id'],"date":{"$gte": starting_at, "$lt": ending_at}}
            colloction.update_one(_filter,{
                "$set":{
                    "present":emploee_dict['action']
                }
            })
            print("success")
        return "success"
        
    def get_attandance_report(self,compony_code, employee_code,starting_date, ending_date):
        # collection = self.db[f'attandance_{compony_code}']
        collection = self.db[f"attandance_{compony_code}_{datetime.utcnow().strftime('%Y-%m')}"]
        # 2025-10-01 formate
        starting_at=datetime.strptime(starting_date, "%Y-%m-%d")
        ending_at=datetime.strptime(ending_date, "%Y-%m-%d")  + timedelta(days=1)
        _filter = {"employee_id":employee_code,"date": {"$gte": starting_at, "$lt": ending_at}}
        employee_log_list = collection.find(_filter,{"_id":0, "log_details":0}).to_list()
        return employee_log_list