# Future Roadmap: Payroll Payment AI Audit

**Status:** Planned — awaiting business approval  
**Recommended Priority:** MEDIUM (Phase 3)  
**Estimated Effort:** 3-4 sprints

---

## 1. Goal

Build an **AI-powered audit layer** for payroll payments that automatically detects anomalies, validates compliance with UAE labor law, and flags suspicious patterns before payments are disbursed. The system acts as a **pre-payment reviewer**, not a replacement for human approval.

---

## 2. Current Problem

### 2.1 Manual Payroll Review Bottleneck
- Payroll processing requires manual review of:
  - Overtime calculations vs. contract hours.
  - Leave balance deductions (annual, sick, unpaid).
  - End-of-service (EOS) gratuity calculations.
  - WPS (Wage Protection System) compliance formatting.
- Human reviewers are prone to fatigue errors, especially during bulk monthly runs.

### 2.2 No Automated Anomaly Detection
- The system currently records `PayrollTransaction` and `SalaryAdvance` but does not:
  - Compare current month pay to historical averages.
  - Flag employees with sudden 50%+ pay changes.
  - Detect duplicate payments or double advances.
  - Validate UAE Labor Law limits (e.g., max 2 hours/day overtime, 150% rate).

### 2.3 Compliance Risk
- UAE Ministry of Human Resources and Emiratisation (MOHRE) penalties for:
  - Late salary payments (must be within 1 month of due date).
  - Incorrect WPS file formatting.
  - Unregistered employees in the system.
- No automated pre-submission validation exists.

---

## 3. Business Decision Required

### Decision 1: AI Scope — Anomaly Detection vs. Full Automation
**Question:** Should the AI **flag anomalies for human review** or **auto-correct and post**?

| Option | Pros | Cons |
|--------|------|------|
| Flag only (recommend) | Human remains in control; low risk of incorrect auto-corrections | Slower; requires reviewer availability |
| Auto-correct with override | Faster processing | High risk if AI miscalculates; liability issue |

**Recommended:** **Flag only** with severity levels (Info, Warning, Critical). Critical flags block payment until manually overridden.

### Decision 2: WPS Integration Depth
**Question:** Should the AI audit layer validate **WPS file format** before bank submission?

| Option | Pros | Cons |
|--------|------|------|
| Yes, validate format | Prevents bank rejection; reduces retry cycles | WPS format changes require AI model updates |
| No, separate WPS tool | Decouples AI from regulatory format | Misses an opportunity for unified validation |

**Recommended:** Yes, include WPS format validation as a rule-based (not ML) check within the audit pipeline.

### Decision 3: Data Privacy & Employee Consent
**Question:** Does using AI to analyze payroll data require employee consent under UAE data protection law?

**Recommended:** Consult legal counsel. From a technical standpoint:
- AI runs entirely on the server (no third-party API for payroll data).
- Audit logs are internal; no PII leaves the tenant's database.
- Document the AI as an "internal calculation tool", not a third-party service.

---

## 4. Technical Approach

### 4.1 Architecture Overview

```
Payroll Run Created
       |
       v
[Rule Engine] --static checks--> OK / Flag
       |
       v
[AI Anomaly Detector] --ML checks--> OK / Flag
       |
       v
[Compliance Validator] --UAE law checks--> OK / Flag
       |
       v
[Audit Report] --severity summary--> Human Reviewer
       |
       v
[Payment Gateway / WPS Export]
```

### 4.2 Component 1: Rule Engine (Static Checks)

```python
class PayrollRuleEngine:
    RULES = [
        # Overtime cap
        {'id': 'OT_001', 'check': lambda p: p.overtime_hours <= 2 * p.work_days,
         'message': 'Overtime exceeds 2 hours/day limit', 'severity': 'critical'},
        # Minimum wage
        {'id': 'MIN_WAGE', 'check': lambda p: p.net_pay >= 0,
         'message': 'Net pay is negative', 'severity': 'critical'},
        # Duplicate payment
        {'id': 'DUP_001', 'check': lambda p: not PayrollTransaction.query.filter_by(
            employee_id=p.employee_id, period_month=p.period_month, period_year=p.period_year
         ).first(),
         'message': 'Duplicate payroll transaction for period', 'severity': 'critical'},
        # Advance vs net pay
        {'id': 'ADV_001', 'check': lambda p: p.total_advances <= p.basic_salary * Decimal('0.5'),
         'message': 'Total advances exceed 50% of basic salary', 'severity': 'warning'},
        # Leave balance negative
        {'id': 'LEAVE_001', 'check': lambda p: p.employee.annual_leave_balance >= 0,
         'message': 'Negative annual leave balance', 'severity': 'warning'},
    ]
```

### 4.3 Component 2: AI Anomaly Detector (ML-Based)

```python
class PayrollAnomalyDetector:
    """
    Uses tenant-specific historical payroll data to detect outliers.
    No external AI service required — runs locally using scikit-learn.
    """

    def train(self, tenant_id):
        """Train an Isolation Forest on last 12 months of payroll data."""
        from sklearn.ensemble import IsolationForest
        data = self._get_historical_features(tenant_id)
        self.model = IsolationForest(contamination=0.05, random_state=42)
        self.model.fit(data)
        # Persist model per tenant (ai_knowledge/models/payroll_anomaly_<tenant_id>.pkl)

    def predict(self, payroll_run):
        """Returns anomaly score (-1 = outlier, 1 = normal)."""
        features = self._extract_features(payroll_run)
        score = self.model.decision_function([features])[0]
        is_outlier = self.model.predict([features])[0] == -1
        return {'score': score, 'is_outlier': is_outlier}
```

