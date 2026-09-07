from config import *
from Plugins.callbacks import *
from Plugins.start import *
from Database.database import CosmicBotz
from pyrogram.types import Message, ChatMemberUpdated, ChatJoinRequest, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram import Client, filters
from pyrogram.errors import PeerIdInvalid, FloodWait, InputUserDeactivated, UserIsBlocked, RPCError
from pyrogram.enums import ChatType, ChatMemberStatus, ParseMode
from datetime import date, timedelta
import asyncio
import time
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

async def check_admin(filter, client, message):
    try:
        user_id = message.from_user.id
        if user_id == OWNER_ID:
            return True
        return await CosmicBotz.is_admin(user_id)
    except Exception as e:
        logger.error(f"Exception in check_admin: {e}")
        return False

admin = filters.create(check_admin)

#============== Admin commands =============================

# Commands for adding admins by owner
@Client.on_message(filters.command('add_admin') & filters.private & admin)
async def add_admins(client: Client, message: Message):
    try:
        pro = await message.reply("<b><i>ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ..</i></b>", quote=True)
        admin_ids = await CosmicBotz.list_admins()
        admins = message.text.split()[1:]

        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close")]])

        if not admins:
            return await pro.edit(
                "<b>Usᴇ ɪᴛ ʟɪᴋᴇ ᴛʜɪs:</b> <code>/add_admin 1234567890</code>\n<b>Oʀ:</b> <code>/add_admin 1234567890 9876543210</code>",
                reply_markup=reply_markup
            )

        successfully_added = []
        admin_list = ""
        
        for admin_id in admins:
            try:
                user_id = int(admin_id)
            except:
                admin_list += f"<blockquote><b>❌ Iɴᴠᴀʟɪᴅ ID: <code>{admin_id}</code></b></blockquote>\n"
                continue

            if user_id in admin_ids:
                try:
                    user = await client.get_users(user_id)
                    admin_list += f"<blockquote><b>⚠️ {user.mention} (<code>{user_id}</code>) ᴀʟʀᴇᴀᴅʏ ᴇxɪsᴛs.</b></blockquote>\n"
                except:
                    admin_list += f"<blockquote><b>⚠️ ID <code>{user_id}</code> ᴀʟʀᴇᴀᴅʏ ᴇxɪsᴛs.</b></blockquote>\n"
                continue

            try:
                user = await client.get_users(user_id)
                await CosmicBotz.add_admin(user_id)
                successfully_added.append(user_id)
                admin_list += f"<b>• Nᴀᴍᴇ: {user.mention}\n⚡ Iᴅ: <code>{user_id}</code></b>\n\n"
            except Exception as e:
                admin_list += f"<blockquote><b>❌ Cᴀɴ'ᴛ ғᴇᴛᴄʜ ᴜsᴇʀ: <code>{user_id}</code></b></blockquote>\n"

        if successfully_added:
            await pro.edit(
                f"<b><u>✅ Aᴅᴍɪɴ(s) ᴀᴅᴅᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ</u></b>\n\n{admin_list}",
                reply_markup=reply_markup
            )
        else:
            await pro.edit(
                f"<b>❌ Nᴏ ᴀᴅᴍɪɴs ᴡᴇʀᴇ ᴀᴅᴅᴇᴅ:</b>\n\n{admin_list.strip()}",
                reply_markup=reply_markup
            )
    except Exception as e:
        await pro.edit(f"<b>❌ Eʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ:</b> <code>{str(e)}</code>")


