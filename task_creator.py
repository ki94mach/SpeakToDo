# task_creator.py
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
        self.board_id = int(config.MONDAY_BOARD_ID)
        self.session = self._create_session_with_proxy()

    # ---------- Networking / Proxy ----------

    def _create_session_with_proxy(self) -> requests.Session:
        session = requests.Session()

        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        if getattr(config, "SOCKS_PROXY_HOST", None) and getattr(config, "SOCKS_PROXY_PORT", None):
            try:
                proxy_url = self._build_proxy_url()
                if proxy_url:
                    session.proxies = {"http": proxy_url, "https": proxy_url}
                    logger.info(f"Configured SOCKS/HTTP proxy: {proxy_url}")
                else:
                    logger.warning("Invalid proxy configuration; continuing without proxy.")
            except Exception as e:
                logger.error(f"Proxy configuration error: {e}")
                logger.warning("Continuing without proxy.")

        return session

    def _build_proxy_url(self) -> Optional[str]:
        try:
            proxy_type = getattr(config, "SOCKS_PROXY_TYPE", "socks5").lower()
            host = config.SOCKS_PROXY_HOST
            port = config.SOCKS_PROXY_PORT
            username = getattr(config, "SOCKS_PROXY_USERNAME", "")
            password = getattr(config, "SOCKS_PROXY_PASSWORD", "")

            if proxy_type not in ["socks4", "socks5", "http", "https"]:
                logger.error(f"Unsupported proxy type: {proxy_type}")
                return None

            if username and password:
                return f"{proxy_type}://{username}:{password}@{host}:{port}"
            return f"{proxy_type}://{host}:{port}"
        except Exception as e:
            logger.error(f"Error building proxy URL: {e}")
            return None

    # ---------- Public API ----------

    async def test_connection(self) -> bool:
        try:
            query = "query { me { name email } }"
            r = self.session.post(self.api_url, json={"query": query}, headers=self.headers, timeout=30)
            if r.status_code == 200 and r.json().get("data", {}).get("me"):
                me = r.json()["data"]["me"]
                logger.info(f"Connected to Monday.com as {me['name']} ({me['email']})")
                return True
            logger.error(f"Connection test failed: {r.status_code} - {r.text}")
            return False
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    async def create_tasks(self, tasks: List[Dict]) -> List[Dict]:
        """
        tasks: List of dicts with keys:
          - project_title (str)  e.g., "فروش"
          - task_title (str)
          - owner (str)          display name to map to a Monday user
          - due_date (str)       ISO date 'YYYY-MM-DD'
          - status (optional)    label text or id (best-effort)
        """
        created = []
        for t in tasks:
            try:
                created.append(await self._create_single_task(t))
            except Exception as e:
                logger.error(f"Error creating task '{t.get('task_title','')}' for project '{t.get('project_title','')}': {e}")
        logger.info(f"Created {len(created)} / {len(tasks)} tasks.")
        return created

    # ---------- Core flow (parent + subitem) ----------

    async def _create_single_task(self, task: Dict) -> Dict:
        if not task.get("project_title"):
            raise ValueError("project_title is required")
        if not task.get("task_title"):
            raise ValueError("task_title is required")

        parent_id = await self._get_or_create_parent_item(task["project_title"])
        sub_board_id, sub_cols = await self._get_subitems_board_columns()
        col_values = await self._prepare_subitem_values(sub_cols, task)

        sub = await self._create_subitem(
            parent_item_id=parent_id,
            item_name=task["task_title"],
            column_values=col_values,
        )

        logger.info(
            f"✅ Created subtask '{sub['name']}' under '{task['project_title']}' "
            f"(parent id {parent_id}, subitem id {sub['id']})"
        )

        return {
            "id": sub["id"],
            "name": sub["name"],
            "created_at": sub["created_at"],
            "project_title": task["project_title"],
            "task_title": task["task_title"],
            "owner": task.get("owner"),
            "due_date": task.get("due_date"),
            "parent_item_id": parent_id,
            "board_id": self.board_id,
            "subitems_board_id": sub_board_id,
            "monday_parent_url": f"https://your-account.monday.com/boards/{self.board_id}/pulses/{parent_id}"
        }

    # ---------- Parent item (project) helpers ----------

    async def _get_or_create_parent_item(self, project_title: str) -> int:
        # Try to find an existing item with the exact name
        query = """
        query ($board_id: [ID!]!) {
          boards(ids: $board_id) {
            groups { id title }
            items_page(limit: 500) {
              items { id name }
            }
          }
        }
        """
        variables = {"board_id": [self.board_id]}
        r = self.session.post(self.api_url, json={"query": query, "variables": variables}, headers=self.headers, timeout=30)
        r.raise_for_status()
        data = r.json()["data"]["boards"][0]
        items = data.get("items_page", {}).get("items", []) or []

        for it in items:
            if (it.get("name") or "").strip() == project_title.strip():
                return int(it["id"])

        # Choose a group to create the parent in (default: first group)
        groups = data.get("groups", []) or []
        group_id = groups[0]["id"] if groups else None

        mutation = """
        mutation ($board_id: ID!, $item_name: String!, $group_id: String) {
          create_item(board_id: $board_id, item_name: $item_name, group_id: $group_id) { id }
        }
        """
        vars2 = {"board_id": self.board_id, "item_name": project_title, "group_id": group_id}
        r2 = self.session.post(self.api_url, json={"query": mutation, "variables": vars2}, headers=self.headers, timeout=30)
        r2.raise_for_status()
        return int(r2.json()["data"]["create_item"]["id"])

    # ---------- Subitems board + columns ----------

    async def _get_subitems_board_columns(self):
        # Get main board columns to locate the Subitems column and its linked board
        query = """
        query ($board_id: [ID!]!) {
          boards(ids: $board_id) {
            columns { id title type settings_str }
          }
        }
        """
        r = self.session.post(self.api_url, json={"query": query, "variables": {"board_id": [self.board_id]}},
                              headers=self.headers, timeout=30)
        r.raise_for_status()
        cols = r.json()["data"]["boards"][0]["columns"]

        subitems_col = next((c for c in cols if c.get("type") in ("subitems", "subtasks")), None)
        if not subitems_col:
            raise RuntimeError("Board has no Subitems column. Add a Subitems column in Monday UI.")

        settings = {}
        if subitems_col.get("settings_str"):
            try:
                settings = json.loads(subitems_col["settings_str"])
            except Exception:
                settings = {}

        sub_board_id = None
        for key in ("linkedBoardsIds", "boardIds"):
            if settings.get(key):
                sub_board_id = settings[key][0]
                break
        if not sub_board_id:
            raise RuntimeError("Could not resolve subitems board id from column settings.")

        # Fetch subitems board columns
        q2 = """
        query ($id: [ID!]!) {
          boards(ids: $id) { id columns { id title type } }
        }
        """
        r2 = self.session.post(self.api_url, json={"query": q2, "variables": {"id": [sub_board_id]}},
                               headers=self.headers, timeout=30)
        r2.raise_for_status()
        sub_cols = r2.json()["data"]["boards"][0]["columns"]
        return int(sub_board_id), sub_cols

    # ---------- Column mapping for subitems ----------

    def _col_by_type(self, columns, t):
        return next((c for c in columns if c.get("type") == t), None)

    async def _prepare_subitem_values(self, subitem_columns, task: Dict) -> Dict:
        values: Dict[str, Dict] = {}

        # People column (type "people")
        people_col = self._col_by_type(subitem_columns, "people")
        if people_col and task.get("owner"):
            uid = await self._resolve_user_id(task["owner"])
            if uid:
                values[people_col["id"]] = {"personsAndTeams": [{"id": uid, "kind": "person"}]}

        # Due date (type "date")
        date_col = self._col_by_type(subitem_columns, "date")
        if date_col and task.get("due_date"):
            values[date_col["id"]] = {"date": task["due_date"]}

        # Status (optional) – if provided as label text, we send it raw; mapping can be added if needed
        status_col = self._col_by_type(subitem_columns, "status")
        if status_col and task.get("status") is not None:
            values[status_col["id"]] = {"label": task["status"]}

        # Long text (optional)
        long_col = self._col_by_type(subitem_columns, "long_text")
        if long_col:
            desc_lines = []
            if task.get("owner"):
                desc_lines.append(f"Owner: {task['owner']}")
            if task.get("due_date"):
                desc_lines.append(f"Due: {task['due_date']}")
            values[long_col["id"]] = {"text": "\n".join(desc_lines) if desc_lines else ""}

        return values

    # ---------- GraphQL mutations ----------

    async def _create_subitem(self, parent_item_id: int, item_name: str, column_values: Dict) -> Dict:
        mutation = """
        mutation ($parent_item_id: ID!, $item_name: String!, $column_values: JSON) {
          create_subitem(parent_item_id: $parent_item_id, item_name: $item_name, column_values: $column_values) {
            id name created_at
          }
        }
        """
        variables = {
            "parent_item_id": int(parent_item_id),
            "item_name": item_name,
            "column_values": json.dumps(column_values, ensure_ascii=False)
        }
        r = self.session.post(self.api_url, json={"query": mutation, "variables": variables},
                              headers=self.headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        if "errors" in data:
            raise RuntimeError(data["errors"])
        return data["data"]["create_subitem"]

    # ---------- Utilities ----------

    async def _resolve_user_id(self, display_name: Optional[str]) -> Optional[int]:
        if not display_name:
            return None
        q = "query { users(limit: 500) { id name email } }"
        r = self.session.post(self.api_url, json={"query": q}, headers=self.headers, timeout=30)
        r.raise_for_status()
        users = r.json().get("data", {}).get("users", []) or []

        # Exact match first
        for u in users:
            if (u.get("name") or "").strip() == display_name.strip():
                return int(u["id"])
        # Fuzzy contains
        for u in users:
            if display_name.strip() in (u.get("name") or ""):
                return int(u["id"])
        return None

