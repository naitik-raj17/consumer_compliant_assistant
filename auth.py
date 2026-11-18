import logging
import sqlite3

import bcrypt
from pydantic import ValidationError

import db
from models import RegisterIn, friendly

log = logging.getLogger(__name__)


class AuthError(Exception):
    pass


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, pw_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], pw_hash.encode())
    except ValueError:
        return False


def register(name: str, email: str, password: str) -> dict:
    try:
        data = RegisterIn(name=name, email=email, password=password)
    except ValidationError as e:
        raise AuthError(friendly(e)) from None
    if db.get_user_by_email(data.email):
        raise AuthError("This email is already registered.")
    try:
        uid = db.create_user(data.name, data.email, hash_password(data.password), "consumer")
    except sqlite3.IntegrityError:
        raise AuthError("This email is already registered.") from None
    log.info("Registered user %s", uid)
    return db.get_user(uid)


def login(email: str, password: str) -> dict:
    email = (email or "").strip().lower()
    user = db.get_user_by_email(email)
    if not user or not verify_password(password or "", user["pw_hash"]):
        log.info("Failed login for %s", email)
        raise AuthError("Invalid email or password.")
    if not user["active"]:
        raise AuthError("This account has been deactivated. Contact the administrator.")
    log.info("User %s logged in", user["id"])
    return user
