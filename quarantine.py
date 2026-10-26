"""
Moves infected files into the quarantine folder and records them in a log.
Files are renamed with a .quarantined suffix so they can't be run by accident.
Restore and delete actions are available from the GUI.
"""
import json
import shutil
import time
from pathlib import Path
from typing import List, Dict

from config import QUARANTINE_DIR, QUARANTINE_LOG


def _load_log() -> List[Dict]:
    if QUARANTINE_LOG.exists():
        return json.loads(QUARANTINE_LOG.read_text(encoding="utf-8"))
    return []


def _save_log(entries: List[Dict]) -> None:
    QUARANTINE_LOG.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def quarantine_file(path: Path, threat: str) -> Path:
    path = Path(path)
    stamp = int(time.time())
    dest = QUARANTINE_DIR / f"{stamp}_{path.name}.quarantined"
    shutil.move(str(path), str(dest))

    entries = _load_log()
    entries.append({
        "original_path": str(path),
        "quarantined_path": str(dest),
        "threat": threat,
        "time": stamp,
    })
    _save_log(entries)
    return dest


def list_quarantined() -> List[Dict]:
    return _load_log()


def restore_file(entry: Dict) -> None:
    src = Path(entry["quarantined_path"])
    dst = Path(entry["original_path"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    _save_log([e for e in _load_log() if e != entry])


def delete_quarantined(entry: Dict) -> None:
    Path(entry["quarantined_path"]).unlink(missing_ok=True)
    _save_log([e for e in _load_log() if e != entry])