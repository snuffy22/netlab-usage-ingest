from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

API_BASE = "https://api.cloudflare.com/client/v4"


class CloudflareAPIError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WorkerModule:
    name: str
    path: Path
    content_type: str


class CloudflareAPI:
    def __init__(self, account_id: str, api_token: str, timeout: float = 60.0) -> None:
        self.account_id = account_id
        self._client = httpx.Client(
            base_url=API_BASE,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CloudflareAPI:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def create_d1(self, name: str) -> dict[str, Any]:
        payload = self._json(
            self._client.post(
                f"/accounts/{self.account_id}/d1/database",
                json={"name": name},
            )
        )
        return payload["result"]

    def query_d1(
        self,
        database_id: str,
        sql: str,
        params: list[str | int | float | None] | None = None,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"sql": sql}
        if params is not None:
            body["params"] = params
        payload = self._json(
            self._client.post(
                f"/accounts/{self.account_id}/d1/database/{database_id}/query",
                json=body,
            )
        )
        result = payload["result"]
        for item in result:
            if item.get("success") is False:
                raise CloudflareAPIError("D1 query returned an unsuccessful statement result")
        return result

    def upload_worker(
        self,
        script_name: str,
        metadata: dict[str, Any],
        modules: Iterable[WorkerModule],
    ) -> dict[str, Any]:
        # Keep file handles open until httpx completes the multipart request.
        handles = []
        try:
            files: list[tuple[str, tuple[Any, ...]]] = [
                (
                    "metadata",
                    (None, json.dumps(metadata, separators=(",", ":")), "application/json"),
                )
            ]
            for module in modules:
                handle = module.path.open("rb")
                handles.append(handle)
                files.append((module.name, (module.name, handle, module.content_type)))

            payload = self._json(
                self._client.put(
                    f"/accounts/{self.account_id}/workers/scripts/{quote(script_name, safe='')}",
                    files=files,
                )
            )
            return payload["result"]
        finally:
            for handle in handles:
                handle.close()

    def set_worker_subdomain(self, script_name: str, enabled: bool = True) -> None:
        path = (
            f"/accounts/{self.account_id}/workers/scripts/"
            f"{quote(script_name, safe='')}/subdomain"
        )
        if enabled:
            self._json(self._client.post(path))
        else:
            self._json(self._client.delete(path))

    def set_cron_triggers(self, script_name: str, crons: Iterable[str]) -> None:
        self._json(
            self._client.put(
                f"/accounts/{self.account_id}/workers/scripts/"
                f"{quote(script_name, safe='')}/schedules",
                json=[{"cron": cron} for cron in crons],
            )
        )

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise CloudflareAPIError(
                f"Cloudflare API returned HTTP {response.status_code} with non-JSON body"
            ) from exc

        if response.is_error or not payload.get("success", False):
            errors = payload.get("errors") or []
            if errors:
                detail = "; ".join(
                    f"{item.get('code', '?')}: {item.get('message', 'unknown error')}"
                    for item in errors
                )
            else:
                detail = response.text[:500]
            raise CloudflareAPIError(
                f"Cloudflare API request failed (HTTP {response.status_code}): {detail}"
            )
        return payload
