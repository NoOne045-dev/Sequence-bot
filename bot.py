import asyncio
import sys
from datetime import datetime
from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from config import *
from Plugins.route import web_server
from Database.database import Seishiro
from aiohttp import web

name = """
Files sequence bot started ✨ Credit:- @CosmicBotz
"""

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="Bot",
            api_hash=API_HASH,
            api_id=APP_ID,
            plugins={"root": "Plugins"},
            workers=TG_BOT_WORKERS,
            bot_token=TG_BOT_TOKEN,
        )
   
    async def start(self, *args, **kwargs):
        await super().start()
        usr_bot_me = await self.get_me()
        self.uptime = datetime.now()

        # Verify database connectivity early so a stale/old DB_URI shows up
        # as a clear log message now, instead of a silent hang later.
        try:
            await Seishiro.dbclient.admin.command("ping")
            print("Database connection OK.")
        except Exception as e:
            print(f"WARNING: Could not reach the database (check DB_URI/DB_NAME): {e}")
        
        # Set bot commands
        try:
            await self.set_bot_commands([
                BotCommand("start", "sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ"),
                BotCommand("ssequence", "sᴛᴀʀᴛ sᴇǫᴜᴇɴᴄɪɴɢ ꜰɪʟᴇs"),
                BotCommand("esequence", "ᴇɴᴅ sᴇǫᴜᴇɴᴄɪɴɢ ᴀɴᴅ sᴇɴᴅ"),
                BotCommand("mode", "ᴄʜᴀɴɢᴇ sᴏʀᴛɪɴɢ ᴍᴏᴅᴇ"),
                BotCommand("cancel", "ᴄᴀɴᴄᴇʟ ᴄᴜʀʀᴇɴᴛ sᴇǫᴜᴇɴᴄɪɴɢ"),
                BotCommand("add_dump", "sᴇᴛ ᴅᴜᴍᴘ ᴄʜᴀɴɴᴇʟ"),
                BotCommand("rem_dump", "ʀᴇᴍᴏᴠᴇ ᴅᴜᴍᴘ ᴄʜᴀɴɴᴇʟ"),
                BotCommand("dump_info", "ᴄʜᴇᴄᴋ ᴅᴜᴍᴘ ᴄʜᴀɴɴᴇʟ ɪɴꜰᴏ"),
                BotCommand("leaderboard", "sʜᴏᴡ ᴜsᴇʀ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ"),
                BotCommand("add_admin", "ᴀᴅᴅ ᴀᴅᴍɪɴ (ᴏɴʟʏ ᴀᴅᴍɪɴs)"),
                BotCommand("deladmin", "ʀᴇᴍᴏᴠᴇ ᴀᴅᴍɪɴ (ᴏɴʟʏ ᴀᴅᴍɪɴs)"),
                BotCommand("admins", "ʟɪsᴛ ᴀᴅᴍɪɴs (ᴏɴʟʏ ᴀᴅᴍɪɴs)"),
                BotCommand("ban", "ʙᴀɴ ᴜsᴇʀ (ᴏɴʟʏ ᴀᴅᴍɪɴs)"),
                BotCommand("unban", "ᴜɴʙᴀɴ ᴜsᴇʀ (ᴏɴʟʏ ᴀᴅᴍɪɴs)"),
                BotCommand("banned", "ʟɪsᴛ ʙᴀɴɴᴇᴅ ᴜsᴇʀs (ᴏɴʟʏ ᴀᴅᴍɪɴs)"),
                BotCommand("fsub_mode", "ᴄʜᴀɴɢᴇ ꜰsᴜʙ ᴍᴏᴅᴇ (ᴏɴʟʏ ᴀᴅᴍɪɴs)"),
                BotCommand("addchnl", "ᴀᴅᴅ ꜰsᴜʙ ᴄʜᴀɴɴᴇʟ (ᴏɴʟʏ ᴀᴅᴍɪɴs)"),
                BotCommand("delchnl", "ʀᴇᴍᴏᴠᴇ ꜰsᴜʙ ᴄʜᴀɴɴᴇʟ (ᴏɴʟʏ ᴀᴅᴍɪɴs)"),
                BotCommand("listchnl", "ʟɪsᴛ ꜰsᴜʙ ᴄʜᴀɴɴᴇʟs (ᴏɴʟʏ ᴀᴅᴍɪɴs)")
            ])
        except Exception as e:
            print(f"Error setting bot commands: {e}")
       
        # Notify bot restart
        try:
            await self.send_photo(
                chat_id=DATABASE_CHANNEL,
                photo="https://ibb.co/DH3N4Lyr",
                caption="**I ʀᴇsᴛᴀʀᴛᴇᴅ ᴀɢᴀɪɴ !**",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("ᴜᴘᴅᴀᴛᴇs", url="https://t.me/RexBots_Official")]]
                )
            )
        except Exception as e:
            print(f"Error sending restart notification: {e}")
       
        self.username = usr_bot_me.username
       
        # Web-response
        try:
            app = web.AppRunner(await web_server())
            await app.setup()
            bind_address = "0.0.0.0"
            await web.TCPSite(app, bind_address, PORT).start()
        except Exception as e:
            print(f"Error starting web server: {e}")
           
    async def stop(self, *args):
        await super().stop()
       
if __name__ == "__main__":
    Bot().run()
