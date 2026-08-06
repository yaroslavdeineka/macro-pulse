from __future__ import annotations

import os
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"

UA = "macro-pulse/1.0 (portfolio project; github.com/yaroslavdeineka)"


class SourceUnavailable(RuntimeError):
    """Raised when a source can't be fetched and no cache exists."""


class BaseClient:
    #: subclasses set this — used in cache filenames and log lines
    source_name: str = "base"

    def __init__(self, timeout: int | None = None):
        # env-tunable so CI / restricted sandboxes can fail fast:
        #   MACRO_PULSE_TIMEOUT (s, default 30), MACRO_PULSE_RETRIES (default 4)
        self.timeout = timeout or int(os.environ.get("MACRO_PULSE_TIMEOUT", 30))
        self.session = requests.Session()
        retry = Retry(
            total=int(os.environ.get("MACRO_PULSE_RETRIES", 4)),
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.headers.update({"User-Agent": UA})
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ---- fetch helpers -----------------------------------------------------
    def get_text(self, url: str, params: dict | None = None) -> str:
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.text

    def get_json(self, url: str, params: dict | None = None):
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ---- cache helpers -----------------------------------------------------
    def cache_path(self, key: str) -> Path:
        return CACHE_DIR / f"{self.source_name}_{key}"

    def write_cache(self, key: str, text: str) -> Path:
        path = self.cache_path(key)
        path.write_text(text, encoding="utf-8")
        return path

    def read_cache(self, key: str) -> str | None:
        path = self.cache_path(key)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def fetch_or_cache(self, key: str, url: str, params: dict | None = None,
                       refresh: bool = False) -> str:
        """Live fetch (writing the cache) when refresh=True or no cache exists;
        otherwise serve from cache. Falls back to stale cache on network error."""
        if not refresh:
            cached = self.read_cache(key)
            if cached is not None:
                return cached
        try:
            text = self.get_text(url, params=params)
            self.write_cache(key, text)
            return text
        except requests.RequestException as exc:
            cached = self.read_cache(key)
            if cached is not None:
                print(f"  [{self.source_name}] network error ({exc}); using cached copy")
                return cached
            raise SourceUnavailable(
                f"{self.source_name}: fetch failed and no cache exists ({exc})"
            ) from exc
