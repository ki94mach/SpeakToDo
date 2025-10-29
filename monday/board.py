from monday.client import MondayClient
from typing import Optional
import json

class BoardDirectory:
    """
    Minimal board directory helper.
    """

    def __init__(self, client: MondayClient):
        self.client = client

    async def get_subitems_board_id(self, parent_board_id: int) -> Optional[int]:
        """
        Given a parent board id, resolve the linked subitems/subtasks board id (if any).
        """
        q = """
        query ($id:[ID!]!) {
          boards(ids:$id) {
            id
            columns { id title type settings_str }
          }
        }
        """
        d = await self.client.post(q, {"id": [int(parent_board_id)]})
        cols = (d.get("data", {}) or {}).get("boards", [{}])[0].get("columns") or []
        sub = next((c for c in cols if c.get("type") in ("subitems", "subtasks")), None)
        if not sub:
            return None
        st = {}
        try:
            if sub.get("settings_str"):
                st = json.loads(sub["settings_str"])
        except Exception:
            st = {}
        for key in ("boardIds", "linkedBoardsIds", "boardId"):
            val = st.get(key)
            if isinstance(val, list) and val:
                return int(val[0])
            if isinstance(val, int):
                return int(val)
        return None