@Client.on_message(filters.command('deladmin') & filters.private & admin)
async def delete_admins(client: Client, message: Message):
    try:
        pro = await message.reply("<b><i>ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ..</i></b>", quote=True)
        admin_ids = await CosmicBotz.list_admins()
        admins = message.text.split()[1:]

        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close")]])

        if not admins:
            return await pro.edit(
                "<b>Usᴇ ɪᴛ ʟɪᴋᴇ ᴛʜɪs:</b> <code>/deladmin 1234567890</code>\n<b>Oʀ ᴜsᴇ:</b> <code>/deladmin all</code> <b>ᴛᴏ ʀᴇᴍᴏᴠᴇ ᴀʟʟ ᴀᴅᴍɪɴs</b>",
                reply_markup=reply_markup
            )

        if len(admins) == 1 and admins[0].lower() == "all":
            if admin_ids:
                removed_list = ""
                for id in admin_ids:
                    try:
                        user = await client.get_users(id)
                        removed_list += f"<b>• Nᴀᴍᴇ: {user.mention}\n⚡ Iᴅ: <code>{id}</code></b>\n\n"
                    except:
                        removed_list += f"<b>• Iᴅ: <code>{id}</code></b>\n\n"
                    await CosmicBotz.remove_admin(id)
                return await pro.edit(
                    f"<b><u>✅ Rᴇᴍᴏᴠᴇᴅ ᴀʟʟ ᴀᴅᴍɪɴs:</u></b>\n\n{removed_list}",
                    reply_markup=reply_markup
                )
            else:
                return await pro.edit(
                    "<b><blockquote>⚠️ Nᴏ ᴀᴅᴍɪɴ IDs ᴛᴏ ʀᴇᴍᴏᴠᴇ.</blockquote></b>",
                    reply_markup=reply_markup
                )

        if admin_ids:
            passed = ''
            for admin_id in admins:
                try:
                    id = int(admin_id)
                except:
                    passed += f"<blockquote><b>❌ Iɴᴠᴀʟɪᴅ ID: <code>{admin_id}</code></b></blockquote>\n"
                    continue

                if id in admin_ids:
                    try:
                        user = await client.get_users(id)
                        passed += f"<b>• Nᴀᴍᴇ: {user.mention}\n⚡ Iᴅ: <code>{id}</code></b>\n\n"
                    except:
                        passed += f"<b>• Iᴅ: <code>{id}</code></b>\n\n"
                    await CosmicBotz.remove_admin(id)
                else:
                    passed += f"<blockquote><b>⚠️ ID <code>{id}</code> ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ ᴀᴅᴍɪɴ ʟɪsᴛ.</b></blockquote>\n"

            await pro.edit(
                f"<b><u>✅ Rᴇᴍᴏᴠᴇᴅ ᴀᴅᴍɪɴ ɪᴅ:</u></b>\n\n{passed}",
                reply_markup=reply_markup
            )
        else:
            await pro.edit(
                "<b><blockquote>⚠️ Nᴏ ᴀᴅᴍɪɴ IDs ᴀᴠᴀɪʟᴀʙʟᴇ ᴛᴏ ᴅᴇʟᴇᴛᴇ.</blockquote></b>",
                reply_markup=reply_markup
            )
    except Exception as e:
        await pro.edit(f"<b>❌ Eʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ:</b> <code>{str(e)}</code>")


@Client.on_message(filters.command('admins') & filters.private & admin)
async def get_admins(client: Client, message: Message):
    try:
        pro = await message.reply("<b><i>ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ..</i></b>", quote=True)
        admin_ids = await CosmicBotz.list_admins()

        if not admin_ids:
            admin_list = "<b><blockquote>❌ Nᴏ ᴀᴅᴍɪɴs ғᴏᴜɴᴅ.</blockquote></b>"
        else:
            admin_list = ""
            for idx, id in enumerate(admin_ids, 1):
                try:
                    user = await client.get_users(id)
                    admin_list += f"<b>{idx}. Nᴀᴍᴇ: {user.mention}\n⚡ Iᴅ: <code>{id}</code></b>\n\n"
                except:
                    admin_list += f"<b>{idx}. Iᴅ: <code>{id}</code></b>\n\n"

        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close")]])
        await pro.edit(
            f"<b>⚡ Cᴜʀʀᴇɴᴛ ᴀᴅᴍɪɴ ʟɪsᴛ:</b>\n\n{admin_list}",
            reply_markup=reply_markup
        )
    except Exception as e:
        await pro.edit(f"<b>❌ Eʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ:</b> <code>{str(e)}</code>")

#============== Ban commands =============================

