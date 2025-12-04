# main.py
import os
import asyncio
import tempfile
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Required env vars
SESSION_STRING = os.getenv("SESSION_STRING")           # REQUIRED
API_ID = int(os.getenv("API_ID") or 0)
API_HASH = os.getenv("API_HASH")
OWNER_ID = int(os.getenv("OWNER_ID") or 0)
SUDO_USERS = [int(x) for x in (os.getenv("SUDO_USERS") or "").split(",") if x.strip().isdigit()]

# Ensure owner's id in sudo users
if OWNER_ID and OWNER_ID not in SUDO_USERS:
    SUDO_USERS.append(OWNER_ID)

if not SESSION_STRING:
    # If no session string provided, try using local session name (for dev)
    print("Warning: SESSION_STRING not set. Expect login issues in headless envs.")
    # do not exit; allow local dev

from pyrogram import Client, filters
from pyrogram.types import Message

# Try import of py-tgcalls
try:
    from py_tgcalls import PyTgCalls
    from py_tgcalls.types import StreamType
    from py_tgcalls.types.input_stream import InputAudioStream, InputVideoStream
except Exception as ex:
    PyTgCalls = None
    _PYTGCALLS_IMPORT_ERROR = ex

# Use session string as session_name to run headless
session_name_or_string = SESSION_STRING if SESSION_STRING else "userbot_session"
app = Client(session_name_or_string, api_id=API_ID, api_hash=API_HASH)

queues = {}   # chat_id -> list of items
playing = {}  # chat_id -> bool
call_py = None

def is_sudo(user_id: int) -> bool:
    return user_id in SUDO_USERS

async def ensure_queue(chat_id: int):
    if chat_id not in queues:
        queues[chat_id] = []
        playing[chat_id] = False

async def download_media_or_ytdl(message: Message):
    """
    If reply to media: download and return {'path', 'title', 'kind'}
    If message includes youtube link: download via yt-dlp to tmpdir.
    """
    # reply file priority
    rt = message.reply_to_message
    if rt and (rt.audio or rt.voice or rt.document or rt.video):
        fname = await rt.download(file_name=tempfile.gettempdir())
        kind = "video" if rt.video else "audio"
        return {"path": fname, "title": Path(fname).name, "kind": kind}

    # search text for youtube link
    text = (message.text or message.caption or "").strip()
    if not text:
        raise RuntimeError("Reply to an audio/video file or provide a YouTube link.")
    if "youtu" in text or "youtube.com" in text or "youtu.be" in text:
        # download with yt-dlp
        import yt_dlp
        tmp = tempfile.mkdtemp(prefix="yt_")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": f"{tmp}/%(title)s.%(ext)s",
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(text, download=True)
            title = info.get("title", "yt")
            # pick the downloaded file
            candidates = list(Path(tmp).glob("*"))
            if not candidates:
                raise RuntimeError("yt-dlp failed to download.")
            return {"path": str(candidates[0]), "title": title, "kind": "audio"}

    raise RuntimeError("Unsupported input. Reply to media or provide a YouTube link.")

async def play_next(chat_id: int):
    global call_py
    await ensure_queue(chat_id)
    if not queues[chat_id]:
        playing[chat_id] = False
        # try leaving group call
        if call_py:
            try:
                await call_py.leave_group_call(chat_id)
            except Exception:
                pass
        return

    item = queues[chat_id].pop(0)
    playing[chat_id] = True
    filepath = item["path"]
    kind = item.get("kind", "audio")

    if not call_py:
        # can't play without py-tgcalls
        print("py-tgcalls not initialized; can't play.")
        playing[chat_id] = False
        return

    try:
        if kind == "audio":
            await call_py.join_group_call(
                chat_id,
                InputAudioStream(Path(filepath).as_posix()),
                stream_type=StreamType().local_stream
            )
        else:
            await call_py.join_group_call(
                chat_id,
                InputVideoStream(Path(filepath).as_posix()),
                stream_type=StreamType().local_stream
            )
    except Exception as exc:
        print("Playback error:", exc)
        # attempt next
        await play_next(chat_id)

# Commands

