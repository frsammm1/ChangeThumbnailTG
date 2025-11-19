import logging
from telegram import Update, InputMediaVideo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telegram.constants import ParseMode
import os, json
from aiohttp import web
import asyncio
from io import BytesIO

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
OWNER_ID = int(os.environ.get('OWNER_ID', '0'))
PORT = int(os.environ.get('PORT', '10000'))

# States for conversation
WAITING_THUMBNAIL, WAITING_FIND_TEXT, WAITING_REPLACE_TEXT, WAITING_BROADCAST = range(4)

# Storage
user_data_store = {}
USER_DB_FILE = 'users.json'
broadcast_queue = {}

def load_users():
    try:
        if os.path.exists(USER_DB_FILE):
            with open(USER_DB_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_users(users):
    try:
        with open(USER_DB_FILE, 'w') as f:
            json.dump(users, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving users: {e}")

users_db = load_users()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user
    
    if str(user_id) not in users_db and user_id != OWNER_ID:
        users_db[str(user_id)] = {
            'id': user_id,
            'name': user.full_name,
            'username': user.username,
            'status': 'active'
        }
        save_users(users_db)
    
    if user_id == OWNER_ID:
        await update.message.reply_text(
            "🎬 Video Editor Bot - Owner Panel\n\n"
            "📹 Video Features:\n"
            "• Send video(s) to edit\n"
            "• Change thumbnails (single/bulk)\n"
            "• Replace text in captions\n\n"
            "📢 Commands:\n"
            "/broadcast - Broadcast message\n"
            "/users - List all users\n"
            "/stats - View statistics\n"
            "/cancel - Cancel current operation\n\n"
            "Just send videos to start editing!"
        )
    else:
        await update.message.reply_text(
            "🎬 Welcome to Video Editor Bot!\n\n"
            "This bot is currently in owner-only mode.\n"
            "Contact the admin for access."
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_data_store:
        del user_data_store[user_id]
    if user_id in broadcast_queue:
        del broadcast_queue[user_id]
    await update.message.reply_text("❌ Operation cancelled!")
    return ConversationHandler.END

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    total = len(users_db)
    active = sum(1 for u in users_db.values() if u.get('status') == 'active')
    blocked = sum(1 for u in users_db.values() if u.get('status') == 'blocked')
    await update.message.reply_text(
        f"📊 Bot Statistics\n\n"
        f"👥 Total Users: {total}\n"
        f"✅ Active: {active}\n"
        f"🚫 Blocked: {blocked}"
    )

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not users_db:
        await update.message.reply_text("📭 No users yet!")
        return
    msg = "👥 All Users:\n\n"
    for u in users_db.values():
        emoji = "✅" if u.get('status') == 'active' else "🚫"
        link = f'<a href="tg://user?id={u["id"]}">{u["name"]}</a>'
        msg += f"{emoji} {link} (ID: {u['id']})\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Owner only!")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📢 Broadcast Mode\n\n"
        "Send me the message/video to broadcast to all users.\n\n"
        "Use /cancel to exit."
    )
    return WAITING_BROADCAST

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    success = fail = blocked = 0
    status_msg = await message.reply_text("📡 Broadcasting...")
    
    for uid_str, user in users_db.items():
        if user.get('status') != 'active':
            continue
        try:
            tid = int(uid_str)
            if message.text:
                await context.bot.send_message(tid, f"📢 Broadcast:\n\n{message.text}")
            elif message.photo:
                await context.bot.send_photo(tid, message.photo[-1].file_id, caption=message.caption)
            elif message.video:
                await context.bot.send_video(tid, message.video.file_id, caption=message.caption)
            elif message.document:
                await context.bot.send_document(tid, message.document.file_id, caption=message.caption)
            success += 1
        except Exception as e:
            err = str(e).lower()
            if 'blocked' in err or 'deactivated' in err or 'not found' in err:
                users_db[uid_str]['status'] = 'blocked'
                blocked += 1
            else:
                fail += 1
    
    save_users(users_db)
    await status_msg.edit_text(
        f"✅ Broadcast Complete!\n\n"
        f"✓ Sent: {success}\n"
        f"🚫 Blocked: {blocked}\n"
        f"✗ Failed: {fail}"
    )
    return ConversationHandler.END

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ This bot is for owner only!")
        return
    
    video = update.message.video
    caption = update.message.caption or ""
    
    # Initialize user data
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            'videos': [],
            'mode': 'single',
            'thumbnail': None,
            'find_text': None,
            'replace_text': None
        }
    
    # Store video
    user_data_store[user_id]['videos'].append({
        'file_id': video.file_id,
        'caption': caption,
        'duration': video.duration,
        'width': video.width,
        'height': video.height
    })
    
    video_count = len(user_data_store[user_id]['videos'])
    
    await update.message.reply_text(
        f"📹 Video {video_count} received!\n\n"
        f"Options:\n"
        f"1️⃣ Send more videos for bulk edit\n"
        f"2️⃣ Type 'done' when ready to edit\n\n"
        f"Current videos: {video_count}"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        return
    
    if user_id not in user_data_store or not user_data_store[user_id].get('videos'):
        await update.message.reply_text("❌ Send videos first, then thumbnail!")
        return
    
    # Get the largest photo
    photo = update.message.photo[-1]
    user_data_store[user_id]['thumbnail'] = photo.file_id
    
    await update.message.reply_text(
        "✅ Thumbnail saved!\n\n"
        "Do you want to replace any text in captions?\n"
        "• Type 'yes' to replace text\n"
        "• Type 'no' to skip and process videos"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.lower().strip()
    
    if user_id != OWNER_ID:
        return
    
    # Check if user said "done" to finish adding videos
    if text == 'done':
        if user_id not in user_data_store or not user_data_store[user_id].get('videos'):
            await update.message.reply_text("❌ No videos to process!")
            return
        
        video_count = len(user_data_store[user_id]['videos'])
        await update.message.reply_text(
            f"✅ {video_count} video(s) ready!\n\n"
            f"Now send a photo for the thumbnail.\n"
            f"(This will be applied to all videos)"
        )
        return
    
    # Check for yes/no for text replacement
    if text == 'yes':
        await update.message.reply_text(
            "🔍 Find & Replace\n\n"
            "Send the text you want to FIND in captions:"
        )
        user_data_store[user_id]['awaiting'] = 'find_text'
        return
    
    if text == 'no':
        await process_videos(update, context, user_id)
        return
    
    # Handle find/replace text
    if user_id in user_data_store:
        if user_data_store[user_id].get('awaiting') == 'find_text':
            user_data_store[user_id]['find_text'] = update.message.text
            user_data_store[user_id]['awaiting'] = 'replace_text'
            await update.message.reply_text(
                f"✅ Will find: '{update.message.text}'\n\n"
                f"Now send the text to REPLACE it with:"
            )
            return
        
        if user_data_store[user_id].get('awaiting') == 'replace_text':
            user_data_store[user_id]['replace_text'] = update.message.text
            user_data_store[user_id]['awaiting'] = None
            await update.message.reply_text(
                f"✅ Will replace with: '{update.message.text}'\n\n"
                f"Processing videos..."
            )
            await process_videos(update, context, user_id)
            return

async def process_videos(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    data = user_data_store[user_id]
    videos = data['videos']
    thumbnail = data.get('thumbnail')
    find_text = data.get('find_text')
    replace_text = data.get('replace_text')
    
    status_msg = await context.bot.send_message(
        user_id,
        f"⏳ Processing {len(videos)} video(s)..."
    )
    
    success = 0
    for idx, video_data in enumerate(videos, 1):
        try:
            # Process caption
            new_caption = video_data['caption']
            if find_text and replace_text and new_caption:
                new_caption = new_caption.replace(find_text, replace_text)
            
            # Download thumbnail if provided
            thumb_file = None
            if thumbnail:
                thumb = await context.bot.get_file(thumbnail)
                thumb_bytes = await thumb.download_as_bytearray()
                thumb_file = BytesIO(thumb_bytes)
                thumb_file.name = "thumb.jpg"
            
            # Send edited video
            await context.bot.send_video(
                chat_id=user_id,
                video=video_data['file_id'],
                caption=new_caption,
                thumbnail=thumb_file,
                duration=video_data['duration'],
                width=video_data['width'],
                height=video_data['height']
            )
            success += 1
            
            await status_msg.edit_text(
                f"⏳ Processing: {idx}/{len(videos)}\n"
                f"✅ Completed: {success}"
            )
        except Exception as e:
            logger.error(f"Error processing video {idx}: {e}")
    
    await status_msg.edit_text(
        f"✅ All Done!\n\n"
        f"Processed: {success}/{len(videos)} videos\n"
        f"{'🖼️ Thumbnail: Changed' if thumbnail else '📝 Thumbnail: Original'}\n"
        f"{'✏️ Caption: Modified' if find_text else '📝 Caption: Original'}"
    )
    
    # Clean up
    del user_data_store[user_id]

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")

async def health_check(request):
    return web.Response(text="Video Editor Bot Running! 🎬")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 Web server on port {PORT}")

async def main():
    if not BOT_TOKEN or not OWNER_ID:
        logger.error("Set BOT_TOKEN and OWNER_ID!")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Broadcast conversation handler
    broadcast_handler = ConversationHandler(
        entry_points=[CommandHandler('broadcast', broadcast_start)],
        states={
            WAITING_BROADCAST: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_message)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("users", list_users))
    app.add_handler(broadcast_handler)
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)
    
    await start_web_server()
    logger.info("🎬 Video Editor Bot started!")
    logger.info(f"👥 {len(users_db)} users loaded")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        await app.stop()

if __name__ == '__main__':
    asyncio.run(main())