@Client.on_message(filters.command("ban") & filters.private & admin)
async def ban_user(bot, message):
    try:
        command_parts = message.text.split(maxsplit=2)
        if len(command_parts) < 2:
            await message.reply_text(
                "<b>Usᴇ ɪᴛ ʟɪᴋᴇ ᴛʜɪs:</b> <code>/ban &lt;ᴜsᴇʀ_ɪᴅ&gt; [ʀᴇᴀsᴏɴ]</code>"
            )
            return

        user_id_str = command_parts[1]
        reason = command_parts[2] if len(command_parts) > 2 else "Nᴏ ʀᴇᴀsᴏɴ ᴘʀᴏᴠɪᴅᴇᴅ"

        if not user_id_str.isdigit():
            await message.reply_text(
                "<b>Usᴇ ɪᴛ ʟɪᴋᴇ ᴛʜɪs:</b> <code>/ban &lt;ᴜsᴇʀ_ɪᴅ&gt; [ʀᴇᴀsᴏɴ]</code>"
            )
            return
            
        user_id = int(user_id_str)
        
        try:
            user = await bot.get_users(user_id)
            user_mention = user.mention
        except:
            user_mention = f"<code>{user_id}</code>"
            
        await CosmicBotz.ban_data.update_one(
            {"_id": user_id},
            {"$set": {
                "ban_status.is_banned": True,
                "ban_status.ban_reason": reason,
                "ban_status.banned_on": date.today().isoformat()
            }},
            upsert=True
        )
        
        await message.reply_text(
            f"<b>🚫 Usᴇʀ ʙᴀɴɴᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ</b>\n\n"
            f"<b>• Usᴇʀ: {user_mention}\n"
            f"⚡ Usᴇʀ ID: <code>{user_id}</code>\n"
            f"📝 Rᴇᴀsᴏɴ: {reason}\n"
            f"📅 Bᴀɴɴᴇᴅ ᴏɴ: {date.today().strftime('%d-%m-%Y')}</b>"
        )
        
        # Notify user
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"<b>🚫 Yᴏᴜ ʜᴀᴠᴇ ʙᴇᴇɴ ʙᴀɴɴᴇᴅ</b>\n\n"
                     f"<blockquote><b>Rᴇᴀsᴏɴ: {reason}\n"
                     f"Dᴀᴛᴇ: {date.today().strftime('%d-%m-%Y')}</b></blockquote>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cᴏɴᴛᴀᴄᴛ Aᴅᴍɪɴ", url=ADMIN_URL)]])
            )
        except:
            pass
            
    except Exception as e:
        await message.reply_text(f"<b>❌ Eʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ:</b> <code>{str(e)}</code>")


@Client.on_message(filters.command("unban") & filters.private & admin)
async def unban_user(bot, message):
    try:
        if len(message.text.split()) < 2:
            await message.reply_text(
                "<b>Usᴇ ɪᴛ ʟɪᴋᴇ ᴛʜɪs:</b> <code>/unban &lt;ᴜsᴇʀ_ɪᴅ&gt;</code>"
            )
            return
            
        user_id = int(message.text.split()[1])
        
        try:
            user = await bot.get_users(user_id)
            user_mention = user.mention
        except:
            user_mention = f"<code>{user_id}</code>"
            
        await CosmicBotz.ban_data.update_one(
            {"_id": user_id},
            {"$set": {
                "ban_status.is_banned": False,
                "ban_status.ban_reason": "",
                "ban_status.banned_on": None
            }}
        )
        
        await message.reply_text(
            f"<b>✅ Usᴇʀ ᴜɴʙᴀɴɴᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ</b>\n\n"
            f"<b>• Usᴇʀ: {user_mention}\n"
            f"⚡ Usᴇʀ ID: <code>{user_id}</code>\n"
            f"📅 Uɴʙᴀɴɴᴇᴅ ᴏɴ: {date.today().strftime('%d-%m-%Y')}</b>"
        )
        
        # Notify user
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"<b>✅ Yᴏᴜ ʜᴀᴠᴇ ʙᴇᴇɴ ᴜɴʙᴀɴɴᴇᴅ</b>\n\n"
                     f"<blockquote><b>Yᴏᴜ ᴄᴀɴ ɴᴏᴡ ᴜsᴇ ᴛʜᴇ ʙᴏᴛ ᴀɢᴀɪɴ!\n"
                     f"Dᴀᴛᴇ: {date.today().strftime('%d-%m-%Y')}</b></blockquote>"
            )
        except:
            pass
            
    except Exception as e:
        await message.reply_text(
            "<b>Usᴇ ɪᴛ ʟɪᴋᴇ ᴛʜɪs:</b> <code>/unban &lt;ᴜsᴇʀ_ɪᴅ&gt;</code>\n\n"
            f"<b>❌ Eʀʀᴏʀ:</b> <code>{str(e)}</code>"
        )


