from flask_wtf import FlaskForm
from wtforms import SelectField, DecimalField, StringField, DateField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional, NumberRange


class ReceiptForm(FlaskForm):
    customer_id = SelectField('الزبون', coerce=int, validators=[DataRequired()])
    amount = DecimalField('المبلغ', validators=[DataRequired(), NumberRange(min=0.01)])
    currency = SelectField('العملة', choices=[
        ('AED', 'درهم'),
        ('USD', 'دولار'),
        ('EUR', 'يورو')
    ], default='AED', validators=[DataRequired()])
    exchange_rate = DecimalField('سعر الصرف (اختياري)', validators=[Optional(), NumberRange(min=0)])
    payment_method = SelectField('طريقة الدفع', choices=[
        ('cash', 'نقدي'),
        ('card', 'بطاقة'),
        ('bank_transfer', 'تحويل بنكي'),
        ('cheque', 'شيك'),
        ('e_wallet', 'محفظة إلكترونية')
    ], default='cash', validators=[DataRequired()])
    reference_number = StringField('رقم المرجع', validators=[Optional()])
    cheque_number = StringField('رقم الشيك', validators=[Optional()])
    cheque_date = DateField('تاريخ الشيك', validators=[Optional()])
    bank_name = StringField('اسم البنك', validators=[Optional()])
    notes = TextAreaField('ملاحظات', validators=[Optional()])
    submit = SubmitField('حفظ')

