# apps/accounts/urls.py
from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    # --- Authentication ---
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('go/', views.go, name='go'),

    # --- Student URLs ---
    path('dashboard/', views.student_dashboard, name='student_dashboard'),
    path("recitations/<int:pk>/action/", views.recitation_action, name="recitation_action"),
    path("reviews/<int:pk>/action/", views.review_action, name="review_action"),
    path("recitations/<int:pk>/start/", views.recitation_start, name="recitation_start"),
    path("recitations/<int:pk>/submit/", views.recitation_submit, name="recitation_submit"),

    # --- Teacher URLs ---
    path("teacher/dashboard/", views.teacher_dashboard, name="teacher_dashboard"),
    path("teacher/halaqat/", views.teacher_halaqat, name="teacher_halaqat"),
    path("teacher/students/", views.teacher_students, name="teacher_students"),
    path('student/<int:student_id>/unassign/', views.unassign_student_from_halaqa, name='unassign_student'),

    # 👇 --- الروابط الجديدة التي أضفناها --- 👇
    # رابط API لجلب السور ديناميكيًا بناءً على نطاق الأجزاء
    path('api/halaqa/<int:halaqa_id>/surahs/', views.get_halaqa_surahs, name='get_halaqa_surahs'),
    # رابط لحفظ المهمة الجديدة من النافذة
    path('teacher/halaqa/add_task/', views.add_halaqa_task, name='add_halaqa_task'),

    path('teacher/halaqa/<int:halaqa_id>/', views.halaqa_details_view, name='halaqa_details'),


    # رابط جديد لإضافة مهمة لطالب معين
    path('teacher/student/add_task/', views.add_student_task, name='add_student_task'),


    path('halaqa/<int:halaqa_id>/send-notification/', views.send_halaqa_notification, name='send_halaqa_notification'),


    path('api/submission/<int:submission_id>/', views.get_submission_details, name='get_submission_details'),
    path('teacher/submission/<int:submission_id>/grade/', views.grade_submission, name='grade_submission'),

    path('teacher/submissions/', views.teacher_submissions, name='teacher_submissions'),



]