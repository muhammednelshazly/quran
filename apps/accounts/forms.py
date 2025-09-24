from django import forms
from django.contrib.auth.models import User
from .models import Halaqa, Profile


class RegisterForm(forms.Form):
    ROLE_CHOICES = (
        (Profile.ROLE_STUDENT, "طالب"),
        (Profile.ROLE_TEACHER, "معلّم"),
    )

    username = forms.CharField(max_length=150, label="اسم المستخدم")
    password1 = forms.CharField(widget=forms.PasswordInput, label="كلمة المرور")
    password2 = forms.CharField(widget=forms.PasswordInput, label="تأكيد كلمة المرور")
    role = forms.ChoiceField(choices=ROLE_CHOICES, label="الدور")
    halaqa = forms.ModelChoiceField(
        queryset=Halaqa.objects.all(),
        required=False,
        label="الحلقة (للطلاب)",
    )

    def clean_username(self):
        u = self.cleaned_data["username"]
        if User.objects.filter(username=u).exists():
            raise forms.ValidationError("اسم المستخدم موجود بالفعل.")
        return u

    def clean(self):
        data = super().clean()
        if data.get("password1") != data.get("password2"):
            self.add_error("password2", "كلمتا المرور غير متطابقتين.")
        if data.get("role") == Profile.ROLE_STUDENT and not data.get("halaqa"):
            self.add_error("halaqa", "اختيار الحلقة مطلوب للطالب.")
        return data
