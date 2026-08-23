from datetime import datetime
from decimal import Decimal

from flask_babel import gettext

from extensions import db
from models import Employee, PayrollTransaction, SalaryAdvance
from services.gl_posting import post_or_fail
from services.gl_service import GLService
from utils.field_validators import normalize_phone_optional
from utils.gl_reference_types import GLRef


class PayrollService:
    @staticmethod
    def _branch_tenant_id(branch_id):
        from models import Branch

        branch = db.session.get(Branch, int(branch_id))
        if not branch:
            raise ValueError(gettext("الفرع المحدد غير موجود."))
        tenant_id = getattr(branch, "tenant_id", None)
        if tenant_id is None:
            raise ValueError(gettext("الفرع المحدد غير مرتبط بشركة نشطة."))
        return int(tenant_id or 0)

    @staticmethod
    def _require_employee_tenant_id(employee):
        tenant_id = getattr(employee, "tenant_id", None)
        if tenant_id is None:
            raise ValueError(gettext("الموظف غير مرتبط بشركة — لا يمكن إتمام العملية."))
        return int(tenant_id or 0)

    @staticmethod
    def create_employee(data):

        branch_id = data.get("branch_id")

        if not branch_id:
            raise ValueError(gettext("يجب ربط الموظف بفرع محدد."))

        tenant_id = PayrollService._branch_tenant_id(branch_id)

        employee = Employee(
            name=data.get("name"),
            name_ar=data.get("name_ar"),
            phone=normalize_phone_optional(data.get("phone")),
            email=data.get("email"),
            employment_type=data.get("employment_type", "salary"),
            basic_salary=Decimal(str(data.get("basic_salary") or "0")),
            branch_id=int(branch_id),
            tenant_id=tenant_id,
            joined_date=(
                datetime.strptime(data.get("joined_date"), "%Y-%m-%d") if data.get("joined_date") else datetime.now()
            ),
        )

        db.session.add(employee)

        try:
            db.session.flush()
        except Exception:
            raise

        return employee

    @staticmethod
    def create_advance(employee_id, amount, description, user_id, actor_user=None):

        employee = Employee.query.get_or_404(employee_id)

        tenant_id = PayrollService._require_employee_tenant_id(employee)

        if actor_user is not None:
            from utils.auth_helpers import is_global_owner_user

            if not is_global_owner_user(actor_user):
                from utils.branching import branch_scope_id_for

                scoped = branch_scope_id_for(actor_user)
                if scoped is not None and employee.branch_id != scoped:
                    raise ValueError(gettext("لا يمكنك إنشاء سلفة لموظف في فرع آخر."))
                from utils.tenanting import get_active_tenant_id

                actor_tid = get_active_tenant_id(actor_user)
                if actor_tid is not None and int(employee.tenant_id) != int(actor_tid):
                    raise ValueError(gettext("الموظف لا ينتمي إلى شركتك النشطة."))

        advance = SalaryAdvance(
            employee_id=employee_id,
            amount=Decimal(amount),
            total_amount=Decimal(amount),
            deducted_amount=Decimal("0"),
            remaining_amount=Decimal(amount),
            description=description,
            created_by=user_id,
            status="approved",
            tenant_id=tenant_id,
        )

        db.session.add(advance)

        db.session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant_id)
        cash_account = GLService.get_default_liquidity_account(
            "cash",
            branch_id=employee.branch_id,
            tenant_id=tenant_id,
        )

        gl_entry = post_or_fail(
            [
                {
                    "account": "1160",
                    "concept_code": "EMPLOYEE_ADVANCES",
                    "debit": Decimal(str(amount)),
                    "credit": 0,
                    "description": f"Advance - {employee.name}",
                },
                {
                    "account": cash_account,
                    "concept_code": "CASH",
                    "debit": 0,
                    "credit": Decimal(str(amount)),
                    "description": "Cash Payment",
                },
            ],
            description=f"Salary Advance for {employee.name}",
            reference_type=GLRef.SALARY_ADVANCE,
            reference_id=advance.id,
            branch_id=employee.branch_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        advance.gl_entry_id = gl_entry.id

        try:
            db.session.flush()
        except Exception:
            raise

        return advance

    @staticmethod
    def process_payroll(
        employee_id,
        month,
        year,
        days_worked,
        allowances,
        deductions,
        user_id,
        actor_user=None,
    ):

        employee = Employee.query.get_or_404(employee_id)

        tenant_id = PayrollService._require_employee_tenant_id(employee)

        if actor_user is not None:
            from utils.auth_helpers import is_global_owner_user

            if not is_global_owner_user(actor_user):
                from utils.branching import branch_scope_id_for

                scoped = branch_scope_id_for(actor_user)
                if scoped is not None and employee.branch_id != scoped:
                    raise ValueError(gettext("لا يمكنك معالجة راتب لموظف في فرع آخر."))
                from utils.tenanting import get_active_tenant_id

                actor_tid = get_active_tenant_id(actor_user)
                if actor_tid is not None and int(employee.tenant_id) != int(actor_tid):
                    raise ValueError(gettext("الموظف لا ينتمي إلى شركتك النشطة."))

        basic_amount = Decimal(0)

        if employee.employment_type == "salary":
            basic_amount = employee.basic_salary

        else:
            basic_amount = employee.basic_salary * Decimal(days_worked)

        pending_advances = SalaryAdvance.query.filter_by(
            employee_id=employee_id,
            is_deducted=False,
            status="approved",
            tenant_id=tenant_id,
        ).all()

        # حساب إجمالي الرصيد المتبقي للسلف (من remaining_amount أو fallback آمن)
        advance_deduction_total = Decimal("0")
        for adv in pending_advances:
            remaining = Decimal(str(adv.remaining_amount or 0))
            if remaining <= Decimal("0"):
                remaining = Decimal(str(adv.total_amount or 0)) - Decimal(str(adv.deducted_amount or 0))
                if remaining < Decimal("0"):
                    remaining = Decimal("0")
            advance_deduction_total += remaining

        net_salary = basic_amount + Decimal(allowances) - Decimal(deductions) - advance_deduction_total

        # التحقق من عدم وجود راتب مكرر لنفس الموظف/الشهر/السنة
        existing = PayrollTransaction.query.filter_by(
            employee_id=employee_id,
            tenant_id=tenant_id,
            month=month,
            year=year,
        ).first()
        if existing:
            raise ValueError(gettext(f'تمت معالجة راتب الموظف "{employee.name}" لشهر {month}/{year} مسبقاً.'))

        # التحقق من أن صافي الراتب غير سالب — خصم جزئي للسلفة
        actual_deduction = advance_deduction_total  # المبلغ الذي سيتم خصمه فعلياً من السلف
        if net_salary < Decimal("0"):
            max_deductible = basic_amount + Decimal(allowances) - Decimal(deductions)
            if max_deductible <= Decimal("0"):
                raise ValueError(
                    gettext(f'صافي راتب الموظف "{employee.name}" سالب ({net_salary}). لا يمكن صرف الراتب.')
                )
            actual_deduction = max_deductible
            net_salary = Decimal("0")

        transaction = PayrollTransaction(
            employee_id=employee_id,
            month=month,
            year=year,
            basic_amount=basic_amount,
            days_worked=days_worked if employee.employment_type == "daily" else 0,
            allowances=Decimal(allowances),
            deductions=Decimal(deductions),
            advances_deducted=actual_deduction,
            net_salary=net_salary,
            branch_id=employee.branch_id,
            tenant_id=tenant_id,
            created_by=user_id,
            status="paid",
        )

        db.session.add(transaction)

        db.session.flush()

        # توزيع الخصم على السلف — يستخدم actual_deduction (ثابت) للتكرار
        remaining_to_apply = actual_deduction
        for adv in pending_advances:
            if remaining_to_apply <= Decimal("0"):
                break
            remaining = Decimal(str(adv.remaining_amount or 0))
            if remaining <= Decimal("0"):
                remaining = Decimal(str(adv.total_amount or 0)) - Decimal(str(adv.deducted_amount or 0))
                if remaining <= Decimal("0"):
                    continue
            to_deduct = min(remaining, remaining_to_apply)
            adv.deducted_amount = Decimal(str(adv.deducted_amount or 0)) + to_deduct
            adv.remaining_amount = Decimal(str(adv.total_amount or 0)) - Decimal(str(adv.deducted_amount or 0))
            remaining_to_apply -= to_deduct
            if adv.remaining_amount <= Decimal("0"):
                adv.is_deducted = True
                adv.fully_deducted_at = datetime.now()

        total_expense = basic_amount + Decimal(allowances)

        GLService.ensure_core_accounts(tenant_id=tenant_id)
        cash_account = GLService.get_default_liquidity_account(
            "cash",
            branch_id=employee.branch_id,
            tenant_id=tenant_id,
        )

        lines = [
            {
                "account": GLService.get_account_code_for_concept(
                    "PAYROLL_EXPENSE",
                    branch_id=employee.branch_id,
                    tenant_id=tenant_id,
                    fallback_key="salaries_expense",
                ),
                "concept_code": "PAYROLL_EXPENSE",
                "debit": Decimal(str(total_expense)),
                "credit": 0,
                "description": f"Salary {month}/{year} - {employee.name}",
            },
            {
                "account": cash_account,
                "concept_code": "CASH",
                "debit": 0,
                "credit": Decimal(str(net_salary)),
                "description": "Net Salary Payment",
            },
        ]

        if deductions > 0:
            lines.append(
                {
                    "account": GLService.get_account_code_for_concept(
                        "PAYROLL_PAYABLE",
                        branch_id=employee.branch_id,
                        tenant_id=tenant_id,
                        fallback_key="salaries_payable",
                    ),
                    "concept_code": "PAYROLL_PAYABLE",
                    "debit": 0,
                    "credit": Decimal(str(deductions)),
                    "description": "Salary Deductions",
                }
            )

        if actual_deduction > 0:
            lines.append(
                {
                    "account": "1160",
                    "concept_code": "EMPLOYEE_ADVANCES",
                    "debit": 0,
                    "credit": Decimal(str(actual_deduction)),
                    "description": "Advance Deduction",
                }
            )

        gl_entry = post_or_fail(
            lines,
            description=f"Payroll {month}/{year} - {employee.name}",
            reference_type=GLRef.PAYROLL,
            reference_id=transaction.id,
            branch_id=employee.branch_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        transaction.gl_entry_id = gl_entry.id

        # Post monthly accruals (end-of-service provision + leave accrual)
        try:
            PayrollService.post_payroll_accruals(employee, month, year, user_id)
        except Exception as accrual_err:
            from flask import current_app

            current_app.logger.warning(
                "Payroll accrual posting failed for employee %s %s/%s: %s",
                employee.name,
                month,
                year,
                accrual_err,
            )

        try:
            db.session.flush()
        except Exception:
            raise

        return transaction

    @staticmethod
    def _calculate_eos_monthly_provision(basic_salary, contract_type="limited"):
        """Calculate monthly end-of-service provision (UAE labor law basis).
        Limited contract: 21 days/year for first 5 years, 30 days after.
        Unlimited contract: 30 days/year.
        Monthly provision = (basic_salary / 30) * (days_per_year / 12).
        """
        from decimal import Decimal

        basic = Decimal(str(basic_salary or 0))
        if basic <= 0:
            return Decimal("0")
        days_per_year = Decimal("30") if contract_type == "unlimited" else Decimal("21")
        monthly = (basic / Decimal("30")) * (days_per_year / Decimal("12"))
        return monthly.quantize(Decimal("0.001"))

    @staticmethod
    def _calculate_leave_monthly_accrual(basic_salary, annual_leave_days=30):
        """Calculate monthly leave accrual liability.
        Monthly = (basic_salary / 30) * (annual_leave_days / 12).
        """
        from decimal import Decimal

        basic = Decimal(str(basic_salary or 0))
        if basic <= 0:
            return Decimal("0")
        days = Decimal(str(annual_leave_days or 30))
        monthly = (basic / Decimal("30")) * (days / Decimal("12"))
        return monthly.quantize(Decimal("0.001"))

    @staticmethod
    def post_payroll_accruals(employee, month, year, user_id):
        """Post monthly end-of-service and leave accrual GL entries.

        Accounting entries:
        - EOS:   Dr 6190 (END_OF_SERVICE_PROVISION expense) / Cr 2140 (END_OF_SERVICE_LIABILITY)
        - Leave: Dr 6220 (PAYROLL_EXPENSE) / Cr 2160 (LEAVE_ACCRUAL_LIABILITY)
        """
        from decimal import Decimal

        tenant_id = PayrollService._require_employee_tenant_id(employee)
        branch_id = employee.branch_id

        eos_amount = PayrollService._calculate_eos_monthly_provision(
            employee.basic_salary, getattr(employee, "contract_type", "limited")
        )
        leave_amount = PayrollService._calculate_leave_monthly_accrual(
            employee.basic_salary, getattr(employee, "annual_leave_days", 30)
        )

        if eos_amount <= Decimal("0") and leave_amount <= Decimal("0"):
            return None

        GLService.ensure_core_accounts(tenant_id=tenant_id)
        accrual_lines = []

        if eos_amount > Decimal("0"):
            accrual_lines.append(
                {
                    "account": GLService.get_account_code_for_concept(
                        "END_OF_SERVICE_PROVISION",
                        branch_id=branch_id,
                        tenant_id=tenant_id,
                        fallback_key="end_of_service_provision",
                    ),
                    "concept_code": "END_OF_SERVICE_PROVISION",
                    "debit": eos_amount,
                    "credit": 0,
                    "description": f"End of Service Provision Expense - {employee.name} {month}/{year}",
                }
            )
            accrual_lines.append(
                {
                    "account": GLService.get_account_code_for_concept(
                        "END_OF_SERVICE_LIABILITY",
                        branch_id=branch_id,
                        tenant_id=tenant_id,
                        fallback_key="end_of_service_liability",
                    ),
                    "concept_code": "END_OF_SERVICE_LIABILITY",
                    "debit": 0,
                    "credit": eos_amount,
                    "description": f"End of Service Liability - {employee.name} {month}/{year}",
                }
            )

        if leave_amount > Decimal("0"):
            accrual_lines.append(
                {
                    "account": GLService.get_account_code_for_concept(
                        "PAYROLL_EXPENSE",
                        branch_id=branch_id,
                        tenant_id=tenant_id,
                        fallback_key="salaries_expense",
                    ),
                    "concept_code": "PAYROLL_EXPENSE",
                    "debit": leave_amount,
                    "credit": 0,
                    "description": f"Leave Accrual Expense - {employee.name} {month}/{year}",
                }
            )
            accrual_lines.append(
                {
                    "account": GLService.get_account_code_for_concept(
                        "LEAVE_ACCRUAL_LIABILITY",
                        branch_id=branch_id,
                        tenant_id=tenant_id,
                        fallback_key="leave_accrual_liability",
                    ),
                    "concept_code": "LEAVE_ACCRUAL_LIABILITY",
                    "debit": 0,
                    "credit": leave_amount,
                    "description": f"Leave Accrual Liability - {employee.name} {month}/{year}",
                }
            )

        gl_entry = post_or_fail(
            accrual_lines,
            description=f"Payroll Accruals {month}/{year} - {employee.name}",
            reference_type=GLRef.PAYROLL,
            reference_id=employee.id,
            branch_id=branch_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return gl_entry

    @staticmethod
    def calculate_eosb(employee):
        """
        Calculate End-of-Service Benefits settlement amount (UAE labor law).

        Limited contract:
        - First 5 years: 21 days/year
        - After 5 years: 30 days/year for additional years
        - Max = 2 years' total salary

        Unlimited contract:
        - First 1 year: no benefit
        - Years 2-5: 21 days/year
        - After 5 years: 30 days/year

        Daily wage = basic_salary / 30.
        """
        if not employee.joined_date or not employee.termination_date:
            return Decimal("0")

        basic = Decimal(str(employee.basic_salary or 0))
        if basic <= 0:
            return Decimal("0")

        joined = employee.joined_date
        terminated = employee.termination_date
        contract_type = getattr(employee, "contract_type", "limited")
        daily_wage = basic / Decimal("30")

        total_days = (terminated - joined).days
        years = total_days // 365

        if years < 1 and contract_type == "unlimited":
            return Decimal("0")

        eligible_years = max(0, years - 1) if contract_type == "unlimited" else years

        first_five = min(eligible_years, 5)
        after_five = max(0, eligible_years - 5)

        total_benefit_days = first_five * 21 + after_five * 30
        amount = daily_wage * Decimal(str(total_benefit_days))

        max_limit = daily_wage * Decimal("730")
        if amount > max_limit:
            amount = max_limit

        return amount.quantize(Decimal("0.01"))

    @staticmethod
    def settle_eosb(employee_id, user_id):
        """
        Settle EOS for a terminated employee:
        1. Calculate EOSB amount
        2. Post GL entry: Dr 6190 (EOS Provision Expense) / Cr 2140 (EOS Liability)
        3. Return the settlement details
        """
        employee = Employee.query.get_or_404(employee_id)
        tenant_id = PayrollService._require_employee_tenant_id(employee)

        eosb_amount = PayrollService.calculate_eosb(employee)
        if eosb_amount <= Decimal("0"):
            raise ValueError(gettext("مبلغ مكافأة نهاية الخدمة صفر — لا يمكن التسوية."))

        GLService.ensure_core_accounts(tenant_id=tenant_id)

        gl_entry = post_or_fail(
            [
                {
                    "account": GLService.get_account_code_for_concept(
                        "END_OF_SERVICE_PROVISION",
                        branch_id=employee.branch_id,
                        tenant_id=tenant_id,
                        fallback_key="end_of_service_provision",
                    ),
                    "concept_code": "END_OF_SERVICE_PROVISION",
                    "debit": eosb_amount,
                    "credit": 0,
                    "description": f"EOSB Settlement - {employee.name}",
                },
                {
                    "account": GLService.get_account_code_for_concept(
                        "END_OF_SERVICE_LIABILITY",
                        branch_id=employee.branch_id,
                        tenant_id=tenant_id,
                        fallback_key="end_of_service_liability",
                    ),
                    "concept_code": "END_OF_SERVICE_LIABILITY",
                    "debit": 0,
                    "credit": eosb_amount,
                    "description": f"EOSB Settlement - {employee.name}",
                },
            ],
            description=f"EOSB Settlement - {employee.name}",
            reference_type=GLRef.PAYROLL,
            reference_id=employee.id,
            branch_id=employee.branch_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        return {
            "employee_id": employee.id,
            "employee_name": employee.name,
            "eosb_amount": eosb_amount,
            "gl_entry_id": gl_entry.id,
            "contract_type": getattr(employee, "contract_type", "limited"),
            "joined_date": str(employee.joined_date),
            "termination_date": str(employee.termination_date),
        }

    @staticmethod
    def process_termination(employee_id, termination_date, termination_reason, user_id):
        """
        Full offboarding flow:
        1. Mark employee inactive + set termination fields
        2. Deduct any remaining salary advances
        3. Settle EOSB via GL
        """
        employee = Employee.query.get_or_404(employee_id)
        tenant_id = PayrollService._require_employee_tenant_id(employee)

        if not employee.is_active:
            raise ValueError(gettext("الموظف غير نشط بالفعل."))

        if isinstance(termination_date, str):
            termination_date = datetime.strptime(termination_date, "%Y-%m-%d").date()

        employee.is_active = False
        employee.termination_date = termination_date
        employee.termination_reason = termination_reason

        pending_advances = SalaryAdvance.query.filter_by(
            employee_id=employee_id,
            is_deducted=False,
            status="approved",
            tenant_id=tenant_id,
        ).all()

        advances_cleared = Decimal("0")
        for adv in pending_advances:
            remaining = Decimal(str(adv.remaining_amount or 0))
            if remaining <= Decimal("0"):
                remaining = Decimal(str(adv.total_amount or 0)) - Decimal(str(adv.deducted_amount or 0))
                if remaining <= Decimal("0"):
                    continue
            adv.deducted_amount = Decimal(str(adv.total_amount or 0))
            adv.remaining_amount = Decimal("0")
            adv.is_deducted = True
            adv.fully_deducted_at = datetime.now()
            advances_cleared += remaining

        eosb_result = None
        try:
            eosb_result = PayrollService.settle_eosb(employee_id, user_id)
        except ValueError:
            eosb_result = None

        db.session.flush()

        return {
            "employee_id": employee.id,
            "employee_name": employee.name,
            "termination_date": str(termination_date),
            "termination_reason": termination_reason,
            "advances_cleared": advances_cleared,
            "eosb": eosb_result,
        }

    @staticmethod
    def generate_branch_payroll(branch_id, month, year, user_id):
        tenant_id = PayrollService._branch_tenant_id(branch_id)
        employees = Employee.query.filter_by(branch_id=branch_id, tenant_id=tenant_id, is_active=True).all()

        generated_count = 0

        skipped_count = 0

        for emp in employees:
            exists = PayrollTransaction.query.filter_by(
                employee_id=emp.id, tenant_id=tenant_id, month=month, year=year
            ).first()

            if exists:
                skipped_count += 1

                continue

            if emp.employment_type == "salary":
                PayrollService.process_payroll(
                    employee_id=emp.id,
                    month=month,
                    year=year,
                    days_worked=0,
                    allowances=0,
                    deductions=0,
                    user_id=user_id,
                )

                generated_count += 1

            else:
                skipped_count += 1

        return generated_count, skipped_count

    @staticmethod
    def list_employees(tenant_id=None, branch_id=None):
        from models import Employee

        query = Employee.query
        if tenant_id is not None:
            query = query.filter(Employee.tenant_id == tenant_id)
        if branch_id is not None:
            query = query.filter(Employee.branch_id == branch_id)
        return query.order_by(Employee.name).all()

    @staticmethod
    def list_branches_at_scope(tenant_id, scoped_branch_id):
        """Active branches restricted to the exact scoped branch id."""
        from models import Branch

        query = Branch.query.filter_by(id=scoped_branch_id, is_active=True)
        if tenant_id is not None:
            query = query.filter(Branch.tenant_id == tenant_id)
        return query.all()

    @staticmethod
    def list_branch_options(tenant_id=None, scoped_branch_id=None):
        from models import Branch

        query = Branch.query.filter_by(is_active=True)
        if tenant_id is not None:
            query = query.filter(Branch.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            query = query.filter(Branch.id == scoped_branch_id)
        return query.order_by(Branch.code, Branch.name).all()

    @staticmethod
    def list_active_employees(tenant_id=None, branch_id=None):
        from models import Employee

        query = Employee.query.filter_by(is_active=True)
        if tenant_id is not None:
            query = query.filter(Employee.tenant_id == tenant_id)
        if branch_id is not None:
            query = query.filter(Employee.branch_id == branch_id)
        return query.order_by(Employee.name).all()

    @staticmethod
    def advance_page_data(tenant_id=None, scoped_branch_id=None):
        from models import Employee, SalaryAdvance

        employees_query = Employee.query.filter_by(is_active=True)
        advances_query = SalaryAdvance.query.join(Employee, SalaryAdvance.employee_id == Employee.id)
        if tenant_id is not None:
            employees_query = employees_query.filter(Employee.tenant_id == tenant_id)
            advances_query = advances_query.filter(Employee.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            employees_query = employees_query.filter(Employee.branch_id == scoped_branch_id)
            advances_query = advances_query.filter(Employee.branch_id == scoped_branch_id)
        employees = employees_query.order_by(Employee.name).all()
        advance_list = advances_query.order_by(SalaryAdvance.date.desc()).limit(50).all()
        return employees, advance_list

    @staticmethod
    def process_page_data(tenant_id=None, scoped_branch_id=None):
        from models import Branch, Employee, PayrollTransaction

        employees_query = Employee.query.filter_by(is_active=True)
        branches_query = Branch.query.filter_by(is_active=True)
        transactions_query = PayrollTransaction.query
        if tenant_id is not None:
            employees_query = employees_query.filter(Employee.tenant_id == tenant_id)
            branches_query = branches_query.filter(Branch.tenant_id == tenant_id)
            transactions_query = transactions_query.filter(PayrollTransaction.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            employees_query = employees_query.filter(Employee.branch_id == scoped_branch_id)
            branches_query = branches_query.filter(Branch.id == scoped_branch_id)
            transactions_query = transactions_query.filter(PayrollTransaction.branch_id == scoped_branch_id)
        employees = employees_query.order_by(Employee.name).all()
        branches = branches_query.order_by(Branch.code, Branch.name).all()
        transactions = transactions_query.order_by(PayrollTransaction.payment_date.desc()).limit(50).all()
        return employees, branches, transactions

    @staticmethod
    def get_transaction_or_404(record_id, tenant_id=None):
        from models import PayrollTransaction

        query = PayrollTransaction.query.filter_by(id=record_id)
        if tenant_id is not None:
            query = query.filter(PayrollTransaction.tenant_id == tenant_id)
        return query.first_or_404()

    @staticmethod
    def get_employee_or_404(record_id, tenant_id=None):
        from models import Employee

        query = Employee.query.filter_by(id=record_id)
        if tenant_id is not None:
            query = query.filter(Employee.tenant_id == tenant_id)
        return query.first_or_404()

    @staticmethod
    def employee_statement_records(employee_id, tenant_id=None):
        from models import PayrollTransaction, SalaryAdvance

        advance_list_query = SalaryAdvance.query.filter_by(employee_id=employee_id)
        payments_query = PayrollTransaction.query.filter_by(employee_id=employee_id)
        if tenant_id is not None:
            advance_list_query = advance_list_query.filter(SalaryAdvance.tenant_id == tenant_id)
            payments_query = payments_query.filter(PayrollTransaction.tenant_id == tenant_id)
        return advance_list_query.all(), payments_query.all()

    @staticmethod
    def get_wps_rows(tenant_id, month, year):
        """Employees with bank details joined to their payroll transaction
        for the given period — single bulk query (fixes per-employee N+1)."""
        from models import Employee, PayrollTransaction

        rows = (
            db.session.query(Employee, PayrollTransaction)
            .join(
                PayrollTransaction,
                (PayrollTransaction.employee_id == Employee.id)
                & (PayrollTransaction.tenant_id == Employee.tenant_id)
                & (PayrollTransaction.month == month)
                & (PayrollTransaction.year == year),
            )
            .filter(
                Employee.tenant_id == tenant_id,
                Employee.is_active.is_(True),
                Employee.bank_code.isnot(None),
                Employee.iban.isnot(None),
            )
            .all()
        )
        out = []
        for emp, txn in rows:
            out.append(
                {
                    "wps_id": f"{emp.id:08d}",
                    "employee_id": emp.id,
                    "name": emp.name,
                    "iban": emp.iban,
                    "bank_code": emp.bank_code,
                    "basic_salary": str(txn.basic_amount),
                    "allowances": str(txn.allowances),
                    "net_salary": str(txn.net_salary),
                    "currency": emp.currency or "AED",
                    "payment_date": txn.payment_date.isoformat() if txn.payment_date else "",
                }
            )
        return out
