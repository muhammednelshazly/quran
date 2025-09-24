# hifztracker/urls.py
from django.contrib import admin
from django.urls import path, include
from apps.accounts.views import home_view
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from apps.accounts import views as acc_views   # ← استيراد مباشر



urlpatterns = [
    path('', acc_views.landing_page, name='landing'),
    path('go/', acc_views.go, name='go'),   # ← تعريف وحيد لـ go


    path('admin/', admin.site.urls),

    # Auth / Profiles / Halaqas / Recitations
    path('accounts/', include(('apps.accounts.urls', 'accounts'), namespace='accounts')),

    # Landing
    # path('', home_view, name='home'),

    # Tracker dashboards and recording forms
    path('tracker/', include('apps.tracker.urls')),

    path('', include('apps.accounts.urls')),

]

# خدمة ملفات الميديا محليًا أثناء التطوير
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
