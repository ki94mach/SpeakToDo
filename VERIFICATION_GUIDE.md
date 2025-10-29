# 🔍 SpeakToDo Verification Guide

This guide will help you verify that voice messages are successfully creating tasks in Monday.com using SpeakToDo.

## 📋 Quick Verification Methods

### 1. **Check Telegram Bot Responses**

When you send a voice message, the bot should respond with:

- ✅ "Successfully created X task(s) in Monday.com!"
- 📝 Task details including project, title, and owner
- 🆔 Monday.com task IDs
- 🔗 Link to view tasks in Monday.com

### 2. **Check the Log File**

Monitor the log file for detailed information:

```bash
# Windows PowerShell
Get-Content logs/speaktodo_bot.log -Tail 20 -Wait

# Or open the file directly
notepad logs/speaktodo_bot.log
```

Look for these log entries:

```
✅ Successfully created task in Monday.com:
   📝 Task Title: [Your Task Name]
   🆔 Monday.com ID: [Task ID]
   📅 Created At: [Timestamp]
   📋 Project: [Project Name]
   👤 Owner: [Owner Name]
   📅 Due Date: [Due Date or Not specified]
   🔗 Monday.com URL: https://your-account.monday.com/boards/[BOARD_ID]/pulses/[TASK_ID]
```

### 3. **Check Monday.com Directly**

1. Open your Monday.com board in a web browser
2. Look for recently created tasks (within the last few minutes)
3. Tasks should have:
   - Recent creation timestamps
   - Project titles (like "General", "Website Project", etc.)
   - Task titles matching your voice messages
   - Owner assignments
   - Due dates (if mentioned in voice)

### 4. **Run the Verification Script**

```bash
python verify_tasks.py
```

This script will:

- Test the Monday.com connection
- Create a test task
- Show recent tasks from your board
- Provide detailed verification steps

## 🧪 Testing Steps

### Step 1: Test with Text Message

1. Send a text message to your bot (not voice)
2. Example: "I need to call John about the website project by Friday"
3. Check if the bot responds with task creation confirmation

### Step 2: Test with Voice Message

1. Record a voice message
2. Example: "Sarah should review the budget proposal and send feedback to the client"
3. Check the bot response and Monday.com board

### Step 3: Verify in Monday.com

1. Go to your Monday.com board
2. Look for the tasks created in the last few minutes
3. Verify the details match your voice message

## 🔧 Troubleshooting

### If No Tasks Are Created:

1. **Check API Credentials**: Verify `MONDAY_API_TOKEN` and `MONDAY_BOARD_ID` in `config.py`
2. **Check Proxy Settings**: If using a proxy, ensure it's working correctly
3. **Check Logs**: Look for error messages in the log file
4. **Test Connection**: Run `python verify_tasks.py` to test the connection

### If Tasks Are Created But Wrong Details:

1. **Check Voice Recognition**: The voice-to-text conversion might be inaccurate
2. **Check Task Extraction**: The AI might not be extracting the right information
3. **Check Column Mapping**: Monday.com columns might not be mapped correctly

### Common Issues:

- **Proxy Connection Errors**: Check your SOCKS proxy settings
- **API Rate Limits**: Monday.com might be rate limiting requests
- **Board Permissions**: Ensure your API token has write access to the board
- **Column Types**: Make sure your Monday.com board has the right column types

## 📊 Expected Task Structure

Each created task should have:

- **Project Title**: Extracted from context or "General"
- **Task Title**: The actual task description
- **Owner**: Person responsible (extracted or "Unassigned")
- **Due Date**: Date in YYYY-MM-DD format (if mentioned)

## 🎯 Success Indicators

You'll know it's working when:

1. ✅ Bot responds with success message
2. ✅ Log file shows detailed task creation info
3. ✅ Tasks appear in Monday.com with correct details
4. ✅ Task IDs are provided for reference
5. ✅ URLs to view tasks are provided

## 📞 Getting Help

If you're still having issues:

1. Check the log file for specific error messages
2. Run the verification script to test the connection
3. Verify your Monday.com board settings
4. Test with simple text messages first
5. Check your internet connection and proxy settings

---

**Remember**: The bot creates tasks in real-time, so you should see them in Monday.com within seconds of sending a voice message!
