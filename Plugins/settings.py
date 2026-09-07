import logging

from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ParseMode

from config import *
from Database.database import CosmicBotz
from Plugins.start import check_ban, check_fsub
from Plugins.sequence import handle_floodwait, verify_and_set_dump_channel

logger = logging.getLogger(__name__)

# user_id -> {'action': 'dump' | 'sticker', 'chat_id': int, 'message_id': int}
pending_settings = {}


async def build_settings_view(user_id):
    dump_channel = await CosmicBotz.get_dump_channel(user_id)
    sticker = await CosmicBotz.get_episode_sticker(user_id)

    text = (
        "<b>⚙️ Yᴏᴜʀ Sᴇᴛᴛɪɴɢs</b>\n\n"
        f"📍 <b>Dump Channel:</b> <code>{dump_channel if dump_channel else 'Not set'}</code>\n"
        f"🎟️ <b>Episode Sticker:</b> {'Set ✅' if sticker else 'Not set'}\n\n"
        "<i>Episode sticker is sent at each episode boundary when sequencing "
        "in Episode-grouped modes (All, All [S→Q→E], Episode).</i>"
    )

    rows = [[InlineKeyboardButton("📍 Set/Change Dump Channel", callback_data="stg_set_dump")]]
    if dump_channel:
        rows.append([InlineKeyboardButton("🗑️ Remove Dump Channel", callback_data="stg_rem_dump")])

    rows.append([InlineKeyboardButton("🎟️ Set/Change Episode Sticker", callback_data="stg_set_sticker")])
    if sticker:
        rows.append([InlineKeyboardButton("🗑️ Remove Episode Sticker", callback_data="stg_rem_sticker")])

    rows.append([InlineKeyboardButton("Close ✖️", callback_data="stg_close")])

    return text, InlineKeyboardMarkup(rows)


@Client.on_message(filters.command("settings") & filters.private)
@check_ban
@check_fsub
async def settings_cmd(client: Client, message: Message):
    try:
        pending_settings.pop(message.from_user.id, None)
        text, kb = await build_settings_view(message.from_user.id)
        await handle_floodwait(message.reply_text, text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error in settings_cmd: {e}")
        await handle_floodwait(message.reply_text, "❌ An error occurred.")


@Client.on_callback_query(filters.regex(r"^stg_"))
async def settings_panel_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    data = cq.data

    try:
        if data == "stg_set_dump":
            pending_settings[user_id] = {'action': 'dump', 'chat_id': cq.message.chat.id, 'message_id': cq.message.id}
            await cq.answer()
            await cq.message.edit_text(
                "📍 Send the channel <b>ID</b> or <b>@username</b> now.\nSend /cancel to abort.",
                parse_mode=ParseMode.HTML
            )

        elif data == "stg_rem_dump":
            pending_settings.pop(user_id, None)
            await CosmicBotz.remove_dump_channel(user_id)
            await cq.answer("Dump channel removed")
            text, kb = await build_settings_view(user_id)
            await cq.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

        elif data == "stg_set_sticker":
            pending_settings[user_id] = {'action': 'sticker', 'chat_id': cq.message.chat.id, 'message_id': cq.message.id}
            await cq.answer()
            await cq.message.edit_text(
                "🎟️ Now send the <b>sticker</b> you want used between episodes.\nSend /cancel to abort.",
                parse_mode=ParseMode.HTML
            )

        elif data == "stg_rem_sticker":
            pending_settings.pop(user_id, None)
            await CosmicBotz.remove_episode_sticker(user_id)
            await cq.answer("Episode sticker removed")
            text, kb = await build_settings_view(user_id)
            await cq.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

        elif data == "stg_close":
            await cq.answer()
            pending_settings.pop(user_id, None)
            await cq.message.delete()

    except Exception as e:
        logger.error(f"Error in settings_panel_callback (data={data!r}): {e}", exc_info=True)
        try:
            await cq.answer("An error occurred. Please try again.", show_alert=True)
        except Exception:
            pass


# ==================== Cancel a pending settings input ====================

@Client.on_message(filters.command("cancel") & filters.private, group=-1)
async def settings_cancel_pending(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in pending_settings:
        pending = pending_settings.pop(user_id)
        try:
            text, kb = await build_settings_view(user_id)
            await client.edit_message_text(
                pending['chat_id'], pending['message_id'],
                "❌ Cancelled.\n\n" + text, reply_markup=kb, parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
    # Let the normal /cancel handler (sequence session cancel) still run.
    raise ContinuePropagation


# ==================== Capture text input (dump channel) ====================

@Client.on_message(filters.private & filters.text, group=-1)
async def settings_text_capture(client: Client, message: Message):
    user_id = message.from_user.id

    if message.text.startswith("/"):
        raise ContinuePropagation

    pending = pending_settings.get(user_id)
    if not pending or pending.get('action') != 'dump':
        raise ContinuePropagation

    raw_target = message.text.strip()
    success, msg, _ = await verify_and_set_dump_channel(client, user_id, raw_target)
    pending_settings.pop(user_id, None)

    text, kb = await build_settings_view(user_id)
    try:
        await client.edit_message_text(
            pending['chat_id'], pending['message_id'],
            msg + "\n\n" + text, reply_markup=kb, parse_mode=ParseMode.HTML
        )
    except Exception:
        await handle_floodwait(message.reply_text, msg, parse_mode=ParseMode.HTML)


# ==================== Capture sticker input (episode sticker) ====================

@Client.on_message(filters.private & filters.sticker, group=-1)
async def settings_sticker_capture(client: Client, message: Message):
    user_id = message.from_user.id
    pending = pending_settings.get(user_id)

    if not pending or pending.get('action') != 'sticker':
        raise ContinuePropagation

    sticker_id = message.sticker.file_id
    await CosmicBotz.set_episode_sticker(user_id, sticker_id)
    pending_settings.pop(user_id, None)

    text, kb = await build_settings_view(user_id)
    try:
        await client.edit_message_text(
            pending['chat_id'], pending['message_id'],
            "✅ Episode sticker saved!\n\n" + text, reply_markup=kb, parse_mode=ParseMode.HTML
        )
    except Exception:
        await handle_floodwait(message.reply_text, "✅ Episode sticker saved!")