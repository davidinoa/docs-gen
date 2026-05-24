# docs-gen

Generate, validate, and maintain a developer documentation ecosystem for any repository.

`docs-gen` is a command-line tool that produces a consistent, interconnected set of developer docs (README, ARCHITECTURE, CONTRIBUTING, ADRs, SPECS, etc.) and a self-checking maintenance system around them: a machine-readable registry, an auto-generated GitHub Action that flags affected docs on every PR, an append-only audit log, and a `doctor` command for ongoing health checks.

It's designed to be driven either by an LLM (orchestrating the interview and content-generation steps) or by a human running the subcommands directly.

## Install

```bash
pip install https://github.com/davidinoa/docs-gen/releases/download/v0.2.0/docs_gen-0.2.0-py3-none-any.whl
```

Or from source:

```bash
git clone https://github.com/davidinoa/docs-gen
cd docs-gen
pip install -e .
```

Requires Python 3.10+ and pyyaml.

## Quick start

```bash
# Initialize state tracking in your repo
docs-gen state init .

# Discover existing docs
docs-gen scan . > .docs-meta/scan-results.json

# Assess any existing spec/PRD
docs-gen assess docs/PRD.md --output .docs-meta/specs-assessment.json

# (Write a doc-plan.json based on the scan + your decisions)

# Verify the plan is well-formed
docs-gen validate-plan .docs-meta/doc-plan.json

# Once docs are generated, check them for contradictions
docs-gen validate *.md --output .docs-meta/validation-report.json

# Generate registry + GitHub Action from the plan
docs-gen build-registry .docs-meta/doc-plan.json . --audit-log DOCS_AUDIT_LOG.md
docs-gen generate-action docs-registry.yaml .github/workflows --audit-log DOCS_AUDIT_LOG.md

# Initialize the audit log (or let the --audit-log flags above create one)
docs-gen audit --log DOCS_AUDIT_LOG.md --init

# Ongoing: check ecosystem health
docs-gen doctor . --full
```

Each subcommand has `--help` for details.

## Subcommands

| Subcommand | What it does |
|------------|--------------|
| `state init / status / advance / get / reset / revert` | Track workflow progress through the 10-step pipeline; `revert --step <s>` rewinds without deleting artifacts |
| `scan <repo>` | Discover existing docs, classify against known types |
| `assess <spec>` | Score a spec/PRD for completeness across 6 dimensions; suggest targeted interview questions for gaps |
| `validate-plan <plan.json>` | Verify doc-plan.json structure before downstream use |
| `build-registry <plan.json> <out>` | Generate `docs-registry.yaml` + `DOCS_REGISTRY.md` with auto cross-reference detection (proposes authoritative doc per overlap) |
| `generate-action <registry.yaml> <out>` | Generate `.github/workflows/docs-check.yml` from the registry |
| `validate <files...>` | Detect contradictions across docs: version drift, env-var duplication, claim conflicts |
| `audit --log <p> [--init / --docs ... --change ... --trigger ... --reviewer ...]` | Maintain append-only audit log |
| `doctor <repo> [--full]` | Health checks: structural (default) or content (`--full`). Honors `.gitignore` inside git checkouts. |
| `template list / show <name> [--template-dir <dir>]` | List or print packaged doc and workflow templates; teams can override individual files via `--template-dir` |

## Global flags

These apply to every subcommand and should appear before it:

| Flag | Behavior |
|------|----------|
| `--verbose`, `-v` | More detailed status output (debug-level events) |
| `--quiet`, `-q` | Suppress status messages; errors still print |
| `--log-format text\|json` | `text` is the default; `json` emits one JSON object per status event on stderr, useful for wrapping scripts |
| `--version` | Print the docs-gen version and exit |

```bash
docs-gen --log-format=json doctor . --full --output health.json
docs-gen --quiet build-registry .docs-meta/doc-plan.json .
```

## File-writing flags (G3, G5)

Commands that write or mutate files share two opt-in flags:

| Flag | Applies to | Behavior |
|------|------------|----------|
| `--dry-run` | `build-registry`, `generate-action`, `audit --init`, `audit` (append), `state init` | Print would-write paths without touching the filesystem |
| `--audit-log <path>` | `build-registry`, `generate-action` | After a successful write, append an audit entry to the named log. Combine with `--reviewer "..."` to record who triggered it. |

```bash
docs-gen build-registry .docs-meta/doc-plan.json . --dry-run
docs-gen generate-action docs-registry.yaml .github/workflows \
    --audit-log DOCS_AUDIT_LOG.md --reviewer "ci-bot"
```

## Custom doc types and claim categories

Every config that ships with docs-gen can be overridden per-repo without forking the package. The relevant flags:

| Flag | Command | Default |
|------|---------|---------|
| `--doc-types <path>` | `scan`, `validate-plan` | packaged `config/doc-types.yaml` |
| `--claim-categories <path>` | `validate` | packaged `config/claim-categories.yaml` |
| `--template-dir <dir>` | `template list`, `template show` | packaged `templates/` |

Use this to extend or replace the defaults:

