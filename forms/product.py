from decimal import Decimal
from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional, NumberRange


class ProductForm(FlaskForm):
    name = StringField('الاسم', validators=[DataRequired()])
    name_ar = StringField('الاسم بالعربي', validators=[Optional()])
    commercial_name = StringField('الاسم التجاري', validators=[Optional()])
    part_number = StringField('رقم القطعة', validators=[Optional()])
    barcode = StringField('الباركود', validators=[Optional()])
    category_id = SelectField('التصنيف', coerce=int, validators=[Optional()])
    country_of_origin = StringField('بلد المنشأ', validators=[Optional()])
    regular_price = DecimalField('السعر العادي', validators=[DataRequired(), NumberRange(min=0)])
    merchant_price = DecimalField('سعر التاجر', validators=[Optional(), NumberRange(min=0)])
    partner_price = DecimalField('سعر الشريك', validators=[Optional(), NumberRange(min=0)])
    cost_price = DecimalField('سعر التكلفة', validators=[Optional(), NumberRange(min=0)])
    current_stock = DecimalField('الكمية الحالية', default=Decimal(), validators=[Optional(), NumberRange(min=0)])
    min_stock_alert = DecimalField('الحد الأدنى للتنبيه', default=Decimal(), validators=[Optional(), NumberRange(min=0)])
    unit = SelectField('الوحدة', choices=[
        ('', 'بلا'),
        ('piece', 'قطعة'),
        ('kg', 'كيلوجرام'),
        ('liter', 'لتر'),
        ('meter', 'متر'),
        ('box', 'صندوق'),
        ('set', 'طقم')
    ], default='piece', validators=[Optional()])
    warranty_period = DecimalField('فترة الكفالة', validators=[Optional(), NumberRange(min=0)])
    warranty_unit = SelectField('وحدة الكفالة', choices=[
        ('days', 'يوم'),
        ('months', 'شهر'),
        ('years', 'سنة')
    ], default='months', validators=[Optional()])
    is_returnable = SelectField('قابل للإرجاع', choices=[
        ('1', 'نعم'),
        ('0', 'لا')
    ], default='1', coerce=int, validators=[Optional()])
    return_period_days = DecimalField('فترة الإرجاع (أيام)', default=Decimal('30'), validators=[Optional(), NumberRange(min=0)])
    description = TextAreaField('الوصف', validators=[Optional()])
    notes = TextAreaField('ملاحظات', validators=[Optional()])
    submit = SubmitField('حفظ')


class ProductCategoryForm(FlaskForm):
    name = StringField('الاسم', validators=[DataRequired()])
    name_ar = StringField('الاسم بالعربي', validators=[Optional()])
    description = TextAreaField('الوصف', validators=[Optional()])
    submit = SubmitField('حفظ')

