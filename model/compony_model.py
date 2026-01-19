import random
from model.database import get_database
from pymongo.errors import DuplicateKeyError
from connection.officekit_onboarding import OnboardingOfficekit
from utility.jwt_utils import create_token
from model.database import get_database
from admin.admin_service.settings import setting

def generate_code():
    """Generate random unique company code like A123"""
    while True:
        code = f"A{random.randint(100, 999)}"
        db = get_database()
        for db_names in db.list_database_names():
            # Ensure uniqueness
            if not db_names == code:
                return code


class ComponyModel():
    def __init__(self, compony_code=None):
        self.db = get_database(compony_code)
        if "compony_details" not in self.db.list_collection_names():
            self.db = None
            self.collection = None
            self.branchcolloction = None
        else:
            self.collection = self.db["compony_details"]
            # self.settings_colloction = self.db["settings"]
            self.collection.create_index("email", unique=True)
            self.collection.create_index("compony_code", unique=True)
            self.branchcolloction = self.db['branch_details']

    def _set(self, compony_name, name, email, password, mobile_no, emp_count, client=None):
        """Store company details"""
        data = {
            "compony_name": compony_name,
            "name": name,
            "email": email,
            "password": password,
            "mobile_no": mobile_no,
            "emp_count": emp_count,
            "compony_code": client,
            "status": "pending"
        }
        if client == "1353":
            data["officekit"] = True
        else:
            data["officekit"] = False
        try:

            self.db = get_database(client)
            self.collection = self.db["compony_details"]
            self.collection.create_index("email", unique=True)
            self.collection.create_index("compony_code", unique=True)
            self.branchcolloction = self.db['branch_details']
            self.collection.insert_one(data)
            return "success", client
        except DuplicateKeyError:
            return "faild", "Email already exists"

    def _get(self, query=None):
        """Retrieve company details (all or by query)"""
        if query:
            return list(self.collection.find(query, {"_id": 0}))
        return list(self.collection.find({}, {"_id": 0}))

    def _verify(self, compony_code):
        """ verify compony code """
        if self.collection is not None and self.collection.find_one({"compony_code": compony_code, "status": "active"}):
            db = get_database("SettingsDB")
            settings_collection = db[f"settings_{compony_code}"]
            settings = settings_collection.find({}, {"_id": 0}).to_list()
            if not settings:
                settings_collection.insert_many(setting)
                for s in setting:
                    s.pop("_id", None)

                settings = setting
            return "success", create_token({"compony_code": compony_code, "settings": settings})
        return "Failed", None

    def _verify_admin(self, compony_code, username, password):
        """ verify admin """
        if self.collection.find_one({"compony_code": compony_code, "email": username, "password": password}):
            return "success"
        return "Failed"

    def _branch_set(self, compony_code, branch_name, latitude, longitude, radius):
        try:
            self.db[f'branch_{compony_code}'].create_index(
                "branch_name", unique=True)

            data = {
                "compony_code": compony_code,
                "branch_name": branch_name,
                "latitude": latitude,
                "longitude": longitude,
                "radius": radius
            }
            self.db[f'branch_{compony_code}'].insert_one(data)
            return True
        except DuplicateKeyError as e:
            return False

    def _get_branch(self, compony_code, offset=0, limit=10, search=None):
        try:
            settings = get_database("SettingsDB")
            _filter = {
                "setting_name": "Office Kit Integration"
            }
            brancheEnable = settings[f'settings_{compony_code}'].find_one(
                _filter)
            if brancheEnable.get("value"):
                connect = OnboardingOfficekit()
                return connect.get_branch(search, offset, limit)
            else:
                branches = self.db[f'branch_{compony_code}'].find(
                    {}, {"_id": 0}).to_list()
                return branches
        except KeyError:
            return False

    def _get_agents(self, compony_code, branch_id):
        try:
            settings = get_database("SettingsDB")
            _filter = {
                "setting_name": "Office Kit Integration"
            }
            brancheEnable = settings[f'settings_{compony_code}'].find_one(
                _filter)
            if brancheEnable.get("value"):
                from connection.officekit_onboarding import OnboardingOfficekit
                connect = OnboardingOfficekit()
                return connect.get_agency(branch_id)
            else:
                agents = self.db[f'agents_{compony_code}'].find(
                    {}, {"_id": 0}).to_list()
                return agents
        except KeyError:
            return False

    def _set_agents(self, compony_code, agent_name):
        try:
            self.db[f'agents_{compony_code}'].create_index(
                "agent_name", unique=True)
            data = {
                "agent_name": agent_name,
            }
            self.db[f'agents_{compony_code}'].insert_one(data)
            return True
        except DuplicateKeyError as e:
            print(f"Error inserting agent:  {str(e)}")
            return False

    def _generate_employee_code(self, compony_code):
        """Generate random unique employee code like E1234"""
        while True:
            emp_code = f"EMP-{random.randint(1000, 9999)}"
            # Ensure uniqueness
            emp_collection = self.db[f'encodings_{compony_code}']
            if not emp_collection.find_one({"employee_code": emp_code}):
                return emp_code
