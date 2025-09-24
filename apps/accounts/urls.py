# apps/accounts/urls.py
from django.urls import path
from .views import login_view, logout_view, register_view, student_dashboard 
from . import views


app_name = "accounts"

urlpatterns = [
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('register/', register_view, name='register'),
    path('dashboard/', student_dashboard, name='student_dashboard'),  # ← جديد
    path("teacher/dashboard/", views.teacher_dashboard, name="teacher_dashboard"),
    path("recitations/<int:pk>/action/", views.recitation_action, name="recitation_action"),
    path("reviews/<int:pk>/action/", views.review_action, name="review_action"),
    path("recitations/<int:pk>/start/", views.recitation_start, name="recitation_start"),     # صفحة التسجيل
    path("recitations/<int:pk>/submit/", views.recitation_submit, name="recitation_submit"), # حفظ الصوت
    path('go/', views.go, name='go'),
]