**Features used:**
- `basic_salary` vs 12-month average.
- `overtime_hours` vs 12-month average.
- `total_deductions` vs 12-month average.
- `net_pay` vs 12-month average.
- `days_worked` vs contract days.
- `advances_taken` vs historical average.

### 4.4 Component 3: UAE Compliance Validator

```python
class UAEComplianceValidator:
    """Hardcoded UAE Labor Law rules (not ML)."""

    def validate(self, payroll_run):
        flags = []
        for emp_payroll in payroll_run.lines:
            # Gratuity calculation (21 days basic for first 5 years, 30 days after)
            if emp_payroll.is_eos:
                expected_gratuity = self._calculate_gratuity(emp_payroll.employee)
                if abs(emp_payroll.gratuity_amount - expected_gratuity) > Decimal('1'):
                    flags.append({
                        'rule': 'EOS_001',
                        'message': 'Gratuity amount does not match UAE labor law formula',
                        'severity': 'critical'
                    })
            # Late payment (payroll date > end_of_month + 1 month)
            if payroll_run.payment_date > payroll_run.period_end + timedelta(days=30):
                flags.append({
                    'rule': 'LATE_PAY',
                    'message': 'Payment date exceeds 1-month legal deadline',
                    'severity': 'warning'
                })
        return flags
```

### 4.5 Component 4: Audit Report & UI

```python
class PayrollAuditReport(db.Model):
    __tablename__ = 'payroll_audit_reports'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    payroll_run_id = db.Column(db.Integer, db.ForeignKey('payrolls.id'), nullable=False, index=True)

    total_checks = db.Column(db.Integer, default=0)
    info_count = db.Column(db.Integer, default=0)
    warning_count = db.Column(db.Integer, default=0)
    critical_count = db.Column(db.Integer, default=0)

    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
```

**UI Workflow:**
1. User clicks "Process Payroll".
2. System generates `PayrollAuditReport`.
3. User sees dashboard: green (0 critical), yellow (warnings), red (criticals).
4. Criticals block "Confirm Payment" button.
5. User can override a critical with a reason (logged in `notes`).

---

## 5. Migration Risk

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| AI model flags legitimate changes as anomalies | Medium | Medium | Tune `contamination` parameter; allow user feedback to retrain |
| Historical payroll data is insufficient for new tenants | High | Low | For tenants < 3 months old, skip ML checks; run rule engine only |
| Performance: training model on every payroll run | Low | Medium | Train once per month (cron job); cache model file per tenant |
| sklearn dependency increases deployment size | Low | Low | Already installed via AI module; no new dependency |
| False sense of security — users trust AI blindly | Medium | High | UI emphasizes "AI assists review, does not replace it"; require human approval for all runs |

---

## 6. Testing Plan

### 6.1 Unit Tests
- `test_overtime_cap_flag()` — 3 hours/day triggers critical.
- `test_negative_net_pay_flag()` — negative net pay triggers critical.
- `test_duplicate_payment_flag()` — second payroll for same period triggers critical.
- `test_anomaly_detector_training()` — model trains on 12 months without error.
- `test_anomaly_outlier_detection()` — 200% salary increase flagged as outlier.

### 6.2 Integration Tests
- Full payroll run → audit report generated → criticals block payment → override → payment proceeds.
- WPS file export after clean audit report.
- Compliance validator with EOS gratuity edge cases (5-year boundary).

### 6.3 Load Tests
- Run audit on 500-employee payroll. Target: < 5 seconds for rule engine + anomaly detection.

### 6.4 User Acceptance Tests
- Finance team reviews flagged payrolls and confirms accuracy of flags.
- HR team validates that override workflow logs reasons correctly.

---

## 7. Rollback Strategy

1. **Feature flag:** `ENABLE_PAYROLL_AI_AUDIT` (default `False`).
2. **Additive only:** New `payroll_audit_reports` table; no changes to existing `payrolls` or `payroll_transactions`.
3. **Code rollback:** Remove audit calls from payroll processing route; payments proceed without AI checks.
4. **Model rollback:** Delete `.pkl` model files in `ai_knowledge/models/`; system falls back to rule engine only.
5. **Data safety:** Audit reports are audit-only; deleting them does not affect financial records.

---

## 8. Recommended Priority

**MEDIUM (Phase 3)**

Rationale:
- Improves operational efficiency and reduces compliance risk.
- Not as urgent as WAC (financial accuracy) or Dynamic GL Mapping (tenant flexibility).
- High value for large tenants with 50+ employees.
- Can be built incrementally: start with **Rule Engine (Phase 1)**, add **ML Anomaly Detection (Phase 2)**, then **WPS Compliance (Phase 3)**.

**Dependencies:**
- Payroll module must be fully functional (already true).
- AI infrastructure (`ai_knowledge`, model persistence) already exists.

**Suggested Start Date:** Parallel with Dynamic GL Mapping (Phase 3). Rule engine can ship first as a quick win.

---

*Roadmap document created: June 4, 2026*
