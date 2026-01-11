"""
Command-line interface for prompt-session-capture.
"""

import argparse
import sys
from datetime import datetime, timedelta

from .capture import Capture
from .database import Database


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

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

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
