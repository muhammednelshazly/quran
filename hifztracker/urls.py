# hifztracker/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.accounts import views as acc_views
# ❌ قم بإزالة أو تجاهل هذا السطر إذا لم تكن تستخدمه:
# from apps.tracker import views as tracker_views 

urlpatterns = [
    path('', acc_views.landing_page, name='landing'),
    path('go/', acc_views.go, name='go'),

    path('admin/', admin.site.urls),

    # Auth / Profiles / Halaqas / Recitations
    path('accounts/', include(('apps.accounts.urls', 'accounts'), namespace='accounts')),

    # Tracker dashboards and recording forms
    path('tracker/', include('apps.tracker.urls')),
    
    # ✅ التصحيح: استخدام acc_views لأن الدالة في تطبيق accounts
    path('students/', acc_views.teacher_students_view, name='teacher_students'),

    path('', include('apps.accounts.urls')),
]

# خدمة ملفات الميديا محليًا أثناء التطوير
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)