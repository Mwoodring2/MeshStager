"""Atomic completed generations, separate from user-owned Tags/Collections."""
from __future__ import annotations
from contextlib import closing
from pathlib import Path
import json
import logging
import sqlite3
import time
import uuid
from meshcorral.app.config import USER_DATA_DIR
from .models import Finding, Snapshot, LABELS, checkpoint, path_key

log = logging.getLogger(__name__)
DEFAULT_DB_PATH = USER_DATA_DIR / "cache" / "asset_housekeeping.sqlite"
SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(root TEXT PRIMARY KEY, generation TEXT NOT NULL, completed REAL NOT NULL, asset_count INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS findings(root TEXT NOT NULL, finding_id TEXT NOT NULL, path TEXT NOT NULL, kind TEXT NOT NULL, severity TEXT NOT NULL, group_id TEXT NOT NULL, identity TEXT NOT NULL, details TEXT NOT NULL, generation TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, PRIMARY KEY(root,finding_id));
CREATE INDEX IF NOT EXISTS findings_path ON findings(root,path);
CREATE INDEX IF NOT EXISTS findings_group ON findings(root,group_id);
CREATE TABLE IF NOT EXISTS suppressions(root TEXT NOT NULL, finding_id TEXT NOT NULL, identity TEXT NOT NULL, ignored_at REAL NOT NULL, PRIMARY KEY(root,finding_id,identity));
PRAGMA user_version=1;
"""

class HousekeepingRepository:
    """Each operation owns a short-lived connection, usable from analysis workers."""
    def __init__(self, db_path=None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.executescript(SCHEMA)

    def publish(self, root, findings, asset_count, canceled=lambda: False):
        root = path_key(root)
        generation, now = uuid.uuid4().hex, time.time()
        checkpoint(canceled)
        rows = [(root, f.finding_id, f.path, f.kind, f.severity, f.group_id, f.identity,
                 json.dumps(f.details, ensure_ascii=True), generation, now, now) for f in findings]
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute("DELETE FROM findings WHERE root=?", (root,))
            conn.executemany("INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
            conn.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?)", (root, generation, now, asset_count))
            checkpoint(canceled)  # exception rolls back rows AND completed generation
        return generation

    def load(self, root):
        root = path_key(root)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""SELECT r.generation AS run_generation,f.*,
                (s.finding_id IS NOT NULL) AS ignored FROM runs r
                LEFT JOIN findings f ON f.root=r.root AND f.generation=r.generation
                LEFT JOIN suppressions s ON s.root=f.root AND s.finding_id=f.finding_id AND s.identity=f.identity
                WHERE r.root=? ORDER BY f.kind,f.path,f.finding_id""", (root,)).fetchall()
        if not rows:
            return Snapshot()
        findings = []
        bad = 0
        for row in rows:
            if row["finding_id"] is None:
                continue
            try:
                details = json.loads(row["details"])
                if row["kind"] not in LABELS or not isinstance(details, dict) or not isinstance(row["path"], str) or "\0" in row["path"]:
                    raise ValueError("invalid finding")
                findings.append(Finding(row["finding_id"], row["path"], row["kind"], row["severity"],
                                        row["group_id"], row["identity"], details, bool(row["ignored"])))
            except (ValueError, TypeError):
                bad += 1
        if bad:
            log.info("Housekeeping ignored %d malformed cache rows", bad)
        return Snapshot(rows[0]["run_generation"], tuple(findings))

    def ignore(self, root, findings):
        additions = [(path_key(root), f.finding_id, f.identity, time.time()) for f in findings if not f.ignored]
        removals = [(path_key(root), f.finding_id, f.identity) for f in findings if f.ignored]
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.executemany("INSERT OR REPLACE INTO suppressions VALUES (?,?,?,?)", additions)
            conn.executemany("DELETE FROM suppressions WHERE root=? AND finding_id=? AND identity=?", removals)

    def close(self):
        """No persistent connections to close."""