@Client.on_message(filters.command("banned") & filters.private & admin)
async def banned_list(bot, message):
    try:
        msg = await message.reply("<b><i>ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ..</i></b>")
        cursor = CosmicBotz.ban_data.find({"ban_status.is_banned": True})
        lines = []
        count = 0
        
        async for user in cursor:
            count += 1
            uid = user['_id']
            reason = user.get('ban_status', {}).get('ban_reason', 'Nᴏ ʀᴇᴀsᴏɴ')
            banned_date = user.get('ban_status', {}).get('banned_on', 'Uɴᴋɴᴏᴡɴ')
            
            try:
                user_obj = await bot.get_users(uid)
                name = user_obj.mention
            except PeerIdInvalid:
                name = f"<code>{uid}</code>"
            except:
                name = f"<code>{uid}</code>"
                
            lines.append(
                f"<b>{count}. {name}\n"
                f"⚡ ID: <code>{uid}</code>\n"
                f"📝 Rᴇᴀsᴏɴ: {reason}\n"
                f"📅 Dᴀᴛᴇ: {banned_date}</b>\n"
            )

        if not lines:
            await msg.edit(
                "<b><blockquote>✅ Nᴏ ᴜsᴇʀ(s) ɪs ᴄᴜʀʀᴇɴᴛʟʏ ʙᴀɴɴᴇᴅ</blockquote></b>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close")]])
            )
        else:
            banned_text = f"<b>🚫 Bᴀɴɴᴇᴅ Usᴇʀs Lɪsᴛ</b>\n\n{''.join(lines[:50])}"
            if len(lines) > 50:
                banned_text += f"\n<i>...ᴀɴᴅ {len(lines) - 50} ᴍᴏʀᴇ</i>"
                
            await msg.edit(
                banned_text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close")]])
            )
    except Exception as e:
        await msg.edit(f"<b>❌ Eʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ:</b> <code>{str(e)}</code>")

# Request force sub mode command
@Client.on_message(filters.command('fsub_mode') & filters.private & admin)
async def change_force_sub_mode(client: Client, message: Message):
    temp = await message.reply("<b><i>ᴡᴀɪᴛ ᴀ sᴇᴄ..</i></b>", quote=True)
    channels = await CosmicBotz.show_channels()

    if not channels:
        return await temp.edit("<b>❌ No force-sub channels found.</b>")

    buttons = []
    for ch_id in channels:
        try:
            chat = await client.get_chat(ch_id)
            mode = await CosmicBotz.get_channel_mode(ch_id)
            status = "🟢" if mode == "on" else "🔴"
            title = f"{status} {chat.title}"
            buttons.append([InlineKeyboardButton(title, callback_data=f"rfs_ch_{ch_id}")])
        except:
            buttons.append([InlineKeyboardButton(f"⚠️ {ch_id} (Unavailable)", callback_data=f"rfs_ch_{ch_id}")])

    buttons.append([InlineKeyboardButton("Close ✖️", callback_data="close")])

    await temp.edit(
        "<b>⚡ Select a channel to toggle Force-Sub Mode:</b>",
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True
    )

# This handler captures membership updates
@Client.on_chat_member_updated()
async def handle_Chatmembers(client, chat_member_updated: ChatMemberUpdated):
    chat_id = chat_member_updated.chat.id
    old_member = chat_member_updated.old_chat_member

    if not old_member or not old_member.user:
        return

    if old_member.status == ChatMemberStatus.MEMBER:
        user_id = old_member.user.id

        if await CosmicBotz.req_user_exist(chat_id, user_id):
            await CosmicBotz.del_req_user(chat_id, user_id)


