# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-05-24

### Added
- New `docs_gen.log` module: centralized status output with `--verbose` / `--quiet` / `--log-format=text|json` global flags, wired through `cli.py`.
- New `state revert --step <s>` subcommand: rewind the pipeline pointer without `--force` or a full reset; artifacts remain on disk.
- New `template list` and `template show <name>` subcommands with `--template-dir <dir>` override so teams can customize templates without forking.
- New starter `workflows/docs-health.yml` template that runs `docs-gen doctor --full` on PRs, main, and a weekly cron; available via `docs-gen template show workflows/docs-health.yml`.
- `--dry-run` on `build-registry`, `generate-action`, `audit --init`, `audit` (append), and `state init`: print would-write paths without touching the filesystem.
- `--audit-log <path>` on `build-registry` and `generate-action`: append an audit entry automatically after a successful write (skipped under `--dry-run`).
- `--claim-categories <path>` override on `validate`.
- Doctor: stale-docs detection. Registry entries with cadence `weekly` / `monthly` / `quarterly` / `yearly` are compared against `last_reviewed` and flagged when past their threshold.
- Doctor: schema version validation for `docs-registry.yaml`.
- `validate-plan` and `validate`: schema version validation for `doc-types.yaml` and `claim-categories.yaml`.
- Documented exit codes per subcommand in the README, plus a CI integration section.

### Changed
- `build-registry` now proposes an authoritative doc for each cross-reference table row, using path-specificity and topic-match heuristics, instead of leaving every row as "[designate authoritative doc]".
- `doctor`'s markdown-file walk now honors `.gitignore` (via `git ls-files`) when run inside a git checkout, falling back to the existing hardcoded ignore list otherwise. Fewer false positives in monorepos with non-standard build directories.
- Raw `yaml.YAMLError`, `json.JSONDecodeError`, `OSError`, and `VersionMismatch` are now wrapped in command entry points with file-path context instead of bubbling up as stack traces.
- `pyproject.toml` now declares `requires-python = ">=3.10"` (PEP 604 union syntax in source).
- Release workflow now emits a correct install URL in the generated release notes (the v0.1.0 workflow accidentally included an extra leading `v` in the wheel filename).

### Infrastructure
- New `.github/workflows/ci.yml` that runs `pytest` on Python 3.10 / 3.11 / 3.12 on every push and pull request.

## [0.1.0] - 2026-05-24

### Added
- Initial release.
- 9 subcommands: scan, assess, validate-plan, build-registry, generate-action, validate, audit, doctor, state.
- Single-source-of-truth configs: doc-types.yaml and claim-categories.yaml.
- Semantic claim conflict detection with dominant-value heuristic.
- Auto cross-reference detection in registry generation.
- Doctor command with --full content validation mode.
- 64 pytest tests covering every subcommand.
