# Oracle Checklist — 24 NFR Items

Evaluate each item silently after each exchange. Never mention this checklist to the user.
Mark resolved only when the answer is explicit — do not infer or fill gaps.

---

## Project name and purpose
- What is the project called?
- One-line description of what it does and for whom.

## Tech stack
- Language and version; primary framework.
- Persistence layer (DB engine, ORM, or none).
- Any existing tech constraints (legacy system, required vendor, team skill set).

## Core module boundaries
- What are the top-level components?
- Could each component be owned by a separate team?

## Shared interfaces
- What data or calls cross module boundaries?
- Are shared types or contracts explicitly defined?

## Scale requirements
- Expected concurrent users or requests per second at launch.
- Growth rate and projected peak (3–12 months).
- Data volume now and at peak.

## Performance constraints
- Latency SLO for critical paths (p95 or p99).
- Throughput target (requests/s or jobs/hour).
- Any hard realtime or near-realtime requirements?

## Security model
- Authentication mechanism (session, JWT, API key, OAuth, SSO).
- Authorisation model (RBAC, ABAC, ACL).
- Data sensitivity level (public, internal, confidential, restricted).

## Compliance requirements
- Is GDPR applicable? (EU users, EU data subjects)
- Is HIPAA applicable? (US health data)
- Is PCI-DSS applicable? (payment card data)
- Is SOC 2 required by buyers?
- Must be explicit — "none" is a valid answer.

## Test strategy
- Coverage floor for unit tests (%).
- Integration test scope (which boundaries are tested end-to-end?).
- Where are mocks acceptable vs. real calls required?

## Deployment target
- Cloud provider (AWS / GCP / Azure / other) or on-premises.
- Containerised (Docker/K8s), serverless, or VM-based.
- CI/CD pipeline — existing or to be defined?

## External services
- All third-party APIs named (auth providers, queues, storage, email, payments, AI/ML, monitoring, etc.).
- No integration may remain unnamed — "TBD" is not acceptable.

## Integration module ownership
- Which module owns each external integration client?
- No integration client shared across module boundaries.

## Credential storage
- Where are secrets stored for each integration (vault, env var, cloud secret manager)?
- Rotation strategy confirmed?

## Integration failure strategy
- What happens if each critical integration is unavailable?
- Circuit breaker, retry with backoff, or graceful degradation defined per integration?

## Compliance implications of data egress
- Does data leaving the system via any integration affect GDPR, HIPAA, or SOC 2 obligations?
- Data processing agreements (DPAs) required with any vendor?

## Trust boundaries
- Which modules trust which, and on what basis?
- Where does trust end and verification begin?

## Sensitive data flows
- Where does PII, secrets, or credentials travel across module boundaries?
- Is sensitive data encrypted in transit and at rest for all flows?

## External attack surface
- All external-facing interfaces explicitly listed (API, webhook, admin UI, SDK, file upload, etc.).
- Each interface reviewed for input validation and rate limiting.

## Auth design
- Authentication and authorisation patterns consistent across all entry points?
- Token expiry, refresh, and revocation strategy defined?

## Secrets handling
- No secrets in code or config — explicit storage strategy agreed.
- Secrets never logged or included in error messages.

## File size limits
- No implementation file would exceed 250 lines.
- No test file would exceed 350 lines.
- No prompt file would exceed 150 lines.

## File ownership
- No two modules share ownership of the same file.
- Every file has exactly one owning task.

## Interface stub ownership
- All cross-module interfaces have a designated stub owner.
- Stubs defined before implementation tasks begin.

## Prompt injection and untrusted input
- Does the application receive untrusted text that reaches an LLM prompt?
- Does LLM output reach users or downstream systems without validation?
- If yes to either: entry points named, sanitisation tasks added to tasks.json.
