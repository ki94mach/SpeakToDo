"""Main Telegram bot class."""

import asyncio
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram import Update

from bot.services.voice_to_text import VoiceToText
from bot.services.task_editor import TaskEditor
from bot.handlers.commands import start_command, help_command
from bot.handlers.messages import MessageHandlers
from bot.handlers.callbacks import CallbackHandlers
from llm.task_extractor import TaskExtractor
from monday.task_creator import TaskCreator
from core import config

logger = logging.getLogger(__name__)


class TelegramBot:
    """Main Telegram bot class that orchestrates handlers and services."""
    
    def __init__(self):
        """Initialize bot services and handlers."""
        self.voice_converter = VoiceToText()
        self.task_extractor = TaskExtractor()
        self.task_creator = TaskCreator()
        self.task_editor = TaskEditor()
        
        # Store user sessions for editing workflow
        self.user_sessions = {}
        
        # Initialize handler classes
        self.message_handlers = MessageHandlers(self)
        self.callback_handlers = CallbackHandlers(self)

    async def show_tasks_for_review(self, message, user_id: int):
        """Show extracted tasks for user review and editing."""
        session = self.user_sessions.get(user_id)
        if not session:
            await message.edit_text("❌ Session expired. Please send your voice message again.")
            return
        
        try:
            message_text, keyboard = self.task_editor.create_task_review_message(
                session['tasks'], 
                session['original_text']
            )
            
            await message.edit_text(
                message_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error showing tasks for review: {e}")
            await message.edit_text(
                f"❌ Error displaying tasks: {str(e)}\n"
                "Please try sending your voice message again."
            )

    async def run(self):
        """Start the bot."""
        # Create the Application
        application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
        
        # Add command handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        
        # Add message handlers
        application.add_handler(MessageHandler(filters.VOICE, self.message_handlers.handle_voice_message))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handlers.handle_text_message))
        
        # Add callback query handler
        application.add_handler(CallbackQueryHandler(self.callback_handlers.handle_callback_query))
        
        # Initialize the application
        await application.initialize()
        
        # Start the application
        await application.start()
        
        # Start polling for updates
        logger.info("🚀 Starting Telegram Bot with interactive task editing...")
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        try:
            # Keep the bot running indefinitely
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received KeyboardInterrupt, stopping bot...")
        except Exception as e:
            logger.error(f"Bot error: {e}")
        finally:
            # Stop the updater and application
            logger.info("Shutting down bot...")
            await application.updater.stop()
            await application.stop()
            await application.shutdown()

