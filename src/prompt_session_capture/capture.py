"""
Capture module for reading Claude Code history.

Reads from ~/.claude/history.jsonl and syncs to local database.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Generator
from collections import defaultdict

from .database import Database
from .sanitizer import Sanitizer, default_sanitizer


# Default history file location
DEFAULT_HISTORY_FILE = Path.home() / ".claude" / "history.jsonl"


def get_history_path() -> Path:
    """Get history file path from environment or default."""
    env_path = os.environ.get("PSC_HISTORY_FILE")
    if env_path:
        return Path(env_path)
    return DEFAULT_HISTORY_FILE


def extract_project_name(project_path: str) -> Optional[str]:
    """
    Extract project name from path.

    Converts absolute paths to just the project folder name.
    """
    if not project_path:
        return None

    path = Path(project_path)

    # Look for common project root patterns
    for parent in path.parents:
        if parent.name in ("projects", "code", "repos", "src", "work"):
            # Return the folder after the projects/code/etc folder
            try:
                relative = path.relative_to(parent)
                return str(relative.parts[0]) if relative.parts else path.name
            except ValueError:
                pass

    # Fallback: just use the folder name
    return path.name or None


def read_history(
    history_path: Optional[Path] = None,
    since_timestamp: int = 0
) -> Generator[Dict[str, Any], None, None]:
    """
    Read entries from Claude Code history file.

    Args:
        history_path: Path to history.jsonl (uses default if not specified)
        since_timestamp: Only yield entries after this timestamp

    Yields:
        Dictionary with prompt data
    """
    path = history_path or get_history_path()

    if not path.exists():
        return

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            timestamp = entry.get("timestamp", 0)
            if timestamp <= since_timestamp:
                continue

            yield {
                "timestamp": timestamp,
                "session_id": entry.get("sessionId", ""),
                "project_path": entry.get("project", ""),
                "prompt": entry.get("display", ""),
                "pasted_contents": entry.get("pastedContents", {}),
            }


class Capture:
    """Captures and syncs Claude Code prompts."""

    def __init__(
        self,
        db: Optional[Database] = None,
        sanitizer: Optional[Sanitizer] = None,
        history_path: Optional[Path] = None
    ):
        """
        Initialize capture.

        Args:
            db: Database instance (creates default if not specified)
            sanitizer: Sanitizer instance (uses default if not specified)
            history_path: Path to history file (uses default if not specified)
        """
        self.db = db or Database()
        self.sanitizer = sanitizer or default_sanitizer
        self.history_path = history_path or get_history_path()

    def sync(self) -> Dict[str, Any]:
        """
        Sync prompts from history file to database.

        Returns:
            Statistics about the sync operation
        """
        if not self.history_path.exists():
            return {"error": f"History file not found: {self.history_path}"}

        last_timestamp = self.db.get_last_sync_timestamp()

        stats = {
            "total_read": 0,
            "new_inserted": 0,
            "duplicates_skipped": 0,
            "empty_skipped": 0,
            "sessions": set(),
            "projects": set(),
        }

        for entry in read_history(self.history_path, last_timestamp):
            stats["total_read"] += 1

            prompt = entry["prompt"]
            if not prompt or not prompt.strip():
                stats["empty_skipped"] += 1
                continue

            # Sanitize content before storage
            sanitized_prompt = self.sanitizer.sanitize(prompt)

            # Extract project name (sanitized)
            project = extract_project_name(entry["project_path"])

            # Insert into database
            inserted = self.db.insert_prompt(
                timestamp=entry["timestamp"],
                session_id=entry["session_id"],
                content=sanitized_prompt,
                project=project,
                has_pasted=bool(entry["pasted_contents"])
            )

            if inserted:
                stats["new_inserted"] += 1
                stats["sessions"].add(entry["session_id"])
                if project:
                    stats["projects"].add(project)
            else:
                stats["duplicates_skipped"] += 1

        # Convert sets to counts
        stats["unique_sessions"] = len(stats["sessions"])
        stats["unique_projects"] = len(stats["projects"])
        del stats["sessions"]
        del stats["projects"]

        return stats

    def generate_summary(self, session_id: str, date: str) -> Optional[Dict[str, Any]]:
        """
        Generate a summary for a session.

        Args:
            session_id: Session identifier
            date: Session date (YYYY-MM-DD)

        Returns:
            Summary dictionary or None if no prompts found
        """
        prompts = self.db.get_prompts_by_session(session_id)
        if not prompts:
            return None

        # Calculate duration
        first_time = prompts[0]["timestamp_iso"]
        last_time = prompts[-1]["timestamp_iso"]

        try:
            first_dt = datetime.fromisoformat(first_time)
            last_dt = datetime.fromisoformat(last_time)
            duration_minutes = int((last_dt - first_dt).total_seconds() / 60)
        except ValueError:
            duration_minutes = 0

        # Extract project
        project = prompts[0].get("project")

        # Detect workflow type from keywords
        all_text = " ".join([p["content"].lower() for p in prompts])
        workflow_type = self._detect_workflow_type(all_text)

        # Extract key topics (word frequency)
        key_topics = self._extract_topics(all_text)

        # Build summary text
        summary = (
            f"Session with {len(prompts)} prompts over {duration_minutes} minutes. "
            f"Workflow: {workflow_type}."
        )
        if key_topics:
            summary += f" Topics: {key_topics}."

        return {
            "session_id": session_id,
            "session_date": date,
            "project": project,
            "prompt_count": len(prompts),
            "first_prompt_time": first_time,
            "last_prompt_time": last_time,
            "duration_minutes": duration_minutes,
            "summary": summary,
            "workflow_type": workflow_type,
            "key_topics": key_topics,
        }

    def summarize_date(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate summaries for all sessions on a date.

        Args:
            date: Date string (YYYY-MM-DD) or None for yesterday

        Returns:
            Statistics about summarization
        """
        if date is None:
            date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        sessions = self.db.get_sessions_for_date(date)

        stats = {
            "date": date,
            "sessions_found": len(sessions),
            "summaries_generated": 0,
        }

        for session in sessions:
            session_id = session["session_id"]

            summary = self.generate_summary(session_id, date)
            if summary:
                if self.db.insert_session_summary(summary):
                    stats["summaries_generated"] += 1

        return stats

    def _detect_workflow_type(self, text: str) -> str:
        """Detect workflow type from text content."""
        patterns = {
            "testing": ["test", "tdd", "spec", "assert"],
            "debugging": ["fix", "bug", "error", "issue", "broken"],
            "refactoring": ["refactor", "clean", "reorganize", "restructure"],
            "feature-development": ["add", "implement", "create", "build", "new"],
            "writing": ["write", "blog", "doc", "readme", "article"],
            "exploration": ["search", "find", "where", "look", "explore"],
            "code-review": ["review", "check", "audit", "verify"],
            "configuration": ["config", "setup", "install", "deploy"],
        }

        for workflow, keywords in patterns.items():
            if any(kw in text for kw in keywords):
                return workflow

        return "general"

    def _extract_topics(self, text: str, max_topics: int = 5) -> str:
        """Extract key topics from text."""
        # Common stop words
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "i", "you", "we",
            "it", "to", "and", "or", "for", "in", "on", "at", "this", "that",
            "with", "can", "do", "please", "let", "me", "be", "have", "has",
            "had", "will", "would", "could", "should", "just", "like", "want",
            "need", "make", "get", "see", "know", "think", "look", "use",
        }

        # Extract words
        words = text.lower().split()
        words = [w.strip(".,!?\"'()[]{}") for w in words]
        words = [w for w in words if len(w) > 3 and w not in stop_words and w.isalpha()]

        # Count frequency
        counts = defaultdict(int)
        for word in words:
            counts[word] += 1

        # Get top topics
        top = sorted(counts.items(), key=lambda x: -x[1])[:max_topics]
        return ", ".join([w[0] for w in top])

    def close(self):
        """Close database connection."""
        self.db.close()
