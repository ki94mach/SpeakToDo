#!/usr/bin/env python3
"""
SOCKS Proxy Test Script for Monday.com Connection

This script helps you test your SOCKS proxy configuration before running the main bot.
"""

import asyncio
import sys
import logging
from monday.task_creator import TaskCreator
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_proxy_connection():
    """Test the SOCKS proxy connection to Monday.com"""
    print("🔍 Testing SOCKS Proxy Configuration for Monday.com")
    print("=" * 50)
    
    # Display current configuration
    print("Current Configuration:")
    print(f"  SOCKS_PROXY_HOST: {config.SOCKS_PROXY_HOST or 'Not configured'}")
    print(f"  SOCKS_PROXY_PORT: {config.SOCKS_PROXY_PORT or 'Not configured'}")
    print(f"  SOCKS_PROXY_TYPE: {config.SOCKS_PROXY_TYPE}")
    print(f"  SOCKS_PROXY_USERNAME: {'***' if config.SOCKS_PROXY_USERNAME else 'Not configured'}")
    print(f"  SOCKS_PROXY_PASSWORD: {'***' if config.SOCKS_PROXY_PASSWORD else 'Not configured'}")
    print()
    
    # Test connection
    try:
        creator = TaskCreator()
        
        print("🚀 Testing connection to Monday.com...")
        success = await creator.test_connection()
        
        if success:
            print("✅ SUCCESS: SOCKS proxy connection to Monday.com is working!")
            print("   You can now run your Telegram bot with confidence.")
        else:
            print("❌ FAILED: Could not connect to Monday.com through proxy")
            print("   Please check your proxy configuration and try again.")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False
    
    return True

def print_troubleshooting_guide():
    """Print troubleshooting guide for common proxy issues"""
    print("\n🔧 Troubleshooting Guide:")
    print("-" * 30)
    print("1. Verify proxy server is running and accessible")
    print("2. Check firewall settings on both client and proxy server")
    print("3. Ensure proxy credentials are correct (if authentication required)")
    print("4. Try different SOCKS versions (socks4/socks5)")
    print("5. Test proxy with other tools (curl, browser) first")
    print("\n📝 Example .env configuration:")
    print("SOCKS_PROXY_HOST=127.0.0.1")
    print("SOCKS_PROXY_PORT=1080")
    print("SOCKS_PROXY_TYPE=socks5")
    print("SOCKS_PROXY_USERNAME=myuser")
    print("SOCKS_PROXY_PASSWORD=mypass")

async def main():
    """Main function"""
    print("Monday.com SOCKS Proxy Test")
    print("=" * 40)
    
    # Check if proxy is configured
    if not config.SOCKS_PROXY_HOST or not config.SOCKS_PROXY_PORT:
        print("ℹ️  No SOCKS proxy configured. Testing direct connection...")
    else:
        print("🔗 SOCKS proxy detected. Testing proxy connection...")
    
    success = await test_proxy_connection()
    
    if not success:
        print_troubleshooting_guide()
        sys.exit(1)
    
    print("\n🎉 All tests passed! Your configuration is ready.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)
