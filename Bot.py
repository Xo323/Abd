import logging
import asyncio
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
import yt_dlp
import json
from urllib.error import URLError

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

TOKEN = '7990464757:D9rfGGYPRtTWwztC9baNFAqnY7dmo'

async def get_video_formats(url):
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
    }
    retries = 3  # Number of retries in case of failure
    for attempt in range(retries):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = []
                for f in info['formats']:
                    if f.get('filesize'):
                        format_note = f"{f['ext']} - {f['format_note']}"
                        formats.append({
                            'format_id': f['format_id'],
                            'format_note': format_note,
                            'filesize': f['filesize'],
                            'url': f['url']
                        })
                return info['title'], formats
        except Exception as e:
            logger.error(f"Error in get_video_formats (Attempt {attempt + 1}): {str(e)}")
            if attempt < retries - 1:
                await asyncio.sleep(2)  # Wait before retrying
            else:
                raise

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Start command received from user {update.effective_user.id}")
    await update.message.reply_text('Welcome! Send me a video URL to download.')

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = update.message.text
    logger.info(f"Received URL: {url} from user {update.effective_user.id}")
    await update.message.reply_text('Processing your request...')
    
    try:
        video_title, formats = await get_video_formats(url)
        formats.sort(key=lambda x: x['filesize'], reverse=True)
        
        # Filter unavailable formats
        available_formats = []
        for fmt in formats:
            try:
                # Check if the URL is accessible
                response = await asyncio.to_thread(requests.head, fmt['url'])
                if response.status_code == 200:
                    available_formats.append(fmt)
            except Exception as e:
                logger.warning(f"Format {fmt['format_id']} is unavailable: {str(e)}")
        
        keyboard = []
        for i, fmt in enumerate(available_formats[:5]):  # Show up to 5 available formats
            size_mb = fmt['filesize'] / (1024 * 1024)
            button_text = f"{fmt['format_note']} ({size_mb:.1f} MB)"
            callback_data = json.dumps({'type': 'format', 'id': i})
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

        # Add Back button if there are available formats
        if len(available_formats) > 0:
            keyboard.append([InlineKeyboardButton("Back", callback_data=json.dumps({'type': 'back'}))])

        reply_markup = InlineKeyboardMarkup(keyboard)
        context.user_data['formats'] = available_formats
        context.user_data['video_title'] = video_title
        
        await update.message.reply_text(f"Title: {video_title}\n\nChoose a format to download:", reply_markup=reply_markup)
    except URLError:
        await update.message.reply_text("Network error occurred while fetching the video information. Please try again.")
    except Exception as e:
        logger.error(f"Error in handle_url: {str(e)}")
        await update.message.reply_text(f"An error occurred: {str(e)}\nPlease try again with a different URL or contact the bot administrator.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    try:
        data = json.loads(query.data)
        if data['type'] == 'format':
            format_index = data['id']
            formats = context.user_data.get('formats', [])
            video_title = context.user_data.get('video_title', 'Video')
            
            if format_index < len(formats):
                chosen_format = formats[format_index]
                url = chosen_format['url']
                
                # Check if URL is accessible
                try:
                    response = await asyncio.to_thread(requests.head, url)
                    if response.status_code == 200:
                        keyboard = [[InlineKeyboardButton("Download", url=url)]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await query.edit_message_text(
                            text=f"Title: {video_title}\n\nFormat: {chosen_format['format_note']}\n\nClick the button below to download:",
                            reply_markup=reply_markup
                        )
                    else:
                        # If the selected format is not available, show a message and provide options again
                        await query.edit_message_text(
                            text="The selected format is not available. Please choose a different one."
                        )
                        # Re-show available formats with a "Back" button
                        keyboard = []
                        for i, fmt in enumerate(formats[:5]):
                            size_mb = fmt['filesize'] / (1024 * 1024)
                            button_text = f"{fmt['format_note']} ({size_mb:.1f} MB)"
                            callback_data = json.dumps({'type': 'format', 'id': i})
                            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
                        keyboard.append([InlineKeyboardButton("Back", callback_data=json.dumps({'type': 'back'}))])

                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await query.edit_message_text(
                            text=f"Title: {video_title}\n\nChoose a format to download:",
                            reply_markup=reply_markup
                        )
                except Exception as e:
                    logger.error(f"Error while checking URL: {str(e)}")
                    await query.edit_message_text(text="The link is not accessible. Please try again later.")
            else:
                await query.edit_message_text(text="Sorry, that format is no longer available.")
        
        elif data['type'] == 'back':
            # If 'Back' button is pressed, show the format selection again
            video_title = context.user_data.get('video_title', 'Video')
            formats = context.user_data.get('formats', [])
            keyboard = []
            for i, fmt in enumerate(formats[:5]):
                size_mb = fmt['filesize'] / (1024 * 1024)
                button_text = f"{fmt['format_note']} ({size_mb:.1f} MB)"
                callback_data = json.dumps({'type': 'format', 'id': i})
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

            keyboard.append([InlineKeyboardButton("Back", callback_data=json.dumps({'type': 'back'}))])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                text=f"Title: {video_title}\n\nChoose a format to download:",
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Error in button_callback: {str(e)}")
        await query.edit_message_text(text="An error occurred. Please try again or contact the bot administrator.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling an update: {context.error}")

def main() -> None:
    try:
        application = Application.builder().token(TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_error_handler(error_handler)

        logger.info("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.critical(f"Critical error in main: {str(e)}")

if __name__ == '__main__':
    main()

print("Bot script executed. Check logs for details.")
