import os
import re
import time
import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.enums import ParseMode

from config import *
from Plugins.callbacks import MODES, get_mode_keyboard
from Database.database import Seishiro
from Plugins.start import *

logger = logging.getLogger(__name__)

user_sessions = {}          # Active sequence sessions
pending_notifications = {}  # User debounce timers

# Ensure commands are strictly ignored by text collector
EXCLUDED_COMMANDS = [
    "ssequence", "esequence", "mode", "cancel",
    "add_dump", "rem_dump", "dump_info", "leaderboard",
    "start", "help", "about",
    "add_admin", "deladmin", "admins",
    "ban", "unban", "banned",
    "broadcast", "stats", "status",
    "fsub_mode", "addchnl", "delchnl", "listchnl",
]

# ==================== FLOODWAIT HANDLER ====================

async def handle_floodwait(func, *args, **kwargs):
    while True:
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            logger.warning(f"FloodWait: Sleeping for {e.value} seconds...")
            await asyncio.sleep(e.value + 1)
        except MessageNotModified:
            break
        except Exception as e:
            logger.error(f"Error in operation: {e}")
            raise e

# ==================== FILE PARSING & MISSING EPISODES ====================

def clean_show_title(filename):
    """Extract clean title before season/episode/quality indicators"""
    temp = re.sub(QUALITY_PATTERN, '', filename, flags=re.IGNORECASE)
    temp = re.sub(SEASON_PATTERN, '', temp, flags=re.IGNORECASE)
    temp = re.sub(EPISODE_PATTERN, '', temp, flags=re.IGNORECASE)
    # Remove file extensions and common metadata inside brackets/parens
    temp = re.sub(r'\.(mkv|mp4|avi|mov|flv|webm)$', '', temp, flags=re.IGNORECASE)
    temp = re.sub(r'\[.*?\]|\(.*?\)', '', temp)
    clean = re.sub(r'[._-]', ' ', temp).strip()
    return clean if clean else "Unknown Show"


def extract_file_info(filename, file_format, file_id=None):
    quality_match = re.search(QUALITY_PATTERN, filename, re.IGNORECASE)
    quality = quality_match.group(1).upper() if quality_match else 'Unknown'

    temp = re.sub(QUALITY_PATTERN, '', filename, flags=re.IGNORECASE) if quality_match else filename

    season_match = re.search(SEASON_PATTERN, temp)
    season = int(season_match.group(1)) if season_match else 0

    episode_match = re.search(EPISODE_PATTERN, temp)
    episode = int(episode_match.group(1)) if episode_match else 0
    if not episode_match:
        nums = re.findall(r'\d{1,3}', temp)
        episode = int(nums[-1]) if nums else 0

    show_title = clean_show_title(filename)

    return {
        'filename': filename,
        'format': file_format,
        'file_id': file_id,
        'show_title': show_title,
        'season': season,
        'episode': episode,
        'quality': quality,
        'quality_order': QUALITY_ORDER.get(quality.lower(), 7),
        'is_series': bool(season or episode)
    }


def parse_and_sort_files(file_data, mode='All'):
    series, non_series = [], []

    for item in file_data:
        info = extract_file_info(item['filename'], item['format'], item.get('file_id'))
        (series if info['is_series'] else non_series).append(info)

    if mode == 'Quality':
        series = sorted(series, key=lambda x: (x['quality_order'], x['filename'].lower()))
    elif mode == 'Season':
        series = sorted(series, key=lambda x: (x['season'], x['filename'].lower()))
    elif mode == 'Episode':
        series = sorted(series, key=lambda x: (x['episode'], x['filename'].lower()))
    elif mode == 'AllSQE':
        series = sorted(series, key=lambda x: (x['season'], x['quality_order'], x['episode']))
    else:  # 'All' default
        series = sorted(series, key=lambda x: (x['season'], x['episode'], x['quality_order']))

    non_series = sorted(non_series, key=lambda x: (x['filename'].lower(), x['quality_order']))

    return series, non_series


