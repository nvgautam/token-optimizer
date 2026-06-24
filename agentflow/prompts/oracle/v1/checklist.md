# Oracle Checklist

Resolve all items before proposing generation. Evaluate silently after each exchange.

## Functional

- [ ] Project name and one-line purpose
- [ ] Tech stack: language, framework, persistence layer
- [ ] Core module boundaries (what are the main components?)
- [ ] Shared interfaces (what crosses module boundaries?)

## Non-functional

- [ ] Scale requirements (expected load, data volume, growth rate)
- [ ] Performance constraints (latency SLOs, throughput targets)
- [ ] Security model (authentication mechanism, data sensitivity level)
- [ ] Compliance requirements (GDPR / HIPAA / SOC2 / PCI / none — must be explicit)
- [ ] Test strategy (coverage floor, integration test scope, mock boundaries)
- [ ] Deployment target (cloud provider, containerised, serverless, on-prem)

## Architecture security review

- [ ] Trust boundaries identified (which modules trust which, and why)
- [ ] Sensitive data flows mapped (where does PII / secrets / credentials travel across module boundaries?)
- [ ] External attack surface reviewed (all external-facing interfaces explicitly listed and hardened)
- [ ] Auth design verified (authentication and authorisation patterns are sound and consistently enforced)
- [ ] Secrets handling design confirmed (no secrets in code, config, or logs — explicit storage strategy)

## Quality gates

- [ ] No module would produce an implementation file exceeding 250 lines
- [ ] No two modules share ownership of the same file
- [ ] All cross-module interfaces have a designated stub owner

## Compliance note

Capture compliance requirements as constraints to be enforced by the security reviewer.
Do not interpret legal obligations — confirm constraint wording with the user before encoding.
