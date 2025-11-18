# database.py
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from config import MONGO_URI

client = MongoClient(MONGO_URI, server_api=ServerApi('1'))

try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")
    client = None

db = client['pharmasearch'] if client else None