def find_missing_episodes(all_files):
    """
    Groups files by Show -> Quality and finds gaps in episode numbers.
    """
    groups = {}  # { "Show Name": { "1080p": [1, 3, 4, 6] } }

    for file_info in all_files:
        if not file_info['is_series'] or file_info['episode'] == 0:
            continue

        title = file_info['show_title']
        quality = file_info['quality']
        ep = file_info['episode']

        if title not in groups:
            groups[title] = {}
        if quality not in groups[title]:
            groups[title][quality] = set()

        groups[title][quality].add(ep)

    missing_report = []

    for title, qualities in groups.items():
        show_lines = []
        for quality, ep_set in qualities.items():
            if not ep_set:
                continue
            sorted_eps = sorted(list(ep_set))
            min_ep, max_ep = sorted_eps[0], sorted_eps[-1]
            full_range = set(range(min_ep, max_ep + 1))
            missing = sorted(list(full_range - ep_set))

            if missing:
                missing_str = ", ".join(str(e) for e in missing)
                show_lines.append(f"  - {quality}: Ep {missing_str}")

        if show_lines:
            missing_report.append(f"• {title}:\n" + "\n".join(show_lines))

    return "\n".join(missing_report) if missing_report else None


# ==================== FILE COLLECTOR ====================

@Client.on_message(
    filters.private &
    (filters.document | filters.video | filters.audio | filters.text) &
    ~filters.command(EXCLUDED_COMMANDS)
)
@check_ban
@check_fsub
async def collect_files(client: Client, message: Message):
    try:
        user_id = message.from_user.id

        if user_id not in user_sessions:
            if message.document or message.video or message.audio:
                await handle_floodwait(
                    message.reply_text,
                    "Usᴇ /ssequence ғɪʀsᴛ ᴛʜᴇɴ sᴇɴᴅ ᴛʜᴇ ғɪʟᴇ(s)."
                )
            return

        session = user_sessions[user_id]
        files = session['files']
        added_this_time = 0

        if message.text and not message.text.startswith("/"):
            for line in filter(None, map(str.strip, message.text.splitlines())):
                files.append({'filename': line, 'format': 'text'})
                added_this_time += 1

        if message.document:
            files.append({
                'filename': message.document.file_name,
                'format': 'document',
                'file_id': message.document.file_id
            })
            added_this_time += 1

        if message.video:
            filename = message.video.file_name or \
                       (message.caption if message.caption else f"video_{message.video.file_unique_id}.mp4")
            files.append({
                'filename': filename,
                'format': 'video',
                'file_id': message.video.file_id
            })
            added_this_time += 1

        if message.audio:
            filename = message.audio.file_name or f"audio_{message.audio.file_unique_id}"
            files.append({
                'filename': filename,
                'format': 'audio',
                'file_id': message.audio.file_id
            })
            added_this_time += 1

        if added_this_time == 0:
            return

        current_total = len(files)

        if user_id in pending_notifications:
            old_task = pending_notifications[user_id].get('timer')
            if old_task and not old_task.done():
                old_task.cancel()

        async def send_debounced_notification():
            await asyncio.sleep(2.3)

            if user_id in user_sessions and len(user_sessions[user_id]['files']) == current_total:
                mode_key = await Seishiro.get_sequence_mode(user_id) or "All"
                mode_display = MODES.get(mode_key, MODES["All"])["button"]

                text = (
                    f"✅ <b>{added_this_time} file(s) added to sequence</b>\n"
                    f"Total files: <code>{current_total}</code>\n\n"
                    f"Current mode: <b>{mode_display}</b>\n"
                    f"Use <code>/esequence</code> when you're done"
                )

                await handle_floodwait(
                    message.reply_text,
                    text,
                    parse_mode=ParseMode.HTML
                )

            pending_notifications.pop(user_id, None)

        pending_notifications[user_id] = {
            'timer': asyncio.create_task(send_debounced_notification()),
            'last_count': current_total
        }

    except Exception as e:
        logger.error(f"Error in collect_files: {e}")
        await handle_floodwait(message.reply_text, "❌ An error occurred while processing file.")


# ==================== START SEQUENCE ====================

@Client.on_message(filters.command("ssequence") & filters.private)
@check_ban
@check_fsub
async def arrange_cmd(client: Client, message: Message):
    try:
        user_id = message.from_user.id
        user_sessions[user_id] = {
            'files': [],
            'start_time': time.time()
        }

        mode_key = await Seishiro.get_sequence_mode(user_id) or "All"
        mode_name = MODES.get(mode_key, MODES["All"])["button"]

        await handle_floodwait(
            message.reply_text,
            f"<b><i>Sᴇǫᴜᴇɴᴄᴇ sᴛᴀʀᴛᴇᴅ</i></b>  (Current mode: {mode_name})\n\n"
            "<i>Nᴏᴡ sᴇɴᴅ ʏᴏᴜʀ ғɪʟᴇ(s) ғᴏʀ sᴇǫᴜᴇɴᴄᴇ.</i>\n"
            "• Usᴇ /mode ᴛᴏ ᴄʜᴀɴɢᴇ ᴛʜᴇ sᴏʀᴛɪɴɢ ᴍᴏᴅᴇ"
        )
    except Exception as e:
        logger.error(f"Error in ssequence command: {e}")
        await handle_floodwait(message.reply_text, "❌ Aɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ. Pʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ.")


