"""
Database module for prompt session storage.

Uses SQLite for local-only storage with proper security defaults.
"""

import sqlite3
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Default database location
DEFAULT_DB_PATH = Path.home() / ".prompt-session-capture" / "sessions.db"


def get_db_path() -> Path:
    """Get database path from environment or default."""
    env_path = os.environ.get("PSC_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


class Database:
    """SQLite database for prompt sessions."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize database connection.

        Args:
            db_path: Path to database file (uses default if not specified)
        """
        self.db_path = db_path or get_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Set secure file permissions (owner read/write only)
        if not self.db_path.exists():
            self.db_path.touch(mode=0o600)
        else:
            os.chmod(self.db_path, 0o600)

        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema."""
        cursor = self.conn.cursor()

        # Schema version tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Check current version
        cursor.execute("SELECT MAX(version) FROM schema_version")
        current = cursor.fetchone()[0] or 0

        if current < 1:
            self._apply_v1_schema(cursor)
            cursor.execute("INSERT INTO schema_version (version) VALUES (1)")

        self.conn.commit()

    def _apply_v1_schema(self, cursor):
        """Apply version 1 schema."""
        # Prompts table - stores individual prompts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                timestamp_iso DATETIME NOT NULL,
                session_id TEXT NOT NULL,
                project TEXT,
                content TEXT NOT NULL,
                content_hash TEXT,
                has_pasted_content BOOLEAN DEFAULT FALSE,

                UNIQUE(session_id, timestamp)
            )
        """)

        # Session summaries table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL UNIQUE,
                session_date DATE NOT NULL,
                project TEXT,
                prompt_count INTEGER DEFAULT 0,
                first_prompt_time DATETIME,
                last_prompt_time DATETIME,
                duration_minutes INTEGER,
                summary TEXT,
                workflow_type TEXT,
                key_topics TEXT,
                generated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Daily summaries table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                summary_date DATE NOT NULL UNIQUE,
                session_count INTEGER DEFAULT 0,
                total_prompts INTEGER DEFAULT 0,
                projects TEXT,
                summary TEXT,
                generated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_prompts_session ON prompts(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_prompts_timestamp ON prompts(timestamp DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_prompts_project ON prompts(project)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_prompts_date ON prompts(DATE(timestamp_iso))")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_summaries_date ON session_summaries(session_date DESC)")

    def insert_prompt(
        self,
        timestamp: int,
        session_id: str,
        content: str,
        project: Optional[str] = None,
        has_pasted: bool = False
    ) -> bool:
        """
        Insert a prompt into the database.

        Args:
            timestamp: Unix timestamp in milliseconds
            session_id: Session identifier
            content: Sanitized prompt content
            project: Project name/path
            has_pasted: Whether prompt included pasted content

        Returns:
            True if inserted, False if duplicate
        """
        cursor = self.conn.cursor()

        try:
            timestamp_iso = datetime.fromtimestamp(timestamp / 1000).isoformat()
        except (ValueError, OSError):
            timestamp_iso = datetime.now().isoformat()

        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        try:
            cursor.execute("""
                INSERT INTO prompts
                (timestamp, timestamp_iso, session_id, project, content, content_hash, has_pasted_content)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (timestamp, timestamp_iso, session_id, project, content, content_hash, has_pasted))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Duplicate

    def get_prompts_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all prompts for a session."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM prompts
            WHERE session_id = ?
            ORDER BY timestamp ASC
        """, (session_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_prompts_by_date(self, date: str) -> List[Dict[str, Any]]:
        """Get all prompts for a date (YYYY-MM-DD)."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM prompts
            WHERE DATE(timestamp_iso) = ?
            ORDER BY timestamp ASC
        """, (date,))
        return [dict(row) for row in cursor.fetchall()]

    def get_sessions_for_date(self, date: str) -> List[Dict[str, Any]]:
        """Get unique sessions for a date with metadata."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                session_id,
                project,
                COUNT(*) as prompt_count,
                MIN(timestamp_iso) as first_prompt,
                MAX(timestamp_iso) as last_prompt
            FROM prompts
            WHERE DATE(timestamp_iso) = ?
            GROUP BY session_id
            ORDER BY MIN(timestamp) ASC
        """, (date,))
        return [dict(row) for row in cursor.fetchall()]

    def get_last_sync_timestamp(self) -> int:
        """Get the timestamp of the most recent synced prompt."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT MAX(timestamp) FROM prompts")
        result = cursor.fetchone()[0]
        return result or 0

    def insert_session_summary(self, summary: Dict[str, Any]) -> bool:
        """Insert or update a session summary."""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO session_summaries
                (session_id, session_date, project, prompt_count, first_prompt_time,
                 last_prompt_time, duration_minutes, summary, workflow_type, key_topics)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                summary["session_id"],
                summary["session_date"],
                summary.get("project"),
                summary.get("prompt_count", 0),
                summary.get("first_prompt_time"),
                summary.get("last_prompt_time"),
                summary.get("duration_minutes", 0),
                summary.get("summary"),
                summary.get("workflow_type"),
                summary.get("key_topics")
            ))
            self.conn.commit()
            return True
        except Exception:
            return False

    def get_recent_summaries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent session summaries."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM session_summaries
            ORDER BY session_date DESC, first_prompt_time DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict[str, Any]:
        """Get overall statistics."""
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM prompts")
        total_prompts = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT session_id) FROM prompts")
        total_sessions = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT project) FROM prompts WHERE project IS NOT NULL")
        total_projects = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM session_summaries")
        total_summaries = cursor.fetchone()[0]

        cursor.execute("SELECT MIN(timestamp_iso), MAX(timestamp_iso) FROM prompts")
        date_range = cursor.fetchone()

        return {
            "total_prompts": total_prompts,
            "total_sessions": total_sessions,
            "total_projects": total_projects,
            "total_summaries": total_summaries,
            "first_prompt": date_range[0],
            "last_prompt": date_range[1],
        }

    def search_prompts(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search prompts by content."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM prompts
            WHERE content LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (f"%{query}%", limit))
        return [dict(row) for row in cursor.fetchall()]

    def close(self):
        """Close database connection."""
        self.conn.close()
