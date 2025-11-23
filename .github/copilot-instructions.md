# Filesync Web UI - AI Coding Assistant Instructions

## Architecture Overview

This is a **server-driven web app** using Flask + HAT stack (HTMX, Alpine.js, Tailwind) for managing local file synchronization tasks. Key architectural decisions:

- **Backend**: Flask app factory pattern (`app/__init__.py`), SQLite database (`database.db`), watchdog-based file monitoring
- **Frontend**: Server-side HTML rendering with HTMX for partial updates, Alpine.js for client-side interactivity, Tailwind CSS v4 for styling
- **Core Logic**: `app/filesync.py` implements `FileSyncManager` with `SourceCopyCoordinator` to serialize copy operations per source path, preventing race conditions
- **State Management**: In-memory `sync_managers` dict in `app/routes.py` tracks active sync tasks (config_id → {manager, thread})
- **Real-time Updates**: Socket.IO for pushing status updates to clients (see `app/static/js/scripts.js`)

## Project Structure

```
app/
├── __init__.py          # Flask app factory, SocketIO init
├── db.py                # SQLite connection helpers
├── filesync.py          # Core sync logic (1200+ lines): FileSyncManager, SourceCopyCoordinator, Watcher, Copier
├── routes.py            # Flask routes & HTMX endpoints
├── schema.sql           # Database schema (sync_configs table)
├── templates/           # Jinja2 templates
│   ├── base.html        # Main layout with HAT stack CDN imports
│   ├── index.html       # Homepage with sync cards list
│   └── partials/        # Reusable HTML fragments for HTMX swaps
│       ├── sync_card.html          # Individual sync task card
│       ├── sync_config_form.html   # Configuration form with Alpine.js
│       ├── sync_status.html        # Status panel with start/stop buttons
│       └── server_status_badge.html # System status indicator
└── static/
    ├── js/scripts.js    # Alpine.js components, Socket.IO client, utility functions
    └── css/tailwind.css # Generated Tailwind CSS v4 output
```

## Development Workflow

### Setup & Running
```bash
# Virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Initialize database (first run or schema changes)
flask init-db

# Run dev server (port 5120)
python run.py
```

### Tailwind CSS Build
```bash
# Watch mode (development)
npm run dev

# Production build
npm run build
```

### Windows Management Scripts
- `run.ps1` - Start server
- `register_task.ps1` - Register as Windows scheduled task
- `tail.ps1` - Real-time log monitoring
- `shutdown.ps1` - Graceful server shutdown via API
- `migrate.ps1` - Database initialization/migration

## Frontend (HAT Stack) Rules

### HTMX Usage
- **DO**: Use for data loading/saving and large region updates (`hx-get`, `hx-post`, `hx-delete`)
- **DO**: Always return HTML fragments from server, never JSON
- **DO**: Target specific elements with `hx-target` and `hx-swap`
- **DON'T**: Render JSON on client side - HTML generation is server responsibility

Example from `sync_card.html`:
```html
<button hx-delete="/filesync/delete/{{ config.id }}" 
        hx-target="#sync-card-{{ config.id }}" 
        hx-swap="outerHTML">Delete</button>
```

### Alpine.js Usage
- **DO**: Use for volatile UI state (modals, tabs, dropdowns, form validation)
- **DO**: Define components in `app/static/js/scripts.js` and reference via `x-data`
- **DO**: Use data binding (`x-model`, `x-text`, `x-show`) instead of direct DOM manipulation
- **DON'T**: Manage business logic - keep it on the server

Example from `sync_config_form.html`:
```html
<form x-data="{ 
    retentionMode: '{{ config.retention_mode }}', 
    retentionValue: {{ config.retention or 60 }}
}" x-init="$watch('retentionMode', value => { /* auto-update value */ })">
```

### Tailwind CSS v4 Specifics
- **CRITICAL**: Always specify border colors explicitly (`border border-gray-300`, NOT just `border`)
- **CRITICAL**: Add `border-none` to buttons with background colors to prevent default borders
- Use utility classes consistently: `bg-{color}-{shade}`, `text-{color}-{shade}`, `border-{color}-{shade}`

