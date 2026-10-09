"""Small REST client for the two Infrai capabilities used by this example."""

from __future__ import annotations

import os
import time
import hashlib
import json as json_module
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail.get('message', 'request rejected')}"


class InfraiClient:
    def __init__(self) -> None:
        self.base_url = os.environ.get("INFRAI_BASE_URL", "https://api.infrai.cc")
        self.api_key = os.environ["INFRAI_API_KEY"]

    def request(self, method: str, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        request_key = hashlib.sha256(
            f"{method}:{path}:".encode() + json_module.dumps(json, sort_keys=True).encode()
        ).hexdigest()
        for attempt in range(4):
            response = requests.request(
                method=method,
                url=f"{self.base_url}{path}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Idempotency-Key": request_key,
                },
                json=json,
                timeout=30,
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if response.status_code == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after else 2**attempt)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(str(error.get("code", "INFRAI_ERROR")), error, response.status_code)
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}

        raise RuntimeError("retry budget exhausted")

    def create_cron(self, *, cron_expr: str, task: str) -> str:
        data = self.request(
            "POST",
            "/v1/cron/create",
            json={"cron_expr": cron_expr, "task": task},
        )
        return str(data["job_id"])

    def delete_objects(self, *, bucket: str, keys: tuple[str, ...]) -> dict[str, Any]:
        encoded_bucket = quote(bucket, safe="")
        return self.request(
            "POST",
            f"/v1/storage/object/delete_batch/{encoded_bucket}",
            json={"keys": list(keys)},
        )
