import logging
import os
import asyncio
from telegram import Update, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.error import BadRequest
from voice_to_text import VoiceToText
from task_extractor import TaskExtractor
from task_creator import TaskCreator
from task_editor import TaskEditor
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
        self.task_editor = TaskEditor()
        
        # Store user sessions for editing workflow
        self.user_sessions = {}

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle voice messages from users."""
        user_id = update.effective_user.id
        voice_path = None
        
        try:
            # Clear any existing session
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]
            
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
            self.user_sessions[user_id] = {
                'original_text': text,
                'tasks': tasks,
                'processing_message_id': processing_message.message_id
            }
            
            # Show tasks for review and editing
            await self.show_tasks_for_review(processing_message, user_id)
            
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
            if voice_path and os.path.exists(voice_path):
                try:
                    os.remove(voice_path)
                    logger.info(f"Cleaned up temporary file: {voice_path}")
                except Exception as e:
                    logger.warning(f"Could not remove temporary file {voice_path}: {e}")

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

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle button callbacks for task editing."""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        session = self.user_sessions.get(user_id)
        
        if not session:
            await query.edit_message_text("❌ Session expired. Please send your voice message again.")
            return
        
        callback_data = query.data
        logger.info(f"Handling callback: {callback_data} for user {user_id}")
        
        try:
            if callback_data == "confirm_all":
                await self.confirm_and_create_tasks(query, user_id, context)
            
            elif callback_data == "cancel_all":
                await self.cancel_task_creation(query, user_id)
            
            elif callback_data.startswith("edit_task_"):
                task_index = int(callback_data.split("_")[2])
                await self.show_task_edit_options(query, user_id, task_index)
            
            elif callback_data == "add_task":
                await self.start_add_task(query, user_id)
            
            elif callback_data == "remove_task":
                await self.show_remove_task_options(query, user_id)
            
            elif callback_data == "back_to_tasks":
                await self.show_tasks_for_review(query.message, user_id)
            
            elif callback_data.startswith("edit_"):
                await self.handle_field_edit(query, user_id, callback_data)
            
            elif callback_data.startswith("remove_task_"):
                task_index = int(callback_data.split("_")[2])
                await self.remove_task(query, user_id, task_index)
                
        except Exception as e:
            logger.error(f"Error handling callback {callback_data}: {e}")
            await query.edit_message_text(
                f"❌ Error processing your request: {str(e)}\n"
                "Please try again or start over with a new voice message."
            )

    async def show_task_edit_options(self, query: CallbackQuery, user_id: int, task_index: int):
        """Show options for editing a specific task."""
        session = self.user_sessions.get(user_id)
        if not session or task_index >= len(session['tasks']):
            await query.edit_message_text("❌ Task not found. Please start over.")
            return
        
        task = session['tasks'][task_index]
        message_text = self.task_editor.format_task_for_editing(task, task_index)
        keyboard = self.task_editor.create_task_edit_keyboard(task_index)
        
        await query.edit_message_text(
            message_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    async def handle_field_edit(self, query: CallbackQuery, user_id: int, callback_data: str):
        """Handle editing of specific task fields."""
        parts = callback_data.split("_")
        if len(parts) < 3:
            await query.edit_message_text("❌ Invalid edit request.")
            return
            
        field = parts[1]  # title, project, owner, due_date
        task_index = int(parts[2])
        
        session = self.user_sessions.get(user_id)
        if not session or task_index >= len(session['tasks']):
            await query.edit_message_text("❌ Session expired or task not found.")
            return
        
        # Store the editing context
        session['editing'] = {
            'field': field,
            'task_index': task_index,
            'query_message_id': query.message.message_id
        }
        
        field_names = {
            'title': 'Task Title',
            'project': 'Project Name', 
            'owner': 'Owner',
            'due_date': 'Due Date (YYYY-MM-DD format or "today", "tomorrow", "next week")'
        }
        
        current_field = 'task_title' if field == 'title' else ('project_title' if field == 'project' else field)
        current_value = session['tasks'][task_index].get(current_field, 'Not set')
        
        await query.edit_message_text(
            f"✏️ **Edit {field_names[field]}**\n\n"
            f"**Current value:** `{current_value}`\n\n"
            f"Please send me the new {field_names[field].lower()}:\n\n"
            f"_Note: Send your message as text (not voice)_",
            parse_mode='Markdown'
        )

    async def start_add_task(self, query: CallbackQuery, user_id: int):
        """Start the process of adding a new task."""
        session = self.user_sessions.get(user_id)
        if not session:
            await query.edit_message_text("❌ Session expired.")
            return
        
        # Store adding context
        session['adding_task'] = {
            'step': 'title',
            'new_task': {
                'project_title': 'General',
                'task_title': '',
                'owner': 'Unassigned', 
                'due_date': None
            }
        }
        
        await query.edit_message_text(
            "➕ **Adding New Task**\n\n"
            "Please send me the task title:\n\n"
            "_Example: \"Call client about project update\"_",
            parse_mode='Markdown'
        )

    async def show_remove_task_options(self, query: CallbackQuery, user_id: int):
        """Show options for removing tasks."""
        session = self.user_sessions.get(user_id)
        if not session or not session['tasks']:
            await query.edit_message_text("❌ No tasks to remove.")
            return
        
        keyboard = []
        for i, task in enumerate(session['tasks']):
            task_preview = task['task_title'][:30] + ("..." if len(task['task_title']) > 30 else "")
            keyboard.append([
                InlineKeyboardButton(f"🗑️ Remove: {task_preview}", callback_data=f"remove_task_{i}")
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Tasks", callback_data="back_to_tasks")])
        
        await query.edit_message_text(
            "🗑️ **Remove Task**\n\nWhich task would you like to remove?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def remove_task(self, query: CallbackQuery, user_id: int, task_index: int):
        """Remove a task from the list."""
        session = self.user_sessions.get(user_id)
        if not session or task_index >= len(session['tasks']):
            await query.edit_message_text("❌ Task not found.")
            return
        
        removed_task = session['tasks'].pop(task_index)
        
        if not session['tasks']:
            await query.edit_message_text(
                "🗑️ All tasks removed!\n\n"
                "Send me a new voice message to start over."
            )
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]
        else:
            await query.message.reply_text(
                f"🗑️ Removed task: `{removed_task['task_title']}`",
                parse_mode='Markdown'
            )
            await self.show_tasks_for_review(query.message, user_id)

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages for editing and adding tasks."""
        user_id = update.effective_user.id
        session = self.user_sessions.get(user_id)
        
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

    async def process_field_edit(self, update: Update, user_id: int, text: str):
        """Process field editing input."""
        session = self.user_sessions[user_id]
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
        await self.show_tasks_for_review(message, user_id)

    async def process_add_task(self, update: Update, user_id: int, text: str):
        """Process adding new task input."""
        session = self.user_sessions[user_id]
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
            await self.show_tasks_for_review(message, user_id)

    async def handle_regular_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle regular text messages (for testing purposes without voice)."""
        try:
            text = update.message.text
            user_id = update.effective_user.id
            
            # Clear any existing session
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]
            
            # Send processing message
            processing_message = await update.message.reply_text(
                "📝 Processing your text message...\n"
                "🔍 Extracting tasks..."
            )
            
            # Extract tasks from text
            tasks = await self.task_extractor.extract_tasks(text)
            
            if not tasks:
                await processing_message.edit_text(
                    "🤔 I couldn't identify any tasks in your message.\n\n"
                    "Please try again with clear task descriptions like:\n"
                    "• \"I need to call John\"\n"
                    "• \"Schedule a meeting with the team\""
                )
                return
            
            # Store session data
            self.user_sessions[user_id] = {
                'original_text': text,
                'tasks': tasks,
                'processing_message_id': processing_message.message_id
            }
            
            # Show tasks for review
            await self.show_tasks_for_review(processing_message, user_id)
            
        except Exception as e:
            logger.error(f"Error processing text message: {e}")
            await update.message.reply_text(
                f"❌ Sorry, there was an error processing your message:\n`{str(e)}`",
                parse_mode='Markdown'
            )

    async def confirm_and_create_tasks(self, query: CallbackQuery, user_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Create tasks in Monday.com after user confirmation with robust UX."""
        session = self.user_sessions.get(user_id)
        if not session:
            await query.edit_message_text("❌ Session expired.")
            return

        chat_id = query.message.chat_id
        message_id = query.message.message_id

        async def _do_create_and_report():
            # Runs in the foreground (or as a background task) and posts the final result.
            try:
                created_tasks = await self.task_creator.create_tasks(session['tasks'])
                if not created_tasks:
                    text = (
                        "❌ **No tasks were created.**\n\n"
                        "Please check your Monday.com configuration and try again."
                    )
                else:
                    task_list = "\n".join(
                        [
                            f"• **{t['name']}**\n"
                            f"  📋 Project: {t.get('project_title', 'N/A')}\n"
                            f"  👤 Owner: {t.get('owner', 'N/A')}\n"
                            f"  🆔 ID: `{t['id']}`"
                            for t in created_tasks
                        ]
                    )
                    text = (
                        f"✅ **Successfully created {len(created_tasks)} task(s) in Monday.com!**\n\n"
                        f"📝 **Tasks created:**\n{task_list}\n\n"
                        f"🔗 **View in Monday.com:** https://your-account.monday.com/boards/{self.task_creator.board_id}\n\n"
                        f"🎯 **Original message:** \"{session['original_text'][:100]}{'...' if len(session['original_text']) > 100 else ''}\""
                    )

                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=text,
                        parse_mode='Markdown'
                    )
                except BadRequest:
                    # Message may be gone/edited; send a fresh one
                    await context.bot.send_message(
                        chat_id=chat_id, text=text, parse_mode='Markdown'
                    )

            except Exception as e:
                err_text = (
                    f"❌ **Error creating tasks:**\n`{str(e)}`\n\n"
                    "It’s possible some items were created if the server finished after a timeout. "
                    "Please check the board link above."
                )
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id, message_id=message_id, text=err_text, parse_mode='Markdown'
                    )
                except BadRequest:
                    await context.bot.send_message(chat_id=chat_id, text=err_text, parse_mode='Markdown')
            finally:
                # Clean up session if it still exists
                if user_id in self.user_sessions:
                    del self.user_sessions[user_id]

        # Immediately show the “working” message (or keep it, but ensure it exists)
        try:
            await query.edit_message_text(
                "📝 **Creating tasks in Monday.com...**\n"
                "⏳ Please wait...",
                parse_mode='Markdown'
            )
        except BadRequest:
            pass

        # Try to complete within a soft timeout; if it exceeds, finish in background and update later
        try:
            await asyncio.wait_for(_do_create_and_report(), timeout=25)
        except asyncio.TimeoutError:
            # Update the UI so the user is not stuck on “please wait…”
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="⏳ Still working on creating your tasks… I’ll post the result here shortly.",
                    parse_mode='Markdown'
                )
            except BadRequest:
                pass
            # Finish in the background and post the final message when done
            asyncio.create_task(_do_create_and_report())

    async def run(self):
        """Start the bot."""
        # Create the Application
        application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(MessageHandler(filters.VOICE, self.handle_voice_message))
        application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        
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

if __name__ == '__main__':
    bot = TelegramBot()
    asyncio.run(bot.run())
    