"""
Command-line interface for prompt-session-capture.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta

from .capture import Capture
from .database import Database
from .procedures import ProcedureMemory


def cmd_sync(args):
    """Sync prompts from history file."""
    capture = Capture()
    print("Syncing prompts from Claude Code history...")

    stats = capture.sync()

    if "error" in stats:
        print(f"Error: {stats['error']}")
        return 1

    print(f"Read {stats['total_read']} entries")
    print(f"  New: {stats['new_inserted']}")
    print(f"  Duplicates: {stats['duplicates_skipped']}")
    print(f"  Empty: {stats['empty_skipped']}")
    print(f"  Sessions: {stats['unique_sessions']}")
    print(f"  Projects: {stats['unique_projects']}")

    capture.close()
    return 0


def cmd_summarize(args):
    """Generate session summaries."""
    capture = Capture()

    date = args.date
    if date is None:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"Generating summaries for {date}...")

    stats = capture.summarize_date(date)

    print(f"Found {stats['sessions_found']} sessions")
    print(f"Generated {stats['summaries_generated']} summaries")

    capture.close()
    return 0


def cmd_recent(args):
    """Show recent session summaries."""
    db = Database()
    summaries = db.get_recent_summaries(limit=args.limit)

    if not summaries:
        print("No summaries found. Run 'sync' and 'summarize' first.")
        db.close()
        return 0

    current_date = None
    for s in summaries:
        if s["session_date"] != current_date:
            current_date = s["session_date"]
            print(f"\n## {current_date}")
            print("-" * 40)

        duration = s["duration_minutes"] or 0
        project = s["project"] or "unknown"
        workflow = s["workflow_type"] or "general"

        print(f"  [{project}] {workflow} - {s['prompt_count']} prompts, {duration}min")
        if s["summary"]:
            print(f"    {s['summary'][:100]}...")
        print()

    db.close()
    return 0


def cmd_stats(args):
    """Show overall statistics."""
    db = Database()
    stats = db.get_stats()

    print("\n## Prompt Session Capture Statistics")
    print("-" * 40)
    print(f"Total prompts: {stats['total_prompts']}")
    print(f"Unique sessions: {stats['total_sessions']}")
    print(f"Projects: {stats['total_projects']}")
    print(f"Session summaries: {stats['total_summaries']}")

    if stats["first_prompt"]:
        first = stats["first_prompt"][:10]
        last = stats["last_prompt"][:10]
        print(f"Date range: {first} to {last}")

    db.close()
    return 0


def cmd_search(args):
    """Search prompts by content."""
    db = Database()
    results = db.search_prompts(args.query, limit=args.limit)

    if not results:
        print(f"No prompts matching '{args.query}'")
        db.close()
        return 0

    print(f"Found {len(results)} matching prompts:\n")

    for r in results:
        ts = r["timestamp_iso"][:16]
        project = r["project"] or "unknown"
        content = r["content"][:100]
        print(f"[{ts}] ({project})")
        print(f"  {content}...")
        print()

    db.close()
    return 0


def cmd_daily(args):
    """Run full daily sync and summarize."""
    capture = Capture()

    # Sync
    print("Step 1: Syncing prompts...")
    sync_stats = capture.sync()
    if "error" not in sync_stats:
        print(f"  Synced {sync_stats['new_inserted']} new prompts")

    # Summarize
    date = args.date
    if date is None:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"\nStep 2: Generating summaries for {date}...")
    sum_stats = capture.summarize_date(date)
    print(f"  Generated {sum_stats['summaries_generated']} summaries")

    # Stats
    print("\nStep 3: Current stats...")
    db_stats = capture.db.get_stats()
    print(f"  Total prompts: {db_stats['total_prompts']}")
    print(f"  Total sessions: {db_stats['total_sessions']}")

    capture.close()
    return 0


# ========== Procedure Commands ==========

def cmd_proc_list(args):
    """List all procedures."""
    pm = ProcedureMemory()
    procedures = pm.list_procedures(status=args.status)

    if not procedures:
        print(f"No {args.status} procedures found.")
        pm.close()
        return 0

    print(f"\n## {args.status.title()} Procedures")
    print("-" * 50)

    for proc in procedures:
        exec_count = proc["execution_count"]
        last_exec = proc["last_executed_at"] or "never"
        if last_exec != "never":
            last_exec = last_exec[:10]

        print(f"\n  {proc['name']}")
        print(f"    {proc['description'][:60]}..." if len(proc.get('description', '') or '') > 60 else f"    {proc.get('description', 'No description')}")
        print(f"    Executions: {exec_count} | Last: {last_exec}")
        print(f"    Steps: {len(proc['steps'])}")

    pm.close()
    return 0


def cmd_proc_show(args):
    """Show details of a procedure."""
    pm = ProcedureMemory()
    proc = pm.get_procedure(args.name)

    if not proc:
        print(f"Procedure '{args.name}' not found.")
        pm.close()
        return 1

    print(f"\n## Procedure: {proc['name']}")
    print("-" * 50)
    print(f"Description: {proc['description']}")
    print(f"Status: {proc['status']}")
    print(f"Executions: {proc['execution_count']}")
    print(f"Last executed: {proc['last_executed_at'] or 'never'}")
    print(f"Created: {proc['created_at'][:10]}")
    print(f"Updated: {proc['updated_at'][:10]}")

    print("\n### Steps:")
    for i, step in enumerate(proc['steps'], 1):
        print(f"  {i}. {step}")

    if proc['context_requirements']:
        print("\n### Context Requirements:")
        for key, value in proc['context_requirements'].items():
            print(f"  - {key}: {value}")

    # Check for updates
    update_check = pm.check_for_updates_needed(args.name)
    if update_check["needs_update"]:
        print(f"\n### Updates Suggested:")
        print(f"  {update_check['reason']}")
        if update_check["suggested_changes"]:
            for change in update_check["suggested_changes"][:5]:
                print(f"  - {change}")

    pm.close()
    return 0


def cmd_proc_create(args):
    """Create a new procedure."""
    pm = ProcedureMemory()

    # Parse steps from JSON or comma-separated
    if args.steps.startswith('['):
        steps = json.loads(args.steps)
    else:
        steps = [s.strip() for s in args.steps.split(',')]

    proc_id = pm.create_procedure(
        name=args.name,
        steps=steps,
        description=args.description or "",
    )

    print(f"Created procedure '{args.name}' (id: {proc_id})")
    print(f"Steps: {len(steps)}")

    pm.close()
    return 0


def cmd_proc_run(args):
    """Find and optionally run a procedure matching a prompt."""
    pm = ProcedureMemory()

    # Find matching procedure
    proc = pm.find_matching_procedure(args.prompt, project=args.project)

    if not proc:
        print(f"No procedure found matching: {args.prompt}")
        print("\nAvailable procedures:")
        for p in pm.list_procedures():
            print(f"  - {p['name']}: {p['description'][:50]}...")
        pm.close()
        return 1

    print(f"\n## Matched Procedure: {proc['name']}")
    print(f"Description: {proc['description']}")

    # Check for updates
    update_check = pm.check_for_updates_needed(proc['name'])
    print(f"\n### Update Check:")
    if update_check["needs_update"]:
        print(f"  ⚠ {update_check['reason']}")
        if update_check["related_sessions"]:
            print(f"  Related sessions: {len(update_check['related_sessions'])}")
    else:
        print(f"  ✓ No updates needed. Last run: {update_check['last_executed'] or 'never'}")

    print(f"\n### Steps to Execute:")
    for i, step in enumerate(proc['steps'], 1):
        print(f"  {i}. {step}")

    # If --execute flag, start execution
    if args.execute:
        exec_id = pm.start_execution(
            procedure_name=proc['name'],
            trigger_prompt=args.prompt,
            project=args.project,
        )
        print(f"\n[Execution started: #{exec_id}]")
        print("Run `psc proc complete {exec_id}` when done.")

    pm.close()
    return 0


def cmd_proc_executions(args):
    """Show recent procedure executions."""
    pm = ProcedureMemory()
    executions = pm.get_recent_executions(
        procedure_name=args.procedure,
        limit=args.limit
    )

    if not executions:
        print("No executions found.")
        pm.close()
        return 0

    print("\n## Recent Executions")
    print("-" * 50)

    for ex in executions:
        outcome_emoji = {"success": "✓", "partial": "◐", "failed": "✗", "abandoned": "○"}.get(ex["outcome"], "?")
        print(f"\n  [{ex['started_at'][:10]}] {ex['procedure_name']} {outcome_emoji}")
        print(f"    Trigger: {ex['trigger_prompt'][:50]}...")
        print(f"    Project: {ex['project'] or 'unknown'}")
        if ex['outcome']:
            print(f"    Outcome: {ex['outcome']} ({ex['duration_minutes']}min)")

    pm.close()
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="psc",
        description="Capture and analyze AI coding assistant sessions"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # sync
    sync_parser = subparsers.add_parser("sync", help="Sync prompts from history file")

    # summarize
    summarize_parser = subparsers.add_parser("summarize", help="Generate session summaries")
    summarize_parser.add_argument("--date", help="Date to summarize (YYYY-MM-DD)")

    # recent
    recent_parser = subparsers.add_parser("recent", help="Show recent session summaries")
    recent_parser.add_argument("--limit", type=int, default=30, help="Number of summaries to show")

    # stats
    stats_parser = subparsers.add_parser("stats", help="Show overall statistics")

    # search
    search_parser = subparsers.add_parser("search", help="Search prompts by content")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=20, help="Max results")

    # daily
    daily_parser = subparsers.add_parser("daily", help="Run full daily sync and summarize")
    daily_parser.add_argument("--date", help="Date to process (YYYY-MM-DD)")

    # ========== Procedure commands ==========
    proc_parser = subparsers.add_parser("proc", help="Manage procedures (workflows)")
    proc_subparsers = proc_parser.add_subparsers(dest="proc_command", help="Procedure commands")

    # proc list
    proc_list = proc_subparsers.add_parser("list", help="List all procedures")
    proc_list.add_argument("--status", default="active", choices=["active", "deprecated", "draft"])

    # proc show
    proc_show = proc_subparsers.add_parser("show", help="Show procedure details")
    proc_show.add_argument("name", help="Procedure name")

    # proc create
    proc_create = proc_subparsers.add_parser("create", help="Create a new procedure")
    proc_create.add_argument("name", help="Procedure name (e.g., security-review)")
    proc_create.add_argument("--steps", required=True, help="Steps as JSON array or comma-separated")
    proc_create.add_argument("--description", help="Procedure description")

    # proc run
    proc_run = proc_subparsers.add_parser("run", help="Find and run a matching procedure")
    proc_run.add_argument("prompt", help="The prompt/request to match")
    proc_run.add_argument("--project", help="Current project context")
    proc_run.add_argument("--execute", action="store_true", help="Start execution tracking")

    # proc executions
    proc_execs = proc_subparsers.add_parser("executions", help="Show recent executions")
    proc_execs.add_argument("--procedure", help="Filter by procedure name")
    proc_execs.add_argument("--limit", type=int, default=10, help="Max results")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    # Handle procedure subcommands
    if args.command == "proc":
        if args.proc_command is None:
            proc_parser.print_help()
            return 0
        proc_commands = {
            "list": cmd_proc_list,
            "show": cmd_proc_show,
            "create": cmd_proc_create,
            "run": cmd_proc_run,
            "executions": cmd_proc_executions,
        }
        return proc_commands[args.proc_command](args)

    commands = {
        "sync": cmd_sync,
        "summarize": cmd_summarize,
        "recent": cmd_recent,
        "stats": cmd_stats,
        "search": cmd_search,
        "daily": cmd_daily,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
