# Telegram Voice-to-Monday.com Task Bot

A powerful Telegram bot that converts voice messages into actionable tasks in Monday.com. Simply send a voice message describing your tasks, and the bot will automatically:

1. 🎙️ Convert your voice to text using OpenAI Whisper
2. 🧠 Extract actionable tasks using AI
3. 📝 Create tasks in your Monday.com board

## Features

- **Voice Recognition**: Supports multiple audio formats (OGG, MP3, WAV)
- **Intelligent Task Extraction**: Uses OpenAI GPT to identify and categorize tasks
- **Monday.com Integration**: Automatically creates tasks with proper metadata
- **Real-time Processing**: Get instant feedback as your voice is processed
- **Fallback Support**: Multiple voice-to-text providers for reliability
- **Rich Task Metadata**: Automatically assigns priority, category, and estimated duration

## Prerequisites

Before running the bot, you'll need:

1. **Telegram Bot Token**: Create a bot via [@BotFather](https://t.me/BotFather)
2. **OpenAI API Key**: For voice-to-text and task extraction
3. **Monday.com API Token**: For creating tasks in your boards
4. **Monday.com Board ID**: The board where tasks will be created

## Installation

1. Clone this repository:

```bash
git clone <repository-url>
cd Telegram-Voice-to-Monday
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Install FFmpeg (required for voice processing):

**Windows:**

- Download FFmpeg from [https://ffmpeg.org/download.html#build-windows](https://ffmpeg.org/download.html#build-windows)
- Extract the archive and add the `bin` folder to your system PATH
- Or use Chocolatey: `choco install ffmpeg`
- Or use winget: `winget install FFmpeg.FFmpeg`

**macOS:**

```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**

```bash
sudo apt update
sudo apt install ffmpeg
```

4. Set up environment variables:

```bash
cp .env.example .env
```

5. Edit `.env` file with your API credentials:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here
MONDAY_API_TOKEN=your_monday_api_token_here
MONDAY_BOARD_ID=your_board_id_here
```

## Getting API Credentials

### Telegram Bot Token

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the instructions
3. Save the bot token provided

### OpenAI API Key

1. Visit [OpenAI Platform](https://platform.openai.com/)
2. Create an account and navigate to API Keys
3. Create a new API key and save it

### Monday.com API Token

1. Go to your Monday.com account
2. Click on your avatar → Admin → API
3. Generate a new API token
4. Copy the token

### Monday.com Board ID

1. Open your Monday.com board
2. The Board ID is in the URL: `https://mycompany.monday.com/boards/XXXXXXXXX`
3. Copy the number after `/boards/`

## Usage

1. Start the bot:

```bash
python main.py
```

2. Find your bot on Telegram and send `/start`

3. Send a voice message describing your tasks, for example:

   - "I need to call John about the project and schedule a meeting with the marketing team"
   - "Review the budget proposal and send feedback to Sarah by Friday"
   - "Research competitors and update the website homepage"

4. The bot will process your message and create tasks in Monday.com!

## Project Structure

```
Telegram-Voice-to-Monday/
├── main.py                 # Main entry point
├── telegram_bot.py         # Telegram bot handler
├── voice_to_text.py        # Voice-to-text conversion
├── task_extractor.py       # AI-powered task extraction
├── task_creator.py         # Monday.com integration
├── config.py               # Configuration management
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variables template
└── README.md              # This file
```

## Components Overview

### 1. Telegram Bot (`telegram_bot.py`)

- Handles incoming voice and text messages
- Manages user interactions and feedback
- Orchestrates the entire processing pipeline

### 2. Voice to Text (`voice_to_text.py`)

- Converts audio files to text using OpenAI Whisper
- Supports multiple audio formats
- Includes fallback to Google Speech Recognition

### 3. Task Extractor (`task_extractor.py`)

- Uses OpenAI GPT to analyze text and extract tasks
- Categorizes tasks by type and priority
- Estimates task duration automatically

### 4. Task Creator (`task_creator.py`)

- Integrates with Monday.com GraphQL API
- Maps task metadata to board columns
- Handles error recovery and validation

## Example Voice Messages

Here are some examples of voice messages the bot can process:

**Project Management:**

> "I need to review the quarterly report, schedule a team standup for tomorrow, and follow up with the client about their feedback"

**Personal Tasks:**

> "Call the dentist to schedule an appointment, buy groceries for the weekend, and prepare slides for Monday's presentation"

**Work Planning:**

> "Research our top three competitors, update the pricing page on the website, and send the proposal to the new client"

## Troubleshooting

### Common Issues

1. **"Missing required environment variables"**

   - Make sure all required variables are set in your `.env` file
   - Check that the `.env` file is in the project root directory

2. **"Monday.com connection failed"**

   - Verify your Monday.com API token is correct
   - Ensure the Board ID exists and you have access to it
   - Check that your API token has the necessary permissions

3. **"OpenAI API error"**

   - Verify your OpenAI API key is valid
   - Check that you have sufficient credits in your OpenAI account
   - Ensure the API key has access to GPT and Whisper models

4. **Voice processing fails**

   - Check that the audio file format is supported
   - Ensure the voice message is clear and audible
   - Try with shorter voice messages (under 2 minutes)

5. **"Couldn't find ffmpeg" warning**
   - Install FFmpeg following the installation instructions above
   - On Windows, ensure FFmpeg is added to your system PATH
   - Restart your terminal/command prompt after installation
   - Test FFmpeg installation by running `ffmpeg -version` in terminal

### Logs

The bot creates detailed logs in `voice_to_tasks_bot.log`. Check this file for detailed error information.

## Advanced Configuration

### Custom Task Categories

You can modify the task categories in `task_extractor.py`:

```python
valid_categories = ['Meeting', 'Call', 'Email', 'Research', 'Development', 'Planning', 'Review', 'Other']
```

### Monday.com Column Mapping

The bot automatically detects your board columns, but you can customize the mapping in `task_creator.py` by modifying the `_prepare_column_values` method.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License. See LICENSE file for details.

## Support

If you encounter any issues or have questions:

1. Check the troubleshooting section above
2. Review the logs in `voice_to_tasks_bot.log`
3. Create an issue on GitHub with detailed information

---

**Happy task management! 🚀**
