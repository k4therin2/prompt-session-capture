# prompt-session-capture

Lightweight tool for capturing and analyzing AI coding assistant sessions. Learn from your workflow patterns.

## What it does

- Captures prompts from Claude Code sessions (reads native `~/.claude/history.jsonl`)
- Generates session summaries with workflow type detection
- Stores everything locally in SQLite
- Privacy-first: sanitizes PII, IPs, and file paths before storage

## Quick Start

```bash
# Install
pip install -e .

# Sync prompts from Claude Code history
psc sync

# Generate summaries for yesterday's sessions
psc summarize

# View recent sessions
psc recent

# Show stats
psc stats
```

## Privacy & Security

This tool is designed with privacy from day one:

- **Local only**: All data stays on your machine in SQLite
- **PII sanitization**: Email addresses, IPs, API keys are redacted before storage
- **Path anonymization**: Absolute paths are converted to relative/generic forms
- **No telemetry**: Zero data sent anywhere

See [SECURITY.md](SECURITY.md) for details.

## Use Cases

- **Workflow replay**: "How did I approach X last time?"
- **Pattern detection**: Identify your common debugging/development patterns
- **Session metrics**: Track coding session duration and focus areas

## Configuration

```bash
# Set custom history file location
export PSC_HISTORY_FILE=~/.claude/history.jsonl

# Set database location
export PSC_DB_PATH=~/.prompt-session-capture/sessions.db
```

## Git Hooks

Security pre-push hook prevents accidentally pushing secrets:

```bash
cp hooks/pre-push .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

Blocks pushes containing:
- API keys, AWS credentials, private keys
- Database files
- Hardcoded home directory paths

## License

MIT
