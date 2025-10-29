import logging
from typing import List, Dict, Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

class TaskEditor:
    def __init__(self):
        pass
    
    def create_task_review_message(self, tasks: List[Dict], original_text: str) -> Tuple[str, InlineKeyboardMarkup]:
        """
        Create a message showing extracted tasks with edit/confirm options.
        
        Args:
            tasks (List[Dict]): Extracted tasks
            original_text (str): Original transcribed text
            
        Returns:
            Tuple[str, InlineKeyboardMarkup]: Message text and keyboard
        """
        message = f"🎙️ **Original message:** \"{original_text}\"\n\n"
        message += f"📝 **I found {len(tasks)} task(s):**\n\n"
        
        for i, task in enumerate(tasks, 1):
            message += f"**Task {i}:**\n"
            message += f"📋 Project: {task['project_title']}\n"
            message += f"✅ Task: {task['task_title']}\n"
            message += f"👤 Owner: {task['owner']}\n"
            message += f"📅 Due Date: {task['due_date'] or 'Not specified'}\n\n"
        
        # Create inline keyboard
        keyboard = []
        
        # Add edit buttons for each task
        for i in range(len(tasks)):
            keyboard.append([
                InlineKeyboardButton(f"✏️ Edit Task {i+1}", callback_data=f"edit_task_{i}")
            ])
        
        # Add global actions
        keyboard.append([
            InlineKeyboardButton("➕ Add Task", callback_data="add_task"),
            InlineKeyboardButton("🗑️ Remove Task", callback_data="remove_task")
        ])
        
        keyboard.append([
            InlineKeyboardButton("✅ Confirm All", callback_data="confirm_all"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_all")
        ])
        
        return message, InlineKeyboardMarkup(keyboard)
    
    def create_task_edit_keyboard(self, task_index: int) -> InlineKeyboardMarkup:
        """Create keyboard for editing a specific task."""
        keyboard = [
            [InlineKeyboardButton("📝 Edit Title", callback_data=f"edit_title_{task_index}")],
            [InlineKeyboardButton("📋 Edit Project", callback_data=f"edit_project_{task_index}")],
            [InlineKeyboardButton("👤 Edit Owner", callback_data=f"edit_owner_{task_index}")],
            [InlineKeyboardButton("📅 Edit Due Date", callback_data=f"edit_due_date_{task_index}")],
            [InlineKeyboardButton("🔙 Back to Tasks", callback_data="back_to_tasks")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    def format_task_for_editing(self, task: Dict, task_index: int) -> str:
        """Format a single task for editing view."""
        message = f"✏️ **Editing Task {task_index + 1}**\n\n"
        message += f"📝 **Title:** {task['task_title']}\n"
        message += f"📋 **Project:** {task['project_title']}\n"
        message += f"👤 **Owner:** {task['owner']}\n"
        message += f"📅 **Due Date:** {task['due_date'] or 'Not specified'}\n\n"
        message += "Choose what you want to edit:"
        return message