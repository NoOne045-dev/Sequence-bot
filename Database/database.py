import motor.motor_asyncio
import logging
from datetime import datetime, date
from typing import List, Optional
from config import *

logging.basicConfig(level=logging.INFO)


class Master:
    def __init__(self, DB_URL, DB_NAME):
        if not DB_URL or not DB_NAME:
            logging.error(
                "DB_URI / DB_NAME is empty. Set them in your environment (or .env) "
                "before starting the bot."
            )
        self.dbclient = motor.motor_asyncio.AsyncIOMotorClient(
            DB_URL,
            serverSelectionTimeoutMS=10000,  # fail fast (10s) instead of hanging
            connectTimeoutMS=10000,
        )
        self.database = self.dbclient[DB_NAME]

        # Collections
        self.user_data = self.database['users']
        self.channel_data = self.database['channels']
        self.admins_data = self.database['admins']
        self.del_timer_data = self.database['del_timer']
        self.ban_data = self.database['ban_data']
        self.fsub_data = self.database['fsub']
        self.rqst_fsub_data = self.database['request_forcesub']
        self.rqst_fsub_Channel_data = self.database['request_forcesub_channel']

        # Per-user sorting mode storage
        self.sequence_mode = self.database['sequence_mode']

        # Backward compatibility alias
        self.col = self.user_data

    def new_user(self, id, username=None):
        return dict(
            _id=int(id),
            username=username.lower() if username else None,
            join_date=date.today().isoformat(),
            ban_status=dict(
                is_banned=False,
                ban_duration=0,
                banned_on=date.max.isoformat(),
                ban_reason='',
            )
        )

    async def add_user(self, b, m):
        u = m.from_user
        if not await self.is_user_exist(u.id):
            user = self.new_user(u.id, u.username)
            try:
                await self.user_data.insert_one(user)
                logging.info(f"New user added: {u.id}")
            except Exception as e:
                logging.error(f"Error adding user {u.id}: {e}")
        else:
            logging.info(f"User {u.id} already exists")

    async def is_user_exist(self, id):
        try:
            user = await self.user_data.find_one({"_id": int(id)})
            return bool(user)
        except Exception as e:
            logging.error(f"Error checking user {id}: {e}")
            return False

    async def get_all_users(self):
        return self.user_data.find({})

    async def total_users_count(self):
        return await self.user_data.count_documents({})

    async def delete_user(self, user_id):
        await self.user_data.delete_one({"_id": int(user_id)})

    async def is_user_banned(self, user_id):
        try:
            user = await self.ban_data.find_one({"_id": int(user_id)})
            if user:
                ban_status = user.get("ban_status", {})
                return ban_status.get("is_banned", False)
            return False
        except Exception as e:
            logging.error(f"Error checking if user {user_id} is banned: {e}")
            return False

    # ==================== DUMP CHANNEL (Per User) ====================

    async def get_dump_channel(self, user_id: int) -> Optional[int]:
        """Get user's saved dump channel ID. Returns int or None."""
        try:
            doc = await self.user_data.find_one({"_id": int(user_id)}, {"dump_channel": 1})
            if doc and doc.get("dump_channel"):
                return int(doc["dump_channel"])
            return None
        except Exception as e:
            logging.error(f"Error getting dump_channel for {user_id}: {e}")
            return None

    async def set_dump_channel(self, user_id: int, channel_id: int) -> bool:
        """Save user's dump channel."""
        try:
            await self.user_data.update_one(
                {"_id": int(user_id)},
                {
                    "$set": {
                        "dump_channel": int(channel_id),
                        "dump_channel_updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            logging.info(f"Dump channel set for {user_id} → {channel_id}")
            return True
        except Exception as e:
            logging.error(f"Error setting dump_channel for {user_id}: {e}")
            return False

    async def remove_dump_channel(self, user_id: int) -> bool:
        """Remove user's saved dump channel."""
        try:
            result = await self.user_data.update_one(
                {"_id": int(user_id)},
                {"$unset": {"dump_channel": "", "dump_channel_updated_at": ""}}
            )
            if result.modified_count > 0:
                logging.info(f"Dump channel removed for user {user_id}")
                return True
            return False
        except Exception as e:
            logging.error(f"Error removing dump_channel for {user_id}: {e}")
            return False

    # ==================== EPISODE STICKER (Per User) ====================

    async def get_episode_sticker(self, user_id: int) -> Optional[str]:
        """Get user's saved episode-separator sticker file_id. Returns str or None."""
        try:
            doc = await self.user_data.find_one({"_id": int(user_id)}, {"episode_sticker": 1})
            if doc and doc.get("episode_sticker"):
                return doc["episode_sticker"]
            return None
        except Exception as e:
            logging.error(f"Error getting episode_sticker for {user_id}: {e}")
            return None

    async def set_episode_sticker(self, user_id: int, sticker_id: str) -> bool:
        """Save user's episode-separator sticker."""
        try:
            await self.user_data.update_one(
                {"_id": int(user_id)},
                {
                    "$set": {
                        "episode_sticker": sticker_id,
                        "episode_sticker_updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            logging.info(f"Episode sticker set for {user_id}")
            return True
        except Exception as e:
            logging.error(f"Error setting episode_sticker for {user_id}: {e}")
            return False

    async def remove_episode_sticker(self, user_id: int) -> bool:
        """Remove user's saved episode-separator sticker."""
        try:
            result = await self.user_data.update_one(
                {"_id": int(user_id)},
                {"$unset": {"episode_sticker": "", "episode_sticker_updated_at": ""}}
            )
            if result.modified_count > 0:
                logging.info(f"Episode sticker removed for user {user_id}")
                return True
            return False
        except Exception as e:
            logging.error(f"Error removing episode_sticker for {user_id}: {e}")
            return False

    # ==================== CAPTION TEMPLATE (Per User) ====================

    async def get_caption_template(self, user_id: int) -> Optional[str]:
        """Get user's saved caption template. Returns str or None (means use plain filename)."""
        try:
            doc = await self.user_data.find_one({"_id": int(user_id)}, {"caption_template": 1})
            if doc and doc.get("caption_template"):
                return doc["caption_template"]
            return None
        except Exception as e:
            logging.error(f"Error getting caption_template for {user_id}: {e}")
            return None

    async def set_caption_template(self, user_id: int, template: str) -> bool:
        """Save user's caption template."""
        try:
            await self.user_data.update_one(
                {"_id": int(user_id)},
                {
                    "$set": {
                        "caption_template": template,
                        "caption_template_updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            logging.info(f"Caption template set for {user_id}")
            return True
        except Exception as e:
            logging.error(f"Error setting caption_template for {user_id}: {e}")
            return False

    async def remove_caption_template(self, user_id: int) -> bool:
        """Remove user's saved caption template (falls back to plain filename)."""
        try:
            result = await self.user_data.update_one(
                {"_id": int(user_id)},
                {"$unset": {"caption_template": "", "caption_template_updated_at": ""}}
            )
            if result.modified_count > 0:
                logging.info(f"Caption template removed for user {user_id}")
                return True
            return False
        except Exception as e:
            logging.error(f"Error removing caption_template for {user_id}: {e}")
            return False

    # ==================== SEQUENCE MODE (Sorting Preference) ====================

    async def get_sequence_mode(self, user_id: int) -> str:
        """
        Get user's preferred sorting mode.
        Default: "All"
        """
        try:
            doc = await self.sequence_mode.find_one({"_id": int(user_id)})
            if doc and "mode" in doc:
                mode = doc["mode"]
                # All currently supported modes
                if mode in ["Quality", "All", "AllSQE", "Episode", "Season"]:
                    return mode
            return "All"  # Default when no document or invalid value
        except Exception as e:
            logging.error(f"Error getting sequence_mode for {user_id}: {e}")
            return "All"

    async def set_sequence_mode(self, user_id: int, mode: str) -> bool:
        """
        Save user's sorting mode preference.
        Supported modes: Quality, All, AllSQE, Episode, Season
        """
        allowed_modes = {"Quality", "All", "AllSQE", "Episode", "Season"}

        if mode not in allowed_modes:
            logging.warning(f"Attempted to set invalid sequence mode '{mode}' for user {user_id}")
            return False

        try:
            await self.sequence_mode.update_one(
                {"_id": int(user_id)},
                {
                    "$set": {
                        "mode": mode,
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            logging.info(f"Sequence mode updated: {user_id} → {mode}")
            return True
        except Exception as e:
            logging.error(f"Error setting sequence_mode for {user_id}: {e}")
            return False

    # ==================== ADMIN FUNCTIONS ====================

    async def is_admin(self, user_id: int) -> bool:
        return bool(await self.admins_data.find_one({"_id": int(user_id)}))

    async def add_admin(self, user_id: int) -> bool:
        try:
            await self.admins_data.update_one(
                {"_id": int(user_id)},
                {"$set": {"_id": int(user_id), "added_at": datetime.utcnow()}},
                upsert=True
            )
            return True
        except Exception as e:
            logging.error(f"Error adding admin {user_id}: {e}")
            return False

    async def remove_admin(self, user_id: int) -> bool:
        result = await self.admins_data.delete_one({"_id": int(user_id)})
        return result.deleted_count > 0

    async def list_admins(self) -> list:
        admins = await self.admins_data.find({}).to_list(None)
        return [a["_id"] for a in admins]

    # ==================== FSUB & OTHER FUNCTIONS ====================

    async def add_fsub_channel(self, channel_id: int) -> bool:
        try:
            await self.fsub_data.update_one(
                {"channel_id": channel_id},
                {"$set": {"channel_id": channel_id, "created_at": datetime.utcnow(), "status": "active", "mode": "off"}},
                upsert=True
            )
            return True
        except Exception as e:
            logging.error(f"Error adding FSub channel {channel_id}: {e}")
            return False

    async def remove_fsub_channel(self, channel_id: int) -> bool:
        result = await self.fsub_data.delete_one({"channel_id": channel_id})
        return result.deleted_count > 0

    async def get_fsub_channels(self) -> List[int]:
        cursor = self.fsub_data.find({"status": "active"})
        channels = await cursor.to_list(None)
        return [ch["channel_id"] for ch in channels if "channel_id" in ch]

    async def show_channels(self) -> List[int]:
        """Alias for get_fsub_channels for backward compatibility"""
        return await self.get_fsub_channels()

    async def get_channel_mode(self, channel_id: int) -> str:
        data = await self.fsub_data.find_one({'channel_id': channel_id})
        return data.get("mode", "off") if data else "off"

    async def get_channel_mode_all(self, channel_id: int) -> str:
        """Alias for get_channel_mode for backward compatibility"""
        return await self.get_channel_mode(channel_id)

    async def set_channel_mode(self, channel_id: int, mode: str):
        await self.fsub_data.update_one(
            {'channel_id': channel_id},
            {'$set': {'mode': mode}},
            upsert=True
        )

    # Request ForceSub helpers
    async def req_user(self, channel_id: int, user_id: int):
        await self.rqst_fsub_Channel_data.update_one(
            {'channel_id': int(channel_id)},
            {'$addToSet': {'user_ids': int(user_id)}},
            upsert=True
        )

    async def del_req_user(self, channel_id: int, user_id: int):
        await self.rqst_fsub_Channel_data.update_one(
            {'channel_id': channel_id},
            {'$pull': {'user_ids': user_id}}
        )

    async def req_user_exist(self, channel_id: int, user_id: int) -> bool:
        found = await self.rqst_fsub_Channel_data.find_one({
            'channel_id': int(channel_id),
            'user_ids': int(user_id)
        })
        return bool(found)


# Initialize
CosmicBotz = Master(DB_URL, DB_NAME)