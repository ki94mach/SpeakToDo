from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from monday.client import MondayClient
from monday.board import BoardDirectory

@dataclass(frozen=True)
class Person:
    id: int
    name: str
    email: Optional[str]
    enabled: bool = True


class AssignablePeopleService:
    """
    Build a people list that matches monday.com's People/Owner picker:

    - All account non-guest users (enabled)  <-- primary source shown in the UI
    - PLUS: Any users (incl. guests) who already have access to the board/subitems board
    - PLUS: Users coming from board/workspace team subscribers

    Expect email=None for users if the token cannot read emails for others.
    """

    def __init__(self, client: MondayClient):
        self.client = client

    async def fetch_assignable_people(
        self,
        parent_board_id: int,
        *,
        include_account_non_guests: bool = True,
        widen_to_workspace: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Returns a de-duplicated list of dicts: [{id, name, email}], sorted by name.
        """
        bd = BoardDirectory(self.client)
        sub_board_id = await bd.get_subitems_board_id(parent_board_id)
        target_board_id = sub_board_id or parent_board_id

        users_map: Dict[int, Person] = {}

        # 1) Account-wide non-guest users (UI's main list)
        if include_account_non_guests:
            for u in await self._all_non_guest_users():
                if u.get("enabled"):
                    self._add_user(users_map, u)

        # 2) Board owners/subscribers + expand team subscribers
        board_info = await self._get_board_people_and_workspace(target_board_id)
        for u in board_info["owners"]:
            self._add_user(users_map, u)
        for u in board_info["subscribers"]:
            self._add_user(users_map, u)

        if board_info["team_ids"]:
            team_users = await self._users_for_teams(board_info["team_ids"])
            for u in team_users:
                self._add_user(users_map, u)

        # 3) Workspace subscribers & team subscribers (if concrete workspace id)
        if widen_to_workspace and board_info["workspace_id"] is not None:
            ws_users, ws_team_ids = await self._workspace_people(board_info["workspace_id"])
            for u in ws_users:
                self._add_user(users_map, u)
            if ws_team_ids:
                ws_team_users = await self._users_for_teams(ws_team_ids)
                for u in ws_team_users:
                    self._add_user(users_map, u)

        out = [
            {"id": p.id, "name": p.name, "email": p.email or None}
            for p in sorted(users_map.values(), key=lambda x: (x.name or "").lower())
            if p.enabled
        ]
        return out

    # ----------------------------- helpers -----------------------------

    def _add_user(self, users_map: Dict[int, Person], u: Dict[str, Any]) -> None:
        try:
            uid = int(u.get("id"))
        except Exception:
            return
        name = u.get("name") or ""
        email = u.get("email")
        enabled = bool(u.get("enabled", True))
        prev = users_map.get(uid)
        if prev is None:
            users_map[uid] = Person(id=uid, name=name, email=email, enabled=enabled)
        else:
            # Prefer whichever has an email populated and a non-empty name
            merged_name = name or prev.name
            merged_email = email or prev.email
            merged_enabled = enabled or prev.enabled
            if (merged_name != prev.name) or (merged_email != prev.email) or (merged_enabled != prev.enabled):
                users_map[uid] = Person(id=uid, name=merged_name, email=merged_email, enabled=merged_enabled)

    async def _all_non_guest_users(self) -> List[Dict[str, Any]]:
        """
        Paginate across account users(kind: non_guests).
        Some tokens may still only see self (privacy/permissions).
        """
        out: List[Dict[str, Any]] = []
        limit = 500
        page = 1
        while True:
            q = """
            query ($limit: Int!, $page: Int) {
              users(limit: $limit, page: $page, kind: non_guests) {
                id
                name
                email
                enabled
              }
            }
            """
            d = await self.client.post(q, {"limit": limit, "page": page})
            chunk = ((d.get("data") or {}).get("users")) or []
            out.extend(chunk)
            if len(chunk) < limit:
                break
            page += 1
        return out

    async def _users_for_teams(self, team_ids: List[int]) -> List[Dict[str, Any]]:
        if not team_ids:
            return []
        q = """
        query ($ids: [ID!]) {
          teams(ids: $ids) {
            id
            users {
              id
              name
              email
              enabled
            }
          }
        }
        """
        d = await self.client.post(q, {"ids": team_ids})
        out: List[Dict[str, Any]] = []
        for t in ((d.get("data") or {}).get("teams")) or []:
            out.extend(t.get("users") or [])
        return out

    async def _get_board_people_and_workspace(self, board_id: int) -> Dict[str, Any]:
        q = """
        query ($id:[ID!]!) {
          boards(ids: $id) {
            id
            workspace_id
            owners { id name email enabled }
            subscribers { id name email enabled }
            team_subscribers { id name }
          }
        }
        """
        d = await self.client.post(q, {"id": [int(board_id)]})
        boards = ((d.get("data") or {}).get("boards")) or []
        if not boards:
            return {"workspace_id": None, "owners": [], "subscribers": [], "team_ids": []}
        b = boards[0]
        team_ids = [int(t["id"]) for t in (b.get("team_subscribers") or []) if t.get("id")]
        return {
            "workspace_id": b.get("workspace_id"),
            "owners": b.get("owners") or [],
            "subscribers": b.get("subscribers") or [],
            "team_ids": team_ids,
        }

    async def _workspace_people(self, workspace_id: int) -> Tuple[List[Dict[str, Any]], List[int]]:
        """
        Return (users_subscribers, teams_subscribers_ids) for the workspace.
        """
        q = """
        query ($wid:[ID!]!) {
          workspaces(ids: $wid) {
            id
            users_subscribers { id name email enabled }
            teams_subscribers { id name }
          }
        }
        """
        d = await self.client.post(q, {"wid": [int(workspace_id)]})
        wss = ((d.get("data") or {}).get("workspaces")) or []
        if not wss:
            return [], []
        ws = wss[0] or {}
        users = ws.get("users_subscribers") or []
        team_ids = [int(t["id"]) for t in (ws.get("teams_subscribers") or []) if t.get("id")]
        return users, team_ids
