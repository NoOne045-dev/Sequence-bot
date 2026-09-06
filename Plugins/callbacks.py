from pyrogram import Client
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
import asyncio
import logging

from config import *
from Database.database import Seishiro

logger = logging.getLogger(__name__)
# If you need user_sessions: uncomment and adjust path
# from Plugins.sequence import user_sessions

# ────────────────────────────────────────────────
#           Mode Configuration (easy to extend)
# ────────────────────────────────────────────────

MODES = {
    "Quality": {
        "button": "Qᴜᴀʟɪᴛʏ",
        "desc": "Sort by quality only",
        "answer": "Sorting mode set to Quality"
    },
    "All": {
        "button": "Aʟʟ (S→E→Q)",
        "desc": "Season → Episode → Quality (classic)",
        "answer": "Sorting mode set to All (S→E→Q)"
    },
    "AllSQE": {
        "button": "Aʟʟ [S→Q→E]",
        "desc": "Season → Quality → Episode",
        "answer": "Sorting mode set to All [S→Q→E]"
    },
    "Episode": {
        "button": "Eᴘɪsᴏᴅᴇ",
        "desc": "Sort by episode number only",
        "answer": "Sorting mode set to Episode"
    },
    "Season": {
        "button": "Sᴇᴀsᴏɴ",
        "desc": "Sort by season number only",
        "answer": "Sorting mode set to Season"
    }
}

MODE_ORDER = ["Quality", "All", "AllSQE", "Episode", "Season"]


def get_mode_keyboard(current_mode: str) -> InlineKeyboardMarkup:
    """Generate fresh mode selection keyboard with current selection marked"""
    buttons = []
    row = []

    for mode_key in MODE_ORDER:
        text = MODES[mode_key]["button"]
        if mode_key == current_mode:
            text += " ✅"
        row.append(InlineKeyboardButton(text, callback_data=f"mode_{mode_key}"))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton("Close ✖️", callback_data="close")])

    return InlineKeyboardMarkup(buttons)


