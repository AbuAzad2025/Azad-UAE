"""
ملء profit_centers من البيانات الموجودة
يمكن تشغيلها بأمان - ستتحقق من البيانات الموجودة أولاً
"""
import os
os.environ['FLASK_APP'] = 'app.py'
from app import create_app
from extensions import db
from datetime import datetime, timezone

app = create_app()

with app.app_context():
    from models.profit_center import ProfitCenter
    from models.branch import Branch
    from models.cost_center import CostCenter
    from models.tenant import Tenant
    from sqlalchemy import text

    print("\n" + "="*70)
    print("ملء جدول profit_centers من البيانات الموجودة")
    print("="*70)

    # الخطوة 1: التحقق من البيانات الموجودة
    print("\n1. التحقق من الوضع الحالي:")

    profit_centers_count = db.session.query(ProfitCenter).count()
    print(f"   عدد profit_centers الموجودة: {profit_centers_count}")

    branches = db.session.query(Branch).all()
    print(f"   عدد branches: {len(branches)}")

    cost_centers = db.session.query(CostCenter).all()
    print(f"   عدد cost_centers: {len(cost_centers)}")

    tenants = db.session.query(Tenant).all()
    print(f"   عدد tenants: {len(tenants)}")

    if profit_centers_count > 0:
        print("\n   ⚠️  profit_centers مملوءة بالفعل!")
    else:
        # الخطوة 2: إنشاء profit_centers من cost_centers
        print("\n2. إنشاء profit_centers من cost_centers الموجودة:")

        created_count = 0
        errors = []

        for cc in cost_centers:
            try:
                # تحقق من عدم وجود profit_center بنفس الكود
                existing = db.session.query(ProfitCenter).filter_by(
                    tenant_id=cc.tenant_id,
                    code=cc.code
                ).first()

                if existing:
                    print(f"   ⏭️  {cc.code} موجود بالفعل - تخطي")
                    continue

                # إنشء profit_center جديد
                pc = ProfitCenter(
                    tenant_id=cc.tenant_id,
                    code=cc.code,
                    name_ar=cc.name_ar,
                    name_en=cc.name_en or f"Profit Center {cc.code}",
                    level=cc.level if hasattr(cc, 'level') else 0,
                    is_active=True,
                    description=f"Created from Cost Center {cc.code}",
                )

                db.session.add(pc)
                created_count += 1
                print(f"   ✅ {cc.code} - {cc.name_ar}")

            except Exception as e:
                errors.append(f"{cc.code}: {str(e)}")
                print(f"   ❌ {cc.code} - خطأ: {str(e)}")

        # حفظ التغييرات
        if created_count > 0:
            try:
                db.session.commit()
                print(f"\n   ✅ تم إنشاء {created_count} profit_center بنجاح")
            except Exception as e:
                db.session.rollback()
                print(f"\n   ❌ خطأ في الحفظ: {str(e)}")

        if errors:
            print(f"\n   ⚠️  أخطاء: {len(errors)}")
            for error in errors:
                print(f"      - {error}")

        # الخطوة 3: إنشاء profit_centers من branches
        print("\n3. إنشاء profit_centers من branches الموجودة:")

        created_from_branches = 0
        for branch in branches:
            try:
                # تحقق من عدم وجود profit_center بنفس الكود
                existing = db.session.query(ProfitCenter).filter_by(
                    tenant_id=branch.tenant_id,
                    code=f"PC-{branch.code}"
                ).first()

                if existing:
                    print(f"   ⏭️  PC-{branch.code} موجود بالفعل")
                    continue

                # إنشء profit_center جديد للفرع
                pc = ProfitCenter(
                    tenant_id=branch.tenant_id,
                    code=f"PC-{branch.code}",
                    name_ar=f"مركز ربح {branch.name}",
                    name_en=f"Profit Center {branch.name}",
                    level=0,
                    is_active=True,
                    description=f"Profit center for branch {branch.name}",
                )

                db.session.add(pc)
                created_from_branches += 1
                print(f"   ✅ PC-{branch.code} - {branch.name}")

            except Exception as e:
                print(f"   ❌ PC-{branch.code} - خطأ: {str(e)}")

        # حفظ التغييرات
        if created_from_branches > 0:
            try:
                db.session.commit()
                print(f"\n   ✅ تم إنشاء {created_from_branches} profit_center من branches")
            except Exception as e:
                db.session.rollback()
                print(f"\n   ❌ خطأ في الحفظ: {str(e)}")

    # الخطوة 4: التحقق النهائي
    print("\n4. التحقق النهائي:")
    final_count = db.session.query(ProfitCenter).count()
    print(f"   عدد profit_centers الآن: {final_count}")

    if final_count > 0:
        print("\n   📋 profit_centers الموجودة:")
        for pc in db.session.query(ProfitCenter).limit(10):
            print(f"      - {pc.code}: {pc.name_ar}")

    print("\n" + "="*70)
    print("اكتمل")
    print("="*70)

