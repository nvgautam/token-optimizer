# Oracle — Market Segment Question Bank

Apply these defaults automatically once the segment is identified. Use follow-up questions to fill gaps.

## Segment defaults

| Dimension | Consumer (B2C) | SMB | Enterprise |
|---|---|---|---|
| Compliance | GDPR (if EU), COPPA (if minors) | GDPR (if EU) | SOC2 + possible HIPAA/PCI |
| Auth | OAuth social login | Email + password, MFA optional | SSO/SAML required |
| Deployment | Cloud, mobile-first | Cloud SaaS | Cloud or on-prem option |
| Scale | Viral growth, elastic | Tens of thousands users | Hundreds of thousands, SLA |

---

## Consumer (B2C)

**Compliance follow-ups:**
- Are any users under 13? (COPPA trigger)
- Will you process EU user data? (GDPR trigger — lawful basis, right to erasure)
- Do you store payment data? (PCI trigger — prefer Stripe/Braintree passthrough)

**Auth follow-ups:**
- Which OAuth providers? (Google, Apple, Facebook — each has distinct UX implications)
- Do you need passwordless or magic-link login?
- Account deletion — must be self-service; what data is purged vs retained?

**Scale / deployment follow-ups:**
- Expected DAU at launch and at 12-month target?
- Is offline-capable mobile required, or web-only?
- CDN needed for media assets?

**UX follow-ups:**
- Onboarding — how many steps before first value? (target: ≤ 3)
- Is there a free tier? What is the conversion funnel?

---

## SMB

**Compliance follow-ups:**
- Do you process EU customer data on behalf of your SMB users? (GDPR data processor role)
- Do any verticals require specific compliance? (e.g., healthcare SMBs → HIPAA)
- Do you store or transmit payment data?

**Auth follow-ups:**
- Do SMB admins need to manage team members and roles?
- Is MFA enforced or optional per account?
- Do you need per-workspace SSO for larger SMB accounts?

**Scale / deployment follow-ups:**
- Tenancy model — shared DB with row-level isolation, or schema-per-tenant?
- Expected seats per account and total accounts?
- SLA requirement (uptime %, incident response)?

**UX follow-ups:**
- Is there an admin portal separate from the end-user interface?
- Billing — self-serve upgrade/downgrade or sales-assisted?

---

## Enterprise

**Compliance follow-ups:**
- SOC2 Type I or Type II required? Target certification date?
- HIPAA — are you a covered entity or business associate?
- PCI — do you store, process, or transmit cardholder data?
- Data residency requirements (EU, US, regional)?

**Auth follow-ups:**
- Which identity providers must be supported? (Okta, Azure AD, Ping Identity)
- SCIM provisioning required for automated user lifecycle?
- Break-glass / emergency access procedure?

**Scale / deployment follow-ups:**
- On-prem or private-cloud deployment required, or cloud-only acceptable?
- SLA tier — 99.9% or 99.99%? RPO/RTO targets?
- Peak load profile — steady or bursty?

**UX / integration follow-ups:**
- Procurement process — does it go through IT/security review?
- Audit log export required (SIEM integration)?
- Dedicated customer success or fully self-serve?
