# docs-gen

Generate, validate, and maintain a developer documentation ecosystem for any repository.

`docs-gen` is a command-line tool that produces a consistent, interconnected set of developer docs (README, ARCHITECTURE, CONTRIBUTING, ADRs, SPECS, etc.) and a self-checking maintenance system around them: a machine-readable registry, an auto-generated GitHub Action that flags affected docs on every PR, an append-only audit log, and a `doctor` command for ongoing health checks.

It's designed to be driven either by an LLM (orchestrating the interview and content-generation steps) or by a human running the subcommands directly.

## Install

```bash
pip install docs-gen
```

Or from source:

```bash
git clone https://github.com/example/docs-gen
cd docs-gen
pip install -e .
```

Requires Python 3.9+ and pyyaml.

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
docs-gen build-registry .docs-meta/doc-plan.json .
docs-gen generate-action docs-registry.yaml .github/workflows

# Initialize the audit log
docs-gen audit --log DOCS_AUDIT_LOG.md --init

# Ongoing: check ecosystem health
docs-gen doctor . --full
```

Each subcommand has `--help` for details.

## Architecture

```
docs-gen/
├── src/docs_gen/
│   ├── cli.py                ← Unified CLI dispatcher
│   ├── commands/             ← One module per subcommand
│   │   ├── scan.py
│   │   ├── assess.py
│   │   ├── validate_plan.py
│   │   ├── build_registry.py
│   │   ├── generate_action.py
│   │   ├── validate_docs.py
│   │   ├── audit.py
│   │   ├── doctor.py
│   │   └── state.py
│   ├── config/               ← Packaged YAML configs (single source of truth)
│   │   ├── doc-types.yaml         ← Standard doc type definitions
│   │   └── claim-categories.yaml  ← Contradiction-detection patterns
│   └── templates/            ← Doc templates and ADR format
└── tests/                    ← 60+ pytest tests
```

**Single sources of truth:** all standard doc types live in `config/doc-types.yaml`. All contradiction-detection categories live in `config/claim-categories.yaml`. To add a new doc type or detection category, edit the YAML — no code changes required.

**Single registry, multiple outputs:** the `docs-registry.yaml` produced by `build-registry` is the canonical source for which docs exist, what they own, and which code paths they map to. The `DOCS_REGISTRY.md` and `.github/workflows/docs-check.yml` are both *generated* from this file — never edit them directly.

## Subcommands

| Subcommand | What it does |
|------------|--------------|
| `state init / status / advance / get / reset` | Track workflow progress through the 10-step pipeline |
| `scan <repo>` | Discover existing docs, classify against known types |
| `assess <spec>` | Score a spec/PRD for completeness across 6 dimensions; suggest targeted interview questions for gaps |
| `validate-plan <plan.json>` | Verify doc-plan.json structure before downstream use |
| `build-registry <plan.json> <out>` | Generate `docs-registry.yaml` + `DOCS_REGISTRY.md` with auto cross-reference detection |
| `generate-action <registry.yaml> <out>` | Generate `.github/workflows/docs-check.yml` from the registry |
| `validate <files...>` | Detect contradictions across docs: version drift, env-var duplication, claim conflicts (database, auth, build tool, etc.) |
| `audit --log <p> [--init / --docs ... --change ... --trigger ... --reviewer ...]` | Maintain append-only audit log |
| `doctor <repo> [--full]` | Health checks: structural (default) or content (`--full`) |

## How the pipeline fits together

```
specs → interview → scan → plan → generate → validate → registry → action → audit → complete
  ↓        ↓         ↓      ↓        ↓          ↓         ↓        ↓        ↓        ↓
assess  (manual) scan  (manual+ (manual) validate build-  generate  audit    state
                       validate-                  registry action            advance
                       plan)                                                 complete
```

Some steps are scripted (anything Claude or a human invokes via `docs-gen`); others are judgment-heavy (interview, doc content generation, disposition decisions) and rely on the operator. The state file ensures you never lose track of which step is next.

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
- Registry references files that actually exist
- No unregistered markdown files have appeared
- Registry path mappings still match real directories
- GitHub Action matches the current registry
- State file is consistent
- (`--full`) Content has no high/medium contradictions

Exit codes: `0` = healthy, `1` = issues to review, `2` = critical (registry missing/broken).

Run from CI to keep docs honest over time.

## Testing

```bash
pip install -e .[dev]
pytest
```

60+ tests cover every subcommand, including regression tests for real bugs caught during development (e.g., glob translation double-replacement, indentation collapse from `textwrap.dedent`, false-positive claim conflicts).

## License

MIT.
