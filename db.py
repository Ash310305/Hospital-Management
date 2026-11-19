import os
from functools import lru_cache

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()


@lru_cache(maxsize=1)
def get_database():
    client = MongoClient(
        os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=5000,
    )
    return client[os.getenv("MONGODB_DATABASE", "hospital_management")]
