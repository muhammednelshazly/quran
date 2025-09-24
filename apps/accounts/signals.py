# apps/accounts/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    ينشئ Profile مرة واحدة عند إنشاء User جديد.
    get_or_create يمنع التكرار لو اتسجّل السيجنال مرتين بالخطأ.
    """
    if created:
        Profile.objects.get_or_create(user=instance)

# (اختياري) لو حابب تحفظ profile تلقائيًا عند حفظ الـUser
# مش ضروري غالبًا، فممكن تمسحه لو مش محتاجه.
@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, "profile"):
        instance.profile.save()
