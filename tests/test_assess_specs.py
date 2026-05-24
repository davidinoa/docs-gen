"""Tests for assess_specs.py."""
import json
from .conftest import run_script


def test_assess_empty_file_exits_nonzero(tmp_repo):
    spec = tmp_repo / "empty.md"
    spec.write_text("")
    result = run_script("assess_specs.py", str(spec))
    assert result.returncode != 0


def test_assess_missing_file_exits_nonzero(tmp_repo):
    result = run_script("assess_specs.py", str(tmp_repo / "nope.md"))
    assert result.returncode == 1


def test_assess_sparse_spec(tmp_repo):
    spec = tmp_repo / "sparse.md"
    spec.write_text("# Project\n\nWe do stuff.\n")
    result = run_script("assess_specs.py", str(spec))
    assert result.returncode == 2  # sparse
    data = json.loads(result.stdout)
    assert data["overall"] == "sparse"
    assert data["interview_scope"] == "full"


def test_assess_comprehensive_spec(tmp_repo):
    """A spec covering all six dimensions with substantive content scores comprehensive."""
    spec = tmp_repo / "comprehensive.md"
    spec.write_text("""# Project Spec

## Purpose & Goals

The system exists to solve the X problem that has been costing the company time
and money for two quarters. The fundamental goal is reducing manual reconciliation
work by automating the data pipeline. Success means that the metric Z hits target W
within six months, and that the operations team can spend their time on higher-value
work rather than chasing data discrepancies. Our success criteria are measurable
and tied to specific KPIs reviewed monthly. The motivation came from a recurring
pain point identified by the operations leadership.

## Users & Personas

### Power users
Technical engineers who interact with the system many times per day. They need
fast workflows, keyboard shortcuts, programmatic access via API, and rich filtering
capabilities. They have deep knowledge of the underlying domain.

### Casual users
Occasional users who check the system once or twice a week. They need clear UI,
sensible defaults, helpful error messages, and a gentle learning curve. Their
sessions are short and goal-directed.

### Admin users
Operations team members who manage configuration, user access, and system health.
They need granular permissions controls and audit logs to track changes over time.

## Functional Requirements

### Core (must-have for launch)
- Feature A — the main capability that solves the primary user need, including
  filtering, sorting, exporting, and sharing
- Feature B — secondary critical capability needed by compliance, with full
  audit trail and exportable reports
- Feature C — required integration with the existing system Z, including
  bi-directional sync and conflict resolution
- Feature D — admin controls for user management and access provisioning

### Secondary requirements
- Bulk operations across collections of records
- Background processing for long-running tasks
- API access for programmatic integration

## Non-Functional Requirements

| Category | Requirement | Priority |
|----------|-------------|----------|
| Performance | All API endpoints must respond within 200ms at p95 under normal load | High |
| Security | All data must be encrypted at rest using AES-256 and in transit via TLS 1.3 | High |
| Availability | The system must maintain 99.95% uptime measured monthly per the SLA | High |
| Scalability | Must handle 10x current peak load without degradation in response times | Medium |
| Compliance | SOX-compliant audit trail with seven-year retention for all financial events | High |

## Constraints & Boundaries

### Out of scope
- Mobile native clients (web-only for the initial release, mobile is a future phase)
- Tax calculation logic (delegated to the existing tax service)
- Payment processing (handled by the payments-service team)
- Customer-facing UI (handled by the billing portal project)

### Technical constraints
- Must use the existing PostgreSQL database — no new datastores introduced
- Python 3.12 is mandated as the org standard for backend services
- Cannot introduce new cloud vendors without procurement review
- Must integrate with the existing auth service rather than implementing new auth

### Timeline and budget
- Launch deadline tied to the Q3 platform migration
- Engineering budget capped at four engineers for two quarters

## Decisions Already Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python 3.12 | Org standard, team familiarity, broad library support |
| Framework | FastAPI | Performance, type safety, native async support, OpenAPI docs |
| Database | PostgreSQL | Org standard, ACID guarantees needed for financial data |
| Idempotency | Idempotency-Key header pattern | Industry-standard Stripe convention |
| API style | REST | Consumer familiarity, mature tooling, simpler than GraphQL |
""")
    result = run_script("assess_specs.py", str(spec))
    data = json.loads(result.stdout)
    assert data["overall"] == "comprehensive"
    assert data["completeness_pct"] >= 75
    assert result.returncode == 0


def test_assess_partial_spec(tmp_repo):
    """A spec with some but not all dimensions covered scores partial."""
    spec = tmp_repo / "partial.md"
    spec.write_text("""# Project

## Purpose & Goals

The purpose is to solve X by enabling Y. Success means measurable Z improvement.
Goals include faster onboarding and better outcomes for end users.

## Users

Primary user is the data analyst. They need to quickly query and visualize.
A secondary persona is the developer integrating with our API.
""")
    result = run_script("assess_specs.py", str(spec))
    data = json.loads(result.stdout)
    assert data["overall"] in ("partial", "sparse")
    if data["overall"] == "partial":
        assert result.returncode == 1
    assert len(data["questions_to_ask"]) > 0


def test_assess_subsection_content_counted(tmp_repo):
    """A section with content in subsections should count toward dimension coverage."""
    spec = tmp_repo / "subs.md"
    spec.write_text("""# Spec

## Users & Personas

### Persona A
A long description of persona A that takes many words. They need this and that
and the other thing. They use the system daily and depend on it for their workflows.

### Persona B
Another long description with substantial content. They are different from persona A
and have their own needs and patterns. The system serves them too.

### Persona C
Yet another persona with their own story. They round out the audience.
""")
    result = run_script("assess_specs.py", str(spec))
    data = json.loads(result.stdout)
    # users dimension should be 'good' because subsection content is counted
    assert data["dimensions"]["users"]["coverage"] == "good"


def test_assess_stdout_pure_json(tmp_repo):
    """Status messages must go to stderr, not stdout."""
    spec = tmp_repo / "s.md"
    spec.write_text("# X\n\nGoals: do thing.\n")
    result = run_script("assess_specs.py", str(spec))
    # Should parse as JSON even if there's stderr
    data = json.loads(result.stdout)
    assert "completeness_pct" in data


def test_assess_emits_both_instructions_keys_for_compat(tmp_repo):
    """`assistant_instructions` is canonical; `claude_instructions` is a deprecated alias."""
    spec = tmp_repo / "s.md"
    spec.write_text("# X\n\nGoals: do thing.\n")
    result = run_script("assess_specs.py", str(spec))
    data = json.loads(result.stdout)
    assert "assistant_instructions" in data
    assert "claude_instructions" in data
    assert data["assistant_instructions"] == data["claude_instructions"]
