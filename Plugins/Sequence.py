import os
import re
import time
import uuid
import shutil
import asyncio
import logging
import html as html_lib
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.enums import ParseMode, ChatAction, ChatMemberStatus

from config import *
from Plugins.callbacks import MODES, get_mode_keyboard
from Database.database import CosmicBotz
from Plugins.start import *

logger = logging.getLogger(__name__)

user_sessions = {}          # Active sequence sessions
pending_notifications = {}  # User debounce timers

# Ensure commands are strictly ignored by text collector
EXCLUDED_COMMANDS = [
    "ssequence", "esequence", "mode", "cancel", "settings",
    "add_dump", "rem_dump", "dump_info", "leaderboard", "mystats",
    "set_caption", "rem_caption", "caption_info",
    "start", "help", "about",
    "add_admin", "deladmin", "admins",
    "ban", "unban", "banned",
    "broadcast", "stats", "status",
    "fsub_mode", "addchnl", "delchnl", "listchnl",
]

# Placeholders supported inside a user's caption template.
CAPTION_PLACEHOLDER_HELP = (
    "<b>Placeholders you can use:</b>\n"
    "<code>{caption}</code> — the file's original caption (with its formatting kept)\n"
    "<code>{filename}</code> — original file name\n"
    "<code>{show_title}</code> — cleaned show/movie title\n"
    "<code>{season}</code> — season number (e.g. 01)\n"
    "<code>{episode}</code> — episode number (e.g. 05)\n"
    "<code>{quality}</code> — quality tag (e.g. 720p)\n\n"
    "HTML tags work too — <code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, "
    "<code>&lt;blockquote&gt;</code>, <code>&lt;code&gt;</code> etc.\n\n"
    "<b>Default (if you don't set one):</b> <code>{caption}</code> — keeps each "
    "file's own original caption, falling back to its filename if it had none.\n\n"
    "<b>Example:</b>\n<code>🎬 {show_title} S{season}E{episode} [{quality}]</code>"
)

# Used when a user hasn't set a custom template — reuses the file's own
# original caption (with its formatting), falling back to the filename.
DEFAULT_CAPTION_TEMPLATE = "{caption}"

# Modes where files are grouped by (season, episode) so episode
# separators / stickers make sense. "All" additionally gets the
# "Episode XX" text label.
EPISODE_GROUPED_MODES = {"All", "AllSQE", "Episode"}

# Small pacing delay between sends during /esequence. Telegram will throw
# FloodWait if you send too fast to the same chat — but the wait it then
# imposes is often much longer than if you'd just paced yourself. A small
# proactive delay per file is the standard way to avoid tripping that limit
# in the first place, so 100+ files finish faster overall (fewer/shorter
# forced waits) rather than slower. Tune via env if needed.
SEND_PACING_DELAY = float(os.environ.get("SEQUENCE_SEND_DELAY", "0.35"))

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

# ==================== SHARED DUMP CHANNEL VERIFICATION ====================

