# accounts/templatetags/custom_filters.py

from django import template
from django.utils.timesince import timesince as dj_timesince
from django.utils.timezone import now

register = template.Library()

@register.filter
def arabic_timesince(value):
    if not value:
        return ""
    
    # حساب الفارق الزمني
    since = dj_timesince(value, now())

    # قائمة الكلمات للترجمة (الجمع أولاً ثم المفرد)
    replacements = [
        ('minutes', 'دقائق'),
        ('minute', 'دقيقة'),
        ('hours', 'ساعات'),
        ('hour', 'ساعة'),
        ('days', 'أيام'),
        ('day', 'يوم'),
        ('weeks', 'أسابيع'),
        ('week', 'أسبوع'),
        ('months', 'أشهر'),
        ('month', 'شهر'),
        ('years', 'سنوات'),
        ('year', 'سنة'),
        ('ago', ''), # إزالة كلمة ago
        (',', ''), # إزالة الفاصلة
    ]
    
    # تطبيق الترجمة بالترتيب
    for en, ar in replacements:
        since = since.replace(en, ar)

    # إضافة "منذ" في البداية
    return f"منذ {since.strip()}"