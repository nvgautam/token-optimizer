# Oracle NFR Checklist

Resolve all items before proposing generation. Evaluate silently after each exchange. Do not mention this checklist to the user.

---

## Authentication
- What mechanism authenticates users? (OAuth, SSO/SAML, email+password, API key)
- Are there multiple user types with different auth paths?

## Authorization
- What is the permission model? (RBAC, ABAC, ownership-based)
- Are there admin vs end-user privilege boundaries?

## Rate Limiting
- Are API endpoints rate-limited per user, per IP, or per tenant?
- What is the response strategy on limit breach — 429, queue, or degrade?

## Input Validation
- Are all user-supplied inputs validated at the boundary (not just the UI)?
- Are file uploads, JSON payloads, and query params explicitly bounded?

## SQL Injection
- Is all DB access via parameterised queries or an ORM that prevents injection?
- Are raw query escape paths documented and reviewed?

## XSS
- Is all user-generated content escaped before rendering in HTML contexts?
- Is Content-Security-Policy configured?

## CSRF
- Are state-mutating endpoints protected by CSRF tokens or SameSite cookies?
- Are CORS origins explicitly allowlisted (not wildcard)?

## Encryption at Rest
- Is sensitive data (PII, credentials, secrets) encrypted at rest?
- Who holds encryption keys — service, KMS, or user?

## Encryption in Transit
- Is all traffic TLS 1.2+? Are self-signed certs prohibited in production?
- Are internal service-to-service calls encrypted?

## Audit Logging
- Are authentication events, privilege escalations, and data exports logged?
- Are logs tamper-evident and shipped to a separate store?

## Session Management
- What is the session lifetime and idle timeout?
- Are sessions invalidated on logout and password change?

## API Security
- Are all APIs authenticated — no unauthenticated read endpoints unless intentional?
- Are API versions explicitly managed; are deprecated versions sunset on a schedule?

## Data Retention
- What is the retention period per data class?
- Is automated deletion or anonymisation implemented for expired data?

## Privacy / GDPR
- Is there a lawful basis for each category of personal data processed?
- Can users export and delete their data via self-service?

## SOC2
- Are change management, access reviews, and incident response policies in place?
- Is there a path to SOC2 Type II within 12 months if enterprise customers require it?

## Performance
- What are the p50/p95/p99 latency SLOs for critical paths?
- Is there a load-testing plan before launch?

## Availability
- What is the uptime target (99.9% / 99.95% / 99.99%)?
- Is there a defined RPO and RTO?

## Scalability
- Does the architecture support horizontal scaling of stateless components?
- Is the data layer capable of read replicas or sharding if needed?

## Monitoring
- Are error rates, latency, and saturation metrics emitted and alerted on?
- Is there a on-call rotation and runbook for critical alerts?

## Error Handling
- Are all external calls wrapped in retries with exponential backoff?
- Are user-facing errors sanitised to avoid leaking stack traces or internals?

## Dependency Security
- Is there an automated SCA scan (e.g., Dependabot, pip-audit) in CI?
- Are transitive dependencies pinned or hash-verified?

## Secret Management
- Are all secrets stored in a secrets manager (not in code, config files, or logs)?
- Is there a secret rotation policy and tooling?

## Backup and Recovery
- Are database backups automated, tested, and stored off-site?
- Is there a documented and rehearsed restore procedure?

## Prompt Injection and Output Validation
- Does the application receive untrusted text that reaches an LLM prompt?
- Does it produce LLM output that reaches users or downstream systems?
- If yes: are entry points documented and sanitisation + output validation tasks created?