async def verify_and_set_dump_channel(client, user_id, raw_target):
    """
    Validates and saves a dump channel for a user.
    Used by both /add_dump and the /settings panel.
    Returns (success: bool, message: str, channel_id: int|None)
    """
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
            return False, "❌ Cannot set a private user chat as dump channel. Use a valid channel ID or @username.", None

    except Exception as e:
        logger.error(f"Dump channel resolution failed for {user_id}: {e}")
        return False, (
            f"❌ <b>Could not find that channel.</b>\n\n<b>Please check:</b>\n"
            f"1. Is the Channel ID or Username typed correctly?\n"
            f"2. Is the bot a member of that channel at all?\n\n"
            f"<code>Details: {str(e)}</code>"
        ), None

    # --- Auto-detect permissions before even attempting a test post ---
    # Gives a specific, actionable reason instead of a generic failure.
    try:
        member = await client.get_chat_member(channel_id, "me")

        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            return False, (
                "❌ <b>I'm not an admin in that channel.</b>\n\n"
                "Please promote me to admin with at least the "
                "<b>Post Messages</b> permission, then try again."
            ), None

        privileges = getattr(member, 'privileges', None)
        if member.status == ChatMemberStatus.ADMINISTRATOR and privileges and not privileges.can_post_messages:
            return False, (
                "❌ <b>I'm admin there, but missing 'Post Messages' permission.</b>\n\n"
                "Please enable it for me in the channel's admin settings, then try again."
            ), None

    except Exception as perm_err:
        # Can't pre-check (e.g. rare API quirk) — fall through to the direct
        # test-post below, which will catch a real permission problem anyway.
        logger.warning(f"Could not pre-check permissions for {channel_id}: {perm_err}")

    # --- Live test: actually try posting ---
    try:
        test_msg = await client.send_message(
            chat_id=channel_id,
            text="⚙️ <i>Testing dump channel connection...</i>",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(1)
        try:
            await test_msg.delete()
        except Exception as del_err:
            # Missing delete permission shouldn't block a working setup —
            # posting is what actually matters for sequencing.
            logger.warning(f"Could not delete test message in {channel_id} (non-critical): {del_err}")

    except Exception as e:
        logger.error(f"Dump verification post failed for {user_id}: {e}")
        return False, (
            f"❌ <b>Cannot post to that channel.</b>\n\n"
            f"<b>Please check:</b>\n"
            f"1. Is the bot added to the channel as an <b>Admin</b>?\n"
            f"2. Does the bot have permission to <b>Post Messages</b>?\n\n"
            f"<code>Details: {str(e)}</code>"
        ), None

    await CosmicBotz.set_dump_channel(user_id, channel_id)
    return True, (
        f"✅ <b>Dump channel saved successfully!</b>\n"
        f"Channel ID: <code>{channel_id}</code>"
    ), channel_id


def build_caption(template, file_info):
    """
    Renders a user's caption template against a file's extracted info.
    HTML tags typed into the template (e.g. <b>, <i>, <blockquote>, <code>)
    are passed through as-is — every send call uses parse_mode=ParseMode.HTML,
    so they render normally, same as {caption}'s own preserved formatting.

    Default behaviour (no template set) is DEFAULT_CAPTION_TEMPLATE, i.e.
    just "{caption}" — reuse the file's own original caption. If the file
    had no caption at all, falls back to the filename.
    """
    filename = file_info.get('filename', 'Unknown')
    orig_caption = file_info.get('orig_caption') or ""

    effective_template = template or DEFAULT_CAPTION_TEMPLATE

    season = file_info.get('season') or 0
    episode = file_info.get('episode') or 0

    values = {
        'caption': orig_caption,
        'filename': filename,
        'show_title': file_info.get('show_title', '') or filename,
        'season': f"{season:02d}" if season else "",
        'episode': f"{episode:02d}" if episode else "",
        'quality': file_info.get('quality', '') or "Unknown",
    }

    try:
        rendered = effective_template.format(**values)
    except Exception as e:
        logger.warning(f"Caption template render failed, falling back: {e}")
        rendered = orig_caption

    return rendered.strip() if rendered and rendered.strip() else filename


async def _mux_cover_into_video(video_path, cover_path):
    """
    Physically embeds cover_path as an attached-picture stream inside
    video_path using ffmpeg -c copy (stream copy — no re-encoding, so it's
    fast and lossless). Returns the path to the new muxed file, or None if
    ffmpeg is unavailable, the extension isn't supported, or muxing fails.
    Mirrors the approach used by CoverChangerBot-style tools.
    """
    ff = shutil.which("ffmpeg")
    if not ff:
        logger.warning("[COVER DEBUG] ffmpeg not found on PATH — cannot mux cover")
        return None

    base, ext = os.path.splitext(video_path)
    ext = ext.lower()
    out_path = base + "_cv" + ext

    if ext == ".mkv":
        cmd = [
            ff, "-y", "-i", video_path,
            "-attach", cover_path,
            "-metadata:s:t", "mimetype=image/jpeg",
            "-metadata:s:t", "filename=cover.jpg",
            "-c", "copy", out_path,
        ]
    elif ext in (".mp4", ".m4v"):
        cmd = [
            ff, "-y", "-i", video_path, "-i", cover_path,
            "-map", "0", "-map", "1", "-c", "copy",
            "-disposition:v:1", "attached_pic", out_path,
        ]
    else:
        logger.warning(f"[COVER DEBUG] muxing not supported for extension {ext!r}")
        return None

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
        )
        _, err = await proc.communicate()
    except Exception as e:
        logger.warning(f"[COVER DEBUG] ffmpeg subprocess failed to start: {e}")
        return None

    if proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        return out_path

    logger.warning(f"[COVER DEBUG] ffmpeg mux failed (code {proc.returncode}): "
                    f"{(err or b'')[-300:].decode(errors='ignore')}")
    try:
        if os.path.exists(out_path):
            os.remove(out_path)
    except Exception:
        pass
    return None


