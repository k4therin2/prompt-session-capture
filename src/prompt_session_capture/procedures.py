"""
Procedural Memory Module

Stores and retrieves reusable procedures (workflows) learned from past sessions.
Based on LEGOMem and A-MEM concepts from 2025 research.

Terminology:
- Procedure: A named, reusable approach to a task (e.g., "security-review")
- Execution: Each time a procedure was run, with context and outcome
- Preference: User patterns extracted from multiple executions
"""

import json
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from .database import Database


class ProcedureMemory:
    """
    Manages procedural memory for workflow capture.

    Supports:
    - Storing named procedures with steps
    - Recording executions with context
    - Checking if procedures need updates
    - Extracting preferences from patterns
    """

    def __init__(self, db: Optional[Database] = None):
        """Initialize with database connection."""
        self.db = db or Database()
        self._ensure_schema()

    def _ensure_schema(self):
        """Ensure procedure tables exist."""
        cursor = self.db.conn.cursor()

        # Procedures table - named reusable workflows
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS procedures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,

                -- The procedure definition
                steps TEXT NOT NULL,  -- JSON array of step descriptions
                context_requirements TEXT,  -- JSON: when to use this procedure

                -- Metadata
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                derived_from_sessions TEXT,  -- JSON array of session_ids
                execution_count INTEGER DEFAULT 0,
                last_executed_at DATETIME,

                -- Status
                status TEXT DEFAULT 'active' CHECK(status IN ('active', 'deprecated', 'draft'))
            )
        """)

        # Executions table - each time a procedure ran
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                procedure_id INTEGER NOT NULL,
                session_id TEXT,  -- Links to the session where this ran

                -- Context at execution time
                project TEXT,
                trigger_prompt TEXT,  -- What the user said to trigger this
                context_notes TEXT,  -- Any relevant context

                -- What happened
                approach_taken TEXT,  -- JSON: actual steps taken (may differ from procedure)
                reasoning TEXT,  -- Why this approach was chosen
                outcome TEXT CHECK(outcome IN ('success', 'partial', 'failed', 'abandoned')),
                outcome_notes TEXT,

                -- Timing
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME,
                duration_minutes INTEGER,

                -- Feedback
                user_feedback TEXT,  -- Any explicit feedback
                suggested_updates TEXT,  -- JSON: proposed changes to procedure

                FOREIGN KEY (procedure_id) REFERENCES procedures(id)
            )
        """)

        # Preferences table - patterns extracted from executions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,  -- e.g., "security-review", "blog-post", "general"
                preference_key TEXT NOT NULL,
                preference_value TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,  -- 0-1, how confident we are

                -- Evidence
                derived_from_executions TEXT,  -- JSON array of execution_ids
                observation_count INTEGER DEFAULT 1,

                -- Metadata
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                UNIQUE(category, preference_key)
            )
        """)

        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_procedures_name ON procedures(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_procedure ON executions(procedure_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_session ON executions(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_preferences_category ON preferences(category)")

        self.db.conn.commit()

    # ========== Procedure CRUD ==========

    def create_procedure(
        self,
        name: str,
        steps: List[str],
        description: str = "",
        context_requirements: Dict[str, Any] = None,
        derived_from_sessions: List[str] = None
    ) -> int:
        """
        Create a new procedure.

        Args:
            name: Unique procedure name (e.g., "security-review")
            steps: List of step descriptions
            description: What this procedure does
            context_requirements: When to use this (project type, etc.)
            derived_from_sessions: Session IDs this was learned from

        Returns:
            Procedure ID
        """
        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT INTO procedures
            (name, description, steps, context_requirements, derived_from_sessions)
            VALUES (?, ?, ?, ?, ?)
        """, (
            name,
            description,
            json.dumps(steps),
            json.dumps(context_requirements or {}),
            json.dumps(derived_from_sessions or [])
        ))
        self.db.conn.commit()
        return cursor.lastrowid

    def get_procedure(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a procedure by name."""
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT * FROM procedures WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            return self._row_to_procedure(row)
        return None

    def list_procedures(self, status: str = "active") -> List[Dict[str, Any]]:
        """List all procedures with given status."""
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT * FROM procedures
            WHERE status = ?
            ORDER BY last_executed_at DESC NULLS LAST
        """, (status,))
        return [self._row_to_procedure(row) for row in cursor.fetchall()]

    def update_procedure(
        self,
        name: str,
        steps: Optional[List[str]] = None,
        description: Optional[str] = None,
        context_requirements: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update an existing procedure."""
        procedure = self.get_procedure(name)
        if not procedure:
            return False

        cursor = self.db.conn.cursor()
        updates = ["updated_at = CURRENT_TIMESTAMP"]
        params = []

        if steps is not None:
            updates.append("steps = ?")
            params.append(json.dumps(steps))
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if context_requirements is not None:
            updates.append("context_requirements = ?")
            params.append(json.dumps(context_requirements))

        params.append(name)
        cursor.execute(f"""
            UPDATE procedures SET {', '.join(updates)}
            WHERE name = ?
        """, params)
        self.db.conn.commit()
        return True

    def _row_to_procedure(self, row) -> Dict[str, Any]:
        """Convert database row to procedure dict."""
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "steps": json.loads(row["steps"]),
            "context_requirements": json.loads(row["context_requirements"] or "{}"),
            "derived_from_sessions": json.loads(row["derived_from_sessions"] or "[]"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "execution_count": row["execution_count"],
            "last_executed_at": row["last_executed_at"],
            "status": row["status"],
        }

    # ========== Execution Recording ==========

    def start_execution(
        self,
        procedure_name: str,
        trigger_prompt: str,
        project: str = None,
        session_id: str = None,
        context_notes: str = None
    ) -> Optional[int]:
        """
        Record the start of a procedure execution.

        Returns execution ID, or None if procedure not found.
        """
        procedure = self.get_procedure(procedure_name)
        if not procedure:
            return None

        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT INTO executions
            (procedure_id, session_id, project, trigger_prompt, context_notes)
            VALUES (?, ?, ?, ?, ?)
        """, (procedure["id"], session_id, project, trigger_prompt, context_notes))

        # Update procedure stats
        cursor.execute("""
            UPDATE procedures
            SET execution_count = execution_count + 1,
                last_executed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (procedure["id"],))

        self.db.conn.commit()
        return cursor.lastrowid

    def complete_execution(
        self,
        execution_id: int,
        approach_taken: List[str],
        reasoning: str,
        outcome: str,
        outcome_notes: str = None,
        suggested_updates: List[str] = None
    ) -> bool:
        """Record completion of an execution."""
        cursor = self.db.conn.cursor()

        # Calculate duration
        cursor.execute("SELECT started_at FROM executions WHERE id = ?", (execution_id,))
        row = cursor.fetchone()
        if not row:
            return False

        started = datetime.fromisoformat(row["started_at"])
        duration = int((datetime.now() - started).total_seconds() / 60)

        cursor.execute("""
            UPDATE executions SET
                approach_taken = ?,
                reasoning = ?,
                outcome = ?,
                outcome_notes = ?,
                suggested_updates = ?,
                completed_at = CURRENT_TIMESTAMP,
                duration_minutes = ?
            WHERE id = ?
        """, (
            json.dumps(approach_taken),
            reasoning,
            outcome,
            outcome_notes,
            json.dumps(suggested_updates or []),
            duration,
            execution_id
        ))
        self.db.conn.commit()
        return True

    def get_recent_executions(
        self,
        procedure_name: str = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent executions, optionally filtered by procedure."""
        cursor = self.db.conn.cursor()

        if procedure_name:
            procedure = self.get_procedure(procedure_name)
            if not procedure:
                return []
            cursor.execute("""
                SELECT e.*, p.name as procedure_name
                FROM executions e
                JOIN procedures p ON e.procedure_id = p.id
                WHERE e.procedure_id = ?
                ORDER BY e.started_at DESC
                LIMIT ?
            """, (procedure["id"], limit))
        else:
            cursor.execute("""
                SELECT e.*, p.name as procedure_name
                FROM executions e
                JOIN procedures p ON e.procedure_id = p.id
                ORDER BY e.started_at DESC
                LIMIT ?
            """, (limit,))

        return [self._row_to_execution(row) for row in cursor.fetchall()]

    def _row_to_execution(self, row) -> Dict[str, Any]:
        """Convert database row to execution dict."""
        return {
            "id": row["id"],
            "procedure_name": row["procedure_name"],
            "session_id": row["session_id"],
            "project": row["project"],
            "trigger_prompt": row["trigger_prompt"],
            "context_notes": row["context_notes"],
            "approach_taken": json.loads(row["approach_taken"] or "[]"),
            "reasoning": row["reasoning"],
            "outcome": row["outcome"],
            "outcome_notes": row["outcome_notes"],
            "suggested_updates": json.loads(row["suggested_updates"] or "[]"),
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "duration_minutes": row["duration_minutes"],
        }

    # ========== Procedure Matching & Updates ==========

    def find_matching_procedure(self, prompt: str, project: str = None) -> Optional[Dict[str, Any]]:
        """
        Find a procedure that matches the given prompt.

        Simple keyword matching for now - can be enhanced with embeddings later.
        """
        procedures = self.list_procedures()

        for proc in procedures:
            # Check if procedure name appears in prompt
            if proc["name"].lower().replace("-", " ") in prompt.lower():
                return proc

            # Check keywords from description
            if proc["description"]:
                keywords = proc["description"].lower().split()
                matches = sum(1 for kw in keywords if kw in prompt.lower() and len(kw) > 4)
                if matches >= 2:
                    return proc

        return None

    def check_for_updates_needed(
        self,
        procedure_name: str,
        current_project: str = None
    ) -> Dict[str, Any]:
        """
        Check if a procedure needs updates based on recent activity.

        Returns:
            Dict with:
            - needs_update: bool
            - reason: str
            - related_sessions: list of session_ids since last execution
            - suggested_changes: list of suggestions from past executions
        """
        procedure = self.get_procedure(procedure_name)
        if not procedure:
            return {"needs_update": False, "reason": "Procedure not found"}

        cursor = self.db.conn.cursor()

        # Find sessions since last execution
        last_exec = procedure["last_executed_at"] or procedure["created_at"]
        cursor.execute("""
            SELECT DISTINCT session_id, project, COUNT(*) as prompt_count
            FROM prompts
            WHERE timestamp_iso > ?
            AND content LIKE ?
            GROUP BY session_id
        """, (last_exec, f"%{procedure_name.replace('-', '%')}%"))

        related_sessions = [
            {"session_id": r["session_id"], "project": r["project"], "prompts": r["prompt_count"]}
            for r in cursor.fetchall()
        ]

        # Get suggested updates from past executions
        cursor.execute("""
            SELECT suggested_updates FROM executions
            WHERE procedure_id = ? AND suggested_updates IS NOT NULL AND suggested_updates != '[]'
            ORDER BY completed_at DESC
            LIMIT 5
        """, (procedure["id"],))

        all_suggestions = []
        for row in cursor.fetchall():
            all_suggestions.extend(json.loads(row["suggested_updates"]))

        # Determine if update needed
        needs_update = len(related_sessions) > 0 or len(all_suggestions) > 0
        reason = ""
        if related_sessions:
            reason += f"{len(related_sessions)} related sessions since last run. "
        if all_suggestions:
            reason += f"{len(all_suggestions)} suggested improvements pending."

        return {
            "needs_update": needs_update,
            "reason": reason.strip() or "No updates needed",
            "related_sessions": related_sessions,
            "suggested_changes": list(set(all_suggestions)),  # Dedupe
            "last_executed": procedure["last_executed_at"],
            "execution_count": procedure["execution_count"],
        }

    # ========== Preferences ==========

    def set_preference(
        self,
        category: str,
        key: str,
        value: str,
        confidence: float = 0.5,
        from_execution_id: int = None
    ):
        """Set or update a preference."""
        cursor = self.db.conn.cursor()

        # Check if exists
        cursor.execute("""
            SELECT id, derived_from_executions, observation_count
            FROM preferences
            WHERE category = ? AND preference_key = ?
        """, (category, key))
        existing = cursor.fetchone()

        if existing:
            # Update existing
            executions = json.loads(existing["derived_from_executions"] or "[]")
            if from_execution_id and from_execution_id not in executions:
                executions.append(from_execution_id)

            cursor.execute("""
                UPDATE preferences SET
                    preference_value = ?,
                    confidence = ?,
                    derived_from_executions = ?,
                    observation_count = observation_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (value, confidence, json.dumps(executions), existing["id"]))
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO preferences
                (category, preference_key, preference_value, confidence, derived_from_executions)
                VALUES (?, ?, ?, ?, ?)
            """, (
                category, key, value, confidence,
                json.dumps([from_execution_id] if from_execution_id else [])
            ))

        self.db.conn.commit()

    def get_preferences(self, category: str = None) -> List[Dict[str, Any]]:
        """Get preferences, optionally filtered by category."""
        cursor = self.db.conn.cursor()

        if category:
            cursor.execute("""
                SELECT * FROM preferences
                WHERE category = ?
                ORDER BY confidence DESC
            """, (category,))
        else:
            cursor.execute("SELECT * FROM preferences ORDER BY category, confidence DESC")

        return [dict(row) for row in cursor.fetchall()]

    def close(self):
        """Close database connection."""
        self.db.close()
