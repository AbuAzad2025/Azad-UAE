# Onboarding Guide — AZAD Intelligent Systems

## 1. Pre-Arrival

| Task | Owner | Timing |
|------|-------|--------|
| Issue GitHub access | CTO | Before day 1 |
| Issue Slack invite | CTO | Before day 1 |
| Prepare workstation | HR / CTO | Before day 1 |
| Send welcome email with handbook link | HR | Before day 1 |
| Assign buddy (senior engineer) | CTO | Before day 1 |

## 2. Day 1 — Orientation

| Time | Activity | Owner |
|------|----------|-------|
| 09:00 | Welcome, office tour, introductions | Buddy |
| 10:00 | Handbook review + Q&A | HR |
| 11:00 | Account setup: GitHub, Slack, email, VPN | DevOps |
| 12:00 | Lunch with team | — |
| 13:00 | GRIMOIRE deep dive (engineering standards) | CTO |
| 14:00 | Security policy + tenant isolation rules | Security Officer |
| 15:00 | Environment setup: clone repo, install dependencies, run tests | Buddy |
| 16:00 | First commit: fix a typo or documentation issue | New hire |

## 3. Week 1 — Environment & Codebase

| Day | Task | Goal |
|-----|------|------|
| 1 | GRIMOIRE + Security + First commit | Understand non-negotiables |
| 2 | Read `docs/TECHNICAL_REFERENCE.md` and `docs/ARCHITECTURE.md` | Understand system architecture |
| 3 | Trace a sale from `routes/sales.py` → `services/sale_service.py` → `models/sale.py` | Understand request flow |
| 4 | Run full test suite: `pytest tests/unit -q` | Verify environment |
| 5 | Review open PRs (if any) and ask questions | Learn review culture |

## 4. Week 2 — First Feature

| Day | Task |
|-----|------|
| 1 | Pick a "good first issue" from backlog |
| 2 | Write failing test first (TDD) |
| 3 | Implement feature in `services/` and `routes/` |
| 4 | Run tests, fix lint, fix type checks |
| 5 | Submit for review; address feedback |

## 5. Month 1 — Independence

| Week | Milestone |
|------|-----------|
| 3 | Complete first feature independently (end-to-end) |
| 4 | Participate in on-call rotation shadowing |

## 6. Tools and Access

| Tool | Purpose | URL / Command |
|------|---------|---------------|
| GitHub | Source control | https://github.com/AbuAzad2025/Azad-UAE |
| Slack | Team communication | #engineering, #support, #general |
| CI/CD | GitHub Actions | `.github/workflows/ci.yml` |
| Monitoring | Application health | `routes/owner/monitoring.py` |
| Error tracking | Sentry (roadmap) | — |

## 7. Buddy System

Every new hire is assigned a buddy for the first 30 days.

| Buddy Responsibility | Frequency |
|----------------------|-----------|
| Daily check-in | Every day for week 1 |
| Weekly 1:1 | Weeks 2–4 |
| Code review pairing | First 2 PRs |
| Career path discussion | End of month 1 |

## 8. Checklist — First 30 Days

- [ ] Read `docs/GRIMOIRE.md` and sign acknowledgment
- [ ] Read `docs/SECURITY_AND_TENANCY.md` (or equivalent)
- [ ] Set up local environment and run tests
- [ ] Complete security training (phishing, password manager)
- [ ] Attend product demo (walkthrough of all modules)
- [ ] Complete first end-to-end feature
- [ ] Shadow support ticket resolution (2 tickets)
- [ ] Attend team retrospective
- [ ] Receive first performance feedback

## 9. Contact

AZAD Intelligent Systems
Email: rafideen.ahmadghannam@gmail.com
