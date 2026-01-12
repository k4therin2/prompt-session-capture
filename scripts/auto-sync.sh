#!/bin/bash
# Auto-sync prompts - runs via cron, logs quietly
cd "$(dirname "$0")/.."
source env/bin/activate 2>/dev/null || python3 -m venv env && source env/bin/activate
pip install -q -e . 2>/dev/null
psc daily --date "$(date +%Y-%m-%d)" >> /tmp/psc-sync.log 2>&1
echo "[$(date)] Sync complete" >> /tmp/psc-sync.log
