import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or None
    DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
    APP_ENV = os.getenv("APP_ENV", "production").strip().lower()
    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "America/Sao_Paulo").strip()
    DEBUG = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = APP_ENV == "production"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = APP_ENV == "production"
