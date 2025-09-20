import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Monday.com Configuration
MONDAY_API_TOKEN = os.getenv('MONDAY_API_TOKEN')
MONDAY_BOARD_ID = os.getenv('MONDAY_BOARD_ID')

# SOCKS Proxy Configuration (optional)
SOCKS_PROXY_HOST = os.getenv('SOCKS_PROXY_HOST')
SOCKS_PROXY_PORT = os.getenv('SOCKS_PROXY_PORT')
SOCKS_PROXY_USERNAME = os.getenv('SOCKS_PROXY_USERNAME')
SOCKS_PROXY_PASSWORD = os.getenv('SOCKS_PROXY_PASSWORD')
SOCKS_PROXY_TYPE = os.getenv('SOCKS_PROXY_TYPE', 'socks5')  # socks4, socks5, or http

# Optional configurations
GOOGLE_SPEECH_API_KEY = os.getenv('GOOGLE_SPEECH_API_KEY')

# Validate required environment variables
required_vars = {
    'TELEGRAM_BOT_TOKEN': TELEGRAM_BOT_TOKEN,
    'OPENAI_API_KEY': OPENAI_API_KEY,
    'MONDAY_API_TOKEN': MONDAY_API_TOKEN,
    'MONDAY_BOARD_ID': MONDAY_BOARD_ID
}

missing_vars = [var for var, value in required_vars.items() if not value]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
