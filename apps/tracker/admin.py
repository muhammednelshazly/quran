from django.contrib import admin
from .models import Halaqa, Student, DailyMemorization, Review, Attendance, WeeklyEvaluation, MonthlyReport

@admin.register(Halaqa)
class HalaqaAdmin(admin.ModelAdmin):
    list_display = ('name', 'teacher', 'start_date')
    search_fields = ('name', 'teacher__username', 'teacher__first_name', 'teacher__last_name')

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('student_no', 'user', 'age', 'joined_at', 'halaqa')
    search_fields = ('student_no', 'user__username', 'user__first_name', 'user__last_name')
    list_filter = ('halaqa',)

@admin.register(DailyMemorization)
class DailyMemorizationAdmin(admin.ModelAdmin):
    list_display = ('student', 'date', 'from_surah', 'from_ayah', 'to_surah', 'to_ayah', 'mastery')
    list_filter = ('date', 'student__halaqa')

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('student', 'date', 'surah_or_juz', 'mastery')
    list_filter = ('date', 'student__halaqa')

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('student', 'date', 'status')
    list_filter = ('date', 'status', 'student__halaqa')

@admin.register(WeeklyEvaluation)
class WeeklyEvaluationAdmin(admin.ModelAdmin):
    list_display = ('student', 'week_start', 'score')
    list_filter = ('week_start',)

@admin.register(MonthlyReport)
class MonthlyReportAdmin(admin.ModelAdmin):
    list_display = ('student', 'month', 'memorized_count', 'mastery_avg', 'attendance_rate')
    list_filter = ('month',)
