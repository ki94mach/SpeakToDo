import logging
import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from voice_to_text import VoiceToText
from task_extractor import TaskExtractor
from task_creator import TaskCreator
import config

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self):
        self.voice_converter = VoiceToText()
        self.task_extractor = TaskExtractor()
        self.task_creator = TaskCreator()
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /start is issued."""
        welcome_message = (
            "🎙️ Welcome to SpeakToDo!\n\n"
            "Send me a voice message and I'll:\n"
            "1. Convert it to text\n"
            "2. Extract tasks from your message\n"
            "3. Create them in Monday.com\n\n"
            "Just record and send your voice message to get started!"
        )
        await update.message.reply_text(welcome_message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /help is issued."""
        help_text = (
            "🔧 How to use SpeakToDo:\n\n"
            "1. Record a voice message describing your tasks\n"
            "2. Send the voice message to this bot\n"
            "3. SpeakToDo will process your message and create tasks in Monday.com\n\n"
            "Example voice message:\n"
            "\"I need to call John about the website project, Sarah should review the budget proposal by Friday, "
            "and schedule a meeting with the marketing team for next week.\"\n\n"
            "Commands:\n"
            "/start - Start SpeakToDo\n"
            "/help - Show this help message"
        )
        await update.message.reply_text(help_text)

    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle voice messages from users."""
        try:
            # Send initial processing message
            processing_message = await update.message.reply_text(
                "🎙️ Processing your voice message...\n"
                "⏳ Converting speech to text..."
            )
            
            # Get voice file
            voice_file = await update.message.voice.get_file()
            voice_path = f"temp_voice_{update.message.message_id}.ogg"
            await voice_file.download_to_drive(voice_path)
            
            # Convert voice to text
            await processing_message.edit_text(
                "🎙️ Processing your voice message...\n"
                "✅ Speech converted to text\n"
                "🔍 Extracting tasks..."
            )
            
            text = await self.voice_converter.convert_to_text(voice_path)
            logger.info(f"Converted text: {text}")
            
            # Extract tasks from text
            tasks = await self.task_extractor.extract_tasks(text)
            logger.info(f"Extracted tasks: {tasks}")
            
            if not tasks:
                await processing_message.edit_text(
                    "🤔 I couldn't identify any tasks in your voice message.\n"
                    "Please try again with clear task descriptions like:\n"
                    "\"I need to call John\" or \"Schedule a meeting with the team\""
                )
                return
            
            # Create tasks in Monday.com
            await processing_message.edit_text(
                "🎙️ Processing your voice message...\n"
                "✅ Speech converted to text\n"
                "✅ Tasks extracted\n"
                "📝 Creating tasks in Monday.com..."
            )
            
            created_tasks = await self.task_creator.create_tasks(tasks)
            
            # Send success message
            task_list = "\n".join([
                f"• {task['task_title']} (Project: {task['project_title']}, Owner: {task['owner']})\n  🆔 ID: {task['id']}"
                for task in created_tasks
            ])
            success_message = (
                f"✅ Successfully created {len(created_tasks)} task(s) in Monday.com!\n\n"
                f"📝 **Tasks created:**\n{task_list}\n\n"
                f"🎯 **Original message:** \"{text}\"\n\n"
                f"🔗 **View in Monday.com:** https://your-account.monday.com/boards/{self.task_creator.board_id}"
            )
            
            await processing_message.edit_text(success_message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error processing voice message: {e}")
            await update.message.reply_text(
                f"❌ Sorry, there was an error processing your voice message:\n{str(e)}\n\n"
                "Please try again or contact support if the issue persists."
            )
        finally:
            # Clean up temporary voice file
            if os.path.exists(voice_path):
                os.remove(voice_path)

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages (for testing purposes)."""
        try:
            text = update.message.text
            
            # Send processing message
            processing_message = await update.message.reply_text(
                "📝 Processing your text message...\n"
                "🔍 Extracting tasks..."
            )
            
            # Extract tasks from text
            tasks = await self.task_extractor.extract_tasks(text)
            
            if not tasks:
                await processing_message.edit_text(
                    "🤔 I couldn't identify any tasks in your message.\n"
                    "Please try again with clear task descriptions."
                )
                return
            
            # Create tasks in Monday.com
            await processing_message.edit_text(
                "📝 Processing your text message...\n"
                "✅ Tasks extracted\n"
                "📝 Creating tasks in Monday.com..."
            )
            
            created_tasks = await self.task_creator.create_tasks(tasks)
            
            # Send success message
            task_list = "\n".join([
                f"• {task['task_title']} (Project: {task['project_title']}, Owner: {task['owner']})\n  🆔 ID: {task['id']}"
                for task in created_tasks
            ])
            success_message = (
                f"✅ Successfully created {len(created_tasks)} task(s) in Monday.com!\n\n"
                f"📝 **Tasks created:**\n{task_list}\n\n"
                f"🔗 **View in Monday.com:** https://your-account.monday.com/boards/{self.task_creator.board_id}"
            )
            
            await processing_message.edit_text(success_message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error processing text message: {e}")
            await update.message.reply_text(
                f"❌ Sorry, there was an error processing your message:\n{str(e)}"
            )

    async def run(self):
        """Start the bot."""
        # Create the Application
        application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

        # Add handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(MessageHandler(filters.VOICE, self.handle_voice_message))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))

        # Initialize the application
        await application.initialize()
        
        # Start the application
        await application.start()
        
        # Start polling for updates
        logger.info("Starting Telegram Bot...")
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

if __name__ == '__main__':
    bot = TelegramBot()
    asyncio.run(bot.run())
