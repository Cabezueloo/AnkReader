# kindle_sync.py
# ==============
# Reads the Kindle's vocab.db SQLite database, extracts new look-ups since
# the last sync, and returns structured records.

from __future__ import annotations

import glob
import os
import sqlite3
from dataclasses import dataclass
from typing import List, Optional

from aqt import mw
from aqt.utils import showWarning


# ---------------------------------------------------------------------------
# Data transfer object
# ---------------------------------------------------------------------------

@dataclass
class VocabEntry:
    """Single vocabulary look-up extracted from the Kindle."""
    word: str
    book_title: str
    usage: str                      # sentence from the book
    timestamp: int                  # epoch-millis of the look-up
    # Filled later by the enrichment stage
    meaning: str = ""               # Spanish translation / significado
    definition: str = ""
    part_of_speech: str = ""
    phonetic_ipa: str = ""
    audio_filename: str = ""
    image_filename: str = ""
    synonyms: str = ""              # comma-separated synonyms from API
    example: str = ""               # example sentence from API


# ---------------------------------------------------------------------------
# Helpers – locate the Kindle
# ---------------------------------------------------------------------------

def _get_config() -> dict:
    """Return the add-on's config dict, falling back to local config.json if needed."""
    cfg: dict = {}
    try:
        if mw and hasattr(mw, "addonManager"):
            cfg = mw.addonManager.getConfig(__name__.split(".")[0]) or {}
    except Exception:
        pass

    if not cfg:
        try:
            import json
            cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
            if os.path.isfile(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as fh:
                    cfg = json.load(fh)
        except Exception:
            pass

    return cfg


def _write_config(cfg: dict) -> None:
    """Persist updated config back through Anki's add-on manager."""
    mw.addonManager.writeConfig(__name__.split(".")[0], cfg)


def find_vocab_db() -> Optional[str]:
    """Locate the Kindle vocab.db on typical Linux mount points.

    Searches across /run/media, /media, /mnt and configured kindle_mount_base.
    """
    cfg = _get_config()
    base = cfg.get("kindle_mount_base", "/run/media")
    rel = cfg.get("vocab_db_relative_path", "system/vocabulary/vocab.db")
    print(f"[AnkReader] find_vocab_db: searching relative path '{rel}'")

    # Check candidate mount bases
    bases = [base, "/run/media", "/media", "/mnt"]
    seen = set()
    unique_bases = []
    for b in bases:
        if b and b not in seen and os.path.isdir(b):
            seen.add(b)
            unique_bases.append(b)

    for search_base in unique_bases:
        pattern = os.path.join(search_base, "**", rel)
        print(f"[AnkReader] find_vocab_db: globbing '{pattern}'")
        try:
            matches = glob.glob(pattern, recursive=True)
            if matches:
                print(f"[AnkReader] find_vocab_db: found Kindle DB at '{matches[0]}'")
                return matches[0]
        except Exception as exc:
            print(f"[AnkReader] find_vocab_db error scanning '{search_base}': {exc}")

    print("[AnkReader] find_vocab_db: Kindle vocab.db NOT found on any mount point")
    return None


# ---------------------------------------------------------------------------
# Core query
# ---------------------------------------------------------------------------

_QUERY = """
SELECT
    w.word,
    b.title,
    l.usage,
    l.timestamp
FROM
    LOOKUPS  AS l
    JOIN WORDS     AS w ON l.word_key  = w.id
    JOIN BOOK_INFO AS b ON l.book_key  = b.id
WHERE
    l.timestamp > ?
    AND (w.lang LIKE 'en%' OR (w.lang IS NULL AND b.lang LIKE 'en%'))
    AND (b.lang NOT LIKE 'es%' OR b.lang IS NULL)
ORDER BY
    l.timestamp ASC;
"""


def fetch_new_entries(db_path: str, since_timestamp: int) -> List[VocabEntry]:
    """Read new vocabulary look-ups from *db_path* after *since_timestamp*.

    Parameters
    ----------
    db_path:
        Absolute path to the Kindle ``vocab.db`` file.
    since_timestamp:
        Epoch-millisecond value; only rows with ``l.timestamp > since_timestamp``
        are returned.

    Returns
    -------
    list[VocabEntry]
        One entry per look-up, sorted chronologically.
    """
    entries: List[VocabEntry] = []
    print(f"[AnkReader] fetch_new_entries: opening '{db_path}' (since_ts={since_timestamp})")

    # Open read-only — never modify the Kindle's database.
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        print("[AnkReader] fetch_new_entries: connection opened OK")
    except sqlite3.OperationalError as exc:
        print(f"[AnkReader] fetch_new_entries: failed to open DB: {exc}")
        showWarning(
            f"AnkReader: could not open vocab.db.\n\n{exc}",
            title="AnkReader – Kindle sync error",
        )
        return entries

    try:
        cursor = conn.execute(_QUERY, (since_timestamp,))
        for row in cursor:
            entries.append(
                VocabEntry(
                    word=row["word"],
                    book_title=row["title"],
                    usage=row["usage"],
                    timestamp=row["timestamp"],
                )
            )
        print(f"[AnkReader] fetch_new_entries: fetched {len(entries)} new entries")
        for e in entries:
            print(f"  -> '{e.word}' in '{e.book_title}' (ts={e.timestamp})")
    except sqlite3.OperationalError as exc:
        print(f"[AnkReader] fetch_new_entries: SQL error: {exc}")
        showWarning(
            f"AnkReader: failed to query vocab.db.\n\n{exc}",
            title="AnkReader – Kindle sync error",
        )
    finally:
        conn.close()
        print("[AnkReader] fetch_new_entries: connection closed")

    return entries


def update_last_sync(new_ts: int) -> None:
    """Persist *new_ts* as the ``last_sync_timestamp`` in config.json."""
    cfg = _get_config()
    cfg["last_sync_timestamp"] = new_ts
    _write_config(cfg)
