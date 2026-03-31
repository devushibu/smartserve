from pymongo import MongoClient

client = MongoClient("mongodb+srv://devushibu28_db_user:abcd123@programming.z6edehb.mongodb.net/?appName=programming")

db = client["smartserve_db"]

users = db["users"]
providers = db["providers"]
bookings = db["bookings"]
payments = db["payments"]
time_slots = db["time_slots"]