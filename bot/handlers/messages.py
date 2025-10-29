"""Message handlers for Telegram bot (voice and text messages)."""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.files import cleanup_temp_file
from core import config

logger = logging.getLogger(__name__)


class MessageHandlers:
    """Handles voice and text messages for the Telegram bot."""
    
    def __init__(self, bot_instance):
        """Initialize with reference to the TelegramBot instance."""
        self.bot = bot_instance
    
    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle voice messages from users."""
        user_id = update.effective_user.id
        voice_path = None
        
        try:
            # Clear any existing session
            if user_id in self.bot.user_sessions:
                del self.bot.user_sessions[user_id]
            
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
            
            text = await self.bot.voice_converter.convert_to_text(voice_path)
            logger.info(f"Converted text: {text}")
            
            # Extract tasks from text
            tasks = await self.bot.task_extractor.extract_tasks(text, board_id=config.MONDAY_BOARD_ID)
            logger.info(f"Extracted {len(tasks)} tasks: {tasks}")
            
            if not tasks:
                await processing_message.edit_text(
                    "🤔 I couldn't identify any tasks in your voice message.\n\n"
                    "Please try again with clear task descriptions like:\n"
                    "• \"I need to call John\"\n"
                    "• \"Schedule a meeting with the team\"\n"
                    "• \"Sarah should review the budget by Friday\""
                )
                return
            
            # Store session data
            self.bot.user_sessions[user_id] = {
                'original_text': text,
                'tasks': tasks,
                'processing_message_id': processing_message.message_id
            }
            
            # Show tasks for review and editing
            await self.bot.show_tasks_for_review(processing_message, user_id)
            
        except Exception as e:
            logger.error(f"Error processing voice message: {e}")
            error_message = (
                f"❌ Sorry, there was an error processing your voice message:\n"
                f"`{str(e)}`\n\n"
                "Please try again or contact support if the issue persists."
            )
            
            if 'processing_message' in locals():
                await processing_message.edit_text(error_message, parse_mode='Markdown')
            else:
                await update.message.reply_text(error_message, parse_mode='Markdown')
                
        finally:
            # Clean up temporary voice file
            cleanup_temp_file(voice_path)

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages for editing and adding tasks."""
        user_id = update.effective_user.id
        session = self.bot.user_sessions.get(user_id)
        
        # If no active session, treat as regular text message for task extraction
        if not session:
            await self.handle_regular_text_message(update, context)
            return
        
        text = update.message.text.strip()
        
        # Handle field editing
        if 'editing' in session:
            await self.process_field_edit(update, user_id, text)
        
        # Handle adding new task
        elif 'adding_task' in session:
            await self.process_add_task(update, user_id, text)
        
        else:
            # Fallback to regular text processing
            await self.handle_regular_text_message(update, context)

    async def handle_regular_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle regular text messages (for testing purposes without voice)."""
        try:
            text = update.message.text
            user_id = update.effective_user.id
            
            # Clear any existing session
            if user_id in self.bot.user_sessions:
                del self.bot.user_sessions[user_id]
            
            # Send processing message
            processing_message = await update.message.reply_text(
                "📝 Processing your text message...\n"
                "🔍 Extracting tasks..."
            )
            
            # Extract tasks from text
            tasks = await self.bot.task_extractor.extract_tasks(text, board_id=config.MONDAY_BOARD_ID)
            
            if not tasks:
                await processing_message.edit_text(
                    "🤔 I couldn't identify any tasks in your message.\n\n"
                    "Please try again with clear task descriptions like:\n"
                    "• \"I need to call John\"\n"
                    "• \"Schedule a meeting with the team\""
                )
                return
            
            # Store session data
            self.bot.user_sessions[user_id] = {
                'original_text': text,
                'tasks': tasks,
                'processing_message_id': processing_message.message_id
            }
            
            # Show tasks for review
            await self.bot.show_tasks_for_review(processing_message, user_id)
            
        except Exception as e:
            logger.error(f"Error processing text message: {e}")
            await update.message.reply_text(
                f"❌ Sorry, there was an error processing your message:\n`{str(e)}`",
                parse_mode='Markdown'
            )

    async def process_field_edit(self, update: Update, user_id: int, text: str):
        """Process field editing input."""
        session = self.bot.user_sessions[user_id]
        editing_context = session['editing']
        field = editing_context['field']
        task_index = editing_context['task_index']
        
        # Update the task field
        field_key = 'task_title' if field == 'title' else ('project_title' if field == 'project' else field)
        session['tasks'][task_index][field_key] = text
        
        # Clear editing context
        del session['editing']
        
        # Show confirmation
        field_name = field.replace('_', ' ').title()
        await update.message.reply_text(
            f"✅ Updated {field_name} to: `{text}`",
            parse_mode='Markdown'
        )
        
        # Show the tasks review again
        message = await update.message.reply_text("🔄 Updating task list...")
        await self.bot.show_tasks_for_review(message, user_id)

    async def process_add_task(self, update: Update, user_id: int, text: str):
        """Process adding new task input."""
        session = self.bot.user_sessions[user_id]
        adding_context = session['adding_task']
        step = adding_context['step']
        new_task = adding_context['new_task']
        
        if step == 'title':
            new_task['task_title'] = text
            adding_context['step'] = 'project'
            await update.message.reply_text(
                f"✅ Task title: `{text}`\n\n"
                "Now send me the project name (or send 'skip' to use 'General'):",
                parse_mode='Markdown'
            )
        
        elif step == 'project':
            if text.lower() != 'skip':
                new_task['project_title'] = text
            adding_context['step'] = 'owner'
            await update.message.reply_text(
                f"✅ Project: `{new_task['project_title']}`\n\n"
                "Now send me the owner name (or send 'skip' to use 'Unassigned'):",
                parse_mode='Markdown'
            )
        
        elif step == 'owner':
            if text.lower() != 'skip':
                new_task['owner'] = text
            adding_context['step'] = 'due_date'
            await update.message.reply_text(
                f"✅ Owner: `{new_task['owner']}`\n\n"
                "Finally, send me the due date (YYYY-MM-DD format, or 'today', 'tomorrow', or send 'skip'):",
                parse_mode='Markdown'
            )
        
        elif step == 'due_date':
            if text.lower() not in ['skip', '']:
                # Simple date parsing
                if text.lower() == 'today':
                    from datetime import datetime
                    new_task['due_date'] = datetime.now().strftime('%Y-%m-%d')
                elif text.lower() == 'tomorrow':
                    from datetime import datetime, timedelta
                    new_task['due_date'] = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
                else:
                    new_task['due_date'] = text
            
            # Add the new task to the list
            session['tasks'].append(new_task)
            
            # Clear adding context
            del session['adding_task']
            
            # Show confirmation and return to task list
            await update.message.reply_text(
                f"✅ **New task added successfully!**\n\n"
                f"📝 **Task:** {new_task['task_title']}\n"
                f"📋 **Project:** {new_task['project_title']}\n"
                f"👤 **Owner:** {new_task['owner']}\n"
                f"📅 **Due Date:** {new_task['due_date'] or 'Not specified'}",
                parse_mode='Markdown'
            )
            
            message = await update.message.reply_text("🔄 Updating task list...")
            await self.bot.show_tasks_for_review(message, user_id)

