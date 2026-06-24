import os
from dotenv import load_dotenv

load_dotenv()

USER_BOT_TOKEN    = os.getenv("USER_BOT_TOKEN")
ADMIN_BOT_TOKEN   = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
DB_PATH           = "data/matrix.db"

BOT_NAME = "Matrix File Receiver"
DIVIDER  = "▰▱" * 8
