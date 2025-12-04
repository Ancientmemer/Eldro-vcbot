# main.py
import os
import asyncio
import logging
from pathlib import Path
from pyrogram import Client, filters
from pyrogram.types import Message
from pytgcalls import PyTgCalls, idle
from pytgcalls.types.input_stream import InputAudioStream, InputVideoStream, InputStream
from pytgcalls.types.input_stream.quality import HighQualityAudio, HighQualityVideo
import yt_dlp

# =============== CONFIG ===============
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
SUDO_USERS = [int(x) for x in os.getenv("SUDO_USERS", "").split()]

# short safe session path (important!)
Path("sessions").mkdir(exist_ok=True)
SESSION_NAME = "sessions/userbot"

# =============== LOGGING ===============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("VCUserbot")

# =============== PYROGRAM CLIENT ===============
app = Client(
    SESSION_NAME,
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)

# =============== VC CLIENT ===============
call = PyTgCalls(app)

queue = {}  # {chat_id: [ {type, file, title} ] }

# ---------------------------------------------------
# Helper: Check sudo
# ---------------------------------------------------
def is_sudo(user_id):
    return user_id in SUDO_USERS

# ---------------------------------------------------
# Helper: Download audio/video using yt-dlp
# ---------------------------------------------------
async def download_media(url, is_video=False):
    ydl_opts = {
        "format": "bestvideo+bestaudio/best" if is_video else "bestaudio/best",
        "outtmpl": "downloads/%(title)s.%(ext)s",
        "quiet": True,
    }

    Path("downloads").mkdir(exist_ok=True)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info)
        return file_path, info.get("title", "Unknown")

# ---------------------------------------------------
# Play next in queue
# ---------------------------------------------------
async def play_next(chat_id):
    if chat_id not in queue or len(queue[chat_id]) == 0:
        await call.leave_group_call(chat_id)
        return

    track = queue[chat_id].pop(0)

    if track["type"] == "audio":
        await call.join_group_call(
            chat_id,
            InputStream(
                InputAudioStream(
                    track["file"],
                    HighQualityAudio()
                )
            )
        )
    else:
        await call.join_group_call(
            chat_id,
            InputStream(
                InputAudioStream(track["file"], HighQualityAudio()),
                InputVideoStream(track["file"], HighQualityVideo())
            )
        )

# ---------------------------------------------------
# COMMANDS
# ---------------------------------------------------

# .play — play audio
@app.on_message(filters.me & filters.command("play", "."))
async def play_cmd(client: Client, msg: Message):
    if not is_sudo(msg.from_user.id):
        return await msg.reply("Not allowed ❌")

    chat_id = msg.chat.id

    if msg.reply_to_message and msg.reply_to_message.audio:
        file = await msg.reply_to_message.download()
        title = msg.reply_to_message.audio.file_name
    else:
        url = msg.text.split(maxsplit=1)[1]
        file, title = await download_media(url, is_video=False)

    if chat_id not in queue:
        queue[chat_id] = []

    queue[chat_id].append({"type": "audio", "file": file, "title": title})

    # If nothing is playing, start immediately
    if len(queue[chat_id]) == 1:
        await play_next(chat_id)

    await msg.reply(f"🎵 Queued: **{title}**")

# .vplay — play video
@app.on_message(filters.me & filters.command("vplay", "."))
async def vplay_cmd(client: Client, msg: Message):
    if not is_sudo(msg.from_user.id):
        return await msg.reply("Not allowed ❌")

    chat_id = msg.chat.id

    url = msg.text.split(maxsplit=1)[1]
    file, title = await download_media(url, is_video=True)

    if chat_id not in queue:
        queue[chat_id] = []

    queue[chat_id].append({"type": "video", "file": file, "title": title})

    if len(queue[chat_id]) == 1:
        await play_next(chat_id)

    await msg.reply(f"📽 Queued video: **{title}**")

# .skip — skip current
@app.on_message(filters.me & filters.command("skip", "."))
async def skip_cmd(client: Client, msg: Message):
    if not is_sudo(msg.from_user.id):
        return await msg.reply("Not allowed ❌")

    chat_id = msg.chat.id
    await msg.reply("⏭ Skipped")

    await play_next(chat_id)

# .playlists — show queue
@app.on_message(filters.me & filters.command("playlists", "."))
async def playlist_cmd(client: Client, msg: Message):
    chat_id = msg.chat.id
    if chat_id not in queue or len(queue[chat_id]) == 0:
        return await msg.reply("😴 Queue empty")

    text = "**Current Queue:**\n\n"
    for i, track in enumerate(queue[chat_id], start=1):
        text += f"**{i}. {track['title']}** — {track['type']}\n"

    await msg.reply(text)

# ---------------------------------------------------
# Pytgcalls Handler — on stream end
# ---------------------------------------------------
@call.on_stream_end()
async def stream_end_handler(_, update):
    chat_id = update.chat_id
    await play_next(chat_id)

# ---------------------------------------------------
# START BOT
# ---------------------------------------------------
async def main():
    await app.start()
    await call.start()
    print("VC Userbot started successfully!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
