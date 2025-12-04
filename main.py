# main.py
# Fixed + hardened userbot main file
import os
import asyncio
from typing import Optional
from pyrogram import Client, filters, idle
from pyrogram.types import Message

# load env
API_ID = int(os.getenv("API_ID") or 0)
API_HASH = os.getenv("API_HASH") or ""
SESSION = os.getenv("SESSION") or None   # string session
OWNER_ID = os.getenv("OWNER_ID") or None

if not API_ID or not API_HASH or not SESSION or not OWNER_ID:
    raise RuntimeError(
        "Missing required environment variables. Please set API_ID, API_HASH, SESSION (string session), OWNER_ID."
    )

SUDO_USERS = [int(OWNER_ID)]

# IMPORTANT: use session_string so pyrogram won't use the string as filename
app = Client(name="userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION)

# Try to import pytgcalls and input stream classes. If fails, disable VC features
PYCALLS_AVAILABLE = True
try:
    from pytgcalls import PyTgCalls
    try:
        from pytgcalls.types.input_stream import InputAudioStream, InputVideoStream, InputStream
        from pytgcalls.types.input_stream.quality import HighQualityAudio, LowQualityVideo
    except Exception:
        try:
            from pytgcalls.types.input_streams import InputAudioStream, InputVideoStream, InputStream
            from pytgcalls.types.input_streams.quality import HighQualityAudio, LowQualityVideo
        except Exception:
            raise
    call = PyTgCalls(app)
except Exception as e:
    PYCALLS_AVAILABLE = False
    _pytgcalls_import_error = e
    call = None

# yt-dlp options (480p max)
from yt_dlp import YoutubeDL
ydl_opts = {
    "format": "best[height<=480]/best",
    "quiet": True,
    "nocheckcertificate": True,
}

# in-memory queue
QUEUE = {}

def add_to_queue(chat_id: int, track: dict):
    QUEUE.setdefault(chat_id, []).append(track)

def get_next(chat_id: int) -> Optional[dict]:
    lst = QUEUE.get(chat_id) or []
    if lst:
        return lst.pop(0)
    return None

def is_sudo(user_id: int) -> bool:
    return int(user_id) in SUDO_USERS

# Commands
@Client.on_message(app, filters.command("play", ".") & filters.user(SUDO_USERS))
async def cmd_play(client: Client, message: Message):
    reply = message.reply_to_message
    chat_id = message.chat.id

    if not reply and len(message.command) == 1:
        return await message.reply("Reply to an audio/video file or give a YouTube link. Example: .play <youtube_url>")

    if reply and reply.audio:
        path = await reply.download()
        add_to_queue(chat_id, {"type": "audio", "file": path})
        await message.reply("Added audio to queue 🎵")
    elif reply and reply.video:
        path = await reply.download()
        add_to_queue(chat_id, {"type": "video", "file": path})
        await message.reply("Added video to queue 🎥")
    else:
        try:
            link = message.text.split(" ", 1)[1].strip()
        except IndexError:
            return await message.reply("Provide a YouTube link after .play or reply to a file.")
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, download=False)
                url = info.get("url")
                is_video = "height" in info or info.get("vcodec") is not None or info.get("acodec") is not None and info.get("width")
                add_to_queue(chat_id, {"type": "video" if is_video else "audio", "url": url, "title": info.get("title")})
                await message.reply(f"Added to queue ▶️\nTitle: {info.get('title')}")
        except Exception as ex:
            return await message.reply(f"Failed to extract video info: {ex}")

    if PYCALLS_AVAILABLE:
        try:
            if not call.get_call(chat_id):
                await start_stream(chat_id, message)
        except Exception as ex:
            await message.reply(f"Cannot start VC stream: {ex}")
    else:
        await message.reply("VC streaming is not available on this instance (pytgcalls import failed).")

@Client.on_message(app, filters.command("vplay", ".") & filters.user(SUDO_USERS))
async def cmd_vplay(client: Client, message: Message):
    reply = message.reply_to_message
    chat_id = message.chat.id

    if not reply and len(message.command) == 1:
        return await message.reply("Reply to a video file or give a YouTube link. Example: .vplay <youtube_url>")

    if reply and reply.video:
        path = await reply.download()
        add_to_queue(chat_id, {"type": "video", "file": path})
        await message.reply("Video file added to queue 🎥")
    else:
        try:
            link = message.text.split(" ", 1)[1].strip()
        except IndexError:
            return await message.reply("Provide a YouTube link after .vplay or reply to a video file.")
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, download=False)
                url = info.get("url")
                add_to_queue(chat_id, {"type": "video", "url": url, "title": info.get("title")})
                await message.reply(f"Added video to queue ▶️\nTitle: {info.get('title')}")
        except Exception as ex:
            return await message.reply(f"Failed to extract video info: {ex}")

    if PYCALLS_AVAILABLE:
        try:
            if not call.get_call(chat_id):
                await start_stream(chat_id, message)
        except Exception as ex:
            await message.reply(f"Cannot start VC stream: {ex}")
    else:
        await message.reply("VC streaming is not available on this instance (pytgcalls import failed).")

