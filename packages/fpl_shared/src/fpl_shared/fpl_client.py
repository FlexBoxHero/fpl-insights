import time
from typing import Any

import httpx

from fpl_shared.config import settings


class FplClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.fpl_api_base).rstrip("/")
        self._client = httpx.Client(timeout=60.0, headers={"User-Agent": "fpl-insights/0.1"})

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = self._client.get(url)
        response.raise_for_status()
        return response.json()

    def bootstrap_static(self) -> dict[str, Any]:
        return self._get("bootstrap-static/")

    def fixtures(self) -> list[dict[str, Any]]:
        return self._get("fixtures/")

    def element_summary(self, element_id: int) -> dict[str, Any]:
        time.sleep(0.1)
        return self._get(f"element-summary/{element_id}/")

    def _get_optional(self, path: str) -> Any | None:
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = self._client.get(url)
        if response.status_code in (403, 404):
            return None
        response.raise_for_status()
        return response.json()

    def entry(self, entry_id: int) -> Any | None:
        return self._get_optional(f"entry/{int(entry_id)}/")

    def entry_picks(self, entry_id: int, event: int) -> Any | None:
        return self._get_optional(f"entry/{int(entry_id)}/event/{int(event)}/picks/")
