import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID"))

# পাসওয়ার্ড এনকোড করা (স্পেশাল ক্যারেক্টার হ্যান্ডেল করার জন্য)
user = os.getenv("DB_USER")
password = quote_plus(os.getenv("DB_PASS")) # এখানে @# এনকোড হবে
host = os.getenv("DB_HOST")
port = os.getenv("DB_PORT")
db_name = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}"