async def start_stream(chat_id: int, message: Message):
    if not PYCALLS_AVAILABLE:
        return await message.reply("VC streaming not available here. (pytgcalls import failed).")

    track = get_next(chat_id)
    if not track:
        return await message.reply("Queue empty. Nothing to play.")

    try:
        if track["type"] == "audio":
            source = track.get("file") or track.get("url")
            stream = InputStream(InputAudioStream(source, HighQualityAudio()))
        else:
            source = track.get("file") or track.get("url")
            stream = InputStream(
                InputVideoStream(source, LowQualityVideo()),
                InputAudioStream(source, HighQualityAudio())
            )

        await call.join_group_call(chat_id, stream)
        await message.reply("Streaming started 🔥")
    except Exception as ex:
        await message.reply(f"Failed to start stream: {ex}")

if PYCALLS_AVAILABLE:
    try:
        @call.on_stream_end()
        async def _on_stream_end(_, update):
            chat_id = update.chat_id
            next_track = get_next(chat_id)
            if not next_track:
                try:
                    await call.leave_group_call(chat_id)
                except:
                    pass
                return

            source = next_track.get("file") or next_track.get("url")
            if next_track["type"] == "audio":
                stream = InputStream(InputAudioStream(source, HighQualityAudio()))
            else:
                stream = InputStream(
                    InputVideoStream(source, LowQualityVideo()),
                    InputAudioStream(source, HighQualityAudio())
                )
            await call.change_stream(chat_id, stream)
    except Exception as e:
        print("Warning: failed to register on_stream_end callback:", e)

@Client.on_message(app, filters.command("skip", ".") & filters.user(SUDO_USERS))
async def cmd_skip(client: Client, message: Message):
    chat_id = message.chat.id
    next_track = get_next(chat_id)

    if not next_track:
        if PYCALLS_AVAILABLE:
            try:
                await call.leave_group_call(chat_id)
            except Exception:
                pass
        return await message.reply("Queue empty. Disconnected.")

    if not PYCALLS_AVAILABLE:
        return await message.reply("VC streaming not available here. Cannot skip.")

    source = next_track.get("file") or next_track.get("url")
    if next_track["type"] == "audio":
        stream = InputStream(InputAudioStream(source, HighQualityAudio()))
    else:
        stream = InputStream(
            InputVideoStream(source, LowQualityVideo()),
            InputAudioStream(source, HighQualityAudio())
        )

    try:
        await call.change_stream(chat_id, stream)
        await message.reply("Skipped ⏭")
    except Exception as ex:
        await message.reply(f"Failed to skip: {ex}")

@Client.on_message(app, filters.command("playlists", ".") & filters.user(SUDO_USERS))
async def cmd_playlists(client: Client, message: Message):
    chat_id = message.chat.id
    q = QUEUE.get(chat_id) or []
    if not q:
        return await message.reply("Queue is empty.")
    text = "**Current Queue:**\n"
    for i, t in enumerate(q, start=1):
        ttype = "🎥 Video" if t.get("type") == "video" else "🎵 Audio"
        title = t.get("title") or (t.get("file") and os.path.basename(t.get("file"))) or t.get("url") or "Unknown"
        text += f"{i}. {ttype} — {title}\n"
    await message.reply(text)

# startup / shutdown
async def start_services():
    print("Starting userbot...")
    await app.start()
    if PYCALLS_AVAILABLE:
        try:
            await call.start()
        except Exception as e:
            print("Failed to start pytgcalls:", e)
    else:
        print("pytgcalls not available:", _pytgcalls_import_error)

async def stop_services():
    print("Stopping userbot...")
    try:
        if PYCALLS_AVAILABLE:
            await call.stop()
    except:
        pass
    try:
        await app.stop()
    except:
        pass

async def main():
    await start_services()
    print("Userbot ready.")
    try:
        await idle()
    finally:
        await stop_services()

if __name__ == "__main__":
    asyncio.run(main())
