# task_creator.py
import logging
import requests
import json
import asyncio
import random
from typing import List, Dict, Optional, Tuple
import config
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Tunables
CONNECT_TIMEOUT = 5           # seconds to establish TCP/TLS
READ_TIMEOUT = 20             # seconds to wait for server response body
MAX_ATTEMPTS = 3              # total tries for transient errors
BASE_BACKOFF = 0.6            # base backoff seconds

def _jittered_backoff(attempt: int) -> float:
    # exponential with jitter
    return BASE_BACKOFF * (2 ** (attempt - 1)) * (0.7 + random.random() * 0.6)

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

        # Allow retries for transient status codes. We will still do our own
        # retry/backoff for connection/timeouts below.
        retry_strategy = Retry(
            total=0,  # we handle retries ourselves to include POST safely
            backoff_factor=0,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
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

        # Don’t inherit env proxies unexpectedly
        session.trust_env = False
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

    # ---------- Low-level async POST with retries & no event-loop blocking ----------

    async def _post_graphql(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """
        Run a GraphQL POST without blocking the event loop.
        Retries on connection/timeouts with jittered backoff.
        """
        last_exc: Optional[Exception] = None
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                def _do_request():
                    return self.session.post(
                        self.api_url,
                        json=payload,
                        headers=self.headers,
                        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                    )

                resp = await asyncio.to_thread(_do_request)
                status = resp.status_code
                text = resp.text

                if status == 200:
                    data = resp.json()
                    if "errors" in data:
                        raise RuntimeError(f"Monday GraphQL errors: {data['errors']}")
                    return data
                else:
                    # Non-200: surface the error (no retry here; Monday already processed/failed)
                    raise RuntimeError(f"HTTP {status}: {text}")

            except (requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.ReadTimeout) as e:
                last_exc = e
                if attempt >= MAX_ATTEMPTS:
                    break
                sleep_s = _jittered_backoff(attempt)
                logger.warning(f"Transient Monday error ({type(e).__name__}). "
                               f"Attempt {attempt}/{MAX_ATTEMPTS} -> retrying in {sleep_s:.2f}s")
                await asyncio.sleep(sleep_s)

        assert last_exc is not None
        raise last_exc

    # ---------- Public API ----------

    async def test_connection(self) -> bool:
        try:
            query = "query { me { name email } }"
            data = await self._post_graphql(query)
            me = data.get("data", {}).get("me")
            if me:
                logger.info(f"Connected to Monday.com as {me['name']} ({me['email']})")
                return True
            logger.error(f"Connection test unexpected response: {data}")
            return False
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    async def create_tasks(self, tasks: List[Dict]) -> List[Dict]:
        """
        tasks: List of dicts with keys:
          - project_title (str)
          - task_title (str)
          - owner (str)
          - due_date (str 'YYYY-MM-DD' or None)
          - status (optional)
        """
        created: List[Dict] = []
        for t in tasks:
            try:
                created.append(await self._create_single_task(t))
            except Exception as e:
                logger.error(f"Error creating task '{t.get('task_title','')}' "
                             f"for project '{t.get('project_title','')}': {e}")
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

        sub = await self._create_subitem_with_verify(
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
            "created_at": sub.get("created_at"),
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
        data = await self._post_graphql(query, variables)
        board = data["data"]["boards"][0]
        items = board.get("items_page", {}).get("items", []) or []

        for it in items:
            if (it.get("name") or "").strip() == project_title.strip():
                return int(it["id"])

        groups = board.get("groups", []) or []
        group_id = groups[0]["id"] if groups else None

        mutation = """
        mutation ($board_id: ID!, $item_name: String!, $group_id: String) {
          create_item(board_id: $board_id, item_name: $item_name, group_id: $group_id) { id }
        }
        """
        vars2 = {"board_id": self.board_id, "item_name": project_title, "group_id": group_id}
        d2 = await self._post_graphql(mutation, vars2)
        return int(d2["data"]["create_item"]["id"])

    # ---------- Subitems board + columns ----------

    async def _get_subitems_board_columns(self) -> Tuple[int, list]:
        query = """
        query ($board_id: [ID!]!) {
          boards(ids: $board_id) {
            columns { id title type settings_str }
          }
        }
        """
        d1 = await self._post_graphql(query, {"board_id": [self.board_id]})
        cols = d1["data"]["boards"][0]["columns"]

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

        q2 = """
        query ($id: [ID!]!) {
          boards(ids: $id) { id columns { id title type } }
        }
        """
        d2 = await self._post_graphql(q2, {"id": [sub_board_id]})
        sub_cols = d2["data"]["boards"][0]["columns"]
        return int(sub_board_id), sub_cols

    # ---------- Column mapping for subitems ----------

    def _col_by_type(self, columns, t):
        return next((c for c in columns if c.get("type") == t), None)

    async def _prepare_subitem_values(self, subitem_columns, task: Dict) -> Dict:
        values: Dict[str, Dict] = {}

        # People
        people_col = self._col_by_type(subitem_columns, "people")
        if people_col and task.get("owner"):
            uid = await self._resolve_user_id(task["owner"])
            if uid:
                values[people_col["id"]] = {"personsAndTeams": [{"id": uid, "kind": "person"}]}

        # Due date
        date_col = self._col_by_type(subitem_columns, "date")
        if date_col and task.get("due_date"):
            values[date_col["id"]] = {"date": task["due_date"]}

        # Status (optional)
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

    # ---------- GraphQL mutations with timeout verification ----------

    async def _create_subitem_with_verify(self, parent_item_id: int, item_name: str, column_values: Dict) -> Dict:
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

        try:
            data = await self._post_graphql(mutation, variables)
            return data["data"]["create_subitem"]

        except (requests.exceptions.Timeout,
                requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError) as e:
            # If we timed out, Monday may still have created the subitem. Verify.
            logger.warning(f"create_subitem timed out/conn error: {e}. Verifying existence...")
            existing = await self._find_subitem_by_name(parent_item_id, item_name)
            if existing:
                logger.warning("Server-side success confirmed after client timeout. Proceeding.")
                return existing
            # If not found, re-raise
            raise

    async def _find_subitem_by_name(self, parent_item_id: int, item_name: str) -> Optional[Dict]:
        """
        Look up subitems under a parent and return the one matching by name (exact).
        """
        q = """
        query ($ids: [ID!]!) {
          items (ids: $ids) {
            id
            name
            subitems {
              id
              name
              created_at
            }
          }
        }
        """
        d = await self._post_graphql(q, {"ids": [int(parent_item_id)]})
        items = d.get("data", {}).get("items", []) or []
        if not items:
            return None
        subitems = items[0].get("subitems", []) or []
        for s in subitems:
            if (s.get("name") or "").strip() == item_name.strip():
                return s
        return None

    # ---------- Utilities ----------

    async def _resolve_user_id(self, display_name: Optional[str]) -> Optional[int]:
        if not display_name:
            return None
        q = "query { users(limit: 500) { id name email } }"
        d = await self._post_graphql(q)
        users = d.get("data", {}).get("users", []) or []

        # Exact match
        for u in users:
            if (u.get("name") or "").strip() == display_name.strip():
                return int(u["id"])
        # Fuzzy contains
        for u in users:
            if display_name.strip() in (u.get("name") or ""):
                return int(u["id"])
        return None
