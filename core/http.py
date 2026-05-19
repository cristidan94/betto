from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class HttpResponse:
    url: str
    status: int
    body: bytes
    headers: dict[str, str]

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class JsonHttpClient:
    def __init__(self, timeout_sec: int = 20, user_agent: str = "betto/0.1") -> None:
        self.timeout_sec = timeout_sec
        self.user_agent = user_agent

    def get(self, base_url: str, path: str, params: dict[str, object] | None = None) -> HttpResponse:
        query = ""
        if params:
            normalized: list[tuple[str, str]] = []
            for key, value in params.items():
                if isinstance(value, (list, tuple)):
                    normalized.extend((key, str(item)) for item in value)
                elif value is not None:
                    normalized.append((key, str(value)))
            query = "?" + urlencode(normalized)
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}{query}"
        request = Request(url, headers={"Accept": "application/json", "User-Agent": self.user_agent})
        with urlopen(request, timeout=self.timeout_sec) as response:
            body = response.read()
            return HttpResponse(
                url=url,
                status=response.status,
                body=body,
                headers={key: value for key, value in response.headers.items()},
            )

