from django.urls import path
from . import views

app_name = 'tracker'

urlpatterns = [
    path('student/', views.student_dashboard, name='student_dashboard'),
    path('teacher/', views.teacher_dashboard, name='teacher_dashboard'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('record/memorization/', views.record_memorization, name='record_memorization'),
    path('record/review/', views.record_review, name='record_review'),
    path('record/attendance/', views.record_attendance, name='record_attendance'),
]
