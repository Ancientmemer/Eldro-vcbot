import os
import asyncio
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pytgcalls import PyTgCalls
from pytgcalls.types.input_stream import InputAudioStream, InputStream, InputVideoStream

from yt_dlp import YoutubeDL

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")

# SUDO USERS (only they can control VC)
SUDO = {int(x) for x in os.getenv("SUDO_USERS", "").split()}  # example: "12345 67890"

# -------------------------------
# FIXED CLIENT – NO MORE FILENAME TOO LONG
# -------------------------------
app = Client(
    "eldro_session",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)

vc = PyTgCalls(app)

QUEUE = {}  # chat_id : [ items ]


# -------------------------------------------------------
# Helper: Download from YouTube or link/file
# -------------------------------------------------------
async def download_media(url, video=False):
    ydl_opts = {
        "format": "bestvideo+bestaudio/best" if video else "bestaudio",
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "quiet": True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)


# -------------------------------------------------------
# Helper: Check sudo users
# -------------------------------------------------------
def is_sudo(_, __, msg):
    return msg.from_user and msg.from_user.id in SUDO


sudo_filter = filters.create(is_sudo)


# -------------------------------------------------------
# VC JOIN AND PLAY FUNCTIONS
# -------------------------------------------------------
async def play_in_vc(chat_id, file_path, video=False):
    if video:
        stream = InputStream(
            InputAudioStream(file_path),
            InputVideoStream(file_path),
        )
    else:
        stream = InputAudioStream(file_path)

    if chat_id in QUEUE and vc.active_calls.get(chat_id):
        # Add to queue
        QUEUE[chat_id].append((file_path, video))
        return "Added to queue."

    QUEUE[chat_id] = []
    await vc.join_group_call(chat_id, stream)
    return "Playing now."


async def skip_track(chat_id):
    if chat_id not in QUEUE or len(QUEUE[chat_id]) == 0:
        await vc.leave_group_call(chat_id)
        return "Queue empty. Stopped."
    next_item = QUEUE[chat_id].pop(0)
    file_path, video = next_item

    await play_in_vc(chat_id, file_path, video)
    return "Skipped."


# -------------------------------------------------------
# COMMANDS
# -------------------------------------------------------

@app.on_message(sudo_filter & filters.command("play", prefixes="."))
async def play_cmd(_, msg):
    chat_id = msg.chat.id

    if msg.reply_to_message and msg.reply_to_message.audio:
        file = await msg.reply_to_message.download()
        reply = await play_in_vc(chat_id, file, video=False)
        return await msg.reply(reply)

    elif len(msg.command) > 1:
        url = msg.command[1]
        file = await download_media(url, video=False)
        reply = await play_in_vc(chat_id, file, video=False)
        return await msg.reply(reply)

    else:
        return await msg.reply("Reply to audio or send YouTube link.")


@app.on_message(sudo_filter & filters.command("vplay", prefixes="."))
async def vplay_cmd(_, msg):
    chat_id = msg.chat.id

    if len(msg.command) > 1:
        url = msg.command[1]
        file = await download_media(url, video=True)
        reply = await play_in_vc(chat_id, file, video=True)
        return await msg.reply(reply)

    return await msg.reply("Send YouTube link to play video.")


@app.on_message(sudo_filter & filters.command("skip", prefixes="."))
async def skip_cmd(_, msg):
    chat_id = msg.chat.id
    reply = await skip_track(chat_id)
    await msg.reply(reply)


@app.on_message(sudo_filter & filters.command("playlists", prefixes="."))
async def playlist_cmd(_, msg):
    chat_id = msg.chat.id

    if chat_id not in QUEUE or len(QUEUE[chat_id]) == 0:
        return await msg.reply("No items in queue.")

    text = "**Queue:**\n"
    for i, (file, video) in enumerate(QUEUE[chat_id], 1):
        t = "🎬 Video" if video else "🎵 Audio"
        text += f"{i}. {t}\n"

    await msg.reply(text)


# -------------------------------------------------------
# START BOT
# -------------------------------------------------------

async def main():
    print("Starting Eldro VC Userbot…")
    await app.start()
    await vc.start()
    print("Userbot Started!")
    
    await asyncio.get_event_loop().create_future()


if __name__ == "__main__":
    asyncio.run(main())