# This handler will capture any join request to the channel/group
@Client.on_chat_join_request()
async def handle_join_request(client, chat_join_request):
    chat_id = chat_join_request.chat.id
    user_id = chat_join_request.from_user.id

    all_channels = await CosmicBotz.show_channels()

    if chat_id in all_channels:
        if not await CosmicBotz.req_user_exist(chat_id, user_id):
            await CosmicBotz.req_user(chat_id, user_id)

@Client.on_message(filters.command('addchnl') & filters.private & admin)
async def add_force_sub(client: Client, message: Message):
    temp = await message.reply("<b><i>ᴡᴀɪᴛ ᴀ sᴇᴄ..</i></b>", quote=True)
    args = message.text.split(maxsplit=1)

    if len(args) != 2:
        return await temp.edit(
            "<b>Usage:</b> <code>/addchnl -100XXXXXXXXXX</code>\n<b>Add only one channel at a time.</b>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Close ✖️", callback_data="close")]])
        )

    try:
        channel_id = int(args[1])
    except ValueError:
        return await temp.edit("<b>❌ Invalid Channel ID!</b>")

    all_channels = await CosmicBotz.show_channels()
    channel_ids_only = [cid if isinstance(cid, int) else cid[0] for cid in all_channels]
    if channel_id in channel_ids_only:
        try:
            chat = await client.get_chat(channel_id)
            return await temp.edit(f"<b>Channel already exists:</b>\n<b>Name:</b> {chat.title}\n<b>ID:</b> <code>{channel_id}</code>")
        except:
            return await temp.edit(f"<b>Channel already exists:</b> <code>{channel_id}</code>")

    try:
        chat = await client.get_chat(channel_id)

        if chat.type != ChatType.CHANNEL:
            return await temp.edit("<b>❌ Only public or private channels are allowed.</b>")

        member = await client.get_chat_member(chat.id, "me")

        if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return await temp.edit("<b>❌ Bot must be an admin in that channel.</b>")

        try:
            link = await client.export_chat_invite_link(chat.id)
        except Exception:
            link = f"https://t.me/{chat.username}" if chat.username else f"https://t.me/c/{str(chat.id)[4:]}"

        await CosmicBotz.add_fsub_channel(channel_id)
        return await temp.edit(
            f"<b>✅ Force-sub channel added successfully!</b>\n\n"
            f"<b>Name:</b> <a href='{link}'>{chat.title}</a>\n"
            f"<b>ID:</b> <code>{channel_id}</code>",
            disable_web_page_preview=True
        )

    except Exception as e:
        return await temp.edit(
            f"<b>❌ Failed to add channel:</b>\n<code>{channel_id}</code>\n\n<i>{e}</i>"
        )

# Delete channel
@Client.on_message(filters.command('delchnl') & filters.private & admin)
async def del_force_sub(client: Client, message: Message):
    temp = await message.reply("<b><i>ᴡᴀɪᴛ ᴀ sᴇᴄ..</i></b>", quote=True)
    args = message.text.split(maxsplit=1)
    all_channels = await CosmicBotz.show_channels()

    if len(args) != 2:
        return await temp.edit("<b>Usage:</b> <code>/delchnl &lt;channel_id | all&gt;</code>")

    if args[1].lower() == "all":
        if not all_channels:
            return await temp.edit("<b>❌ No force-sub channels found.</b>")
        for ch_id in all_channels:
            await CosmicBotz.remove_fsub_channel(ch_id)
        return await temp.edit("<b>✅ All force-sub channels have been removed.</b>")

    try:
        ch_id = int(args[1])
    except ValueError:
        return await temp.edit("<b>❌ Invalid Channel ID</b>")

    if ch_id in all_channels:
        await CosmicBotz.remove_fsub_channel(ch_id)
        try:
            chat = await client.get_chat(ch_id)
            return await temp.edit(f"<b>✅ Channel removed:</b>\n<b>Name:</b> {chat.title}\n<b>ID:</b> <code>{ch_id}</code>")
        except:
            return await temp.edit(f"<b>✅ Channel removed:</b> <code>{ch_id}</code>")
    else:
        try:
            chat = await client.get_chat(ch_id)
            return await temp.edit(f"<b>❌ Channel not found in force-sub list:</b>\n<b>Name:</b> {chat.title}\n<b>ID:</b> <code>{ch_id}</code>")
        except:
            return await temp.edit(f"<b>❌ Channel not found in force-sub list:</b> <code>{ch_id}</code>")