## Backend Patterns

### Template Partials Pattern
Reusable HTML fragments in `app/templates/partials/` follow `{feature}_{action}.html` naming:
- `sync_card.html` - Full sync task card
- `sync_status.html` - Status section with control buttons
- `sync_config_form.html` - Configuration form

### Route Response Strategy
Routes check `Accept` header to return JSON or HTML:
```python
def _status_response(config_id, is_running, status):
    wants_json = request.accept_mimetypes["application/json"] >= request.accept_mimetypes["text/html"]
    if wants_json:
        return jsonify(...)
    return render_template("partials/sync_status.html", ...)
```

### Sync Manager Lifecycle
1. Config created in database via `routes.py`
2. User clicks "Start Sync" → creates `FileSyncManager` in `sync_managers` dict
3. Manager spawns background thread with Watcher (monitors changes) and Copier (processes queue)
4. Status updates pushed via Socket.IO to connected clients
5. "Stop Sync" → cancels thread, removes from `sync_managers`

### Copy Coordination
`SourceCopyCoordinator` in `filesync.py` prevents multiple tasks from copying from the same source simultaneously:
```python
coordinator = SourceCopyCoordinator()
if coordinator.acquire(source_path, config_id, cancel_event):
    try:
        # Perform copy operation
    finally:
        coordinator.release(source_path, config_id)
```

## Coding Conventions

### Python
- PEP 8 style, 4-space indentation
- Use `logging` module (never `print` statements)
- Add type hints to new functions
- Modular design: separate blueprints for features

### JavaScript
- Define Alpine.js components in `app/static/js/scripts.js`
- Use `resolveUrl()` helper for all API calls to handle script root correctly
- Socket.IO client wrapper: `getSyncSocket()` singleton pattern

### HTML Templates
- IDs for script access: `id="sync-card-{{ config.id }}"`
- Classes for styling: `class="bg-gray-50 p-4 rounded"`
- Conditional fields: Use `<template x-if>` to prevent hidden field submission

## 한국어 주석 및 에이전트 응답 지침

- **에이전트 응답 언어**: 모든 AI 코파일럿/에이전트의 응답은 한국어로 작성하세요(코드 리뷰 코멘트·PR 설명·질문 응답 포함).
- **주석 언어**: 함수의 docstring, 인라인 주석, 템플릿 주석은 한국어로 작성합니다. 변수명·함수명 등 코드 심볼은 영어로 유지하세요.
- **예외 사항**: 외부 라이브러리 명칭, 표준 에러/로그 메시지(관례적 영어 표기)는 영어로 남겨도 됩니다. 단, 내부 동작을 설명하는 주석은 한국어로 병기하세요.

## Testing Guidelines

- **No automated test suite yet** - manual testing required
- Test flow: Create sync task → Start → Verify logs → Stop → Delete
- Check error handling: non-existent paths, permission errors
- Verify status updates appear in real-time
- Future: Use `pytest` with Flask test client

## Key Files to Reference

- `AGENTS.md` - Complete repository guidelines (this file expands on it)
- `doc/HTMX.md` - Comprehensive HTMX usage guide with examples
- `doc/Alpine.js.md` - Alpine.js patterns and best practices
- `doc/WebSocket.md` - Socket.IO integration details
- `app/filesync.py` lines 1-150 - Core sync architecture and coordination logic

## Common Tasks

**Add new sync configuration field:**
1. Update `app/schema.sql` and run `flask init-db`
2. Modify `sync_config_form.html` partial
3. Update `routes.py` to handle new field in POST handler
4. Pass to `SyncConfig` dataclass in `filesync.py`

**Add new status indicator:**
1. Update status dict in `FileSyncManager.get_status()` (`filesync.py`)
2. Modify `sync_status.html` template to display new field
3. Update Alpine.js `syncStatusPanel` component if client-side logic needed

**Fix Tailwind styling issues:**
- Check if using Tailwind v4 syntax (borders require explicit colors)
- Rebuild: `npm run build`
- Verify classes are not purged (check `tailwind.config.js` content paths)
