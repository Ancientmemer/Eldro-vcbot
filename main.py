import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pytgcalls import PyTgCalls
from pytgcalls.types.input_stream import InputAudioStream, InputVideoStream, InputStream
from pytgcalls.types.input_stream.quality import HighQualityAudio, LowQualityVideo
from yt_dlp import YoutubeDL
import os

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")

# Add your Telegram ID here:
SUDO_USERS = [int(os.getenv("OWNER_ID"))]

app = Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION)
call = PyTgCalls(app)

QUEUE = {}   # {chat_id: [tracks]}

ydl_opts = {
    "format": "best[height<=480]/best",
    "quiet": True,
}


def add_to_queue(chat_id, track):
    if chat_id not in QUEUE:
        QUEUE[chat_id] = []
    QUEUE[chat_id].append(track)


def get_next(chat_id):
    if chat_id in QUEUE and QUEUE[chat_id]:
        return QUEUE[chat_id].pop(0)
    return None


# ------------------------------
# STARTUP
# ------------------------------

@app.on_message(filters.command("play", ".") & filters.user(SUDO_USERS))
async def play_cmd(_, message: Message):
    reply = message.reply_to_message

    if not reply and len(message.command) == 1:
        return await message.reply("Reply to an audio/video file or give a YouTube link.")

    chat_id = message.chat.id

    if reply and reply.audio:
        file = await reply.download()
        add_to_queue(chat_id, {"type": "audio", "file": file})
        await message.reply("Added to queue 🎵")
    elif reply and reply.video:
        file = await reply.download()
        add_to_queue(chat_id, {"type": "video", "file": file})
        await message.reply("Added to queue 🎥")
    else:
        link = message.text.split(" ", 1)[1]
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=False)
            url = info["url"]
            is_video = "height" in info

        add_to_queue(chat_id, {"type": "video" if is_video else "audio", "url": url})
        await message.reply("Added to queue ▶️")

    if not call.get_call(chat_id):
        await start_stream(chat_id, message)


@app.on_message(filters.command("vplay", ".") & filters.user(SUDO_USERS))
async def vplay_cmd(_, message: Message):
    reply = message.reply_to_message

    if not reply and len(message.command) == 1:
        return await message.reply("Reply to a video file or give a YouTube link.")

    chat_id = message.chat.id

    if reply and reply.video:
        file = await reply.download()
        add_to_queue(chat_id, {"type": "video", "file": file})
        await message.reply("Video added 🎥")
    else:
        link = message.text.split(" ", 1)[1]
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=False)
            url = info["url"]

        add_to_queue(chat_id, {"type": "video", "url": url})
        await message.reply("Video added ▶️")

    if not call.get_call(chat_id):
        await start_stream(chat_id, message)


async def start_stream(chat_id, message):
    track = get_next(chat_id)
    if not track:
        return await message.reply("Queue empty.")

    stream = None

    if track["type"] == "audio":
        source = track.get("file") or track.get("url")
        stream = InputStream(InputAudioStream(source, HighQualityAudio()))
    else:
        source = track.get("file") or track.get("url")
        stream = InputStream(
            InputVideoStream(source, LowQualityVideo()),  # 480p
            InputAudioStream(source, HighQualityAudio())
        )

    await call.join_group_call(chat_id, stream)
    await message.reply("Streaming started 🔥")


@call.on_stream_end()
async def stream_end_handler(_, update):
    chat_id = update.chat_id
    next_track = get_next(chat_id)

    if next_track:
        source = next_track.get("file") or next_track.get("url")

        if next_track["type"] == "audio":
            stream = InputStream(InputAudioStream(source, HighQualityAudio()))
        else:
            stream = InputStream(
                InputVideoStream(source, LowQualityVideo()),
                InputAudioStream(source, HighQualityAudio())
            )

        await call.change_stream(chat_id, stream)
    else:
        await call.leave_group_call(chat_id)


@app.on_message(filters.command("skip", ".") & filters.user(SUDO_USERS))
async def skip(_, message):
    chat_id = message.chat.id
    next_track = get_next(chat_id)

    if not next_track:
        await call.leave_group_call(chat_id)
        return await message.reply("Queue empty. Disconnected.")

    source = next_track.get("file") or next_track.get("url")

    if next_track["type"] == "audio":
        stream = InputStream(InputAudioStream(source, HighQualityAudio()))
    else:
        stream = InputStream(
            InputVideoStream(source, LowQualityVideo()),
            InputAudioStream(source, HighQualityAudio())
        )

    await call.change_stream(chat_id, stream)
    await message.reply("Skipped ⏭")


@app.on_message(filters.command("playlists", ".") & filters.user(SUDO_USERS))
async def playlist(_, message):
    chat_id = message.chat.id

    if chat_id not in QUEUE or not QUEUE[chat_id]:
        return await message.reply("Queue is empty.")

    text = "**Current Queue:**\n"
    for i, track in enumerate(QUEUE[chat_id], start=1):
        ttype = "🎥 Video" if track["type"] == "video" else "🎵 Audio"
        text += f"{i}. {ttype}\n"

    await message.reply(text)


async def main():
    print("Userbot Starting...")
    await app.start()
    await call.start()
    print("Userbot ready!")
    await idle()


if __name__ == "__main__":
    asyncio.run(main())
