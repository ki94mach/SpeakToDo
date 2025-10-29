#!/usr/bin/env python3
"""
SpeakToDo - Telegram Voice-to-Task Bot

This bot receives voice messages from Telegram users, converts them to text,
extracts actionable tasks, and creates them in Monday.com.

Author: Assistant
Date: 2025
"""

import sys
import asyncio
from bot.bot import TelegramBot
from monday.task_creator import TaskCreator
from core import config
from core.logging import setup_logging

# Configure logging with rotation based on config
use_timed = config.LOG_ROTATION_MODE.lower() == 'time'
logger = setup_logging(
    log_file=config.LOG_FILE,
    max_bytes=config.LOG_MAX_BYTES,
    backup_count=config.LOG_BACKUP_COUNT,
    use_timed_rotation=use_timed,
    when=config.LOG_ROTATION_WHEN,
    interval=config.LOG_ROTATION_INTERVAL
)

async def test_integrations():
    """Test all integrations before starting the bot."""
    logger.info("Testing integrations...")
    
    # Test Monday.com connection
    try:
        task_creator = TaskCreator()
        monday_connected = await task_creator.test_connection()
        
        if monday_connected:
            logger.info("✅ Monday.com integration test passed")
        else:
            logger.error("❌ Monday.com integration test failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Monday.com integration error: {e}")
        return False
    
    # Test OpenAI connection (basic validation)
    try:
        if not config.OPENAI_API_KEY:
            logger.error("❌ OpenAI API key not configured")
            return False
        else:
            logger.info("✅ OpenAI API key configured")
            
    except Exception as e:
        logger.error(f"❌ OpenAI configuration error: {e}")
        return False
    
    # Test Telegram Bot token
    try:
        if not config.TELEGRAM_BOT_TOKEN:
            logger.error("❌ Telegram Bot token not configured")
            return False
        else:
            logger.info("✅ Telegram Bot token configured")
            
    except Exception as e:
        logger.error(f"❌ Telegram Bot configuration error: {e}")
        return False
    
    logger.info("🎉 All integration tests passed!")
    return True

async def main_async():
    """Async main function to handle all async operations."""
    logger.info("🚀 Starting SpeakToDo Bot...")
    
    try:
        # Validate configuration
        logger.info("Validating configuration...")
        
        # Test integrations
        if not await test_integrations():
            logger.error("❌ Integration tests failed. Please check your configuration.")
            sys.exit(1)
        
        # Start the bot
        logger.info("🤖 Starting Telegram Bot...")
        bot = TelegramBot()
        await bot.run()
        
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
        
    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        sys.exit(1)

def main():
    """Main entry point for the application."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
