from django import forms
from .models import DailyMemorization, Review, Attendance

class DailyMemorizationForm(forms.ModelForm):
    class Meta:
        model = DailyMemorization
        fields = ['student','date','from_surah','from_ayah','to_surah','to_ayah','mastery']

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['student','date','surah_or_juz','mastery']

class AttendanceForm(forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ['student','date','status']



# tracker/forms.py
from django import forms
from django.contrib.auth.models import User
from apps.accounts.models import Profile, Halaqa  # عدّل الاستيراد حسب مسارك الفعلي

class StudentSignupForm(forms.Form):
    # لو عندك حقول تانية لليوزر ضيفها هنا (email, first_name, ... إلخ)
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    halaqa = forms.ModelChoiceField(
        queryset=Halaqa.objects.all(),
        empty_label="اختر الحلقة",
        required=True,
        label="الحلقة"
    )

    def clean_username(self):
        u = self.cleaned_data['username']
        if User.objects.filter(username=u).exists():
            raise forms.ValidationError("اسم المستخدم مستخدم بالفعل.")
        return u


class TeacherSignupForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    # ممكن تضيف institution/bio/certificate لو عايز في الفورم
    institution = forms.CharField(max_length=255, required=False)
    bio = forms.CharField(widget=forms.Textarea, required=False)

    def clean_username(self):
        u = self.cleaned_data['username']
        if User.objects.filter(username=u).exists():
            raise forms.ValidationError("اسم المستخدم مستخدم بالفعل.")
        return u
    


    
# tracker/forms.py
from django import forms
from django.contrib.auth.models import User
from apps.accounts.models import Profile, Halaqa  # عدّل الاستيراد حسب مسارك الفعلي

class StudentSignupForm(forms.Form):
    # لو عندك حقول تانية لليوزر ضيفها هنا (email, first_name, ... إلخ)
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    halaqa = forms.ModelChoiceField(
        queryset=Halaqa.objects.all(),
        empty_label="اختر الحلقة",
        required=True,
        label="الحلقة"
    )

    def clean_username(self):
        u = self.cleaned_data['username']
        if User.objects.filter(username=u).exists():
            raise forms.ValidationError("اسم المستخدم مستخدم بالفعل.")
        return u


class TeacherSignupForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    # ممكن تضيف institution/bio/certificate لو عايز في الفورم
    institution = forms.CharField(max_length=255, required=False)
    bio = forms.CharField(widget=forms.Textarea, required=False)

    def clean_username(self):
        u = self.cleaned_data['username']
        if User.objects.filter(username=u).exists():
            raise forms.ValidationError("اسم المستخدم مستخدم بالفعل.")
        return u

