#!/usr/bin/env python3
"""
Task Verification Script for Monday.com

This script helps verify that tasks are being created successfully in Monday.com
and provides various ways to check the created tasks.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from task_creator import TaskCreator
import config

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TaskVerifier:
    def __init__(self):
        self.task_creator = TaskCreator()
    
    async def test_task_creation(self):
        """Test creating a sample task to verify the connection works."""
        print("🧪 Testing task creation...")
        
        test_task = {
            "project_title": "Verification Test",
            "task_title": f"Test task created at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "owner": "Verification Bot",
            "due_date": (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        }
        
        try:
            created_tasks = await self.task_creator.create_tasks([test_task])
            if created_tasks:
                task = created_tasks[0]
                print("✅ Test task created successfully!")
                print(f"   📝 Title: {task['task_title']}")
                print(f"   🆔 Monday.com ID: {task['id']}")
                print(f"   📅 Created: {task['created_at']}")
                print(f"   🔗 URL: {task.get('monday_parent_url', 'N/A')}")
                return True
            else:
                print("❌ No tasks were created")
                return False
        except Exception as e:
            print(f"❌ Error creating test task: {e}")
            return False
    
    async def check_connection(self):
        """Check if we can connect to Monday.com."""
        print("🔌 Checking Monday.com connection...")
        
        try:
            is_connected = await self.task_creator.test_connection()
            if is_connected:
                print("✅ Successfully connected to Monday.com")
                return True
            else:
                print("❌ Failed to connect to Monday.com")
                return False
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False
    
    async def get_recent_tasks(self, limit=10):
        """Get recent tasks from Monday.com board."""
        print(f"📋 Fetching last {limit} tasks from Monday.com...")
        
        try:
            # Query to get recent items from the board
            query = """
            query ($board_id: [ID!]!, $limit: Int!) {
                boards (ids: $board_id) {
                    items (limit: $limit) {
                        id
                        name
                        created_at
                        updated_at
                        column_values {
                            id
                            title
                            text
                        }
                    }
                }
            }
            """
            
            variables = {
                "board_id": [int(config.MONDAY_BOARD_ID)],
                "limit": limit
            }
            payload = {"query": query}
            if variables:
                payload["variables"] = variables
            response = self.task_creator.session.post(
                self.task_creator.api_url,
                json=payload,
                headers=self.task_creator.headers
            )
            
            if response.status_code == 200:
                response_data = response.json()
                if "data" in response_data and response_data["data"]["boards"]:
                    items = response_data["data"]["boards"][0]["items"]
                    print(f"✅ Found {len(items)} recent tasks:")
                    
                    for i, item in enumerate(items, 1):
                        print(f"\n   Task {i}:")
                        print(f"   📝 Title: {item['name']}")
                        print(f"   🆔 ID: {item['id']}")
                        print(f"   📅 Created: {item['created_at']}")
                        print(f"   🔗 URL: https://your-account.monday.com/boards/{config.MONDAY_BOARD_ID}/pulses/{item['id']}")
                        
                        # Show column values if available
                        if item.get('column_values'):
                            print("   📊 Column Values:")
                            for col in item['column_values']:
                                if col.get('text'):
                                    print(f"      {col['title']}: {col['text']}")
                    
                    return items
                else:
                    print("❌ No data returned from Monday.com")
                    return []
            else:
                print(f"❌ API error: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            print(f"❌ Error fetching tasks: {e}")
            return []
    
    def print_verification_guide(self):
        """Print a guide on how to manually verify tasks."""
        print("\n" + "="*60)
        print("📖 MANUAL VERIFICATION GUIDE")
        print("="*60)
        print("\n1. 🌐 Open Monday.com in your browser")
        print(f"   URL: https://your-account.monday.com/boards/{config.MONDAY_BOARD_ID}")
        print("\n2. 🔍 Look for tasks with these characteristics:")
        print("   - Recent creation time (within last few minutes)")
        print("   - Project titles like 'General', 'Website Project', etc.")
        print("   - Task titles that match your voice messages")
        print("   - Owner assignments")
        print("   - Due dates if mentioned in voice")
        print("\n3. 📱 Check the Telegram bot responses:")
        print("   - Bot should show 'Successfully created X task(s)'")
        print("   - Should display task details with project and owner")
        print("\n4. 📋 Check the log file:")
        print("   - Look for '✅ Successfully created task in Monday.com' messages")
        print("   - Check for Monday.com IDs and URLs")
        print("\n5. 🧪 Run this verification script:")
        print("   python verify_tasks.py")
        print("="*60)

async def main():
    """Main verification function."""
    print("🔍 Monday.com Task Verification Tool")
    print("="*50)
    
    verifier = TaskVerifier()
    
    # Step 1: Check connection
    if not await verifier.check_connection():
        print("\n❌ Cannot proceed - Monday.com connection failed")
        print("Please check your API credentials in config.py")
        return
    
    # Step 2: Test task creation
    print("\n" + "-"*30)
    if await verifier.test_task_creation():
        print("✅ Task creation is working!")
    else:
        print("❌ Task creation failed")
        return
    
    # Step 3: Show recent tasks
    print("\n" + "-"*30)
    await verifier.get_recent_tasks(5)
    
    # Step 4: Show verification guide
    verifier.print_verification_guide()

if __name__ == "__main__":
    asyncio.run(main())