# View all channels
@Client.on_message(filters.command('listchnl') & filters.private & admin)
async def list_force_sub_channels(client: Client, message: Message):
    temp = await message.reply("<b><i>ᴡᴀɪᴛ ᴀ sᴇᴄ..</i></b>", quote=True)
    channels = await CosmicBotz.show_channels()

    if not channels:
        return await temp.edit("<b>❌ No force-sub channels found.</b>")

    result = "<b>⚡ Force-sub Channels:</b>\n\n"
    for ch_id in channels:
        try:
            chat = await client.get_chat(ch_id)
            link = chat.invite_link or await client.export_chat_invite_link(chat.id)
            result += f"<b>•</b> <a href='{link}'>{chat.title}</a> [<code>{ch_id}</code>]\n"
        except Exception:
            result += f"<b>•</b> <code>{ch_id}</code> — <i>Unavailable</i>\n"

    await temp.edit(result, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Close ✖️", callback_data="close")]]))

@Client.on_message(filters.command("broadcast") & filters.private & admin)
async def broadcast_handler(client: Client, m: Message):
    try:
        if not m.reply_to_message:
            return await m.reply_text(
                "<b>⚠️ Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ ɪᴛ!</b>\n\n"
                "<i>Usᴀɢᴇ: Rᴇᴘʟʏ ᴛᴏ ᴀɴʏ ᴍᴇssᴀɢᴇ ᴀɴᴅ ᴜsᴇ /broadcast</i>",
                parse_mode=ParseMode.HTML
            )
        
        try:
            all_users = await CosmicBotz.get_all_users()
        except Exception as e:
            logger.error(f"Error fetching users from database: {e}")
            return await m.reply_text(
                "<b>❌ Eʀʀᴏʀ ғᴇᴛᴄʜɪɴɢ ᴜsᴇʀs ғʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ!</b>",
                parse_mode=ParseMode.HTML
            )
        
        broadcast_msg = m.reply_to_message
        
        try:
            sts_msg = await m.reply_text("Bʀᴏᴀᴅᴄᴀsᴛ Sᴛᴀʀᴛᴇᴅ...!!")
        except Exception as e:
            logger.error(f"Error sending broadcast start message: {e}")
            return
        
        done = 0
        failed = 0
        success = 0
        start_time = time.time()
        
        try:
            total_users = await CosmicBotz.total_users_count()
        except Exception as e:
            logger.error(f"Error getting total users count: {e}")
            total_users = 0
        
        try:
            async for user in all_users:
                try:
                    sts = await send_msg(user['_id'], broadcast_msg)
                    if sts == 200:
                        success += 1
                    else:
                        failed += 1
                    if sts == 400:
                        try:
                            await CosmicBotz.delete_user(user['_id'])
                        except Exception as e:
                            logger.error(f"Error deleting user {user['_id']}: {e}")
                    done += 1
                    
                    if done % 50 == 0:
                        try:
                            await sts_msg.edit(
                                f"Broadcast In Progress: \n\n"
                                f"Total Users {total_users} \n"
                                f"Completed : {done} / {total_users}\n"
                                f"Success : {success}\n"
                                f"Failed : {failed}"
                            )
                        except FloodWait as e:
                            logger.warning(f"FloodWait during status update: waiting {e.value}s")
                            await asyncio.sleep(e.value)
                        except Exception as e:
                            logger.error(f"Error updating broadcast status: {e}")
                            
                except Exception as e:
                    logger.error(f"Error processing user {user.get('_id', 'unknown')}: {e}")
                    failed += 1
                    done += 1
                    continue
            
            completed_in = timedelta(seconds=int(time.time() - start_time))
            
            try:
                await sts_msg.edit(
                    f"Bʀᴏᴀᴅᴄᴀꜱᴛ Cᴏᴍᴩʟᴇᴛᴇᴅ: \n"
                    f"Cᴏᴍᴩʟᴇᴛᴇᴅ Iɴ {completed_in}.\n\n"
                    f"Total Users {total_users}\n"
                    f"Completed: {done} / {total_users}\n"
                    f"Success: {success}\n"
                    f"Failed: {failed}"
                )
            except Exception as e:
                logger.error(f"Error sending final broadcast status: {e}")
                try:
                    await m.reply_text(
                        f"Bʀᴏᴀᴅᴄᴀꜱᴛ Cᴏᴍᴩʟᴇᴛᴇᴅ: \n"
                        f"Cᴏᴍᴩʟᴇᴛᴇᴅ Iɴ {completed_in}.\n\n"
                        f"Total Users {total_users}\n"
                        f"Completed: {done} / {total_users}\n"
                        f"Success: {success}\n"
                        f"Failed: {failed}"
                    )
                except Exception as e2:
                    logger.error(f"Error sending fallback broadcast status: {e2}")
                    
        except Exception as e:
            logger.error(f"Critical error during broadcast loop: {e}")
            try:
                await sts_msg.edit(
                    f"<b>❌ Bʀᴏᴀᴅᴄᴀsᴛ Fᴀɪʟᴇᴅ!</b>\n\n"
                    f"Completed: {done}\n"
                    f"Success: {success}\n"
                    f"Failed: {failed}\n\n"
                    f"<blockquote expandable><b>Eʀʀᴏʀ:</b> {str(e)}</blockquote>",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
                
    except Exception as e:
        logger.error(f"Fatal error in broadcast_handler: {e}")
        try:
            await m.reply_text(
                f"<b>❌ Aɴ ᴜɴᴇxᴘᴇᴄᴛᴇᴅ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ! {e}</b>\n\n"
                f"<i>Pʟᴇᴀsᴇ ᴄᴏɴᴛᴀᴄᴛ ᴛʜᴇ ᴅᴇᴠᴇʟᴏᴘᴇʀ.</i>",
                parse_mode=ParseMode.HTML
            )
        except:
            pass

async def send_msg(user_id, message):
    try:
        await message.copy(chat_id=int(user_id))
        return 200
    except FloodWait as e:
        logger.warning(f"FloodWait for user {user_id}: waiting {e.value}s")
        await asyncio.sleep(e.value)
        return await send_msg(user_id, message)
    except InputUserDeactivated:
        logger.info(f"{user_id} : Deactivated")
        return 400
    except UserIsBlocked:
        logger.info(f"{user_id} : Blocked The Bot")
        return 400
    except PeerIdInvalid:
        logger.info(f"{user_id} : User ID Invalid")
        return 400
    except RPCError as e:
        logger.error(f"{user_id} : RPC Error - {e}")
        return 500
    except Exception as e:
        logger.error(f"{user_id} : Unexpected error - {e}")
        return 500

@Client.on_message(filters.command(["stats", "status"]) & filters.private & admin)
async def get_stats(bot: Client, message: Message):
    try:
        start_t = time.time()
        st = await message.reply("<b><i>ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ..</i></b>", quote=True)
        end_t = time.time()
        time_taken_ms = (end_t - start_t) * 1000

        total_users = await CosmicBotz.total_users_count()

        start_uptime = getattr(bot, "uptime", time.time())
        
        # Handle both float timestamps and datetime objects for uptime
        if hasattr(start_uptime, "timestamp"):
            uptime_seconds = int(time.time() - start_uptime.timestamp())
        else:
            uptime_seconds = int(time.time() - float(start_uptime))
        
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours:02d}h {minutes:02d}m {seconds:02d}s"

        await st.edit(
            f"<b>⚡ <u>Bᴏᴛ Sᴛᴀᴛᴜs &amp; Sᴛᴀᴛs</u></b>\n\n"
            f"<b>➲ Bᴏᴛ Uᴘᴛɪᴍᴇ:</b> <code>{uptime_str}</code>\n"
            f"<b>➲ Pɪɴɢ:</b> <code>{time_taken_ms:.2f} ms</code>\n"
            f"<b>➲ Vᴇʀsɪᴏɴ:</b> <code>2.0.0</code>\n"
            f"<b>➲ Tᴏᴛᴀʟ Uꜱᴇʀꜱ:</b> <code>{total_users}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close")]])
        )
    except Exception as e:
        logger.error(f"Error in get_stats handler: {e}")
        await message.reply_text(f"<b>❌ Eʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ:</b> <code>{str(e)}</code>")
