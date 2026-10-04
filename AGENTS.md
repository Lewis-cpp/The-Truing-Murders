# Repository Guidelines

## Project Structure & Module Organization

This repository is currently an empty project shell. Keep the root limited to project-wide documentation and configuration. As implementation is added, place application code in `src/`, automated checks in `tests/`, and non-code resources in `assets/`. Mirror source paths in the test tree where practical; for example, test `src/parser.py` in `tests/test_parser.py`.

Do not commit generated output, local editor settings, caches, or credentials. Add such paths to `.gitignore` when the corresponding tooling is introduced.

## Build, Test, and Development Commands

No build system, dependency manifest, or test runner is configured yet. Contributors should document the first toolchain in the root `README.md` and expose a small, stable command set through the ecosystem's standard mechanism, such as `npm` scripts, `make`, or `pyproject.toml`.

Before submitting a change, run every formatter, linter, and test command defined by that toolchain. Avoid adding wrapper scripts that merely rename an existing standard command.

## Coding Style & Naming Conventions

Follow the formatter and idioms of the language introduced. Use spaces rather than tabs unless the formatter requires otherwise, keep files focused, and prefer clear names over abbreviations. Use `snake_case` for Python files and functions, or the language's established equivalent; reserve `PascalCase` for types. Keep Markdown headings in sentence case and use fenced code blocks with a language identifier.

## Testing Guidelines

Add tests with each behavior change or bug fix. Store them under `tests/` and name them for the unit or behavior they verify, following the chosen framework's discovery convention. Test public behavior and edge cases rather than implementation details. If coverage enforcement is added, record the command and threshold in the README instead of relying on an unwritten target.

## Commit & Pull Request Guidelines

No Git history is available to establish a repository-specific convention. Use short, imperative commit subjects such as `Add suspect timeline parser`, and keep unrelated changes separate.

Pull requests should explain the purpose and approach, list verification performed, and link relevant issues. Include screenshots only for visible interface changes. Call out configuration changes, migrations, or known follow-up work explicitly.
