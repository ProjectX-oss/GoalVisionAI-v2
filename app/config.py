import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not found.")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found.")

if not FOOTBALL_API_KEY:
    raise RuntimeError("FOOTBALL_API_KEY not found.")