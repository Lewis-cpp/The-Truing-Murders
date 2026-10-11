# Repository Guidelines

## Project Structure & Module Organization

The repository holds two independent subprojects plus project-wide documentation. Keep the root limited to `README.md`, `AGENTS.md`, `docs/`, CI under `.github/`, and repository-wide settings such as `.gitignore`.

- `backend/` is the Python project: `pyproject.toml`, `uv.lock`, `alembic.ini`, `compose.yaml` and `.env.example` live here. Application code goes in `backend/src/backend/`, tests in `backend/tests/`, and backend-only resources (cases, prompts, database init scripts) in `backend/assets/`.
- `frontend/` is the Node project: `package.json`, `package-lock.json` and the Vite, TypeScript, ESLint and Prettier configs live here. Application code goes in `frontend/src/`, tests in `frontend/tests/`, and public static files in `frontend/public/`.

Mirror source paths in each subproject's test tree where practical; for example, test `backend/src/backend/domain/rules.py` in `backend/tests/domain/test_rules.py`. Never place case files or prompts under `frontend/`.

Do not commit generated output, local editor settings, caches, or credentials. Add such paths to `.gitignore` when the corresponding tooling is introduced.

## Build, Test, and Development Commands

Each subproject exposes its own commands: `uv` and `pyproject.toml` for `backend/`, `npm` scripts for `frontend/`. Run commands from inside the subproject directory. The root `README.md` documents installation, startup and checks for both.

Before submitting a change, run every formatter, linter, and test command defined by the subproject you touched. Avoid adding wrapper scripts that merely rename an existing standard command.

## Coding Style & Naming Conventions

Follow the formatter and idioms of the language introduced. Use spaces rather than tabs unless the formatter requires otherwise, keep files focused, and prefer clear names over abbreviations. Use `snake_case` for Python files and functions, or the language's established equivalent; reserve `PascalCase` for types. Keep Markdown headings in sentence case and use fenced code blocks with a language identifier.

## Testing Guidelines

Add tests with each behavior change or bug fix. Store them under the subproject's `tests/` directory and name them for the unit or behavior they verify, following the chosen framework's discovery convention. Test public behavior and edge cases rather than implementation details. If coverage enforcement is added, record the command and threshold in the README instead of relying on an unwritten target.

## Commit & Pull Request Guidelines

Use short, imperative commit subjects such as `Add suspect timeline parser`, and keep unrelated changes separate.

Pull requests should explain the purpose and approach, list verification performed, and link relevant issues. Include screenshots only for visible interface changes. Call out configuration changes, migrations, or known follow-up work explicitly.
