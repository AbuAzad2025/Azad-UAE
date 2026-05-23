from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, DecimalField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional, NumberRange, Email


class PurchaseForm(FlaskForm):
    supplier_name = StringField('اسم المورد', validators=[DataRequired()])
    supplier_phone = StringField('هاتف المورد', validators=[Optional()])
    supplier_email = StringField('بريد المورد', validators=[Optional(), Email()])
    currency = SelectField('العملة', choices=[
        ('AED', 'درهم'),
        ('USD', 'دولار'),
        ('EUR', 'يورو')
    ], default='AED', validators=[DataRequired()])
    exchange_rate = DecimalField('سعر الصرف (اختياري)', validators=[Optional(), NumberRange(min=0)])
    discount_amount = DecimalField('الخصم', default=0, validators=[Optional(), NumberRange(min=0)])
    tax_rate = DecimalField('الضريبة %', default=0, validators=[Optional(), NumberRange(min=0, max=100)])
    notes = TextAreaField('ملاحظات', validators=[Optional()])
    submit = SubmitField('حفظ')

