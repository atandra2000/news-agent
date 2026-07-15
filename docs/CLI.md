# CLI

> All `newsagent` CLI commands, flags, and scheduler setup.

---

## 1. Commands

The CLI exposes **7 commands**. The unified pipeline is invoked by
`newsagent news <prompt.md>`; the rest are inspection / post-hoc utilities.

| Command | Positional | Flags |
|---------|------------|-------|
| `news` | `<prompt.md>` (required) | — |
| `eval` | `<report.md>` | `--prompt <prompt.md>`, `--cadence <name>`, `--rate 1-5` |
| `quality` | — | `--date YYYY-MM-DD` |
| `profiles` | — | — |
| `status` | — | — |
| `models` | — | — |
| `sources` | — | — |

> `news` no longer accepts `--daily` / `--weekly` / `--monthly`; cadence is
> configured via `NEWSAGENT_CADENCE` in `.env`. The legacy `--rate` flag for
> feedback was moved to `newsagent eval --rate 1-5`.

### `newsagent news`

Run the unified research pipeline. Required argument is a Markdown prompt
file; the orchestrator parses it into a `BriefSpec`, collects items, builds
the evidence graph, and (if the spec has 3+ sections) runs the cognition
core before per-section synthesis.

```bash
newsagent news <prompt.md>
```

### `newsagent eval`

Evaluate a brief-generated report against its prompt. With `--rate N`,
record user feedback (1-5) for the prompt instead of running evaluation.
Scores are stored in the `ReportEval` table and feed the adaptive adapter.

```bash
newsagent eval <report.md> --prompt <prompt.md> [--cadence daily|weekly|monthly] [--rate 1-5]
```

### `newsagent quality`

Self-assess a previously-generated report on 6 quality dimensions. Persists
improvement notes to self-improving memory.

```bash
newsagent quality [--date YYYY-MM-DD]
```

### `newsagent profiles`

List available report profiles with their configuration.

```bash
newsagent profiles
```

### `newsagent status`

Show database stats: total items, canonical items, reports, evals, adapter
state.

```bash
newsagent status
```

### `newsagent models`

List all models on the live LLM endpoint and check them against the curated
catalog. Shows ✓ (present) or · (not found) for each catalog model.

```bash
newsagent models
```

### `newsagent sources`

List registered collectors and which are enabled in config.

```bash
newsagent sources
```

### `newsagent help`

Print usage.

```bash
newsagent help
newsagent -h
newsagent --help
```

---

## 2. Scheduler setup

newsagent is a one-shot CLI — no daemon. The OS scheduler invokes
`newsagent news <prompt.md>` once a day.

### macOS (launchd)

Create `~/Library/LaunchAgents/com.newsagent.daily.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.newsagent.daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/.venv/bin/newsagent</string>
        <string>news</string>
        <string>example_prompt.md</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/news-agent</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/path/to/newsagent/storage/logs/newsagent.out.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/newsagent/storage/logs/newsagent.err.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.newsagent.daily.plist
```

### Linux (systemd)

Create `~/.config/systemd/user/newsagent.service`:

```ini
[Unit]
Description=newsagent daily AI research report
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/news-agent
ExecStart=/path/to/.venv/bin/newsagent news example_prompt.md
Environment=NEWSAGENT_LOG_LEVEL=INFO
```

Create `~/.config/systemd/user/newsagent.timer`:

```ini
[Unit]
Description=Run newsagent daily at 08:00

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user enable newsagent.timer
systemctl --user start newsagent.timer
```

### Cron (simplest)

```bash
# Run newsagent daily at 08:00.
0 8 * * * cd /path/to/news-agent && .venv/bin/newsagent news example_prompt.md >> storage/logs/newsagent.log 2>&1
```

---

## 3. Environment

The CLI reads `.env` from the working directory. All settings use the
`NEWSAGENT_` prefix. See [CONFIGURATION.md](./CONFIGURATION.md) for the full
reference.

```bash
# Required for LLM-backed runs:
NEWSAGENT_LLM_BACKEND=opencode_go
NEWSAGENT_LLM_OPENCODE_GO_API_KEY=<key>

# Cadence for `newsagent news`:
NEWSAGENT_CADENCE=daily

# Optional for web-grounded synthesis:
NEWSAGENT_SEARCH_BACKEND=tavily
NEWSAGENT_SEARCH_TAVILY_API_KEY=<key>

# Optional for Obsidian mirror:
NEWSAGENT_STORAGE_OBSIDIAN_VAULT=~/Documents/obsidian
```

---

## 4. Output locations

| Path | Contents |
|------|----------|
| `storage/newsagent.db` | SQLite database (all tables) |
| `storage/reports/<prompt-slug>.md` | Unified pipeline reports |
| `storage/run_manifests/<timestamp>.json` | Per-run manifests with stage stats |
| `storage/quality/YYYY-MM-DD.md` | Quality self-assessment reports |
| `storage/quality/YYYY-MM-DD.json` | Quality scores (JSON) |
| `storage/adapter_state/<hash>.json` | Adaptive state per prompt |
| `storage/vectors/` | Qdrant local vectors (if enabled) |
| `storage/logs/` | Scheduler log output |