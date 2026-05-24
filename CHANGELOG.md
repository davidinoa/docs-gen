# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-05-24

### Added
- **Agentic workflow primitives**:
  - `summary:` field per registry entry, auto-extracted from each doc's
    first paragraph at `build-registry` time (or set explicitly via
    `summary:` in the doc-plan).
  - `docs-gen lookup --path X | --owns Y | --query Z [--json]` — find
    docs in the registry by code path glob, ownership topic, or
    summary substring. Exit code 0 on matches, 2 on no matches.
  - Companion `repo-docs-consumer.skill` ships separately, teaching
    LLM agents to consult the registry before editing code.
- **Solo-dev bootstrap**:
  - `docs-gen init [--preset minimal|standard|full] [--scaffold]
    [--interactive] [--name <n>] [--force]` detects the project
    (Python / Node / Rust / Go / Java / Ruby / generic), writes a
    sensible doc-plan, optionally scaffolds H1-only doc stubs, then
    runs `sync`. `minimal` ships three docs; `full` ships fourteen.
  - `docs-gen sync <plan>` runs `build-registry` →
    `generate-action` → `audit --init` in one command. Passes
    through `--strict`, `--dry-run`, `--audit-log`, `--reviewer`.
- **Enforcement and ownership**:
  - `generate-action --strict` emits a workflow that fails the PR
    check when affected docs aren't updated, instead of just
    commenting. Default behavior is unchanged (soft nudge).
  - `owners: [@alice, @team-arch]` field per registry entry.
  - `docs-gen codeowners <registry.yaml> [<out>]` exports a
    `.github/CODEOWNERS` file from registry entries with `owners`.
    Stdout mode via `--stdout`.
- **Long-term comprehension**:
  - `docs-gen snapshot <name> [--git-ref <tag>]` freezes the
    registry plus every referenced doc under
    `.docs-meta/snapshots/<name>/` with a `manifest.json`. `--list`
    shows existing snapshots.
- `DOCS_REGISTRY.md` now renders a "Doc Summaries" section (and a
  "Doc Owners" section when any doc declares owners).

### Changed
- README rewritten around the two-track quick start: solo dev via
  `init`, team via `sync`. Subcommand table reorganized by lifecycle
  phase (Setup / Discovery / Generation / Use / Validation /
  Maintenance). Exit codes updated for every new subcommand.

## [0.2.1] - 2026-05-24

### Changed
- Rename JSON output key `claude_instructions` to `assistant_instructions` in
  `assess` and `validate` reports. The old key is still emitted with the same
  value for one release as a compatibility shim — switch consumers over and
  expect `claude_instructions` to be removed in a future version.
- Replace incidental "Claude" references in internal docstrings with the
  generic "an LLM" / "the operator" — the tool itself is LLM-agnostic; only
  the companion `repo-docs-generator` skill is Claude-specific (by design,
  since it's an Anthropic skill).

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
