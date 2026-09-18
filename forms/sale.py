from decimal import Decimal

from flask_wtf import FlaskForm
from wtforms import DecimalField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, NumberRange, Optional

from utils.currency_utils import context_aware_default_currency


class SaleForm(FlaskForm):
    customer_id = SelectField("الزبون", coerce=int, validators=[DataRequired()])
    currency = SelectField(
        "العملة",
        choices=[("AED", "درهم"), ("USD", "دولار"), ("EUR", "يورو")],
        default=context_aware_default_currency,
        validators=[DataRequired()],
    )
    exchange_rate = DecimalField("سعر الصرف", default=Decimal("1.0"), validators=[Optional(), NumberRange(min=0)])
    discount_amount = DecimalField("الخصم", default=Decimal(), validators=[Optional(), NumberRange(min=0)])
    shipping_cost = DecimalField("الشحن", default=Decimal(), validators=[Optional(), NumberRange(min=0)])
    tax_rate = DecimalField(
        "الضريبة %",
        default=Decimal(),
        validators=[Optional(), NumberRange(min=0, max=100)],
    )
    payment_method = SelectField(
        "طريقة الدفع",
        choices=[
            ("", "آجل (بدون دفع)"),
            ("cash", "نقدي"),
            ("card", "بطاقة"),
            ("bank_transfer", "تحويل بنكي"),
            ("cheque", "شيك"),
            ("e_wallet", "محفظة إلكترونية"),
        ],
        validators=[Optional()],
    )
    notes = TextAreaField("ملاحظات", validators=[Optional()])
    submit = SubmitField("حفظ الفاتورة")
