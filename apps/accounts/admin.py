from django.contrib import admin
from .models import (
    Profile, Halaqa,
    Recitation, RecitationSubmission,
    Review, ReviewSubmission,
)

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display  = ("user", "role", "halaqa_name", "teacher_status_display")
    list_filter   = ("role", "teacher_status", "halaqa")
    search_fields = ("user__username", "user__first_name", "user__last_name")

    def halaqa_name(self, obj):
        return obj.halaqa.name if obj.halaqa else "-"
    halaqa_name.short_description = "HALAQA"

    def teacher_status_display(self, obj):
        # إظهار الحالة للمعلم فقط — الطالب يظهر "-"
        return obj.teacher_status.title() if obj.role == Profile.ROLE_TEACHER else "-"
    teacher_status_display.short_description = "TEACHER STATUS"


@admin.register(Halaqa)
class HalaqaAdmin(admin.ModelAdmin):
    list_display  = ("name",)
    search_fields = ("name",)
    filter_horizontal = ("teachers",)  # لو حابب تسهّل اختيار المعلمين على الأدمن


@admin.register(Recitation)
class RecitationAdmin(admin.ModelAdmin):
    list_display  = ("surah", "range_text", "halaqa", "created_by")
    search_fields = ("surah", "range_text", "halaqa__name", "created_by__user__username")
    list_filter   = ("halaqa",)


@admin.register(RecitationSubmission)
class RecitationSubmissionAdmin(admin.ModelAdmin):
    list_display  = ("recitation", "student", "status", "created_at")
    list_filter   = ("status", "recitation__halaqa")
    search_fields = ("recitation__surah", "student__user__username")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display  = ("surah", "range_text", "halaqa", "created_by")
    search_fields = ("surah", "range_text", "halaqa__name", "created_by__user__username")
    list_filter   = ("halaqa",)


@admin.register(ReviewSubmission)
class ReviewSubmissionAdmin(admin.ModelAdmin):
    list_display  = ("review", "student", "status", "created_at")
    list_filter   = ("status", "review__halaqa")
    search_fields = ("review__surah", "student__user__username")
