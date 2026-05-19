from __future__ import annotations

import itertools
import random
import string


class ProxyRotator:
    def __init__(self, proxy_url: str = "", regions: list[str] | None = None) -> None:
        self.proxy_url = proxy_url
        self.regions = regions or ["us", "eu", "br"]
        self._regions = itertools.cycle(self.regions)
        self._sticky_session: str | None = None
        self.current_region: str | None = None

    def next_proxy(self) -> str | None:
        if not self.proxy_url:
            return None
        session = self._sticky_session or _session_id()
        region = self.current_region or next(self._regions)
        self.current_region = region
        return self.proxy_url.replace("{session}", session).replace("{region}", region)

    def start_sticky_session(self) -> str:
        self._sticky_session = _session_id()
        self.current_region = next(self._regions)
        return self._sticky_session

    def end_sticky_session(self) -> None:
        self._sticky_session = None
        self.current_region = None


def _session_id(length: int = 10) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))
