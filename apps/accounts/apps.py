# apps/accounts/apps.py
from django.apps import AppConfig

class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'

    def ready(self):
        # تحميل الإشارات (signals) تلقائيًا
        import apps.accounts.signals  # noqa