async def send_video_with_cover(client, target_chat, file_info, caption_text):
    """
    CONFIRMED via live diagnostic testing on the actual bot: Telegram's
    Bot-API-style cover= parameter on send_video does NOT reliably apply —
    neither a reused file_id nor a freshly-uploaded cover image resulted in
    a visible cover, even though the send call itself succeeds with no
    error (pyrofork 2.3.69 session logs confirmed this). That rules out any
    application-level parameter fix.

    The only reliable method — the same one CoverChangerBot-style tools
    use — is to physically embed the cover into the video file's own
    container via ffmpeg, then upload the resulting file fresh. This is
    heavier than the usual copy_message path (downloads + re-uploads the
    full video, not just a small cover image), so it's only used for files
    that actually have a cover to preserve; everything else keeps using
    the fast copy_message path untouched.
    """
    file_id = file_info.get('file_id')
    cover_file_id = file_info.get('cover')
    source_chat_id = file_info.get('source_chat_id')
    source_message_id = file_info.get('source_message_id')
    filename = file_info.get('filename') or 'video.mp4'

    async def _fallback_copy():
        if source_chat_id and source_message_id:
            return await handle_floodwait(
                client.copy_message, chat_id=target_chat, from_chat_id=source_chat_id,
                message_id=source_message_id, caption=caption_text, parse_mode=ParseMode.HTML
            )
        return await handle_floodwait(
            client.send_video, chat_id=target_chat, video=file_id,
            caption=caption_text, parse_mode=ParseMode.HTML
        )

    if not cover_file_id:
        return await _fallback_copy()

    work_id = uuid.uuid4().hex[:8]
    ext = os.path.splitext(filename)[1] or ".mp4"
    video_local = None
    cover_local = None
    muxed_local = None

    try:
        video_local = await client.download_media(file_id, file_name=f"/tmp/seq_{work_id}{ext}")
        cover_local = await client.download_media(cover_file_id, file_name=f"/tmp/seq_cover_{work_id}.jpg")

        if not video_local or not cover_local:
            logger.warning("[COVER DEBUG] download failed, falling back to copy_message")
            return await _fallback_copy()

        muxed_local = await _mux_cover_into_video(video_local, cover_local)

        if not muxed_local:
            logger.warning("[COVER DEBUG] mux failed, falling back to copy_message")
            return await _fallback_copy()

        logger.info(f"[COVER DEBUG] muxed cover into {muxed_local}, uploading fresh")
        result = await handle_floodwait(
            client.send_video, chat_id=target_chat, video=muxed_local,
            caption=caption_text, parse_mode=ParseMode.HTML
        )
        logger.info("[COVER DEBUG] muxed video uploaded successfully")
        return result

    except Exception as e:
        logger.warning(f"[COVER DEBUG] mux-and-reupload pipeline failed ({e}), falling back to copy_message")
        return await _fallback_copy()

    finally:
        for p in (video_local, cover_local, muxed_local):
            if p:
                try:
                    os.remove(p)
                except Exception:
                    pass

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


