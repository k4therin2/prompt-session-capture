"""
prompt-session-capture: Capture and analyze AI coding assistant sessions.

Terminology (based on 2025 research):
- Procedure: Named reusable workflow (procedural memory)
- Execution: Each time a procedure ran (episodic memory)
- Preference: Learned user patterns (user profile)
"""

from .capture import Capture
from .database import Database
from .sanitizer import Sanitizer, sanitize
from .procedures import ProcedureMemory

__version__ = "0.1.0"
__all__ = ["Capture", "Database", "Sanitizer", "sanitize", "ProcedureMemory"]
