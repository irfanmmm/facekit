from pymongo import MongoClient

def get_database():
    CONNECTION_URL = "mongodb://localhost:27017/"
    client = MongoClient(CONNECTION_URL)
    return client['Attandance'] 