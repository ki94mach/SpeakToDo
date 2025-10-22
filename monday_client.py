# monday_client.py (merged)
from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config

logger = logging.getLogger(__name__)

# Tunables
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 20
MAX_ATTEMPTS = 4
BASE_BACKOFF = 0.6


def _jittered_backoff(attempt: int) -> float:
    return BASE_BACKOFF * (2 ** (attempt - 1)) * (0.7 + random.random() * 0.6)


class MondayClient:
    """
    Lightweight Monday GraphQL client with proxy support and resilient POST.
    """

    def __init__(self, token: str, api_url: str = "https://api.monday.com/v2"):
        self.api_url = api_url
        self.headers = {
            "Authorization": token,
            "Content-Type": "application/json",
            "API-Version": "2024-10",
        }
        self.session = self._create_session_with_proxy()

    # ----- proxy config -----
    def _create_session_with_proxy(self) -> requests.Session:
        s = requests.Session()

        # Pooling adapter; we handle retries ourselves in post()
        adapter = HTTPAdapter(
            max_retries=Retry(total=0, backoff_factor=0),
            pool_connections=10,
            pool_maxsize=20,
        )
        s.mount("http://", adapter)
        s.mount("https://", adapter)

        proxy_url = self._build_proxy_url()
        if proxy_url:
            s.proxies = {"http": proxy_url, "https": proxy_url}
            logger.info(f"Configured proxy for MondayClient: {proxy_url}")
        else:
            logger.info("No explicit proxy configured for MondayClient.")

        # Don’t inherit env proxies unexpectedly (HTTP[S]_PROXY)
        s.trust_env = False
        return s

    def _build_proxy_url(self) -> Optional[str]:
        try:
            ptype = getattr(config, "SOCKS_PROXY_TYPE", "socks5").lower()
            host = getattr(config, "SOCKS_PROXY_HOST", None)
            port = getattr(config, "SOCKS_PROXY_PORT", None)
            user = getattr(config, "SOCKS_PROXY_USERNAME", "") or ""
            pwd = getattr(config, "SOCKS_PROXY_PASSWORD", "") or ""
            if not host or not port:
                return None
            if ptype not in ("socks5", "socks5h", "socks4", "http", "https"):
                logger.warning(f"Unsupported proxy type: {ptype} (fallback to socks5)")
                ptype = "socks5"
            if user and pwd:
                return f"{ptype}://{user}:{pwd}@{host}:{port}"
            return f"{ptype}://{host}:{port}"
        except Exception as e:
            logger.error(f"Error building proxy URL: {e}")
            return None

    # ----- single POST with resilient retries & JSON-safe parsing -----
    async def post(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        last_exc: Optional[Exception] = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                def _do():
                    return self.session.post(
                        self.api_url,
                        json=payload,
                        headers=self.headers,
                        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                    )

                resp = await asyncio.to_thread(_do)
                status = resp.status_code
                ctype = resp.headers.get("Content-Type", "")
                text = resp.text or ""

                if status == 200:
                    try:
                        data = resp.json()
                    except ValueError:
                        snippet = text[:600].replace("\n", " ")
                        logger.error(
                            f"Monday returned non-JSON on 200. Content-Type='{ctype}', "
                            f"first bytes: {snippet!r}"
                        )
                        raise RuntimeError("Non-JSON response from Monday API on status 200")

                    if "errors" in data:
                        err_str = json.dumps(data["errors"], ensure_ascii=False).lower()
                        if any(k in err_str for k in ("rate limit", "complexity", "budget exhausted")) and attempt < MAX_ATTEMPTS:
                            sleep_s = _jittered_backoff(attempt)
                            logger.warning(f"GraphQL rate/complexity hint; retry in {sleep_s:.2f}s")
                            await asyncio.sleep(sleep_s)
                            continue
                        raise RuntimeError(f"Monday GraphQL errors: {data['errors']}")
                    return data

                if status == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if not retry_after:
                        try:
                            body = resp.json()
                            retry_after = str(body.get("retry_in_seconds", ""))  # best-effort
                        except Exception:
                            retry_after = ""
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else _jittered_backoff(attempt)
                    if attempt < MAX_ATTEMPTS:
                        logger.warning(f"429 rate limited. Waiting {wait:.2f}s then retrying.")
                        await asyncio.sleep(wait)
                        continue
                    raise RuntimeError(f"HTTP 429 after retries: {text}")

                if status == 407:
                    snippet = text[:600].replace("\n", " ")
                    logger.error(
                        f"Proxy authentication required (407). "
                        f"Check SOCKS/HTTP credentials in config. First bytes: {snippet!r}"
                    )
                    raise RuntimeError("Proxy authentication required (407)")

                if 500 <= status < 600 and attempt < MAX_ATTEMPTS:
                    sleep_s = _jittered_backoff(attempt)
                    logger.warning(f"HTTP {status}. Retrying in {sleep_s:.2f}s")
                    await asyncio.sleep(sleep_s)
                    continue

                snippet = text[:600].replace("\n", " ")
                logger.error(
                    f"HTTP {status} from Monday. Content-Type='{ctype}', first bytes: {snippet!r}"
                )
                raise RuntimeError(f"HTTP {status}: {snippet[:200]}")

            except (requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.ReadTimeout) as e:
                last_exc = e
                if attempt >= MAX_ATTEMPTS:
                    break
                sleep_s = _jittered_backoff(attempt)
                logger.warning(f"Network error {type(e).__name__}. Retry in {sleep_s:.2f}s")
                await asyncio.sleep(sleep_s)

        assert last_exc is not None
        raise last_exc


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


# ---------------------- Assignable People (merged) ---------------------- #

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


# ----------------------------- quick test -----------------------------
# Run: python monday_client.py  (requires config.MONDAY_API_TOKEN and config.MONDAY_BOARD_ID)
if __name__ == "__main__":
    async def _main():
        client = MondayClient(config.MONDAY_API_TOKEN)
        svc = AssignablePeopleService(client)
        people = await svc.fetch_assignable_people(config.MONDAY_BOARD_ID)
        print(json.dumps(people, ensure_ascii=False, indent=2))

    asyncio.run(_main())
