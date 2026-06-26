# Market Segment Question Bank

Ask first: "Who is your primary user — consumer (B2C), small/medium business (SMB), or enterprise?
Describe them in one sentence."

Branch on the answer and apply the defaults below without prompting the user to confirm them.

---

## Consumer

**Defaults applied automatically**
| Dimension | Default |
|---|---|
| Compliance | GDPR if EU users present; COPPA if users may be under 13 |
| Auth | OAuth social login (Google / Apple / GitHub) |
| Deployment | Cloud, mobile-first |
| Scale | Viral growth model — elastic, burst-tolerant |

**Follow-up questions**
- Are any users under 13? If yes, COPPA parental consent and data minimisation apply.
- Are you storing payment details, or passing through to a processor (Stripe, etc.)?
- What personal data do you persist — profile, behavioural, health, or location?
- Do you plan a free tier with paid upgrade? If yes, what gates the upgrade?
- Will users generate content others can see? If yes, moderation strategy?

---

## SMB

**Defaults applied automatically**
| Dimension | Default |
|---|---|
| Compliance | GDPR if any EU customers; explicit "none" otherwise |
| Auth | Email + password, MFA optional at account level |
| Deployment | Cloud SaaS, multi-tenant by default |
| Scale | Tens of thousands of users; steady growth, no burst assumption |

**Follow-up questions**
- Do customers need per-tenant data isolation, or is shared-schema acceptable?
- Do any customers have their own compliance obligations (e.g. healthcare, finance)?
- Will you offer a self-serve trial? If yes, what converts trial to paid?
- Do customers need audit logs or activity exports for their own compliance?
- Is there a reseller or white-label requirement?

---

## Enterprise

**Defaults applied automatically**
| Dimension | Default |
|---|---|
| Compliance | SOC 2 Type II required; HIPAA if health data; PCI-DSS if payment data |
| Auth | SSO / SAML required; SCIM for user provisioning |
| Deployment | Cloud or on-premises option; customer may dictate region |
| Scale | Hundreds of thousands of users; 99.9%+ SLA; change-management window required |

**Follow-up questions**
- Which compliance certifications do your buyers require at contract time (SOC 2, ISO 27001, FedRAMP)?
- Do customers require data residency in a specific region or country?
- Will you support on-premises / air-gapped deployment, or cloud-only?
- How are user accounts provisioned — SCIM, LDAP sync, or manual?
- What is the expected incident response SLA (P1 response time, RTO, RPO)?
