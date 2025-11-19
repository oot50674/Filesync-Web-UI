# Repository Guidelines

## Project Structure & Module Organization
`app/` hosts the Flask package: `__init__.py` wires the app factory, `db.py` exposes the SQLite helpers, `routes.py` carries HTMX-ready view handlers, and `templates/` plus `static/` hold Jinja layouts and assets. Keep reusable HTML fragments inside `templates/partials/` for HTMX swaps, and place client scripts or CSS under `static/js` and `static/css`. Database artifacts (`schema.sql`, `database.db`) sit at the repo root next to `run.py`, while long-form notes live under `doc/`. Mirror this layout whenever you introduce new modules so onboarding developers can predict where logic belongs.

## Build, Test, and Development Commands
- `python -m venv venv && source venv/bin/activate` — create and enter an isolated interpreter that matches production libraries.
- `pip install -r requirements.txt` — install Flask, HTMX helpers, and other pinned dependencies.
- `flask init-db` — reset the SQLite file using `schema.sql`; run whenever models change.
- `python run.py` — launch the dev server on `127.0.0.1:5000` with auto reload enabled.
Avoid running commands that compile or test on behalf of the user; describe expected output instead.

## Coding Style & Naming Conventions
Backend code is Python 3 with 4-space indentation and descriptive snake_case names (see `app/routes.py`). Java additions must target JDK 1.7 only and avoid lambdas or streams. Frontend scripts must stay within ES5: declare variables with `var`, favor function declarations, and no arrow functions or `class` syntax. When adding controllers in any Java modules, ensure filenames end with `.do`. Follow existing quoting style (double quotes in HTML, single quotes in Python) and keep Tailwind markup inline unless a utility class is reused broadly.

## Testing Guidelines
No automated harness is bundled yet; favor lightweight Flask view functions that are easy to exercise manually. When proposing tests, stick to the frameworks already in requirements (e.g., `pytest` if introduced) and mirror template names such as `test_routes.py`. Provide instructions for maintainers to run tests locally instead of executing them yourself.

## Commit & Pull Request Guidelines
Commits should be small, imperative statements (`add todo HTMX partial`) referencing the touched module. Explain structural changes (schema edits, template moves) inside the body. Pull requests should summarize the intent, list key files (`app/routes.py`, `app/templates/index.html`), mention any new commands or config flags, and link tracking issues. Include before/after screenshots for user-facing HTMX regions and note any migrations so reviewers can re-run `flask init-db`.

## Security & Configuration Tips
Keep secrets out of source; rely on environment variables surfaced through `app/__init__.py`. Document any optional `.env` keys inside `doc/` rather than committing them. For browser safety, validate HTMX endpoints on the server, sanitize user input in Jinja templates, and restrict static uploads to vetted directories.
