import json
import re
import urllib.request
import urllib.error
from pathlib import Path

import config

# Set this to your Render URL, e.g. https://your-service.onrender.com
SERVER_URL = "https://shield3xx.onrender.com"
ACCOUNT_FILE = config.DATA_DIR / "account.json"
GMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@gmail\.com$", re.IGNORECASE)


def valid_gmail(email: str) -> bool:
    return bool(GMAIL_RE.match(email.strip()))


def load_account() -> dict | None:
    if not ACCOUNT_FILE.exists():
        return None
    try:
        return json.loads(ACCOUNT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_account(email: str, username: str, password: str) -> None:
    ACCOUNT_FILE.write_text(json.dumps({
        "email": email.strip().lower(),
        "username": username.strip(),
        "password": password,
        "synced": False,
    }), encoding="utf-8")


def mark_synced() -> None:
    acc = load_account()
    if acc:
        acc["synced"] = True
        ACCOUNT_FILE.write_text(json.dumps(acc), encoding="utf-8")


def sync_to_server(timeout: float = 8.0) -> tuple[bool, str]:
    """Send the account to the Render server. Returns (ok, message).
    Never raises, so scans keep working when offline."""
    acc = load_account()
    if not acc or acc.get("synced"):
        return True, "Nothing to sync"
    body = json.dumps({
        "email": acc["email"],
        "username": acc["username"],
        "password": acc["password"],
    }).encode("utf-8")
    req = urllib.request.Request(
        SERVER_URL.rstrip("/") + "/sync", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                mark_synced()
                return True, "Synced"
            return False, f"Server returned {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"Server rejected sync ({e.code})"
    except Exception:
        return False, "Offline - will sync when connected"
