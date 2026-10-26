"""
Scanning engine. Sends files to the Shield3xxAV server (/scan endpoint),
so no local ClamAV install or running clamd daemon is needed.

Requires: the server at config.SERVER_URL is reachable and you are logged in.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Optional

import requests
from config import SERVER_URL


def login(username, password):
    r = requests.post(f"{SERVER_URL}/login",
                      json={"username": username, "password": password},
                      timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def cloud_scan(path, token):
    with open(path, "rb") as f:
        r = requests.post(f"{SERVER_URL}/scan",
                          headers={"Authorization": f"Bearer {token}"},
                          files={"file": (str(path), f)},
                          timeout=120)
    r.raise_for_status()
    return r.json()   # {"status": "clean" | "infected", ...}


@dataclass
class ScanResult:
    path: str
    infected: bool
    threat: Optional[str] = None
    error: Optional[str] = None


class Scanner:
    """Same interface as the old clamd-based Scanner, backed by the server."""

    def __init__(self, token: Optional[str] = None):
        self.token = token
        self.available = True

    def login(self, username: str, password: str) -> None:
        self.token = login(username, password)

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{SERVER_URL}/", timeout=10)
            return r.status_code < 500
        except Exception:
            return False

    def scan_file(self, path: Path) -> ScanResult:
        try:
            if not self.token:
                return ScanResult(str(path), infected=False,
                                  error="Not logged in to the scan server.")
            data = cloud_scan(path, self.token)
            infected = str(data.get("status", "")).lower() == "infected"
            threat = data.get("threat") or data.get("virus") if infected else None
            return ScanResult(str(path), infected=infected, threat=threat)
        except Exception as e:
            return ScanResult(str(path), infected=False, error=str(e))

    def scan_folder(
        self,
        folder: Path,
        on_progress: Optional[Callable[[ScanResult], None]] = None,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> Iterator[ScanResult]:
        for path in self._iter_files(folder):
            if should_stop():
                return
            result = self.scan_file(path)
            if on_progress:
                on_progress(result)
            yield result

    @staticmethod
    def _iter_files(folder: Path) -> Iterator[Path]:
        for p in Path(folder).rglob("*"):
            if p.is_file() and not p.is_symlink():
                yield p
