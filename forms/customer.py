from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Optional, Email


class CustomerForm(FlaskForm):
    name = StringField('الاسم', validators=[DataRequired()])
    name_ar = StringField('الاسم بالعربية', validators=[Optional()])
    customer_type = SelectField('النوع', choices=[
        ('regular', 'عادي'),
        ('merchant', 'تاجر'),
        ('partner', 'شريك')
    ], validators=[DataRequired()])
    phone = StringField('الهاتف', validators=[Optional()])
    email = StringField('البريد الإلكتروني', validators=[Optional(), Email()])
    address = TextAreaField('العنوان', validators=[Optional()])
    tax_number = StringField('الرقم الضريبي', validators=[Optional()])
    preferred_currency = SelectField('العملة الافتراضية', choices=[
        ('AED', 'درهم'),
        ('USD', 'دولار'),
        ('EUR', 'يورو')
    ], default='AED', validators=[Optional()])  # TODO: use Config.DEFAULT_CURRENCY
    is_active = BooleanField('نشط', default=True)
    notes = TextAreaField('ملاحظات', validators=[Optional()])
    submit = SubmitField('حفظ')

