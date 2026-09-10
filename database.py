"""
database.py
Multiple MongoDB profiles ka connection management.
Har profile ka apna client cache hota hai — switch karne pe
naya connection nahi banta agar pehle se bana hua hai.
"""

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from config import settings

_clients = {}


def get_client(profile_name: str = None) -> MongoClient:
    """
    Diye gaye profile ka MongoClient deta hai (cached).
    profile_name na diya ho to abhi ka active_profile use hota hai.
    """
    profile_name = profile_name or settings.active_profile
    if profile_name not in _clients:
        profile = settings.get_profile(profile_name)
        _clients[profile_name] = MongoClient(
            profile["mongo_uri"], serverSelectionTimeoutMS=5000
        )
    return _clients[profile_name]


def get_db(profile_name: str = None):
    """Diye gaye (ya active) profile ka database object deta hai."""
    profile_name = profile_name or settings.active_profile
    profile = settings.get_profile(profile_name)
    return get_client(profile_name)[profile["db_name"]]


def check_connection(profile_name: str = None) -> bool:
    """Profile ka connection verify karta hai."""
    try:
        get_client(profile_name).admin.command("ping")
        return True
    except ConnectionFailure:
        return False
    except Exception:
        return False