```bash
# Start by exporting the packaged YAMLs so you can edit them.
docs-gen template show doc-templates.md > my-templates/doc-templates.md
# Then point commands at your custom copies:
docs-gen scan . --doc-types ./custom-doc-types.yaml
docs-gen validate *.md --claim-categories ./custom-categories.yaml
docs-gen template show adr-format.md --template-dir ./my-templates
```

Both `doc-types.yaml` and `claim-categories.yaml` declare a top-level `version:` field. docs-gen validates this at load time and refuses files with versions newer than the current release supports — bump docs-gen rather than silently ignoring a schema you don't understand.

## CI integration

Copy the bundled starter workflow into your repo:

```bash
docs-gen template show workflows/docs-health.yml > .github/workflows/docs-health.yml
```

It runs `docs-gen doctor --full` on PRs, on pushes to `main`, and weekly via cron. Critical issues fail the run; non-critical issues post a comment without blocking the merge.

## Architecture

```
docs-gen/
├── src/docs_gen/
│   ├── cli.py                ← Unified CLI dispatcher + global flag parsing
│   ├── log.py                ← Centralized status logger (--verbose/--quiet/--log-format)
│   ├── commands/             ← One module per subcommand
│   │   ├── scan.py
│   │   ├── assess.py
│   │   ├── validate_plan.py
│   │   ├── build_registry.py
│   │   ├── generate_action.py
│   │   ├── validate_docs.py
│   │   ├── audit.py
│   │   ├── doctor.py
│   │   ├── state.py
│   │   └── template.py
│   ├── config/               ← Packaged YAML configs (single source of truth)
│   │   ├── doc-types.yaml
│   │   └── claim-categories.yaml
│   └── templates/            ← Doc and workflow templates
│       ├── doc-templates.md
│       ├── adr-format.md
│       └── workflows/
│           └── docs-health.yml
└── tests/                    ← pytest suite covering every subcommand
```

**Single sources of truth:** all standard doc types live in `config/doc-types.yaml`. All contradiction-detection categories live in `config/claim-categories.yaml`. To add a new doc type or detection category, edit the YAML — no code changes required.

**Single registry, multiple outputs:** the `docs-registry.yaml` produced by `build-registry` is the canonical source for which docs exist, what they own, and which code paths they map to. The `DOCS_REGISTRY.md` and `.github/workflows/docs-check.yml` are both *generated* from it — never edit them directly.

**Templates live in the tool.** The companion `repo-docs-generator` skill reads templates via `docs-gen template show <name>` rather than duplicating them, so templates and the code that consumes them stay in lockstep.

## Validation: heuristic and semantic

`docs-gen validate` runs three classes of checks:

- **Heuristic** — version conflicts (Node 18 vs 20), env-var definitions in multiple docs (medium), duplicate section headers across docs (low).
- **Semantic claim conflicts** — extracts named technology choices per doc across categories (database, auth provider, build tool, deploy target, monorepo tool, package manager, state management libs, CI/CD). Uses a **dominant-value heuristic**: if a single doc mentions multiple alternatives in a mutually-exclusive category, the value with count ≥ 2× the runner-up is the "claimed" one. Alternatives mentioned in passing (e.g., "we chose NX over Turborepo") don't propagate to conflict checks.
- **Semantic summary** — per-doc fact extraction surfaced for LLM-aided review of conflicts that named-entity matching can't catch.

## Doctor — ongoing maintenance

```bash
docs-gen doctor .            # Structural checks
docs-gen doctor . --full     # Adds content validation
```

Checks include:

- Registry exists, parses, and declares a supported `version`
- Registry references files that actually exist
- No unregistered markdown files have appeared (respects `.gitignore` via `git ls-files` when in a checkout, falls back to a small hardcoded ignore list otherwise)
- Registry path mappings still match real directories
- Docs aren't past their review cadence (currently `weekly`, `monthly`, `quarterly`, `yearly`; event-driven cadences like `on-change` are not time-checked)
- GitHub Action matches the current registry
- State file is consistent
- (`--full`) Content has no high/medium contradictions

## Exit codes

Conventions are consistent within each command and surface as the process exit status. CI scripts can branch on them:

| Command | 0 | 1 | 2 |
|---------|---|---|---|
| `scan` | success | error (config missing, parse failure) | — |
| `assess` | `comprehensive` (≥75%) | `partial` (40–74%) | `sparse` (<40%) |
| `validate-plan` | plan is valid | errors present (must fix) | warnings only (review recommended) |
| `validate` (docs) | no high/medium issues | medium issues only | one or more high-severity issues |
| `build-registry`, `generate-action`, `audit`, `template` | success | error (missing input, parse failure, IO error) | — |
| `state` (init, advance, get, reset, revert) | success | misuse or already-exists | advance skipping ahead without `--force` |
| `doctor` | healthy | non-critical issues found (stale docs, unregistered files, etc.) | critical (registry missing, registry unparsable, registry version unsupported) |

## Testing

```bash
pip install -e .[dev]
pytest
```

The suite covers every subcommand, including regression tests for real bugs caught during development (glob translation double-replacement, indentation collapse from `textwrap.dedent`, false-positive claim conflicts, release-notes install URL).

## License

MIT.
