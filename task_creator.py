import logging
import requests
import json
from typing import List, Dict
import config

logger = logging.getLogger(__name__)

class TaskCreator:
    def __init__(self):
        self.api_url = "https://api.monday.com/v2"
        self.headers = {
            "Authorization": config.MONDAY_API_TOKEN,
            "Content-Type": "application/json"
        }
        self.board_id = config.MONDAY_BOARD_ID
    
    async def create_tasks(self, tasks: List[Dict]) -> List[Dict]:
        """
        Create tasks in Monday.com board.
        
        Args:
            tasks (List[Dict]): List of tasks to create
            
        Returns:
            List[Dict]: List of created tasks with Monday.com IDs
        """
        created_tasks = []
        
        for task in tasks:
            try:
                created_task = await self._create_single_task(task)
                if created_task:
                    created_tasks.append(created_task)
                    
            except Exception as e:
                logger.error(f"Error creating task '{task['name']}': {e}")
                # Continue with other tasks even if one fails
                continue
        
        logger.info(f"Successfully created {len(created_tasks)} out of {len(tasks)} tasks")
        return created_tasks
    
    async def _create_single_task(self, task: Dict) -> Dict:
        """
        Create a single task in Monday.com.
        
        Args:
            task (Dict): Task information
            
        Returns:
            Dict: Created task information
        """
        try:
            # Prepare the GraphQL mutation
            mutation = """
            mutation ($board_id: Int!, $item_name: String!, $column_values: JSON!) {
                create_item (board_id: $board_id, item_name: $item_name, column_values: $column_values) {
                    id
                    name
                    created_at
                }
            }
            """
            
            # Prepare column values based on task metadata
            column_values = await self._prepare_column_values(task)
            
            variables = {
                "board_id": int(self.board_id),
                "item_name": task['name'],
                "column_values": json.dumps(column_values)
            }
            
            # Make the API request
            response = requests.post(
                self.api_url,
                json={"query": mutation, "variables": variables},
                headers=self.headers
            )
            
            if response.status_code != 200:
                logger.error(f"Monday.com API error: {response.status_code} - {response.text}")
                raise Exception(f"Monday.com API returned status {response.status_code}")
            
            response_data = response.json()
            
            if "errors" in response_data:
                logger.error(f"Monday.com GraphQL errors: {response_data['errors']}")
                raise Exception(f"GraphQL errors: {response_data['errors']}")
            
            created_item = response_data["data"]["create_item"]
            
            logger.info(f"Successfully created task: {created_item['name']} (ID: {created_item['id']})")
            
            return {
                "id": created_item["id"],
                "name": created_item["name"],
                "created_at": created_item["created_at"],
                "priority": task.get("priority", "Medium"),
                "category": task.get("category", "Other"),
                "estimated_duration": task.get("estimated_duration", "30 minutes")
            }
            
        except Exception as e:
            logger.error(f"Error creating task in Monday.com: {e}")
            raise
    
    async def _prepare_column_values(self, task: Dict) -> Dict:
        """
        Prepare column values for Monday.com based on task metadata.
        Note: Column IDs need to be retrieved from your specific Monday.com board.
        
        Args:
            task (Dict): Task information
            
        Returns:
            Dict: Column values for Monday.com
        """
        # Get board columns to map our task data
        board_columns = await self._get_board_columns()
        
        column_values = {}
        
        # Map priority if priority column exists
        priority_column = self._find_column_by_type(board_columns, "color")
        if priority_column:
            priority_mapping = {
                "High": {"label": "High Priority"},
                "Medium": {"label": "Medium Priority"},
                "Low": {"label": "Low Priority"}
            }
            if task.get("priority") in priority_mapping:
                column_values[priority_column["id"]] = priority_mapping[task["priority"]]
        
        # Map category if status column exists
        status_column = self._find_column_by_type(board_columns, "color")
        if status_column and not priority_column:  # Use status column for category if no priority column
            category_mapping = {
                "Meeting": {"label": "Meeting"},
                "Call": {"label": "Call"},
                "Email": {"label": "Email"},
                "Research": {"label": "Research"},
                "Development": {"label": "Development"},
                "Planning": {"label": "Planning"},
                "Review": {"label": "Review"},
                "Other": {"label": "Task"}
            }
            if task.get("category") in category_mapping:
                column_values[status_column["id"]] = category_mapping[task["category"]]
        
        # Map estimated duration if timeline column exists
        timeline_column = self._find_column_by_type(board_columns, "timeline")
        if timeline_column:
            # For now, we'll just add it as text. In a real implementation,
            # you might want to set actual dates based on the duration
            pass
        
        # Add notes/description if text column exists
        text_column = self._find_column_by_type(board_columns, "long_text")
        if text_column:
            description = f"Category: {task.get('category', 'Other')}\n"
            description += f"Estimated Duration: {task.get('estimated_duration', 'Unknown')}\n"
            description += f"Priority: {task.get('priority', 'Medium')}"
            column_values[text_column["id"]] = {"text": description}
        
        return column_values
    
    async def _get_board_columns(self) -> List[Dict]:
        """
        Get column information for the Monday.com board.
        
        Returns:
            List[Dict]: Board column information
        """
        try:
            query = """
            query ($board_id: [Int!]!) {
                boards (ids: $board_id) {
                    columns {
                        id
                        title
                        type
                        settings_str
                    }
                }
            }
            """
            
            variables = {"board_id": [int(self.board_id)]}
            
            response = requests.post(
                self.api_url,
                json={"query": query, "variables": variables},
                headers=self.headers
            )
            
            if response.status_code == 200:
                response_data = response.json()
                if "data" in response_data and response_data["data"]["boards"]:
                    return response_data["data"]["boards"][0]["columns"]
            
            logger.warning("Could not retrieve board columns, using default column mapping")
            return []
            
        except Exception as e:
            logger.error(f"Error retrieving board columns: {e}")
            return []
    
    def _find_column_by_type(self, columns: List[Dict], column_type: str) -> Dict:
        """
        Find a column by its type.
        
        Args:
            columns (List[Dict]): List of board columns
            column_type (str): Type of column to find
            
        Returns:
            Dict: Column information or None
        """
        for column in columns:
            if column.get("type") == column_type:
                return column
        return None
    
    async def test_connection(self) -> bool:
        """
        Test the connection to Monday.com API.
        
        Returns:
            bool: True if connection is successful
        """
        try:
            query = """
            query {
                me {
                    name
                    email
                }
            }
            """
            
            response = requests.post(
                self.api_url,
                json={"query": query},
                headers=self.headers
            )
            
            if response.status_code == 200:
                response_data = response.json()
                if "data" in response_data and "me" in response_data["data"]:
                    user_info = response_data["data"]["me"]
                    logger.info(f"Successfully connected to Monday.com as {user_info['name']} ({user_info['email']})")
                    return True
            
            logger.error(f"Monday.com connection test failed: {response.status_code} - {response.text}")
            return False
            
        except Exception as e:
            logger.error(f"Error testing Monday.com connection: {e}")
            return False

# Example usage and testing
if __name__ == "__main__":
    import asyncio
    
    async def test_task_creator():
        creator = TaskCreator()
        
        # Test connection
        if await creator.test_connection():
            print("✅ Monday.com connection successful!")
            
            # Test task creation
            test_tasks = [
                {
                    "name": "Test task from Voice Bot",
                    "priority": "High",
                    "category": "Development",
                    "estimated_duration": "1 hour"
                }
            ]
            
            created_tasks = await creator.create_tasks(test_tasks)
            print(f"Created {len(created_tasks)} test tasks")
            
        else:
            print("❌ Monday.com connection failed!")
    
    # Uncomment to test (requires valid API credentials)
    # asyncio.run(test_task_creator())
