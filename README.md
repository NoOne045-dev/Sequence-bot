<div align="center">

# 🤖 Advanced Telegram File Sequence Bot

<img src="https://img.shields.io/badge/Telegram-Bot-blue?style=for-the-badge&logo=telegram" alt="Telegram Bot">
<img src="https://img.shields.io/badge/Python-3.10+-yellow?style=for-the-badge&logo=python" alt="Python">
<img src="https://img.shields.io/badge/Pyrogram-v2.0+-blueviolet?style=for-the-badge&logo=telegram" alt="Pyrogram">
<img src="https://img.shields.io/badge/MongoDB-Database-green?style=for-the-badge&logo=mongodb" alt="MongoDB">
<img src="https://img.shields.io/badge/License-MIT-red?style=for-the-badge" alt="License">

### *An ultra-fast, intelligent Telegram bot designed for seamless file sorting, missing episode detection, dump channel routing with pause/resume support, custom caption templates, cover preservation, and multi-period leaderboards.*

[Features](#-key-features) • [Sorting Modes](#-sorting-modes) • [Commands](#-bot-commands) • [Environment Variables](#%EF%B8%8F-environment-variables) • [Deployment](#-deployment-guide) • [Credits](#-credits--acknowledgments)

</div>

---

## ✨ Key Features

### 📁 Advanced File Sequencing
- **Smart Regex Parsing**: Extracts show titles, season numbers (`S01`), episode numbers (`E01`-`E9999`), and quality tags (`480p`, `720p`, `1080p`, `HDRip`, `2K`, `4K`).
- **5 Sorting Modes**:
  - **Quality**: Sort strictly by resolution order.
  - **All (S→E→Q)**: Season → Episode → Quality (Classic series layout).
  - **All [S→Q→E]**: Season → Quality → Episode.
  - **Episode**: Sort purely by episode number.
  - **Season**: Sort purely by season number.
- **Batch Forwarding Support**: Gracefully receives forwarded batches of 100+ files with quiet debouncing and zero message spam.
- **Queue Arrival Preservation**: Files remain strictly in the order received during reception until sorting executes at `/esequence`.
- **Live Missing Files Alert**: Automatically scans received batches for missing episode numbers or quality variants and alerts the user in real-time **before** sequencing starts.
- **Cover Art & Thumbnail Preservation**: Uses MTProto server-side copy (`messages.ForwardMessages`) to ensure Telegram 8.1+ video covers and thumbnails are preserved without re-encoding.

---

### 📍 Dump Channel Routing with Pause / Resume
- **Custom Dump Channel**: Route all sequenced outputs directly to your private channel or group.
- **Pause & Resume**: Toggle output routing directly inside `/settings` using **⏸️ Pause** / **▶️ Resume**.
  - When **Active**, outputs deliver directly to your dump channel.
  - When **Paused**, outputs automatically redirect to your private DM without deleting your saved channel configuration.

---

### 📝 Dynamic Captions & Episode Separators
- **Custom Caption Template**: Use placeholders like `{caption}`, `{filename}`, `{show_title}`, `{season}`, `{episode}`, and `{quality}` formatted in HTML.
- **Episode Boundary Stickers**: Send a custom sticker at each episode transition in grouped modes.

---

### 📊 Activity Leaderboards & Personal Stats
- **Multi-Period Leaderboards**: View top users for **Today** (`daily`), **This Week** (`weekly`), **This Month** (`monthly`), and **All-Time** (`alltime`).
- **Personal Stats (`/mystats`)**: Track total files sequenced, total batches completed, favorite mode, and join date.

---

### 🔐 Channel Access Control & Admin Tools
- **Multi-Channel ForceSub**: Require users to join up to multiple mandatory channels before using the bot.
- **Admin Dashboard & Controls**: Add/remove admins, ban/unban users, broadcast mass messages, and check system status.

---

## 📝 Bot Commands

### 👤 User Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot and view main menu |
| `/ssequence` | Begin a file sequencing session |
| `/esequence` | Complete sequencing and output files |
| `/mode` | Change current file sorting mode |
| `/cancel` | Cancel current active session or setting |
| `/settings` | Open interactive settings panel (Dump channel, Pause toggle, Sticker, Caption) |
| `/add_dump` | Save custom dump channel ID or username |
| `/del_dump` | Remove saved dump channel |
| `/dump_info` | View current dump channel details |
| `/set_caption` | Set custom caption template |
| `/del_caption` | Remove caption template |
| `/caption_info` | View current caption template & placeholders |
| `/leaderboard` | View user activity leaderboards (Today, Week, Month, All-Time) |
| `/mystats` | Check personal sequencing statistics |
| `/help` | View help and usage instructions |
| `/about` | View bot credits and information |

---

### 👑 Admin & ForceSub Commands

| Command | Description |
|---------|-------------|
| `/dashboard` | View bot overview & system statistics |
| `/add_admin <user_id>` | Promote user to bot administrator |
| `/deladmin <user_id>` | Demote administrator |
| `/admins` | List active bot administrators |
| `/ban <user_id> [reason]` | Ban user from using the bot |
| `/unban <user_id>` | Unban user |
| `/banned` | List all banned users |
| `/broadcast` | Broadcast message to all registered users |
| `/fsub_mode` | View/toggle ForceSub channels status |
| `/addchnl <chat_id>` | Add mandatory subscription channel |
| `/delchnl <chat_id>` | Remove mandatory subscription channel |
| `/listchnl` | List configured ForceSub channels |

---

## ⚙️ Environment Variables

Create a `.env` file in the root directory:

```env
# Telegram API Credentials (from my.telegram.org)
API_ID=123456
API_HASH=your_api_hash_here
BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ
OWNER_ID=123456789

# Database Configuration (MongoDB Atlas or local)
DB_URI=mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority
DB_NAME=SequenceBot

# Optional Customizations & Links
DATABASE_CHANNEL=-1001234567890
GLOBAL_DUMP_CHANNEL=-1001234567890 # Auto background dump for all user sequences (defaults to DATABASE_CHANNEL)
UPDATES_URL=https://t.me/CosmicBotz
SUPPORT_URL=https://t.me/JustThreshold
ADMIN_URL=https://t.me/JustThreshold
START_PIC=https://ibb.co/84T5kmF7
FSUB_PIC=https://ibb.co/0RK2DVc5
PORT=8080
```


---

## 🚀 Deployment Guide

### Option 1: Local System / Linux VPS

```bash
# Clone the repository
git clone https://github.com/NoOne045-dev/Sequence-bot.git
cd Sequence-bot

# Install dependencies
pip install -r requirements.txt

# Create .env file and set your variables
nano .env

# Run the bot
python bot.py
```

---

### Option 2: Docker Container

```bash
# Build Docker image
docker build -t sequence-bot .

# Run Docker container
docker run -d --name sequence-bot --env-file .env sequence-bot
```

---

### Option 3: Heroku Deployment

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)

1. Fork or clone this repository to GitHub.
2. Click **Deploy to Heroku** above.
3. Configure your Environment Variables and deploy!

---

## 👨‍💻 Credits & Acknowledgments

- **Creator & Developer**: [Sudo User](https://t.me/JustThreshold) (`@JustThreshold`)
- **Founder & Network**: [CosmicBotz](https://t.me/CosmicBotz) (`@CosmicBotz`)
- **Framework**: Built with [Pyrogram](https://github.com/pyrogram/pyrogram) & [Motor](https://motor.readthedocs.io/)
- **Repository Link**: [https://github.com/NoOne045-dev/Sequence-bot](https://github.com/NoOne045-dev/Sequence-bot)

---

<div align="center">

### Made with ❤️ by [CosmicBotz](https://t.me/CosmicBotz)

**© 2026 Advanced Telegram File Sequence Bot. All Rights Reserved.**

</div>
