#!/usr/bin/env python3
"""
Setup Test Script for SpeakToDo Bot

This script helps verify that all components are properly configured
before running the main bot.
"""

import asyncio
import sys
import logging
from typing import Dict, Any

# Configure logging for testing
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

async def test_configuration() -> Dict[str, Any]:
    """Test basic configuration loading."""
    results = {"config": False, "details": []}
    
    try:
        import config
        
        # Check required variables
        required_vars = [
            ('TELEGRAM_BOT_TOKEN', config.TELEGRAM_BOT_TOKEN),
            ('OPENAI_API_KEY', config.OPENAI_API_KEY),
            ('MONDAY_API_TOKEN', config.MONDAY_API_TOKEN),
            ('MONDAY_BOARD_ID', config.MONDAY_BOARD_ID)
        ]
        
        missing_vars = []
        for var_name, var_value in required_vars:
            if not var_value:
                missing_vars.append(var_name)
            else:
                results["details"].append(f"✅ {var_name} is configured")
        
        if missing_vars:
            results["details"].append(f"❌ Missing variables: {', '.join(missing_vars)}")
            results["config"] = False
        else:
            results["config"] = True
            results["details"].append("✅ All required environment variables are configured")
            
    except Exception as e:
        results["details"].append(f"❌ Configuration error: {str(e)}")
        results["config"] = False
    
    return results

async def test_dependencies() -> Dict[str, Any]:
    """Test that all required dependencies are installed."""
    results = {"dependencies": False, "details": []}
    
    required_packages = [
        ('telegram', 'python-telegram-bot'),
        ('openai', 'openai'),
        ('requests', 'requests'),
        ('pydub', 'pydub'),
        ('speech_recognition', 'SpeechRecognition')
    ]
    
    missing_packages = []
    
    for package_name, pip_name in required_packages:
        try:
            __import__(package_name)
            results["details"].append(f"✅ {pip_name} is installed")
        except ImportError:
            missing_packages.append(pip_name)
            results["details"].append(f"❌ {pip_name} is missing")
    
    if missing_packages:
        results["dependencies"] = False
        results["details"].append(f"❌ Install missing packages: pip install {' '.join(missing_packages)}")
    else:
        results["dependencies"] = True
        results["details"].append("✅ All required dependencies are installed")
    
    return results

async def test_openai_connection() -> Dict[str, Any]:
    """Test OpenAI API connection."""
    results = {"openai": False, "details": []}
    
    try:
        from openai import OpenAI
        import config
        
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        
        # Test with a simple completion request
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Say 'Hello, API test successful!'"}],
            max_tokens=10
        )
        
        if response.choices:
            results["openai"] = True
            results["details"].append("✅ OpenAI API connection successful")
            results["details"].append(f"✅ Response: {response.choices[0].message.content.strip()}")
        else:
            results["details"].append("❌ OpenAI API returned empty response")
            
    except Exception as e:
        results["details"].append(f"❌ OpenAI API error: {str(e)}")
        results["openai"] = False
    
    return results

async def test_monday_connection() -> Dict[str, Any]:
    """Test Monday.com API connection."""
    results = {"monday": False, "details": []}
    
    try:
        from task_creator import TaskCreator
        
        task_creator = TaskCreator()
        connection_success = await task_creator.test_connection()
        
        if connection_success:
            results["monday"] = True
            results["details"].append("✅ Monday.com API connection successful")
        else:
            results["details"].append("❌ Monday.com API connection failed")
            
    except Exception as e:
        results["details"].append(f"❌ Monday.com API error: {str(e)}")
        results["monday"] = False
    
    return results

async def test_task_extraction() -> Dict[str, Any]:
    """Test task extraction functionality."""
    results = {"extraction": False, "details": []}
    
    try:
        from task_extractor import TaskExtractor
        
        extractor = TaskExtractor()
        test_text = "I need to call John about the project and schedule a meeting with the marketing team"
        
        tasks = await extractor.extract_tasks(test_text)
        
        if tasks:
            results["extraction"] = True
            results["details"].append(f"✅ Task extraction successful - found {len(tasks)} tasks")
            for task in tasks:
                results["details"].append(f"  - {task['name']} [{task['priority']}]")
        else:
            results["details"].append("❌ Task extraction failed - no tasks found")
            
    except Exception as e:
        results["details"].append(f"❌ Task extraction error: {str(e)}")
        results["extraction"] = False
    
    return results

async def run_all_tests():
    """Run all tests and display results."""
    print("🧪 Running setup tests for SpeakToDo Bot...\n")
    
    # Run all tests
    test_functions = [
        ("Configuration", test_configuration),
        ("Dependencies", test_dependencies),
        ("OpenAI Connection", test_openai_connection),
        ("Monday.com Connection", test_monday_connection),
        ("Task Extraction", test_task_extraction)
    ]
    
    all_passed = True
    
    for test_name, test_func in test_functions:
        print(f"🔍 Testing {test_name}...")
        
        try:
            result = await test_func()
            
            # Print details
            for detail in result["details"]:
                print(f"  {detail}")
            
            # Check if test passed
            test_key = list(result.keys())[0]  # Get the first key (not 'details')
            if test_key != "details" and not result[test_key]:
                all_passed = False
                
        except Exception as e:
            print(f"  ❌ Test failed with error: {str(e)}")
            all_passed = False
        
        print()  # Empty line for readability
    
    # Final summary
    if all_passed:
        print("🎉 All tests passed! Your bot is ready to run.")
        print("💡 Start the bot with: python main.py")
        return 0
    else:
        print("❌ Some tests failed. Please fix the issues above before running the bot.")
        print("💡 Check the README.md for setup instructions.")
        return 1

def main():
    """Main entry point."""
    try:
        exit_code = asyncio.run(run_all_tests())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n👋 Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error during testing: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