@Client.on_callback_query()
async def settings_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data

    try:
        # ─── Sorting Mode Callbacks ───────────────────────────────
        if data.startswith("mode_"):
            mode_key = data.split("_", 1)[1]

            if mode_key not in MODES:
                await callback_query.answer("Unknown sorting mode!", show_alert=True)
                return

            # Save selected mode
            await Seishiro.set_sequence_mode(user_id, mode_key)

            # Optional: update active session if available
            try:
                from Plugins.sequence import user_sessions
                if user_id in user_sessions:
                    user_sessions[user_id]['mode'] = mode_key
            except ImportError:
                pass

            # Show feedback
            await callback_query.answer(MODES[mode_key]["answer"])

            # Build updated message
            lines = []
            for key, info in MODES.items():
                prefix = "→" if key == mode_key else "•"
                lines.append(f"{prefix} <b>{info['button']}:</b> {info['desc']}")

            text = (
                f"<b>Sorting Mode Settings</b>\n"
                f"Current: <code>{MODES[mode_key]['button']}</code>\n\n"
                f"<b>Available modes:</b>\n\n"
                + "\n".join(lines) +
                "\n\n<i>Choose how you want your files to be ordered ↓</i>"
            )

            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=get_mode_keyboard(mode_key),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                await callback_query.message.edit_text(
                    text,
                    reply_markup=get_mode_keyboard(mode_key),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )

        # ─── Other existing callbacks ──────────────────────────────
        elif data == "about":
            user = await client.get_users(OWNER_ID)  # Make sure OWNER_ID is defined somewhere
            await callback_query.edit_message_media(
                InputMediaPhoto("https://envs.sh/Wdj.jpg", ABOUT_TXT),
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("• back", callback_data="start"),
                        InlineKeyboardButton("close •", callback_data="close")
                    ]
                ])
            )

        elif data == "help":
            await callback_query.edit_message_media(
                InputMediaPhoto(
                    "https://envs.sh/Wdj.jpg",
                    HELP_TXT.format(
                        first=callback_query.from_user.first_name,
                        last=callback_query.from_user.last_name or "",
                        username=f"@{callback_query.from_user.username}" if callback_query.from_user.username else "None",
                        mention=callback_query.from_user.mention,
                        id=callback_query.from_user.id
                    )
                ),
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("• back", callback_data="start"),
                        InlineKeyboardButton("close •", callback_data="close")
                    ]
                ])
            )

        elif data == "start":
            rows = [
                [
                    InlineKeyboardButton("• about", callback_data="about"),
                    InlineKeyboardButton("Help •", callback_data="help")
                ]
            ]
            extra_row = []
            if UPDATES_URL:
                extra_row.append(InlineKeyboardButton("Uᴘᴅᴀᴛᴇs", url=UPDATES_URL))
            if SUPPORT_URL:
                extra_row.append(InlineKeyboardButton("Sᴜᴘᴘᴏʀᴛ", url=SUPPORT_URL))
            if extra_row:
                rows.append(extra_row)
            inline_buttons = InlineKeyboardMarkup(rows)

            try:
                await callback_query.edit_message_media(
                    InputMediaPhoto(
                        START_PIC,
                        START_MSG.format(
                            first=callback_query.from_user.first_name,
                            last=callback_query.from_user.last_name or "",
                            username=f"@{callback_query.from_user.username}" if callback_query.from_user.username else "None",
                            mention=callback_query.from_user.mention,
                            id=callback_query.from_user.id
                        )
                    ),
                    reply_markup=inline_buttons
                )
            except Exception:
                await callback_query.edit_message_text(
                    START_MSG.format(
                        first=callback_query.from_user.first_name,
                        last=callback_query.from_user.last_name or "",
                        username=f"@{callback_query.from_user.username}" if callback_query.from_user.username else "None",
                        mention=callback_query.from_user.mention,
                        id=callback_query.from_user.id
                    ),
                    reply_markup=inline_buttons,
                    parse_mode=ParseMode.HTML
                )

        # ForceSub related callbacks
        elif data.startswith("rfs_ch_"):
            cid = int(data.split("_")[2])
            try:
                chat = await client.get_chat(cid)
                mode = await Seishiro.get_channel_mode(cid)
                status = "ON" if mode == "on" else "OFF"
                new_mode = "off" if mode == "on" else "on"
                buttons = [
                    [InlineKeyboardButton(f"ForceSub Mode {'OFF' if mode == 'on' else 'ON'}",
                                          callback_data=f"rfs_toggle_{cid}_{new_mode}")],
                    [InlineKeyboardButton("back", callback_data="fsub_back")]
                ]
                await callback_query.message.edit_text(
                    f"Channel: {chat.title}\nCurrent Force-Sub Mode: {status}",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            except Exception:
                await callback_query.answer("Failed to fetch channel info", show_alert=True)

        elif data.startswith("rfs_toggle_"):
            parts = data.split("_")[2:]
            cid = int(parts[0])
            action = parts[1]
            mode = "on" if action == "on" else "off"

            await Seishiro.set_channel_mode(cid, mode)
            await callback_query.answer(f"Force-Sub set to {'ON' if mode == 'on' else 'OFF'}")

            chat = await client.get_chat(cid)
            status = "ON" if mode == "on" else "OFF"
            new_mode = "off" if mode == "on" else "on"
            buttons = [
                [InlineKeyboardButton(f"ForceSub Mode {'OFF' if mode == 'on' else 'ON'}",
                                      callback_data=f"rfs_toggle_{cid}_{new_mode}")],
                [InlineKeyboardButton("back", callback_data="fsub_back")]
            ]
            await callback_query.message.edit_text(
                f"Channel: {chat.title}\nCurrent Force-Sub Mode: {status}",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        elif data == "fsub_back":
            channels = await Seishiro.show_channels()
            buttons = []
            for cid in channels:
                try:
                    chat = await client.get_chat(cid)
                    mode = await Seishiro.get_channel_mode(cid)
                    status = "✅" if mode == "on" else "❌"
                    buttons.append([InlineKeyboardButton(f"{status} {chat.title}", callback_data=f"rfs_ch_{cid}")])
                except Exception:
                    continue

            if not buttons:
                buttons.append([InlineKeyboardButton("No Channels Found", callback_data="no_channels")])

            await callback_query.message.edit_text(
                "Select a channel to toggle its force-sub mode:",
                reply_markup=InlineKeyboardMarkup(buttons + [
                    [InlineKeyboardButton("Close", callback_data="close")]
                ])
            )

        elif data == "close":
            await callback_query.message.delete()
            try:
                await callback_query.message.reply_to_message.delete()
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Error in callback handler (data={data!r}): {e}", exc_info=True)
        try:
            await callback_query.answer("An error occurred. Please try again.", show_alert=True)
        except Exception:
            pass
