import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-please-change'
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'simdemocracy.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Discord Config
    DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID')
    DISCORD_CLIENT_SECRET = os.environ.get('DISCORD_CLIENT_SECRET')
    DISCORD_REDIRECT_URI = os.environ.get('DISCORD_REDIRECT_URI')
    DISCORD_API_BASE_URL = 'https://discord.com/api/v10'
    
    # Admins: Loaded from .env (comma-separated string) -> List
    # Example .env: ADMIN_IDS=123456,987654
    raw_admins = os.environ.get('ADMIN_IDS')
    ADMIN_IDS = raw_admins.split(',') if raw_admins else []