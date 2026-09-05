"""Payroll action pack — monthly calculation (read-only) + approval via PayrollService.

Independent domain module: handlers + command patterns + help lines live
here and are wired by ``ai_knowledge.actions``. Calculation never writes —
it aggregates basic salary, pending advances, and existing transactions.
Approval delegates every employee to ``PayrollService.process_payroll``
(duplicate guard, advance apportioning, GL posting, accruals) inside one
``atomic_transaction``, with per-employee error isolation so one bad record
never blocks the whole run. Permission mirror of routes/payroll.py:
``manage_payroll``.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from ai_knowledge.actions.base import (
    ActionResult,
    actor,
    atomic_transaction,
    audit,
    escape_like,
    pack_error,
    tenant_guard,
)

PERMISSION = "manage_payroll"

HELP_LINES = [
    "💰 **الرواتب:** `مسير الرواتب: الشهر, السنة` | `اعتماد الرواتب: الشهر, السنة`",
]


def _parse_month_year(body: str) -> dict[str, Any]:
    parts = [p.strip() for p in body.split(",")]
    args: dict[str, Any] = {}
    numbers = []
    for part in parts:
        numbers.extend(re.findall(r"\d+", part))
    ints = [int(n) for n in numbers]
    for value in ints:
        if 1 <= value <= 12 and "month" not in args:
            args["month"] = value
        elif 2000 <= value <= 2100 and "year" not in args:
            args["year"] = value
    if "year" not in args:
        args["year"] = datetime.now().year
    return args


def _parse_calculate(body: str) -> tuple[str, dict[str, Any]] | None:
    return "calculate_monthly_payroll", _parse_month_year(body)


def _parse_approve(body: str) -> tuple[str, dict[str, Any]] | None:
    return "approve_and_post_payroll", _parse_month_year(body)


PATTERNS = [
    (
        re.compile(r"^(مسير\s*الرواتب|حساب\s*الرواتب|كشف\s*الرواتب|رواتب|payroll)\s*[:：=]\s*(.+)$", re.IGNORECASE),
        lambda m: _parse_calculate(m.group(2)),
    ),
    (
        re.compile(
            r"^(اعتماد\s*الرواتب|صرف\s*الرواتب|ترحيل\s*الرواتب|approve\s*payroll)\s*[:：=]\s*(.+)$",
            re.IGNORECASE,
        ),
        lambda m: _parse_approve(m.group(2)),
    ),
]


def _resolve_branch(tid: int, branch_id: int | None):
    """Active tenant branch by id (None when not requested)."""
    if not branch_id:
        return None
    from models import Branch

    return Branch.query.filter_by(id=int(branch_id), tenant_id=tid, is_active=True).first()


def _pending_advances_total(employee_id: int, tenant_id: int) -> Decimal:
    """Sum of undeducted approved advances (read-only preview math)."""
    from models import SalaryAdvance

    advances = SalaryAdvance.query.filter_by(
        employee_id=employee_id,
        is_deducted=False,
        status="approved",
        tenant_id=tenant_id,
    ).all()
    total = Decimal("0")
    for adv in advances:
        remaining = Decimal(str(adv.remaining_amount or 0))
        if remaining <= 0:
            remaining = Decimal(str(adv.total_amount or 0)) - Decimal(str(adv.deducted_amount or 0))
        total += max(remaining, Decimal("0"))
    return total


def _already_posted(employee_id: int, tenant_id: int, month: int, year: int) -> bool:
    from models import PayrollTransaction

    return (
        PayrollTransaction.query.filter_by(employee_id=employee_id, tenant_id=tenant_id, month=month, year=year).first()
        is not None
    )


def _preview_employee(employee, tenant_id: int, days_default: float = 0) -> dict[str, Any]:
    """Read-only net computation mirroring process_payroll math (no writes)."""
    basic = Decimal(str(employee.basic_salary or 0))
    if (employee.employment_type or "salary") != "salary":
        if not days_default:
            return {"name": employee.name, "skipped": True, "reason": "يحتاج أيام الدوام (غير شهري)"}
        basic = basic * Decimal(str(days_default))
    advances = _pending_advances_total(employee.id, tenant_id)
    net = basic - advances
    return {
        "id": employee.id,
        "name": employee.name,
        "basic": float(basic),
        "advances": float(advances),
        "net": float(max(net, Decimal("0"))),
        "wps_eligible": bool(getattr(employee, "iban", None) and getattr(employee, "bank_code", None)),
    }


def _calculate_monthly_payroll(args: dict) -> ActionResult:
    try:
        from services.payroll_service import PayrollService

        tid, guard = tenant_guard()
        if guard:
            return guard
        month_raw, year_raw = args.get("month"), args.get("year")
        if month_raw is None or year_raw is None:
            return ActionResult(False, "⚠️ الشهر والسنة مطلوبان (مثال: 9, 2026)")
        month, year = int(month_raw), int(year_raw)
        branch = _resolve_branch(tid, args.get("branch_id"))
        if args.get("branch_id") and branch is None:
            return ActionResult(False, "⚠️ الفرع المحدد غير موجود في منشأتك")
        employees = PayrollService.list_active_employees(tenant_id=tid, branch_id=branch.id if branch else None)
        name_filter = str(args.get("employee_name") or "").strip().lower()
        if name_filter:
            employees = [e for e in employees if name_filter in (e.name or "").lower()]
        if not employees:
            return ActionResult(False, "⚠️ لا يوجد موظفون نشطون ضمن النطاق المحدد")
        rows, posted, total_net = [], 0, 0.0
        for employee in employees:
            if _already_posted(employee.id, tid, month, year):
                posted += 1
                rows.append({"name": employee.name, "status": "posted"})
                continue
            preview = _preview_employee(employee, tid)
            if preview.get("skipped"):
                rows.append({"name": employee.name, "status": "needs_days", "reason": preview["reason"]})
                continue
            total_net += preview["net"]
            rows.append({**preview, "status": "ready"})
        ready = sum(1 for r in rows if r.get("status") == "ready")
        wps = sum(1 for r in rows if r.get("wps_eligible") and r.get("status") == "ready")
        return ActionResult(
            True,
            f"مسير {month}/{year}: {ready} جاهز للاعتماد (صافي: {total_net:,.2f} درهم) | "
            f"{posted} مرحّل مسبقاً | مؤهل WPS: {wps}",
            {"month": month, "year": year, "rows": rows, "total_net": total_net, "wps_eligible": wps},
            "payroll_calculate",
            PERMISSION,
        )
    except Exception as e:
        return pack_error("calculate_monthly_payroll", e, args)


def _match_adjustment(adjustments: list, employee_name: str) -> dict:
    lowered = (employee_name or "").lower()
    for adj in adjustments or []:
        if isinstance(adj, dict) and lowered and lowered in str(adj.get("employee_name") or "").lower():
            return adj
    return {}


def _approve_and_post_payroll(args: dict) -> ActionResult:
    try:
        from services.payroll_service import PayrollService

        tid, guard = tenant_guard()
        if guard:
            return guard
        user = actor()
        if user is None or getattr(user, "id", None) is None:
            return ActionResult(False, "🚫 لا يمكن اعتماد الرواتب دون مستخدم موثّق — يرجى تسجيل الدخول")
        month_raw, year_raw = args.get("month"), args.get("year")
        if month_raw is None or year_raw is None:
            return ActionResult(False, "⚠️ الشهر والسنة مطلوبان (مثال: 9, 2026)")
        month, year = int(month_raw), int(year_raw)
        branch = _resolve_branch(tid, args.get("branch_id"))
        if args.get("branch_id") and branch is None:
            return ActionResult(False, "⚠️ الفرع المحدد غير موجود في منشأتك")
        employees = PayrollService.list_active_employees(tenant_id=tid, branch_id=branch.id if branch else None)
        if not employees:
            return ActionResult(False, "⚠️ لا يوجد موظفون نشطون ضمن النطاق المحدد")
        adjustments = args.get("adjustments") or []
        posted, skipped, failed = [], [], []
        total_net = Decimal("0")
        with atomic_transaction("ai_approve_payroll"):
            for employee in employees:
                if _already_posted(employee.id, tid, month, year):
                    skipped.append(employee.name)
                    continue
                adj = _match_adjustment(adjustments, employee.name)
                emp_type = employee.employment_type or "salary"
                days = adj.get("days_worked")
                if days is None:
                    days = 0 if emp_type == "salary" else None
                if days is None:
                    failed.append({"name": employee.name, "error": "أيام الدوام مطلوبة لغير الشهري"})
                    continue
                try:
                    txn = PayrollService.process_payroll(
                        employee_id=employee.id,
                        month=month,
                        year=year,
                        days_worked=days,
                        allowances=float(adj.get("allowances") or 0),
                        deductions=float(adj.get("deductions") or 0),
                        user_id=user.id,
                        actor_user=user,
                    )
                    posted.append(employee.name)
                    total_net += Decimal(str(txn.net_salary or 0))
                except ValueError as ve:
                    failed.append({"name": employee.name, "error": str(ve)})
        wps_rows = PayrollService.get_wps_rows(tid, month, year)
        audit(
            "approve",
            "PayrollTransaction",
            None,
            {"month": month, "year": year, "posted": len(posted), "total_net": float(total_net)},
        )
        summary = (
            f"تم اعتماد رواتب {month}/{year}: {len(posted)} موظف (صافي: {float(total_net):,.2f} درهم) | "
            f"ملف WPS: {len(wps_rows)} سطر"
        )
        if skipped:
            summary += f" | متخطى (مرحّل): {len(skipped)}"
        if failed:
            summary += f" | فشل: {len(failed)}"
        return ActionResult(
            True,
            summary,
            {
                "month": month,
                "year": year,
                "posted": posted,
                "skipped": skipped,
                "failed": failed,
                "total_net": float(total_net),
                "wps_rows": len(wps_rows),
            },
            "payroll_approve",
            PERMISSION,
        )
    except Exception as e:
        return pack_error("approve_and_post_payroll", e, args)


def register(register_fn) -> None:
    """Register this pack's actions on the dispatcher registry."""
    register_fn("calculate_monthly_payroll", _calculate_monthly_payroll, PERMISSION, "احتساب مسير الرواتب (قراءة فقط)")
    register_fn(
        "approve_and_post_payroll",
        _approve_and_post_payroll,
        PERMISSION,
        "اعتماد وترحيل الرواتب مع القيود",
        confirm_required=True,
    )


def resolve_employee(tenant_id: int, name: str):
    """First active tenant employee whose name contains ``name`` (or None)."""
    from models import Employee

    safe = escape_like((name or "").strip())
    if not safe:
        return None
    return (
        Employee.query.filter(
            Employee.tenant_id == tenant_id,
            Employee.is_active,
            Employee.name.ilike(f"%{safe}%", escape="\\"),
        )
        .order_by(Employee.name)
        .first()
    )
