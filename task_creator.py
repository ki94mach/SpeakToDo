import logging
import requests
import json
from typing import List, Dict, Optional
import config
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class TaskCreator:
    def __init__(self):
        self.api_url = "https://api.monday.com/v2"
        self.headers = {
            "Authorization": config.MONDAY_API_TOKEN,
            "Content-Type": "application/json"
        }
        self.board_id = config.MONDAY_BOARD_ID
        
        # Initialize session with proxy configuration
        self.session = self._create_session_with_proxy()
    
    def _create_session_with_proxy(self) -> requests.Session:
        """
        Create a requests session with SOCKS proxy configuration if provided.
        
        Returns:
            requests.Session: Configured session object
        """
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Configure SOCKS proxy if provided
        if config.SOCKS_PROXY_HOST and config.SOCKS_PROXY_PORT:
            try:
                proxy_url = self._build_proxy_url()
                if proxy_url:
                    session.proxies = {
                        'http': proxy_url,
                        'https': proxy_url
                    }
                    logger.info(f"Configured SOCKS proxy: {config.SOCKS_PROXY_HOST}:{config.SOCKS_PROXY_PORT}")
                else:
                    logger.warning("Invalid proxy configuration, proceeding without proxy")
            except Exception as e:
                logger.error(f"Error configuring SOCKS proxy: {e}")
                logger.warning("Proceeding without proxy")
        else:
            logger.info("No SOCKS proxy configuration found, using direct connection")
        
        return session
    
    def _build_proxy_url(self) -> Optional[str]:
        """
        Build proxy URL from configuration.
        
        Returns:
            str: Properly formatted proxy URL or None if invalid
        """
        try:
            proxy_type = config.SOCKS_PROXY_TYPE.lower()
            host = config.SOCKS_PROXY_HOST
            port = config.SOCKS_PROXY_PORT
            username = config.SOCKS_PROXY_USERNAME
            password = config.SOCKS_PROXY_PASSWORD
            
            # Validate proxy type
            if proxy_type not in ['socks4', 'socks5', 'http', 'https']:
                logger.error(f"Unsupported proxy type: {proxy_type}")
                return None
            
            # Build URL with or without authentication
            if username and password:
                proxy_url = f"{proxy_type}://{username}:{password}@{host}:{port}"
            else:
                proxy_url = f"{proxy_type}://{host}:{port}"
            
            return proxy_url
            
        except Exception as e:
            logger.error(f"Error building proxy URL: {e}")
            return None
    
    async def create_tasks(self, tasks: List[Dict]) -> List[Dict]:
        """
        Create tasks in Monday.com board.
        
        Args:
            tasks (List[Dict]): List of tasks to create with fields: project_title, task_title, owner, due_date
            
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
                logger.error(f"Error creating task '{task.get('task_title', 'Unknown')}': {e}")
                # Continue with other tasks even if one fails
                continue
        
        logger.info(f"Successfully created {len(created_tasks)} out of {len(tasks)} tasks")
        return created_tasks
    
    async def _create_single_task(self, task: Dict) -> Dict:
        """
        Create a single task in Monday.com.
        
        Args:
            task (Dict): Task information with fields: project_title, task_title, owner, due_date
            
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
                "item_name": task['task_title'],
                "column_values": json.dumps(column_values)
            }
            
            # Make the API request using session with proxy
            response = self.session.post(
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
                "project_title": task.get("project_title", "General"),
                "task_title": task.get("task_title", ""),
                "owner": task.get("owner", "Unassigned"),
                "due_date": task.get("due_date")
            }
            
        except Exception as e:
            logger.error(f"Error creating task in Monday.com: {e}")
            raise
    
    async def _prepare_column_values(self, task: Dict) -> Dict:
        """
        Prepare column values for Monday.com based on task metadata.
        Note: Column IDs need to be retrieved from your specific Monday.com board.
        
        Args:
            task (Dict): Task information with fields: project_title, task_title, owner, due_date
            
        Returns:
            Dict: Column values for Monday.com
        """
        # Get board columns to map our task data
        board_columns = await self._get_board_columns()
        
        column_values = {}
        
        # Map project title if text column exists
        project_column = self._find_column_by_title(board_columns, "project")
        if not project_column:
            project_column = self._find_column_by_type(board_columns, "text")
        if project_column:
            column_values[project_column["id"]] = {"text": task.get("project_title", "General")}
        
        # Map owner if person column exists
        owner_column = self._find_column_by_type(board_columns, "person")
        if owner_column:
            # For person columns, we need to provide user IDs or emails
            # For now, we'll store the owner name as text
            column_values[owner_column["id"]] = {"text": task.get("owner", "Unassigned")}
        
        # Map due date if date column exists
        due_date_column = self._find_column_by_type(board_columns, "date")
        if due_date_column and task.get("due_date"):
            column_values[due_date_column["id"]] = {"date": task["due_date"]}
        
        # Add additional details if long text column exists
        description_column = self._find_column_by_type(board_columns, "long_text")
        if description_column:
            description = f"Project: {task.get('project_title', 'General')}\n"
            description += f"Owner: {task.get('owner', 'Unassigned')}\n"
            if task.get("due_date"):
                description += f"Due Date: {task['due_date']}"
            column_values[description_column["id"]] = {"text": description}
        
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
            
            response = self.session.post(
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
    
    def _find_column_by_title(self, columns: List[Dict], title_keyword: str) -> Dict:
        """
        Find a column by its title containing a keyword.
        
        Args:
            columns (List[Dict]): List of board columns
            title_keyword (str): Keyword to search for in column title
            
        Returns:
            Dict: Column information or None
        """
        for column in columns:
            if title_keyword.lower() in column.get("title", "").lower():
                return column
        return None
    
    async def test_connection(self) -> bool:
        """
        Test the connection to Monday.com API.
        
        Returns:
            bool: True if connection is successful
        """
        try:
            # Log proxy status
            proxy_info = ""
            if hasattr(self.session, 'proxies') and self.session.proxies:
                proxy_info = f" via proxy {config.SOCKS_PROXY_HOST}:{config.SOCKS_PROXY_PORT}"
            
            logger.info(f"Testing Monday.com connection{proxy_info}...")
            
            query = """
            query {
                me {
                    name
                    email
                }
            }
            """
            
            response = self.session.post(
                self.api_url,
                json={"query": query},
                headers=self.headers,
                timeout=30  # Add timeout for proxy connections
            )
            
            if response.status_code == 200:
                response_data = response.json()
                if "data" in response_data and "me" in response_data["data"]:
                    user_info = response_data["data"]["me"]
                    logger.info(f"✅ Successfully connected to Monday.com as {user_info['name']} ({user_info['email']}){proxy_info}")
                    return True
            
            logger.error(f"❌ Monday.com connection test failed: {response.status_code} - {response.text}")
            return False
            
        except requests.exceptions.ProxyError as e:
            logger.error(f"❌ SOCKS Proxy connection error: {e}")
            logger.error("Please check your proxy configuration and ensure the proxy server is accessible")
            return False
        except requests.exceptions.ConnectTimeout as e:
            logger.error(f"❌ Connection timeout: {e}")
            logger.error("The connection timed out. This might be due to proxy or network issues")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ Connection error: {e}")
            logger.error("Unable to establish connection. Check your internet connection and proxy settings")
            return False
        except Exception as e:
            logger.error(f"❌ Error testing Monday.com connection: {e}")
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
                    "project_title": "Voice Bot Integration",
                    "task_title": "Test task from Voice Bot",
                    "owner": "Test User",
                    "due_date": "2024-01-15"
                }
            ]
            
            created_tasks = await creator.create_tasks(test_tasks)
            print(f"Created {len(created_tasks)} test tasks")
            
        else:
            print("❌ Monday.com connection failed!")
    
    # Uncomment to test (requires valid API credentials)
    # asyncio.run(test_task_creator())
