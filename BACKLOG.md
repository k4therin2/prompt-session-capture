# Backlog - prompt-session-capture

## Overview

This is the project backlog for prompt-session-capture. Items are prioritized by value and effort.

---

## Phase 1: Core Foundation (Current)

### P1 - Critical

- [x] Basic prompt capture from Claude Code history.jsonl
- [x] SQLite storage with secure defaults (600 permissions)
- [x] PII sanitization (emails, IPs, secrets, paths)
- [x] CLI commands: sync, summarize, recent, stats, search
- [ ] Unit tests for sanitizer patterns
- [ ] Integration test with sample history file

### P2 - Important

- [ ] Support for multiple AI assistants (Cursor, Copilot history formats)
- [ ] Config file support (~/.config/psc/config.yaml)
- [ ] Custom sanitization patterns via config

---

## Phase 2: Workflow Analysis

### P1 - Critical

- [ ] Semantic search (find sessions by meaning, not just keywords)
- [ ] Workflow pattern extraction ("how did I approach X last time?")
- [ ] Session similarity detection (find related past sessions)

### P2 - Important

- [ ] Export summaries to markdown
- [ ] Session tagging (manual + auto)
- [ ] Workflow templates (extract reusable patterns)

### P3 - Nice to Have

- [ ] Web UI for browsing sessions
- [ ] Integration with note-taking tools (Obsidian, Notion)

---

## Phase 3: Advanced Features

### P2 - Important

- [ ] AI-powered summaries (optional, local LLM or API)
- [ ] Cross-session insights ("you often debug X after doing Y")
- [ ] Time tracking integration

### P3 - Nice to Have

- [ ] Team sharing (sanitized session patterns, not content)
- [ ] Metrics dashboard
- [ ] IDE extension for real-time capture

---

## Security & Privacy Backlog

### P1 - Critical (Always)

- [ ] Security audit before v1.0 release
- [ ] Fuzz testing sanitizer with edge cases
- [ ] Verify no PII in any example files or tests
- [ ] Document threat model

### P2 - Important

- [ ] Optional encryption at rest
- [ ] Audit log for data access
- [ ] GDPR-friendly data export/delete

---

## Technical Debt

- [ ] Add type hints throughout
- [ ] Set up CI/CD (GitHub Actions)
- [ ] Add pre-commit hooks (ruff, mypy)
- [ ] Documentation site (mkdocs)

---

## Ideas / Future Exploration

- Multi-machine sync (encrypted cloud backup)
- Voice memo integration (transcribe and capture)
- Calendar integration (link sessions to meetings)
- Git integration (link sessions to commits/branches)

---

## Contributing

See CONTRIBUTING.md for how to propose new backlog items.
