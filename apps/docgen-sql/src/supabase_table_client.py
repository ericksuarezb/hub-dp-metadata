from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib import error, parse, request

from src.run_repository import load_supabase_settings


class SupabaseTableClient:
    def __init__(self):
        self.settings = load_supabase_settings()
        self.base_url = self.settings.url.rstrip("/")
        self.service_role_key = self.settings.service_role_key

    def is_enabled(self) -> bool:
        return self.settings.enabled and bool(self.base_url) and bool(self.service_role_key)

    def upsert_rows(self, table: str, rows: List[Dict[str, Any]], on_conflict: str) -> None:
        if not rows:
            return
        endpoint = f"{self.base_url}/rest/v1/{table}?on_conflict={parse.quote(on_conflict, safe=',')}"
        self._request_json(
            "POST",
            endpoint,
            rows,
            headers=self._headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        )

    def fetch_schema_catalog_map(self) -> Dict[str, Dict[str, Any]]:
        endpoint = f"{self.base_url}/rest/v1/entropy_schema_catalog?select=*"
        rows = self._fetch_json(endpoint, headers=self._headers({"Accept": "application/json"}))
        if not isinstance(rows, list):
            return {}
        return {
            str(row.get("schema_name") or "").strip(): row
            for row in rows
            if isinstance(row, dict) and row.get("schema_name")
        }

    def fetch_rows(self, table_or_view: str, filters: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        query = "select=*"
        if filters:
            query += "&" + "&".join(f"{key}={value}" for key, value in filters.items())
        endpoint = f"{self.base_url}/rest/v1/{table_or_view}?{query}"
        rows = self._fetch_json(endpoint, headers=self._headers({"Accept": "application/json"}))
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _fetch_json(self, endpoint: str, headers: Dict[str, str]) -> Any:
        req = request.Request(endpoint, method="GET", headers=headers)
        try:
            with request.urlopen(req, timeout=self.settings.timeout_seconds) as response:
                body = response.read()
                if not body:
                    return None
                return json.loads(body.decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase devolvio HTTP {exc.code} en {endpoint}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"No fue posible conectar con Supabase en {endpoint}: {exc.reason}") from exc

    def _request_json(self, method: str, endpoint: str, payload: Any, headers: Dict[str, str]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(endpoint, data=body, method=method, headers=headers)
        try:
            with request.urlopen(req, timeout=self.settings.timeout_seconds) as response:
                response.read()
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase devolvio HTTP {exc.code} en {endpoint}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"No fue posible conectar con Supabase en {endpoint}: {exc.reason}") from exc
