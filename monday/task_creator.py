# task_creator.py
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import requests

from core import config
from monday.client import MondayClient

logger = logging.getLogger(__name__)

# Note: Retry logic and timeouts are handled by MondayClient


@dataclass
class LLMTask:
    project_title: str
    task_title: str
    owner: Optional[str] = None
    due_date: Optional[str] = None   # 'YYYY-MM-DD'
    status: Optional[str | int] = None  # label or index


class TaskCreator:
    def __init__(self):
        self.board_id = int(config.MONDAY_BOARD_ID)
        self.client = MondayClient(config.MONDAY_API_TOKEN)

        # caches
        self._dropdown_labels_cache: Dict[str, List[str]] = {}
        self._board_people_cache: Dict[int, Dict[int, Dict[str, Any]]] = {}
        self._subitems_board_cache: Optional[Tuple[int, List[Dict[str, Any]]]] = None  # (sub_board_id, columns)
        self._parent_item_cache: Dict[str, int] = {}  # project_title -> item_id
        self._first_group_id_cache: Optional[str] = None

    # ---------- Public API ----------

    async def test_connection(self) -> bool:
        try:
            data = await self.client.post("query { me { name email } }")
            me = data.get("data", {}).get("me")
            if me:
                logger.info(f"Connected as {me['name']} ({me['email']})")
                return True
            logger.error(f"Connection test unexpected response: {data}")
            return False
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    async def create_tasks(self, tasks: List[Dict[str, Any] | LLMTask]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for t in tasks:
            task = LLMTask(**t) if isinstance(t, dict) else t
            try:
                out.append(await self._create_single_task(task))
            except Exception as e:
                logger.error(
                    f"Error creating task '{task.task_title}' for project '{task.project_title}': {e}"
                )
        logger.info(f"Created {len(out)} / {len(tasks)} tasks.")
        return out

    # ---------- Core flow ----------

    async def _create_single_task(self, task: LLMTask) -> Dict[str, Any]:
        if not task.project_title:
            raise ValueError("project_title is required")
        if not task.task_title:
            raise ValueError("task_title is required")

        parent_id = await self._get_or_create_parent_item(task.project_title)
        sub_board_id, sub_cols = await self._get_subitems_board_columns()
        col_values = await self._prepare_subitem_values(sub_cols, task, sub_board_id=sub_board_id)

        sub = await self._create_subitem_with_verify(
            parent_item_id=parent_id,
            item_name=task.task_title,
            column_values=col_values,
            create_labels_if_missing=True,   # helpful when status/dropdown label not present
        )

        logger.info(
            f"✅ Created subtask '{sub['name']}' under '{task.project_title}' "
            f"(parent id {parent_id}, subitem id {sub['id']})"
        )
        return {
            "id": sub["id"],
            "name": sub["name"],
            "created_at": sub.get("created_at"),
            "project_title": task.project_title,
            "task_title": task.task_title,
            "owner": task.owner,
            "due_date": task.due_date,
            "parent_item_id": parent_id,
            "board_id": self.board_id,
            "subitems_board_id": sub_board_id,
            "monday_parent_url": f"https://your-account.monday.com/boards/{self.board_id}/pulses/{parent_id}",
        }

    # ---------- Parent item (project) helpers ----------

    async def _get_or_create_parent_item(self, project_title: str) -> int:
        """
        Find an item with name == project_title using items_page pagination.
        If not found, create it (in the first group). Results are cached.
        """
        # Normalize project title for cache key (consistent comparison)
        normalized_title = project_title.strip()
        
        # Check cache first
        if normalized_title in self._parent_item_cache:
            return self._parent_item_cache[normalized_title]

        # 1) Pull groups + first cursor
        q1 = """
        query ($board_id: [ID!]!, $limit: Int!) {
          boards(ids: $board_id) {
            groups { id title }
            items_page(limit: $limit) {
              cursor
              items { id name }
            }
          }
        }
        """
        data = await self.client.post(q1, {"board_id": [self.board_id], "limit": 200})
        board = data["data"]["boards"][0]
        groups = board.get("groups", []) or []
        first_group_id = groups[0]["id"] if groups else None
        
        # Cache first_group_id for later use
        if self._first_group_id_cache is None:
            self._first_group_id_cache = first_group_id

        # scan first page
        page = board.get("items_page") or {}
        for it in (page.get("items") or []):
            item_name = (it.get("name") or "").strip()
            if item_name == normalized_title:
                item_id = int(it["id"])
                # Cache all items found during lookup
                self._parent_item_cache[item_name] = item_id
                return item_id

        cursor = page.get("cursor")

        # 2) continue with next_items_page until found or exhausted
        while cursor:
            q2 = """
            query ($cursor: String!, $limit: Int!) {
              next_items_page(cursor: $cursor, limit: $limit) {
                cursor
                items { id name }
              }
            }
            """
            d2 = await self.client.post(q2, {"cursor": cursor, "limit": 500})
            nx = d2.get("data", {}).get("next_items_page") or {}
            for it in (nx.get("items") or []):
                item_name = (it.get("name") or "").strip()
                if item_name == normalized_title:
                    item_id = int(it["id"])
                    self._parent_item_cache[item_name] = item_id
                    return item_id
            cursor = nx.get("cursor")

        # 3) Create parent item (use cached first_group_id if available)
        group_id = first_group_id or self._first_group_id_cache
        m = """
        mutation ($board_id: ID!, $item_name: String!, $group_id: String) {
          create_item(board_id: $board_id, item_name: $item_name, group_id: $group_id) { id }
        }
        """
        vars_ = {"board_id": self.board_id, "item_name": project_title, "group_id": group_id}
        d3 = await self.client.post(m, vars_)
        item_id = int(d3["data"]["create_item"]["id"])
        
        # Cache the newly created item
        self._parent_item_cache[normalized_title] = item_id
        return item_id

    # ---------- Subitems board + columns ----------

    async def _get_subitems_board_columns(self) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Read the Subitems column settings to find the linked subitems board id,
        then fetch its columns. Cached to avoid repeated API calls.
        """
        if self._subitems_board_cache is not None:
            return self._subitems_board_cache

        q1 = """
        query ($board_id: [ID!]!) {
          boards(ids: $board_id) {
            columns { id title type settings_str }
          }
        }
        """
        d1 = await self.client.post(q1, {"board_id": [self.board_id]})
        cols = d1["data"]["boards"][0]["columns"]

        sub_col = next((c for c in cols if c.get("type") in ("subitems", "subtasks")), None)
        if not sub_col:
            raise RuntimeError("Board has no Subitems column. Add a Subitems column in Monday UI.")

        settings = {}
        if sub_col.get("settings_str"):
            try:
                settings = json.loads(sub_col["settings_str"])
            except Exception:
                settings = {}

        sub_board_id = None
        # settings can vary: "boardIds", "linkedBoardsIds", or "boardId"
        for key in ("boardIds", "linkedBoardsIds", "boardId"):
            val = settings.get(key)
            if isinstance(val, list) and val:
                sub_board_id = val[0]
                break
            if isinstance(val, int):
                sub_board_id = val
                break
        if not sub_board_id:
            raise RuntimeError("Could not resolve subitems board id from column settings.")

        q2 = """
        query ($id: [ID!]!) {
          boards(ids: $id) { id columns { id title type settings_str } }
        }
        """
        d2 = await self.client.post(q2, {"id": [sub_board_id]})
        sub_cols = d2["data"]["boards"][0]["columns"]
        self._subitems_board_cache = (int(sub_board_id), sub_cols)
        return self._subitems_board_cache

    # ---------- Column helpers ----------

    def _find_ownerish_column(self, columns: List[Dict[str, Any]], *, want_type: str) -> Optional[Dict[str, Any]]:
        """
        Prefer titles matching 'Owner'/'Assignee'/'Person' (case-insensitive),
        otherwise return first column of given type.
        """
        title_re = re.compile(r"\b(owner|assignee|person)\b", re.I)
        candidates = [c for c in columns if c.get("type") == want_type]
        if not candidates:
            return None
        for c in candidates:
            if title_re.search(c.get("title") or ""):
                return c
        return candidates[0]

    def _norm(self, s: Optional[str]) -> str:
        return (s or "").strip().lower()

    # ---------- People/labels discovery ----------

    async def _get_board_people_map(self, board_ids: List[int]) -> Dict[int, Dict[int, Dict[str, Any]]]:
        """
        Returns {board_id: { user_id: {id,name,email} }} from owners+subscribers.
        Cached per board id.
        """
        out: Dict[int, Dict[int, Dict[str, Any]]] = {}
        to_fetch = [b for b in board_ids if b not in self._board_people_cache]

        if to_fetch:
            q = """
            query($ids:[ID!]!) {
              boards(ids:$ids) {
                id
                owners { id name email }
                subscribers { id name email }
              }
            }
            """
            data = await self.client.post(q, {"ids": to_fetch})
            for b in (data.get("data", {}).get("boards") or []):
                bmap: Dict[int, Dict[str, Any]] = {}
                for u in (b.get("owners") or []):
                    bmap[int(u["id"])] = {"id": int(u["id"]), "name": u.get("name"), "email": u.get("email")}
                for u in (b.get("subscribers") or []):
                    bmap[int(u["id"])] = {"id": int(u["id"]), "name": u.get("name"), "email": u.get("email")}
                self._board_people_cache[int(b["id"])] = bmap

        for bid in board_ids:
            out[bid] = self._board_people_cache.get(bid, {})
        return out

    def _match_owner_to_user(self, owner_str: str, *people_maps: Dict[int, Dict[str, Any]]) -> Optional[int]:
        """
        Map an input 'owner' string to a user id by name/email (exact, startswith, contains, email local-part).
        """
        t = self._norm(owner_str)
        if not t:
            return None
        users: Dict[int, Dict[str, Any]] = {}
        for m in people_maps:
            for uid, u in (m or {}).items():
                users[uid] = u

        # exact name or email
        for uid, u in users.items():
            if self._norm(u.get("name")) == t or self._norm(u.get("email")) == t:
                return uid
        # startswith / contains
        for uid, u in users.items():
            if self._norm(u.get("name")).startswith(t):
                return uid
        for uid, u in users.items():
            if t in self._norm(u.get("name")):
                return uid
        # email local part
        if "@" in t:
            local = t.split("@", 1)[0]
            for uid, u in users.items():
                if self._norm((u.get("email") or "").split("@", 1)[0]) == local:
                    return uid
        return None

    def _dropdown_labels_from_settings(self, col: Dict[str, Any]) -> List[str]:
        """
        Returns label names from a dropdown column's settings_str.
        Accepts legacy shapes: list[str], dict[str->label], or list[dict{name:..}].
        """
        if not col or not col.get("settings_str"):
            return []
        try:
            st = json.loads(col["settings_str"])
            labels = st.get("labels") or []
            if isinstance(labels, list):
                # could be ["A","B"] or [{"id":..,"name":"A"}, ...]
                if labels and isinstance(labels[0], dict):
                    return [x.get("name") or x.get("label") for x in labels if isinstance(x, dict)]
                return [str(x) for x in labels]
            if isinstance(labels, dict):  # {"1":"A","2":"B"}
                return [labels[k] for k in sorted(labels, key=lambda x: int(x) if str(x).isdigit() else str(x))]
        except Exception:
            pass
        return []

    # ---------- Column value assembly ----------

    async def _prepare_subitem_values(self, subitem_columns: List[Dict[str, Any]],
                                      task: LLMTask,
                                      sub_board_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Build {column_id: value} for create_subitem column_values.

        Notes (per Monday docs):
        - Text: pass a simple string. :contentReference[oaicite:6]{index=6}
        - Long text: pass {"text": "..."} JSON. :contentReference[oaicite:7]{index=7}
        - Date: pass {"date":"YYYY-MM-DD"} (optionally time). :contentReference[oaicite:8]{index=8}
        - Status: pass "Done" or {"label":"Done"} or {"index": N}. :contentReference[oaicite:9]{index=9}
        - People: {"personsAndTeams":[{"id":UID,"kind":"person"}]}. :contentReference[oaicite:10]{index=10}
        - Dropdown: {"labels":["A","B"]}. :contentReference[oaicite:11]{index=11}
        """
        values: Dict[str, Any] = {}

        # Identify useful columns by type
        people_col   = self._find_ownerish_column(subitem_columns, want_type="people")
        owner_text   = self._find_ownerish_column(subitem_columns, want_type="text")
        owner_dd_col = self._find_ownerish_column(subitem_columns, want_type="dropdown")
        date_col     = next((c for c in subitem_columns if c.get("type") == "date"), None)
        status_col   = next((c for c in subitem_columns if c.get("type") == "status"), None)
        long_col     = next((c for c in subitem_columns if c.get("type") == "long_text"), None)

        # Due date
        if date_col and task.due_date:
            values[date_col["id"]] = {"date": task.due_date}

        # Status
        if status_col and task.status is not None:
            if isinstance(task.status, int):
                values[status_col["id"]] = {"index": task.status}
            else:
                values[status_col["id"]] = {"label": str(task.status)}

        # Long text summary
        if long_col:
            bits = []
            if task.owner:
                bits.append(f"Owner: {task.owner}")
            if task.due_date:
                bits.append(f"Due: {task.due_date}")
            values[long_col["id"]] = {"text": "\n".join(bits) if bits else ""}

        owner_in = (task.owner or "").strip()
        if owner_in:
            # Mirror owner into text field (simple string)
            if owner_text:
                values[owner_text["id"]] = owner_in  # text wants a plain string

            # Dropdown best-effort label match
            if owner_dd_col:
                labels = self._dropdown_labels_cache.get(owner_dd_col["id"])
                if labels is None:
                    labels = self._dropdown_labels_from_settings(owner_dd_col)
                    self._dropdown_labels_cache[owner_dd_col["id"]] = labels
                if labels:
                    target = self._norm(owner_in)
                    match = next((l for l in labels if self._norm(l) == target), None)
                    if not match:
                        # soft fallback if "Owner" label missing
                        for candidate in ("unassigned", "tbd", "unknown", "other"):
                            if any(self._norm(l) == candidate for l in labels):
                                match = next(l for l in labels if self._norm(l) == candidate)
                                break
                    if match:
                        values[owner_dd_col["id"]] = {"labels": [match]}

            # People assignment from board visibility
            if people_col:
                board_ids = list({self.board_id, int(sub_board_id)}) if sub_board_id else [self.board_id]
                maps = await self._get_board_people_map(board_ids)
                main_map = maps.get(self.board_id, {})
                sub_map = maps.get(int(sub_board_id), {}) if sub_board_id else {}
                uid = self._match_owner_to_user(owner_in, main_map, sub_map)
                if uid:
                    values[people_col["id"]] = {"personsAndTeams": [{"id": uid, "kind": "person"}]}

        return values

    # ---------- Mutations with verification ----------

    async def _create_subitem_with_verify(
        self,
        parent_item_id: int,
        item_name: str,
        column_values: Dict[str, Any],
        create_labels_if_missing: bool = False,
    ) -> Dict[str, Any]:
        """
        Wraps create_subitem and verifies existence on timeout.
        """
        mutation = """
        mutation ($parent_item_id: ID!, $item_name: String!, $column_values: JSON, $create: Boolean) {
          create_subitem(
            parent_item_id: $parent_item_id,
            item_name: $item_name,
            column_values: $column_values,
            create_labels_if_missing: $create
          ) { id name created_at }
        }
        """
        variables = {
            "parent_item_id": int(parent_item_id),
            "item_name": item_name,
            "column_values": json.dumps(column_values, ensure_ascii=False),
            "create": bool(create_labels_if_missing),
        }

        try:
            data = await self.client.post(mutation, variables)
            return data["data"]["create_subitem"]
        except (requests.exceptions.Timeout,
                requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError) as e:
            logger.warning(f"create_subitem timed out/conn error: {e}. Verifying existence...")
            existing = await self._find_subitem_by_name(parent_item_id, item_name)
            if existing:
                logger.warning("Server-side success confirmed after client timeout. Proceeding.")
                return existing
            raise

    async def _find_subitem_by_name(self, parent_item_id: int, item_name: str) -> Optional[Dict[str, Any]]:
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
        d = await self.client.post(q, {"ids": [int(parent_item_id)]})
        items = d.get("data", {}).get("items", []) or []
        if not items:
            return None
        for s in (items[0].get("subitems") or []):
            if (s.get("name") or "").strip() == item_name.strip():
                return s
        return None
