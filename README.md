# Video Editor Bot 🎬

A powerful Telegram bot for editing videos with custom thumbnails and caption replacements.

## Features

�� **Video Editing:**
- Change thumbnails (single/bulk)
- Replace text in captions (find & replace)
- Batch processing support

📢 **Broadcasting:**
- Send messages to all users
- Track delivery status

👥 **User Management:**
- View all users
- Track active/blocked users
- Statistics dashboard

## Commands

**Owner Commands:**
- `/start` - Start the bot
- `/broadcast` - Broadcast message
- `/users` - List all users
- `/stats` - View statistics
- `/cancel` - Cancel operation

## How to Use

1. Send video(s) to the bot
2. Type "done" when finished
3. Send thumbnail photo
4. Choose to replace caption text (yes/no)
5. If yes, provide find & replace text
6. Get processed videos!

## Environment Variables

Set these on Render:
- `BOT_TOKEN` - Your bot token from @BotFather
- `OWNER_ID` - Your Telegram user ID

## Deploy on Render

1. Build Command: `pip install -r requirements.txt`
2. Start Command: `python bot.py`
3. Add environment variables
4. Deploy!

Runs 24/7 on Render free tier! ✅
