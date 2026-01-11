# Security & Privacy

## Design Principles

1. **Local-first**: All data stored locally, never transmitted
2. **Sanitize at capture**: PII removed before storage, not after
3. **Minimal retention**: Only store what's needed for analysis
4. **No secrets**: Never store API keys, passwords, or tokens

## Sanitization Rules

Before any prompt is stored, the following patterns are redacted:

### Always Redacted

| Pattern | Replacement | Example |
|---------|-------------|---------|
| Email addresses | `[EMAIL]` | `user@example.com` → `[EMAIL]` |
| IP addresses | `[IP]` | `192.168.1.1` → `[IP]` |
| API keys/tokens | `[REDACTED]` | `sk-abc123...` → `[REDACTED]` |
| Bearer tokens | `[REDACTED]` | `Bearer eyJ...` → `[REDACTED]` |
| AWS keys | `[REDACTED]` | `AKIA...` → `[REDACTED]` |
| Private keys | `[REDACTED]` | `-----BEGIN PRIVATE KEY-----` → `[REDACTED]` |

### Path Anonymization

| Original | Sanitized |
|----------|-----------|
| `/home/username/projects/foo` | `~/projects/foo` |
| `/Users/username/code/bar` | `~/code/bar` |
| `C:\Users\username\Documents` | `~\Documents` |

### Optional Redactions

These can be enabled via config:

- Hostnames: `myserver.local` → `[HOST]`
- URLs: Full URLs → domain only
- Custom patterns: Regex-based redaction

## Database Security

- Database file permissions: `600` (owner read/write only)
- No WAL mode by default (single file, easier to secure)
- Content hashes use SHA-256 (truncated, non-reversible)

## What We DON'T Store

- Claude's responses (only your prompts)
- File contents from pasted code blocks
- Environment variables
- Shell command outputs

## Reporting Security Issues

If you find a security issue, please email [TBD] or open a private security advisory on GitHub.
