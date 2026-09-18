from decimal import Decimal

from flask_wtf import FlaskForm
from wtforms import DecimalField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, NumberRange, Optional

from utils.currency_utils import context_aware_default_currency


class PurchaseForm(FlaskForm):
    supplier_name = StringField("اسم المورد", validators=[DataRequired()])
    supplier_phone = StringField("هاتف المورد", validators=[Optional()])
    supplier_email = StringField("بريد المورد", validators=[Optional(), Email()])
    currency = SelectField(
        "العملة",
        choices=[("AED", "درهم"), ("USD", "دولار"), ("EUR", "يورو")],
        default=context_aware_default_currency,
        validators=[DataRequired()],
    )
    exchange_rate = DecimalField("سعر الصرف (اختياري)", validators=[Optional(), NumberRange(min=0)])
    discount_amount = DecimalField("الخصم", default=Decimal(), validators=[Optional(), NumberRange(min=0)])
    tax_rate = DecimalField(
        "الضريبة %",
        default=Decimal(),
        validators=[Optional(), NumberRange(min=0, max=100)],
    )
    notes = TextAreaField("ملاحظات", validators=[Optional()])
    submit = SubmitField("حفظ")
