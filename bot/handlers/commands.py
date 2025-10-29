"""Command handlers for Telegram bot."""

from telegram import Update
from telegram.ext import ContextTypes


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    welcome_message = (
        "🎙️ **Welcome to SpeakToDo!**\n\n"
        "Send me a voice message and I'll:\n"
        "1. Convert it to text\n"
        "2. Extract tasks from your message\n"
        "3. Let you review and edit the tasks\n"
        "4. Create them in Monday.com after your confirmation\n\n"
        "Just record and send your voice message to get started!\n\n"
        "Use /help for more detailed instructions."
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "🔧 **How to use SpeakToDo:**\n\n"
        "1. 🎙️ Record a voice message describing your tasks\n"
        "2. 📤 Send the voice message to this bot\n"
        "3. 🔍 Review the extracted tasks\n"
        "4. ✏️ Edit any tasks if needed (title, project, owner, due date)\n"
        "5. ➕ Add or 🗑️ remove tasks as needed\n"
        "6. ✅ Confirm to create tasks in Monday.com\n\n"
        "**Example voice message:**\n"
        "_\"I need to call John about the website project, Sarah should review the budget proposal by Friday, "
        "and schedule a meeting with the marketing team for next week.\"_\n\n"
        "**Interactive Features:**\n"
        "• Edit task titles, projects, owners, and due dates\n"
        "• Add new tasks or remove unwanted ones\n"
        "• Preview everything before creating in Monday.com\n\n"
        "**Commands:**\n"
        "/start - Start SpeakToDo\n"
        "/help - Show this help message"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

