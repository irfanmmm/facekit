import random
from model.database import get_database
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError
from connection.officekit_onboarding import OnboardingOfficekit
from utility.jwt_utils import create_token
from utility.settings import Settings

def generate_code():
    """Generate random unique company code like A123"""
    while True:
        code = f"A{random.randint(100, 999)}"
        db = get_database()
        if code not in db.list_database_names():
            return code


class ComponyModel():
    def __init__(self, compony_code=None): 
        self.db = get_database(compony_code)
        if not isinstance(self.db, Database) or "compony_details" not in self.db.list_collection_names():
            self.db = None
            self.collection = None
            self.branchcolloction = None
        else:
            self.collection = self.db["compony_details"]
            self.collection.create_index("email", unique=True)
            self.collection.create_index("compony_code", unique=True)
            self.branchcolloction = self.db['branch_details']

    def _set(self, compony_name, name, email, password, mobile_no, emp_count, client=None):
        """Store company details"""
        if client is None:
            client = generate_code()
        data = {
            "compony_name": compony_name,
            "name": name,
            "email": email,
            "password": password,
            "mobile_no": mobile_no,
            "emp_count": emp_count,
            "compony_code": client,
        "status": "pending",
            "officekit": (client == "1353")
        }
        try:
            self.db = get_database(client)
            self.collection = self.db["compony_details"]
            # self.collection.create_index("email", unique=True)
            self.collection.create_index("compony_code", unique=True)
            self.branchcolloction = self.db['branch_details']
            self.collection.insert_one(data)
            return "success", client
        except DuplicateKeyError:
            return "faild", "Email already exists"

    def _get(self, query=None):
        """Retrieve company details (all or by query)"""
        if self.collection is None:
            return []
        if query:
            return list(self.collection.find(query, {"_id": 0}))
        return list(self.collection.find({}, {"_id": 0}))

    def _verify(self, compony_code):
        """ verify compony code and return token with settings """
        if self.collection is not None and self.collection.find_one({"compony_code": compony_code}):
            # Fetch settings using the new centralized Settings utility
            sm = Settings(compony_code)
            settings = sm.get_all()
            return "success", create_token({"compony_code": compony_code, "settings": settings})
        return "Failed", None

    def _verify_admin(self, compony_code, username, password):
        """ verify admin """
        if self.collection is not None and self.collection.find_one({"compony_code": compony_code, "email": username, "password": password}):
            return "success"
        return "Failed"

    def _branch_set(self, compony_code, branch_name, latitude, longitude, radius):
        try:
            self.db[f'branch_{compony_code}'].create_index("branch_name", unique=True)
            data = {
                "compony_code": compony_code,
                "branch_name": branch_name,
                "latitude": latitude,
                "longitude": longitude,
                "radius": radius
            }
            self.db[f'branch_{compony_code}'].insert_one(data)
            return True
        except DuplicateKeyError:
            return False

    def _get_branch(self, compony_code, offset=0, limit=10, search=None):
        try:
            # Fully dynamic settings check
            office_kit_enabled = Settings.get_setting(compony_code, "Office Kit Integration")
            if office_kit_enabled:
                connect = OnboardingOfficekit(compony_code)
                return connect.get_branch(search, offset, limit)
            else:
                # Fallback to local branches - using list() instead of to_list() for standard pymongo
                branches = list(self.db[f'branch_{compony_code}'].find({}, {"_id": 0}))
                return branches
        except (KeyError, AttributeError):
            return False

    def _get_agents(self, compony_code, branch_id):
        try:
            # Fully dynamic settings check
            office_kit_enabled = Settings.get_setting(compony_code, "Office Kit Integration")
            if office_kit_enabled:
                connect = OnboardingOfficekit(compony_code)
                return connect.get_agency(branch_id)
            else:
                # Fallback to local agents
                agents = list(self.db[f'agents_{compony_code}'].find({}, {"_id": 0}))
                return agents
        except (KeyError, AttributeError):
            return False

    def _set_agents(self, compony_code, agent_name):
        try:
            self.db[f'agents_{compony_code}'].create_index("agent_name", unique=True)
            data = {"agent_name": agent_name}
            self.db[f'agents_{compony_code}'].insert_one(data)
            return True
        except DuplicateKeyError as e:
            print(f"Error inserting agent: {str(e)}")
            return False

    def _generate_employee_code(self, compony_code):
        """Generate random unique employee code like EMP-1234"""
        while True:
            emp_code = f"EMP-{random.randint(1000, 9999)}"
            emp_collection = self.db[f'encodings_{compony_code}']
            if not emp_collection.find_one({"employee_code": emp_code}):
                return emp_code
    
    def _check_employee_code(self, compony_code, employee_code):
        emp_collection = self.db[f'encodings_{compony_code}']
        if emp_collection.find_one({"employee_code": employee_code}):
            return True
        return False
