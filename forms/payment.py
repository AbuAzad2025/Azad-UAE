from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    DecimalField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, NumberRange, Optional

from utils.currency_utils import context_aware_default_currency


class ReceiptForm(FlaskForm):
    customer_id = SelectField("الزبون", coerce=int, validators=[DataRequired()])
    amount = DecimalField("المبلغ", validators=[DataRequired(), NumberRange(min=0.01)])
    currency = SelectField(
        "العملة",
        choices=[("AED", "درهم"), ("USD", "دولار"), ("EUR", "يورو")],
        default=context_aware_default_currency,
        validators=[DataRequired()],
    )
    exchange_rate = DecimalField("سعر الصرف (اختياري)", validators=[Optional(), NumberRange(min=0)])
    payment_method = SelectField(
        "طريقة الدفع",
        choices=[
            ("cash", "نقدي"),
            ("card", "بطاقة"),
            ("bank_transfer", "تحويل بنكي"),
            ("cheque", "شيك"),
            ("e_wallet", "محفظة إلكترونية"),
        ],
        default="cash",
        validators=[DataRequired()],
    )
    reference_number = StringField("رقم المرجع", validators=[Optional()])
    cheque_number = StringField("رقم الشيك", validators=[Optional()])
    cheque_date = DateField("تاريخ الشيك", validators=[Optional()])
    bank_name = StringField("اسم البنك", validators=[Optional()])
    notes = TextAreaField("ملاحظات", validators=[Optional()])
    submit = SubmitField("حفظ")
