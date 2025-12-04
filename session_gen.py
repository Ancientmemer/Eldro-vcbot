from pyrogram import Client

print("Enter API ID:")
api_id = int(input().strip())

print("Enter API HASH:")
api_hash = input().strip()

with Client(name="session", api_id=api_id, api_hash=api_hash) as app:
    print("Your string session:")
    print(app.export_session_string())