# ==================== MODE COMMAND ====================

@Client.on_message(filters.command("mode") & filters.private)
@check_ban
@check_fsub
async def mode_cmd(client: Client, message: Message):
    try:
        user_id = message.from_user.id
        current = await Seishiro.get_sequence_mode(user_id) or "All"
        current_name = MODES.get(current, MODES["All"])["button"]

        kb = get_mode_keyboard(current)

        await handle_floodwait(
            message.reply_text,
            f"<b><u>Sᴇʟᴇᴄᴛ Sᴏʀᴛɪɴɢ Mᴏᴅᴇ</u></b> (Current: {current_name})\n\n"
            "<b>Available modes:</b>\n"
            "• <b>Qᴜᴀʟɪᴛʏ</b>: Sort by quality only\n"
            "• <b>Aʟʟ (S→E→Q)</b>: Season → Episode → Quality\n"
            "• <b>Aʟʟ [S→Q→E]</b>: Season → Quality → Episode\n"
            "• <b>Eᴘɪsᴏᴅᴇ</b>: Sort by episode number only\n"
            "• <b>Sᴇᴀsᴏɴ</b>: Sort by season number only\n\n"
            "<i>Choose your preferred order ↓</i>",
            reply_markup=kb,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error in mode command: {e}")
        await handle_floodwait(message.reply_text, "❌ Aɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ. Pʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ.")


# ==================== END SEQUENCE / SEND FILES ====================

@Client.on_message(filters.command("esequence") & filters.private)
@check_ban
@check_fsub
async def end_cmd(client: Client, message: Message):
    try:
        user_id = message.from_user.id
        session = user_sessions.get(user_id)

        if not session or not session.get('files'):
            await handle_floodwait(message.reply_text, "Nᴏ ғɪʟᴇs ᴡᴇʀᴇ sᴇɴᴛ ғᴏʀ sᴇǫᴜᴇɴᴄᴇ")
            return

        start_time = session.get('start_time', time.time())

        if user_id in pending_notifications:
            task = pending_notifications[user_id].get('timer')
            if task and not task.done():
                task.cancel()
            pending_notifications.pop(user_id, None)

        mode_key = await Seishiro.get_sequence_mode(user_id) or "All"
        dump_channel = await Seishiro.get_dump_channel(user_id)

        series, non_series = parse_and_sort_files(session['files'], mode_key)
        total_files = len(series) + len(non_series)
        all_sorted_files = series + non_series

        is_dump_mode = bool(dump_channel)
        target_chat = dump_channel if is_dump_mode else message.chat.id

        status_msg = await handle_floodwait(
            message.reply_text,
            f"📤 Sᴇɴᴅɪɴɢ {total_files} ғɪʟᴇs ɪɴ sᴇǫᴜᴇɴᴄᴇ...",
            parse_mode=ParseMode.HTML
        )

        sent_count = 0
        failed_files = []

        for file_info in all_sorted_files:
            try:
                file_id = file_info.get('file_id')
                filename = file_info.get('filename', 'Unknown')
                file_format = file_info.get('format')

                if file_id and file_format in ['document', 'video', 'audio']:
                    if file_format == 'document':
                        await handle_floodwait(client.send_document, chat_id=target_chat, document=file_id, caption=filename)
                    elif file_format == 'video':
                        await handle_floodwait(client.send_video, chat_id=target_chat, video=file_id, caption=filename)
                    elif file_format == 'audio':
                        await handle_floodwait(client.send_audio, chat_id=target_chat, audio=file_id, caption=filename)
                else:
                    await handle_floodwait(client.send_message, chat_id=target_chat, text=f"📄 {filename}")

                sent_count += 1

            except Exception as file_error:
                logger.error(f"Failed to send file {filename}: {file_error}")
                failed_files.append(filename)
                continue

        elapsed_sec = int(time.time() - start_time)
        time_taken_str = time.strftime('%H:%M:%S', time.gmtime(elapsed_sec))

        # Send completion sticker if defined
        sticker_id = getattr(globals().get('config'), 'COMPLETION_STICKER', None) or os.environ.get("COMPLETION_STICKER")
        if sticker_id:
            try:
                await client.send_sticker(chat_id=message.chat.id, sticker=sticker_id)
            except Exception as st_err:
                logger.error(f"Failed to send sticker: {st_err}")

        # Format final completion text
        mode_display = MODES.get(mode_key, MODES["All"])["button"].lower()
        
        completion_text = (
            f"Fɪʟᴇꜱ Sᴏʀᴛᴇᴅ: {sent_count}/{total_files}\n"
            f"Mᴏᴅᴇ: {mode_display}\n"
            f"Tɪᴍᴇ Tᴀᴋᴇɴ: {time_taken_str}\n"
        )

        # Check missing episodes
        missing_report = find_missing_episodes(all_sorted_files)
        if missing_report:
            completion_text += f"\nMɪꜱꜱɪɴɢ Eᴘɪꜱᴏᴅᴇꜱ:\n{missing_report}"

        await handle_floodwait(message.reply_text, completion_text)

        # Update stats
        await Seishiro.col.update_one(
            {"_id": int(user_id)},
            {
                "$inc": {"sequence_count": sent_count},
                "$set": {
                    "mention": message.from_user.mention,
                    "last_activity_timestamp": datetime.now()
                }
            },
            upsert=True
        )

        if user_id in user_sessions:
            del user_sessions[user_id]

    except Exception as e:
        logger.error(f"Error in esequence command: {e}")
        await handle_floodwait(message.reply_text, f"❌ Aɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ: {str(e)}")


# ==================== CANCEL ====================

@Client.on_message(filters.command("cancel") & filters.private)
@check_ban
@check_fsub
async def cancel_cmd(client: Client, message: Message):
    try:
        user_id = message.from_user.id

        if user_id in user_sessions:
            if user_id in pending_notifications:
                task = pending_notifications[user_id].get('timer')
                if task and not task.done():
                    task.cancel()
                pending_notifications.pop(user_id, None)

            del user_sessions[user_id]
            await handle_floodwait(message.reply_text, "Sᴇǫᴜᴇɴᴄᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ...!!")
        else:
            await handle_floodwait(message.reply_text, "Nᴏ ᴀᴄᴛɪᴠᴇ sᴇǫᴜᴇɴᴄᴇ ғᴏᴜɴᴅ.")
    except Exception as e:
        logger.error(f"Error in cancel command: {e}")
        await handle_floodwait(message.reply_text, "❌ Aɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ. Pʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ.")


# ==================== DUMP CHANNEL COMMANDS ====================

@Client.on_message(filters.command("add_dump") & filters.private)
@check_ban
@check_fsub
async def add_dump_cmd(client: Client, message: Message):
    try:
        user_id = message.from_user.id

        if len(message.command) < 2:
            await handle_floodwait(
                message.reply_text,
                "<b>Usage:</b> <code>/add_dump <Channel ID or Username></code>\n\n"
                "<b>Example:</b> <code>/add_dump -1001234567890</code> or <code>/add_dump @MyChannel</code>",
                parse_mode=ParseMode.HTML
            )
            return

        raw_target = message.command[1].strip()

        try:
            if raw_target.startswith("-100") or raw_target.startswith("-"):
                channel_id = int(raw_target)
            elif raw_target.isdigit():
                channel_id = int(f"-100{raw_target}")
            else:
                target_username = raw_target if raw_target.startswith("@") else f"@{raw_target}"
                chat = await client.get_chat(target_username)
                channel_id = chat.id

            if channel_id > 0:
                await handle_floodwait(
                    message.reply_text,
                    "❌ Cannot set a private user chat as dump channel. Use a valid channel ID or @username.",
                    parse_mode=ParseMode.HTML
                )
                return

            test_msg = await client.send_message(
                chat_id=channel_id,
                text="⚙️ <i>Testing dump channel connection...</i>",
                parse_mode=ParseMode.HTML
            )
            await asyncio.sleep(1)
            await test_msg.delete()

        except Exception as e:
            logger.error(f"Dump verification failed for {user_id}: {e}")
            await handle_floodwait(
                message.reply_text,
                f"❌ <b>Cannot connect to channel.</b>\n\n"
                f"<b>Please check:</b>\n"
                f"1. Is the bot added to the channel as an <b>Admin</b>?\n"
                f"2. Does the bot have permission to <b>Post Messages</b>?\n"
                f"3. Is the Channel ID or Username typed correctly?\n\n"
                f"<code>Details: {str(e)}</code>",
                parse_mode=ParseMode.HTML
            )
            return

        await Seishiro.set_dump_channel(user_id, channel_id)

        await handle_floodwait(
            message.reply_text,
            f"✅ <b>Dump channel saved successfully!</b>\n"
            f"Channel ID: <code>{channel_id}</code>\n\n"
            f"All future sequence output will be sent there automatically.",
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Error in add_dump: {e}")
        await handle_floodwait(message.reply_text, f"❌ Error processing command: {str(e)}", parse_mode=ParseMode.HTML)


@Client.on_message(filters.command("rem_dump") & filters.private)
@check_ban
@check_fsub
async def rem_dump_cmd(client: Client, message: Message):
    try:
        user_id = message.from_user.id
        current = await Seishiro.get_dump_channel(user_id)

        if not current:
            await handle_floodwait(message.reply_text, "Yᴏᴜ ʜᴀᴠᴇɴ'ᴛ sᴇᴛ ᴀɴʏ ᴅᴜᴍᴘ ᴄʜᴀɴɴᴇʟ ʏᴇᴛ.")
            return

        await Seishiro.remove_dump_channel(user_id)
        await handle_floodwait(
            message.reply_text,
            f"✅ Dump channel removed!\nOld ID: <code>{current}</code>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error in rem_dump: {e}")
        await handle_floodwait(message.reply_text, "❌ An error occurred.", parse_mode=ParseMode.HTML)


@Client.on_message(filters.command("dump_info") & filters.private)
@check_ban
@check_fsub
async def dump_info_cmd(client: Client, message: Message):
    try:
        user_id = message.from_user.id
        dump_channel = await Seishiro.get_dump_channel(user_id)

        if not dump_channel:
            await handle_floodwait(
                message.reply_text,
                "❌ No dump channel set.\nUse /add_dump to set one."
            )
            return

        try:
            chat = await client.get_chat(dump_channel)
            await handle_floodwait(
                message.reply_text,
                f"📍 <b>Your Dump Channel:</b>\n\n"
                f"Name: <b>{chat.title}</b>\n"
                f"ID: <code>{dump_channel}</code>\n"
                f"Username: @{chat.username if chat.username else 'N/A'}\n\n"
                f"Use /rem_dump to remove.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            await handle_floodwait(
                message.reply_text,
                f"📍 <b>Your Dump Channel:</b>\n\n"
                f"ID: <code>{dump_channel}</code>\n\n"
                f"Use /rem_dump to remove.",
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        logger.error(f"Error in dump_info: {e}")
        await handle_floodwait(message.reply_text, "❌ An error occurred.", parse_mode=ParseMode.HTML)


# ==================== LEADERBOARD ====================

@Client.on_message(filters.command("leaderboard") & filters.private)
@check_ban
@check_fsub
async def leaderboard_cmd(client: Client, message: Message):
    try:
        user_id = message.from_user.id

        cursor = Seishiro.col.find(
            {"sequence_count": {"$exists": True, "$gt": 0}}
        ).sort("sequence_count", -1).limit(10)

        top_users = await cursor.to_list(length=10)

        if not top_users:
            await handle_floodwait(
                message.reply_text,
                "📊 <b>Sequence Leaderboard</b>\n\n❌ No user data found yet!",
                parse_mode=ParseMode.HTML
            )
            return

        text = "📊 <b>Top 10 Sequence Users</b>\n\n"
        medals = ["🥇", "🥈", "🥉"]

        current_user_rank = None

        for idx, user in enumerate(top_users, 1):
            count = user.get("sequence_count", 0)
            mention = user.get("mention", f"User {user['_id']}")

            if user["_id"] == user_id:
                current_user_rank = idx

            rank = medals[idx-1] if idx <= 3 else f"{idx}."
            text += f"{rank} {mention}\n"
            text += f"    └ <b>{count:,}</b> files sequenced\n\n"

        if current_user_rank is None:
            user_doc = await Seishiro.col.find_one({"_id": user_id})
            user_count = user_doc.get("sequence_count", 0) if user_doc else 0

            if user_count > 0:
                rank = await Seishiro.col.count_documents({
                    "sequence_count": {"$gt": user_count}
                }) + 1
                text += "─────────────────\n"
                text += f"📍 <b>Your Rank:</b> #{rank}\n"
                text += f"    └ <b>{user_count:,}</b> files sequenced"
            else:
                text += "─────────────────\n"
                text += "📍 You haven't sequenced any files yet!"
        else:
            text += "─────────────────\n"
            text += f"🎉 <b>You're ranked #{current_user_rank}!</b>"

        await handle_floodwait(
            message.reply_text,
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"Leaderboard error: {e}", exc_info=True)
        await handle_floodwait(
            message.reply_text,
            "❌ Error loading leaderboard."
        )
