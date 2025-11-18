import random
from model.database import get_database
from pymongo.errors import DuplicateKeyError


class ComponyModel():
    def __init__(self):
        self.db = get_database()
        self.collection = self.db['compony_details']
        self.collection.create_index("email", unique=True)
        self.collection.create_index("compony_code", unique=True)
        self.branchcolloction = self.db['branch_details']

    def _generate_code(self):
        """Generate random unique company code like A123"""
        while True:
            code = f"A{random.randint(100, 999)}"
            # Ensure uniqueness
            if not self.collection.find_one({"compony_code": code}):
                return code

    def _set(self, compony_name, name, email, password, mobile_no, emp_count, client=None):
        """Store company details"""
        if not client:
            compony_code = self._generate_code()
        elif client == "150":
            compony_code = client
        else:
            return "faild", "Falid this compony code"
        data = {
            "compony_name": compony_name,
            "name": name,
            "email": email,
            "password": password,
            "mobile_no": mobile_no,
            "emp_count": emp_count,
            "compony_code": compony_code
        }
        if client:
            data["officekit"] = True
        else:
            data["officekit"] = False
        try:
            self.collection.insert_one(data)
            return "success", compony_code
        except DuplicateKeyError:
            return "faild", "Email already exists"

    def _get(self, query=None):
        """Retrieve company details (all or by query)"""
        if query:
            return list(self.collection.find(query, {"_id": 0}))
        return list(self.collection.find({}, {"_id": 0}))

    def _verify(self, compony_code):
        """ verify compony code """
        if self.collection.find_one({"compony_code": compony_code}):
            return "success"
        return "Faild"

    def _verify_admin(self, compony_code, username, password):
        """ verify admin """
        if self.collection.find_one({"compony_code": compony_code, "email": username, "password": password}):
            return "success"
        return "Faild"

    def _branch_set(self, compony_code, branch_name, latitude, longitude, radius):
        try:
            data = {
                "compony_code": compony_code,
                "branch_name": branch_name,
                "latitude": latitude,
                "longitude": longitude,
                "radius": radius,
            }
            self.db[f'branch_{compony_code}'].insert_one(data)
            return True
        except DuplicateKeyError:
            return False

    def _get_branch(self, compony_code):
        try:
            branches = self.db[f'branch_{compony_code}'].find(
                {}, {"_id": 0}).to_list()
            return branches
        except KeyError:
            return False
