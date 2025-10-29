"""Callback query handlers for Telegram bot."""

import asyncio
import logging
from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class CallbackHandlers:
    """Handles callback queries for the Telegram bot."""
    
    def __init__(self, bot_instance):
        """Initialize with reference to the TelegramBot instance."""
        self.bot = bot_instance
    
    async def handle_callback_query(self, update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle button callbacks for task editing."""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        session = self.bot.user_sessions.get(user_id)
        
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
                await self.bot.show_tasks_for_review(query.message, user_id)
            
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
        session = self.bot.user_sessions.get(user_id)
        if not session or task_index >= len(session['tasks']):
            await query.edit_message_text("❌ Task not found. Please start over.")
            return
        
        task = session['tasks'][task_index]
        message_text = self.bot.task_editor.format_task_for_editing(task, task_index)
        keyboard = self.bot.task_editor.create_task_edit_keyboard(task_index)
        
        await query.edit_message_text(
            message_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    async def handle_field_edit(self, query: CallbackQuery, user_id: int, callback_data: str):
        """Handle editing of specific task fields."""
        # Parse callback_data format: edit_<field>_<task_index>
        # Handle fields with underscores like "due_date"
        parts = callback_data.split("_")
        if len(parts) < 3:
            await query.edit_message_text("❌ Invalid edit request.")
            return
        
        # Last part is always the task_index
        try:
            task_index = int(parts[-1])
        except ValueError:
            await query.edit_message_text("❌ Invalid edit request.")
            return
        
        # Everything between "edit" and the task_index is the field name
        # Join parts[1:-1] to handle fields like "due_date"
        field = "_".join(parts[1:-1])  # title, project, owner, due_date
        
        session = self.bot.user_sessions.get(user_id)
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
            'due_date': 'Due Date (YYYY-MM-DD format)'
        }
        
        current_field = 'task_title' if field == 'title' else ('project_title' if field == 'project' else field)
        current_value = session['tasks'][task_index].get(current_field, 'Not set')
        
        # Use ForceReply to show an input box with the current value as placeholder
        placeholder_value = str(current_value) if current_value != 'Not set' else field_names[field]
        
        await query.message.reply_text(
            f"✏️ **Edit {field_names[field]}**\n\n"
            f"**Current value:** `{current_value}`\n\n"
            f"Type the new value below:\n\n"
            f"_Current value will appear in the input box_",
            reply_markup=ForceReply(selective=True, input_field_placeholder=placeholder_value),
            parse_mode='Markdown'
        )

    async def start_add_task(self, query: CallbackQuery, user_id: int):
        """Start the process of adding a new task."""
        session = self.bot.user_sessions.get(user_id)
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
        session = self.bot.user_sessions.get(user_id)
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
        session = self.bot.user_sessions.get(user_id)
        if not session or task_index >= len(session['tasks']):
            await query.edit_message_text("❌ Task not found.")
            return
        
        removed_task = session['tasks'].pop(task_index)
        
        if not session['tasks']:
            await query.edit_message_text(
                "🗑️ All tasks removed!\n\n"
                "Send me a new voice message to start over."
            )
            if user_id in self.bot.user_sessions:
                del self.bot.user_sessions[user_id]
        else:
            await query.message.reply_text(
                f"🗑️ Removed task: `{removed_task['task_title']}`",
                parse_mode='Markdown'
            )
            await self.bot.show_tasks_for_review(query.message, user_id)

    async def cancel_task_creation(self, query: CallbackQuery, user_id: int):
        """Cancel task creation and reset the session, with safe UI update."""
        # Clear any editing/adding context and tasks
        self.bot.user_sessions.pop(user_id, None)

        try:
            await query.edit_message_text(
                "❌ **Task creation cancelled.**\n\n"
                "Send me another voice message when you're ready! 🎙️",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"cancel_task_creation: could not edit message ({e}); sending a new one.")
            await query.message.reply_text(
                "❌ **Task creation cancelled.**",
                parse_mode='Markdown'
            )

    async def confirm_and_create_tasks(self, query: CallbackQuery, user_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Create tasks in Monday.com after user confirmation with robust UX."""
        session = self.bot.user_sessions.get(user_id)
        if not session:
            await query.edit_message_text("❌ Session expired.")
            return

        chat_id = query.message.chat_id
        message_id = query.message.message_id

        async def _do_create_and_report():
            # Runs in the foreground (or as a background task) and posts the final result.
            try:
                created_tasks = await self.bot.task_creator.create_tasks(session['tasks'])
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
                        f"🔗 **View in ** https://quantum-aesthetics.monday.com/boards/{self.bot.task_creator.board_id}\n\n"
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
                    "It's possible some items were created if the server finished after a timeout. "
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
                if user_id in self.bot.user_sessions:
                    del self.bot.user_sessions[user_id]

        # Immediately show the "working" message (or keep it, but ensure it exists)
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
            # Update the UI so the user is not stuck on "please wait…"
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="⏳ Still working on creating your tasks… I'll post the result here shortly.",
                    parse_mode='Markdown'
                )
            except BadRequest:
                pass
            # Finish in the background and post the final message when done
            asyncio.create_task(_do_create_and_report())

