from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    username = StringField("اسم المستخدم", validators=[DataRequired(), Length(min=3, max=50)])
    password = PasswordField("كلمة المرور", validators=[DataRequired()])
    remember = BooleanField("تذكرني")
    submit = SubmitField("تسجيل الدخول")
