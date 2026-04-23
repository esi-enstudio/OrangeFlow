import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID"))
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", 8080))
FORWARD_OTPS_TO = os.getenv("FORWARD_OTPS_TO")
START_NGROK = os.getenv("START_NGROK", "False") == "True"
STATIC_DOMAIN = os.getenv("STATIC_DOMAIN")
DISABLE_SCHEDULER = os.getenv("DISABLE_SCHEDULER", "False") == "True"



# excel_wa_sync.py হেডলেস মুড কন্ট্রোল (স্ট্রিং থেকে বুলিয়ান এ রূপান্তর)
HEADLESS = os.getenv("HEADLESS_MODE", "True").lower() == "true"

# পাসওয়ার্ড এনকোড করা (স্পেশাল ক্যারেক্টার হ্যান্ডেল করার জন্য)
user = os.getenv("DB_USER")
password = quote_plus(os.getenv("DB_PASS")) # এখানে @# এনকোড হবে
host = os.getenv("DB_HOST")
port = os.getenv("DB_PORT")
db_name = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}"