def extract_file_info(filename, file_format, file_id=None, extra=None):
    quality_match = re.search(QUALITY_PATTERN, filename, re.IGNORECASE)
    if quality_match:
        raw_quality = quality_match.group(1)
        quality = QUALITY_CANONICAL.get(raw_quality.lower(), raw_quality)
    else:
        quality = 'Unknown'

    temp = re.sub(QUALITY_PATTERN, '', filename, flags=re.IGNORECASE) if quality_match else filename

    season_match = re.search(SEASON_PATTERN, temp, re.IGNORECASE)
    season = int(season_match.group(1)) if season_match else 0

    episode_match = re.search(EPISODE_PATTERN, temp, re.IGNORECASE)
    episode = int(episode_match.group(1)) if episode_match else 0
    if not episode_match:
        nums = re.findall(r'\d{1,4}', temp)
        episode = int(nums[-1]) if nums else 0

    show_title = clean_show_title(filename)

    info = {
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

    # Carry through thumbnail / duration / dimensions captured at collection
    # time so the original cover art survives re-sequencing.
    if extra:
        info.update(extra)

    return info


def build_dedup_key(info):
    """
    A key that identifies 'the same file' within a sequence session for
    duplicate detection — series files are matched by show+season+episode+
    quality (so re-sending the same episode/quality is caught even under a
    slightly different filename), non-series files are matched by filename.
    """
    if info['is_series']:
        return ('series', info['show_title'].strip().lower(), info['season'], info['episode'], info['quality'].lower())
    return ('file', info['filename'].strip().lower())


def parse_and_sort_files(file_data, mode='All'):
    series, non_series = [], []

    for item in file_data:
        extra = {k: v for k, v in item.items() if k not in ('filename', 'format', 'file_id')}
        info = extract_file_info(item['filename'], item['format'], item.get('file_id'), extra=extra)
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
    Groups files by Show -> Season, then:
      1. Missing Episodes  — takes the overall episode range for that season
         (lowest episode number to highest, across ALL qualities combined —
         e.g. if you have Ep 1 and Ep 7, the range checked is 1-7) and lists
         any episode number in that range that doesn't exist in ANY quality.
      2. Missing Quality    — for every episode that DOES exist, compares it
         against every quality seen anywhere else in that season and lists
         which quality variants that specific episode is missing.
    """
    groups = {}  # { (title, season): { "720p": {1, 3, 4, 6} } }

    for file_info in all_files:
        if not file_info['is_series'] or file_info['episode'] == 0:
            continue

        title = file_info['show_title']
        season = file_info['season']
        quality = file_info['quality']
        ep = file_info['episode']

        key = (title, season)
        if key not in groups:
            groups[key] = {}
        if quality not in groups[key]:
            groups[key][quality] = set()

        groups[key][quality].add(ep)

    missing_report = []

    for (title, season), qualities in sorted(groups.items(), key=lambda kv: (kv[0][0].lower(), kv[0][1])):
        all_qualities = sorted(qualities.keys(), key=lambda q: QUALITY_ORDER.get(q.lower(), 7))

        # Every episode number that exists in ANY quality for this season.
        episodes_present = set()
        for ep_set in qualities.values():
            episodes_present |= ep_set

        if not episodes_present:
            continue

        overall_min, overall_max = min(episodes_present), max(episodes_present)
        full_range = set(range(overall_min, overall_max + 1))

        # 1. Fully missing episodes — absent from every quality, within the
        #    season's overall episode span.
        fully_missing = sorted(full_range - episodes_present)

        # 2. Missing quality — only checked for episodes that actually exist,
        #    and only meaningful if the season has more than one quality.
        quality_lines = []
        if len(all_qualities) > 1:
            for ep in sorted(episodes_present):
                have = {q for q in all_qualities if ep in qualities[q]}
                missing_q = [q for q in all_qualities if q not in have]
                if missing_q:
                    quality_lines.append(f"  - Ep {ep:02d}: missing {', '.join(missing_q)}")

        show_lines = []
        if fully_missing:
            ep_str = ", ".join(str(e) for e in fully_missing)
            show_lines.append(f"  <i>Missing Episodes:</i>\n  - Ep {ep_str}")
        if quality_lines:
            show_lines.append("  <i>Missing Quality:</i>")
            show_lines.extend(quality_lines)

        if show_lines:
            season_label = f"S{season:02d}" if season else "Sxx"
            missing_report.append(f"• {title} [{season_label}]:\n" + "\n".join(show_lines))

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
        seen_keys = session.setdefault('seen_keys', set())
        added_this_time = 0
        duplicates_this_time = 0

        if message.text and not message.text.startswith("/"):
            for line in filter(None, map(str.strip, message.text.splitlines())):
                key = ('file', line.lower())
                if key in seen_keys:
                    duplicates_this_time += 1
                    continue
                seen_keys.add(key)
                files.append({'filename': line, 'format': 'text'})
                added_this_time += 1

        if message.document:
            filename = message.document.file_name
            key = build_dedup_key(extract_file_info(filename, 'document'))
            if key in seen_keys:
                duplicates_this_time += 1
            else:
                seen_keys.add(key)
                files.append({
                    'filename': filename,
                    'format': 'document',
                    'file_id': message.document.file_id,
                    'source_chat_id': message.chat.id,
                    'source_message_id': message.id,
                    'orig_caption': message.caption.html if message.caption else None
                })
                added_this_time += 1

        if message.video:
            filename = message.video.file_name or \
                       (message.caption if message.caption else f"video_{message.video.file_unique_id}.mp4")
            key = build_dedup_key(extract_file_info(filename, 'video'))
            if key in seen_keys:
                duplicates_this_time += 1
            else:
                seen_keys.add(key)
                # 'cover' (Bot API 8.1+) is Telegram's dedicated video-cover
                # field, DISTINCT from 'thumb' — a file can have a cover with
                # no thumb at all. getattr with a default keeps this safe on
                # pyrofork builds that don't expose it yet.
                vid_cover_obj = getattr(message.video, 'cover', None)
                vid_cover = vid_cover_obj.file_id if vid_cover_obj else None
                vid_thumb = message.video.thumbs[-1].file_id if message.video.thumbs else None

                # TEMP DIAGNOSTIC — remove once cover is confirmed working.
                # Tells us definitively whether pyrofork even exposes a
                # 'cover' attribute on this Video object, and what it holds.
                logger.info(
                    f"[COVER DEBUG] file={filename!r} "
                    f"has_cover_attr={hasattr(message.video, 'cover')} "
                    f"cover_obj={vid_cover_obj!r} cover_file_id={vid_cover!r} "
                    f"thumb_file_id={vid_thumb!r}"
                )

                files.append({
                    'filename': filename,
                    'format': 'video',
                    'file_id': message.video.file_id,
                    'cover': vid_cover,
                    'thumb': vid_thumb,
                    'source_chat_id': message.chat.id,
                    'source_message_id': message.id,
                    'orig_caption': message.caption.html if message.caption else None
                })
                added_this_time += 1

        if message.audio:
            filename = message.audio.file_name or f"audio_{message.audio.file_unique_id}"
            key = build_dedup_key(extract_file_info(filename, 'audio'))
            if key in seen_keys:
                duplicates_this_time += 1
            else:
                seen_keys.add(key)
                files.append({
                    'filename': filename,
                    'format': 'audio',
                    'file_id': message.audio.file_id,
                    'source_chat_id': message.chat.id,
                    'source_message_id': message.id,
                    'orig_caption': message.caption.html if message.caption else None
                })
                added_this_time += 1

        # Track duplicates for this whole session (shown once in the final
        # completion summary alongside "Time Taken", instead of a separate
        # message here — fewer messages during collection, and it also
        # helps keep the file count down when sequencing 100+ files).
        session['total_duplicates'] = session.get('total_duplicates', 0) + duplicates_this_time

        if added_this_time == 0:
            return

        # Give a lightweight "bot is alive" signal without sending an actual
        # message — this is a status ping (shows as "sending file..." /
        # "typing..." near the input box), not a chat message, so it doesn't
        # break the quiet batching the debounced notification relies on.
        #
        # Throttled to at most once per ~4s per user: Telegram's chat-action
        # indicator visually lasts ~5s on its own, so firing it on every
        # single file in a rapid 100+ file batch was pure waste — each call
        # is its own API request and itself contributes to flood risk with
        # zero visible benefit between calls that land under a second apart.
        now_ts = time.time()
        if now_ts - session.get('last_chat_action', 0) >= 4:
            session['last_chat_action'] = now_ts
            try:
                if message.document or message.video or message.audio:
                    await message.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
                else:
                    await message.reply_chat_action(ChatAction.TYPING)
            except Exception as ca_err:
                logger.debug(f"chat_action failed (non-critical): {ca_err}")

        current_total = len(files)

        if user_id in pending_notifications:
            old_task = pending_notifications[user_id].get('timer')
            if old_task and not old_task.done():
                old_task.cancel()

        async def send_debounced_notification():
            await asyncio.sleep(2.3)

            if user_id in user_sessions and len(user_sessions[user_id]['files']) == current_total:
                mode_key = await CosmicBotz.get_sequence_mode(user_id) or "All"
                mode_display = MODES.get(mode_key, MODES["All"])["button"]

                text = (
                    f"✅ <b>{added_this_time} file(s) added to sequence</b>\n"
                    f"Total files: <code>{current_total}</code>\n\n"
                    f"Current mode: <b>{mode_display}</b>\n"
                    f"Use <code>/esequence</code> when you're done"
                )

                quick_kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("⚙️ Mode", callback_data="nq_mode"),
                        InlineKeyboardButton("🛠️ Settings", callback_data="nq_settings")
                    ],
                    [InlineKeyboardButton("• Sᴇǫᴜᴇɴᴄᴇ Nᴏᴡ •", callback_data="nq_end")]
                ])

                await handle_floodwait(
                    message.reply_text,
                    text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=quick_kb
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
            'seen_keys': set(),
            'total_duplicates': 0,
            'last_chat_action': 0,
            'start_time': time.time()
        }

        mode_key = await CosmicBotz.get_sequence_mode(user_id) or "All"
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

async def get_mode_menu(user_id):
    current = await CosmicBotz.get_sequence_mode(user_id) or "All"
    current_name = MODES.get(current, MODES["All"])["button"]
    kb = get_mode_keyboard(current)
    text = (
        f"<b><u>Sᴇʟᴇᴄᴛ Sᴏʀᴛɪɴɢ Mᴏᴅᴇ</u></b> (Current: {current_name})\n\n"
        "<b>Available modes:</b>\n"
        "• <b>Qᴜᴀʟɪᴛʏ</b>: Sort by quality only\n"
        "• <b>Aʟʟ (S→E→Q)</b>: Season → Episode → Quality\n"
        "• <b>Aʟʟ [S→Q→E]</b>: Season → Quality → Episode\n"
        "• <b>Eᴘɪsᴏᴅᴇ</b>: Sort by episode number only\n"
        "• <b>Sᴇᴀsᴏɴ</b>: Sort by season number only\n\n"
        "<i>Choose your preferred order ↓</i>"
    )
    return text, kb


@Client.on_message(filters.command("mode") & filters.private)
@check_ban
@check_fsub
async def mode_cmd(client: Client, message: Message):
    try:
        text, kb = await get_mode_menu(message.from_user.id)
        await handle_floodwait(message.reply_text, text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error in mode command: {e}")
        await handle_floodwait(message.reply_text, "❌ Aɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ. Pʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ.")


# ==================== QUICK ACTIONS (buttons on file-added notification) ====================

@Client.on_callback_query(filters.regex(r"^nq_"))
async def quick_notification_callback(client: Client, cq):
    user_id = cq.from_user.id
    data = cq.data

    try:
        if data == "nq_mode":
            await cq.answer()
            text, kb = await get_mode_menu(user_id)
            await handle_floodwait(
                client.send_message, chat_id=cq.message.chat.id, text=text,
                reply_markup=kb, parse_mode=ParseMode.HTML
            )

        elif data == "nq_settings":
            await cq.answer()
            from Plugins.settings import build_settings_view  # deferred: avoids circular import
            text, kb = await build_settings_view(user_id)
            await handle_floodwait(
                client.send_message, chat_id=cq.message.chat.id, text=text,
                reply_markup=kb, parse_mode=ParseMode.HTML
            )

        elif data == "nq_end":
            await cq.answer("Starting sequence...")

            async def notify(text, **kwargs):
                return await handle_floodwait(client.send_message, chat_id=cq.message.chat.id, text=text, **kwargs)

            await perform_esequence(client, user_id, cq.message.chat.id, cq.from_user.mention, notify)

    except Exception as e:
        logger.error(f"Error in quick_notification_callback (data={data!r}): {e}", exc_info=True)
        try:
            await cq.answer("An error occurred. Please try again.", show_alert=True)
        except Exception:
            pass


# ==================== END SEQUENCE / SEND FILES ====================

async def perform_esequence(client, user_id, chat_id, user_mention, notify):
    """
    Core /esequence logic, extracted so it can be triggered either by the
    /esequence command or by the inline 'Sequence Now' button on the
    file-added notification.

    notify: async callable(text, **kwargs) that sends a text message to the
    user's chat (already wraps handle_floodwait internally).
    """
    try:
        session = user_sessions.get(user_id)

        if not session or not session.get('files'):
            await notify("Nᴏ ғɪʟᴇs ᴡᴇʀᴇ sᴇɴᴛ ғᴏʀ sᴇǫᴜᴇɴᴄᴇ")
            return

        start_time = session.get('start_time', time.time())
        total_duplicates = session.get('total_duplicates', 0)

        if user_id in pending_notifications:
            task = pending_notifications[user_id].get('timer')
            if task and not task.done():
                task.cancel()
            pending_notifications.pop(user_id, None)

        mode_key = await CosmicBotz.get_sequence_mode(user_id) or "All"
        dump_channel = await CosmicBotz.get_dump_channel(user_id)
        episode_sticker = await CosmicBotz.get_episode_sticker(user_id)
        caption_template = await CosmicBotz.get_caption_template(user_id)

        series, non_series = parse_and_sort_files(session['files'], mode_key)
        total_files = len(series) + len(non_series)
        all_sorted_files = series + non_series

        is_dump_mode = bool(dump_channel)
        target_chat = dump_channel if is_dump_mode else chat_id

        await notify(f"📤 Sᴇɴᴅɪɴɢ {total_files} ғɪʟᴇs ɪɴ sᴇǫᴜᴇɴᴄᴇ...", parse_mode=ParseMode.HTML)

        sent_count = 0
        failed_files = []

        last_episode_key = None
        uses_episode_grouping = mode_key in EPISODE_GROUPED_MODES

        for file_info in all_sorted_files:
            try:
                file_id = file_info.get('file_id')
                filename = file_info.get('filename', 'Unknown')
                file_format = file_info.get('format')
                is_series = file_info.get('is_series')
                season = file_info.get('season')
                episode = file_info.get('episode')

                if uses_episode_grouping and is_series and episode:
                    current_key = (season, episode)

                    if current_key != last_episode_key:
                        if last_episode_key is not None and episode_sticker:
                            try:
                                await handle_floodwait(
                                    client.send_sticker, chat_id=target_chat, sticker=episode_sticker
                                )
                            except Exception as ep_st_err:
                                logger.error(f"Failed to send episode sticker: {ep_st_err}")

                        if mode_key == "All":
                            await handle_floodwait(
                                client.send_message,
                                chat_id=target_chat,
                                text=f"📌 <b>Episode {episode:02d}</b>",
                                parse_mode=ParseMode.HTML
                            )

                        last_episode_key = current_key

                source_chat_id = file_info.get('source_chat_id')
                source_message_id = file_info.get('source_message_id')
                caption_text = build_caption(caption_template, file_info)

                if file_format == 'video' and file_info.get('cover'):
                    # This file has Telegram's distinct video 'cover' field —
                    # copy_message doesn't reliably relay it, so it needs its
                    # own explicit send with cover= (falls back internally to
                    # copy_message if the cover attempt fails for any reason).
                    await send_video_with_cover(client, target_chat, file_info, caption_text)

                elif source_chat_id and source_message_id and file_format in ['document', 'video', 'audio']:
                    # copy_message asks Telegram's own servers to duplicate the
                    # original message's media exactly — thumbnail, duration,
                    # dimensions, everything — with nothing re-uploaded and
                    # nothing for us to guess or reattach.
                    await handle_floodwait(
                        client.copy_message,
                        chat_id=target_chat,
                        from_chat_id=source_chat_id,
                        message_id=source_message_id,
                        caption=caption_text,
                        parse_mode=ParseMode.HTML
                    )
                elif file_id and file_format in ['document', 'video', 'audio']:
                    # Fallback for any older session data collected before this
                    # source-tracking existed (no source_chat_id/message_id).
                    if file_format == 'document':
                        await handle_floodwait(
                            client.send_document, chat_id=target_chat, document=file_id,
                            caption=caption_text, parse_mode=ParseMode.HTML
                        )
                    elif file_format == 'video':
                        await handle_floodwait(
                            client.send_video, chat_id=target_chat, video=file_id,
                            caption=caption_text, parse_mode=ParseMode.HTML
                        )
                    elif file_format == 'audio':
                        await handle_floodwait(
                            client.send_audio, chat_id=target_chat, audio=file_id,
                            caption=caption_text, parse_mode=ParseMode.HTML
                        )
                else:
                    await handle_floodwait(client.send_message, chat_id=target_chat, text=f"📄 {filename}")

                sent_count += 1
                await asyncio.sleep(SEND_PACING_DELAY)

            except Exception as file_error:
                logger.error(f"Failed to send file {filename}: {file_error}")
                failed_files.append(filename)
                continue

        if uses_episode_grouping and last_episode_key is not None and episode_sticker:
            try:
                await handle_floodwait(client.send_sticker, chat_id=target_chat, sticker=episode_sticker)
            except Exception as ep_st_err:
                logger.error(f"Failed to send final episode sticker: {ep_st_err}")

        elapsed_sec = int(time.time() - start_time)
        time_taken_str = time.strftime('%H:%M:%S', time.gmtime(elapsed_sec))

        sticker_id = getattr(globals().get('config'), 'COMPLETION_STICKER', None) or os.environ.get("COMPLETION_STICKER")
        if sticker_id:
            try:
                await client.send_sticker(chat_id=chat_id, sticker=sticker_id)
            except Exception as st_err:
                logger.error(f"Failed to send sticker: {st_err}")

        mode_display = MODES.get(mode_key, MODES["All"])["button"].lower()

        completion_text = (
            f"Fɪʟᴇꜱ Sᴏʀᴛᴇᴅ: {sent_count}/{total_files}\n"
            f"Mᴏᴅᴇ: {mode_display}\n"
            f"Tɪᴍᴇ Tᴀᴋᴇɴ: {time_taken_str}\n"
            + (f"Dᴜᴘʟɪᴄᴀᴛᴇꜱ Sᴋɪᴘᴘᴇᴅ: {total_duplicates}\n" if total_duplicates else "")
        )

        missing_report = find_missing_episodes(all_sorted_files)
        if missing_report:
            completion_text += f"\nMɪꜱꜱɪɴɢ Eᴘɪꜱᴏᴅᴇꜱ:\n{missing_report}"

        await notify(completion_text, parse_mode=ParseMode.HTML)

        await CosmicBotz.col.update_one(
            {"_id": int(user_id)},
            {
                "$inc": {
                    "sequence_count": sent_count,
                    "batches_completed": 1,
                    f"mode_usage.{mode_key}": 1
                },
                "$set": {
                    "mention": user_mention,
                    "last_activity_timestamp": datetime.now()
                }
            },
            upsert=True
        )

        if user_id in user_sessions:
            del user_sessions[user_id]

    except Exception as e:
        logger.error(f"Error in perform_esequence: {e}")
        await notify(f"❌ Aɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ: {str(e)}")


@Client.on_message(filters.command("esequence") & filters.private)
@check_ban
@check_fsub
async def end_cmd(client: Client, message: Message):
    async def notify(text, **kwargs):
        return await handle_floodwait(message.reply_text, text, **kwargs)

    await perform_esequence(
        client, message.from_user.id, message.chat.id, message.from_user.mention, notify
    )


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

        success, msg, channel_id = await verify_and_set_dump_channel(client, user_id, raw_target)

        if success:
            msg += "\n\nAll future sequence output will be sent there automatically."

        await handle_floodwait(message.reply_text, msg, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Error in add_dump: {e}")
        await handle_floodwait(message.reply_text, f"❌ Error processing command: {str(e)}", parse_mode=ParseMode.HTML)


@Client.on_message(filters.command("rem_dump") & filters.private)
@check_ban
@check_fsub
async def rem_dump_cmd(client: Client, message: Message):
    try:
        user_id = message.from_user.id
        current = await CosmicBotz.get_dump_channel(user_id)

        if not current:
            await handle_floodwait(message.reply_text, "Yᴏᴜ ʜᴀᴠᴇɴ'ᴛ sᴇᴛ ᴀɴʏ ᴅᴜᴍᴘ ᴄʜᴀɴɴᴇʟ ʏᴇᴛ.")
            return

        await CosmicBotz.remove_dump_channel(user_id)
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
        dump_channel = await CosmicBotz.get_dump_channel(user_id)

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


# ==================== CAPTION TEMPLATE COMMANDS ====================

@Client.on_message(filters.command("set_caption") & filters.private)
@check_ban
@check_fsub
async def set_caption_cmd(client: Client, message: Message):
    try:
        user_id = message.from_user.id

        if len(message.command) < 2:
            await handle_floodwait(
                message.reply_text,
                "<b>Usage:</b> <code>/set_caption &lt;template&gt;</code>\n\n" + CAPTION_PLACEHOLDER_HELP,
                parse_mode=ParseMode.HTML
            )
            return

        template = message.text.split(None, 1)[1].strip()
        await CosmicBotz.set_caption_template(user_id, template)

        preview = build_caption(template, {
            'filename': 'Show.Name.S01E05.720p.mkv', 'show_title': 'Show Name',
            'season': 1, 'episode': 5, 'quality': '720p',
            'orig_caption': '🎬 <b>Show Name</b> Episode 5'
        })

        await handle_floodwait(
            message.reply_text,
            f"✅ <b>Caption template saved!</b>\n\n<b>Preview:</b>\n{preview}",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error in set_caption: {e}")
        await handle_floodwait(message.reply_text, "❌ An error occurred.", parse_mode=ParseMode.HTML)


@Client.on_message(filters.command("rem_caption") & filters.private)
@check_ban
@check_fsub
async def rem_caption_cmd(client: Client, message: Message):
    try:
        user_id = message.from_user.id
        current = await CosmicBotz.get_caption_template(user_id)

        if not current:
            await handle_floodwait(message.reply_text, "Yᴏᴜ ʜᴀᴠᴇɴ'ᴛ sᴇᴛ ᴀ ᴄᴀᴘᴛɪᴏɴ ᴛᴇᴍᴘʟᴀᴛᴇ ʏᴇᴛ.")
            return

        await CosmicBotz.remove_caption_template(user_id)
        await handle_floodwait(
            message.reply_text,
            "✅ Caption template removed! Files will use their plain filename as caption again.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error in rem_caption: {e}")
        await handle_floodwait(message.reply_text, "❌ An error occurred.", parse_mode=ParseMode.HTML)


@Client.on_message(filters.command("caption_info") & filters.private)
@check_ban
@check_fsub
async def caption_info_cmd(client: Client, message: Message):
    try:
        user_id = message.from_user.id
        template = await CosmicBotz.get_caption_template(user_id)

        if not template:
            await handle_floodwait(
                message.reply_text,
                "❌ No caption template set. Files use their plain filename as caption.\n\n"
                "Use /set_caption to create one.\n\n" + CAPTION_PLACEHOLDER_HELP,
                parse_mode=ParseMode.HTML
            )
            return

        preview = build_caption(template, {
            'filename': 'Show.Name.S01E05.720p.mkv', 'show_title': 'Show Name',
            'season': 1, 'episode': 5, 'quality': '720p',
            'orig_caption': '🎬 <b>Show Name</b> Episode 5'
        })

        await handle_floodwait(
            message.reply_text,
            f"📝 <b>Your Caption Template:</b>\n<code>{html_lib.escape(template)}</code>\n\n"
            f"<b>Preview:</b>\n{preview}\n\n"
            "Use /rem_caption to remove it.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error in caption_info: {e}")
        await handle_floodwait(message.reply_text, "❌ An error occurred.", parse_mode=ParseMode.HTML)


# ==================== PER-USER STATS ====================

@Client.on_message(filters.command("mystats") & filters.private)
@check_ban
@check_fsub
async def mystats_cmd(client: Client, message: Message):
    try:
        user_id = message.from_user.id
        user_doc = await CosmicBotz.col.find_one({"_id": user_id}) or {}

        total_files = user_doc.get("sequence_count", 0)
        total_batches = user_doc.get("batches_completed", 0)
        mode_usage = user_doc.get("mode_usage", {}) or {}
        join_date = user_doc.get("join_date", "Unknown")
        last_activity = user_doc.get("last_activity_timestamp")

        if mode_usage:
            fav_mode_key = max(mode_usage, key=mode_usage.get)
            fav_mode = MODES.get(fav_mode_key, {}).get("button", fav_mode_key)
        else:
            fav_mode = "N/A"

        last_active_str = (
            last_activity.strftime("%d-%m-%Y %H:%M")
            if isinstance(last_activity, datetime) else "N/A"
        )

        text = (
            "<b>📊 Yᴏᴜʀ Sᴛᴀᴛs</b>\n\n"
            f"📁 <b>Files Sequenced:</b> <code>{total_files:,}</code>\n"
            f"📦 <b>Batches Completed:</b> <code>{total_batches:,}</code>\n"
            f"⭐ <b>Favorite Mode:</b> {fav_mode}\n"
            f"📅 <b>Member Since:</b> <code>{join_date}</code>\n"
            f"🕓 <b>Last Active:</b> <code>{last_active_str}</code>"
        )

        await handle_floodwait(message.reply_text, text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error in mystats: {e}")
        await handle_floodwait(message.reply_text, "❌ An error occurred.", parse_mode=ParseMode.HTML)


# ==================== LEADERBOARD ====================

@Client.on_message(filters.command("leaderboard") & filters.private)
@check_ban
@check_fsub
async def leaderboard_cmd(client: Client, message: Message):
    try:
        user_id = message.from_user.id

        cursor = CosmicBotz.col.find(
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
            user_doc = await CosmicBotz.col.find_one({"_id": user_id})
            user_count = user_doc.get("sequence_count", 0) if user_doc else 0

            if user_count > 0:
                rank = await CosmicBotz.col.count_documents({
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