@app.on_message(filters.me & filters.command("play", prefixes="."))
async def cmd_play(client: Client, message: Message):
    user = message.from_user
    if user and not is_sudo(user.id):
        return await message.reply_text("You are not authorized to use this command.")
    chat_id = message.chat.id
    await ensure_queue(chat_id)
    try:
        info = await download_media_or_ytdl(message)
    except Exception as e:
        return await message.reply_text(f"Error: {e}")
    queues[chat_id].append({"path": info["path"], "title": info["title"], "kind": "audio", "requester": user.id if user else None})
    await message.reply_text(f"Added to queue: {info['title']} (pos {len(queues[chat_id])})")
    if not playing.get(chat_id, False):
        await play_next(chat_id)

@app.on_message(filters.me & filters.command("vplay", prefixes="."))
async def cmd_vplay(client: Client, message: Message):
    user = message.from_user
    if user and not is_sudo(user.id):
        return await message.reply_text("You are not authorized to use this command.")
    chat_id = message.chat.id
    await ensure_queue(chat_id)
    try:
        info = await download_media_or_ytdl(message)
    except Exception as e:
        return await message.reply_text(f"Error: {e}")
    # force video
    queues[chat_id].append({"path": info["path"], "title": info["title"], "kind": "video", "requester": user.id if user else None})
    await message.reply_text(f"Added video to queue: {info['title']} (pos {len(queues[chat_id])})")
    if not playing.get(chat_id, False):
        await play_next(chat_id)

@app.on_message(filters.me & filters.command("skip", prefixes="."))
async def cmd_skip(client: Client, message: Message):
    user = message.from_user
    if user and not is_sudo(user.id):
        return await message.reply_text("You are not authorized to use this command.")
    chat_id = message.chat.id
    await ensure_queue(chat_id)
    # stop current (leave) then play next
    if call_py:
        try:
            await call_py.leave_group_call(chat_id)
        except Exception:
            pass
    playing[chat_id] = False
    await message.reply_text("Skipped current track.")
    await play_next(chat_id)

@app.on_message(filters.me & filters.command("playlists", prefixes="."))
async def cmd_playlists(client: Client, message: Message):
    chat_id = message.chat.id
    await ensure_queue(chat_id)
    if not queues[chat_id]:
        return await message.reply_text("Queue is empty.")
    lines = []
    for i, item in enumerate(queues[chat_id], start=1):
        lines.append(f"{i}. {item['title']} (req: {item.get('requester')})")
    await message.reply_text("Queue:\n" + "\n".join(lines))

@app.on_message(filters.me & filters.command("sudo", prefixes="."))
async def cmd_sudo(client: Client, message: Message):
    # .sudo add 12345 / .sudo remove 12345 / .sudo list
    if message.from_user and message.from_user.id != OWNER_ID:
        return await message.reply_text("Only owner can manage sudo.")
    parts = (message.text or "").split()
    if len(parts) < 2:
        return await message.reply_text("Usage: .sudo add|remove|list <user_id>")
    action = parts[1].lower()
    if action == "list":
        return await message.reply_text("Sudo users: " + ", ".join(str(x) for x in SUDO_USERS))
    if len(parts) < 3:
        return await message.reply_text("Provide user id.")
    try:
        uid = int(parts[2])
    except:
        return await message.reply_text("Invalid user id.")
    if action == "add":
        if uid in SUDO_USERS:
            return await message.reply_text("Already sudo.")
        SUDO_USERS.append(uid)
        return await message.reply_text(f"Added {uid}")
    if action == "remove":
        if uid not in SUDO_USERS:
            return await message.reply_text("Not in sudo.")
        SUDO_USERS.remove(uid)
        return await message.reply_text(f"Removed {uid}")
    return await message.reply_text("Unknown action.")

@app.on_message(filters.me & filters.command("ping", prefixes="."))
async def ping_cmd(_, m: Message):
    await m.reply_text("Pong!")

# Start py-tgcalls
async def start_calls():
    global call_py
    if PyTgCalls is None:
        print("py-tgcalls not available:", globals().get("_PYTGCALLS_IMPORT_ERROR"))
        return
    call_py = PyTgCalls(app)
    # no extra event wire here to keep minimal cross-version compatibility

async def main():
    print("Starting userbot...")
    await app.start()
    await start_calls()
    print("Userbot started. Commands: .play .vplay .skip .playlists")
    # keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down...")
        asyncio.run(app.stop())
