# monday_client.py (merged)
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core import config

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
