from pymongo import MongoClient

def get_database():
    CONNECTION_URL = "mongodb+srv://admin:123@attandance.e24v5se.mongodb.net/?retryWrites=true&w=majority&appName=Attandanc"
    client = MongoClient(CONNECTION_URL)
    return client['Attandance'] 