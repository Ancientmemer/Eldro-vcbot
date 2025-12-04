# session_gen.py
from pyrogram import Client
import os

API_ID = int(os.environ.get("API_ID") or input("API_ID: ").strip())
API_HASH = os.environ.get("API_HASH") or input("API_HASH: ").strip()
PHONE = os.environ.get("PHONE") or input("Phone (with country code, eg +91...): ").strip()

# This will create session named 'userbot_session'
with Client("userbot_session", api_id=API_ID, api_hash=API_HASH) as app:
    print("Logged in as:", app.get_me().username or app.get_me().first_name)

print("Session string generated in the file: userbot_session.session (or use .session to export)")
print("To get the actual string programmatically use: Client.export_session_string() if needed.")
