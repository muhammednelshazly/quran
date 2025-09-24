from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Avg, Count, Q
from datetime import date, timedelta
from .models import Student, DailyMemorization, Review, Attendance, Halaqa
from .forms import DailyMemorizationForm, ReviewForm, AttendanceForm
from django.utils import timezone
from apps.accounts.models import (
    Recitation,
    RecitationSubmission,
    Attendance,
    Profile,        # إن كنت تستخدمه في الفيوز
)



@login_required
def student_dashboard(request):
    profile = request.user.profile

    recitations = (Recitation.objects
                   .filter(halaqa=profile.halaqa)
                   .select_related("halaqa", "created_by"))

    # استخدم student_id لتفادي فحص النوع
    subs = RecitationSubmission.objects.filter(
        student_id=profile.id,          # ← بدّلها
        recitation__in=recitations
    )
    submissions_map = {s.recitation_id: s for s in subs}

    for r in recitations:
        setattr(r, "sub", submissions_map.get(r.id))

    # برضه هنا استخدم student_id
    week_attendance = (Attendance.objects
                       .filter(student_id=profile.id)  # ← بدّلها
                       .order_by('-date')[:7][::-1])

    return render(request, "students/student_dashboard.html", {
        "user": request.user,
        "profile": profile,
        "recitations": recitations,
        "week_attendance": week_attendance,
        "weekly_score": 90, "ayah_count": 120, "accuracy_pct": 90, "presence_pct": 86,
        "now": timezone.now(),
    })

@login_required
def teacher_dashboard(request):
    halaqat = Halaqa.objects.filter(teacher=request.user).prefetch_related('students')
    recent = DailyMemorization.objects.filter(student__halaqa__teacher=request.user)[:10]
    return render(request, 'dashboard/teacher_dashboard.html', {'halaqat': halaqat, 'recent': recent})

@login_required
def admin_dashboard(request):
    # Simple KPIs
    students_count = Student.objects.count()
    total_memos = DailyMemorization.objects.count()
    present_count = Attendance.objects.filter(status='present').count()
    absent_count = Attendance.objects.filter(status='absent').count()
    return render(request, 'dashboard/admin_dashboard.html', {
        'students_count': students_count,
        'total_memos': total_memos,
        'present_count': present_count,
        'absent_count': absent_count,
    })

@login_required
def record_memorization(request):
    if request.method == 'POST':
        form = DailyMemorizationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Memorization saved.")
            return redirect('tracker:teacher_dashboard')
    else:
        form = DailyMemorizationForm()
    return render(request, 'forms/record_form.html', {'form': form, 'title': 'Record Memorization'})

@login_required
def record_review(request):
    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Review saved.")
            return redirect('tracker:teacher_dashboard')
    else:
        form = ReviewForm()
    return render(request, 'forms/record_form.html', {'form': form, 'title': 'Record Review'})

@login_required
def record_attendance(request):
    if request.method == 'POST':
        form = AttendanceForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Attendance saved.")
            return redirect('tracker:teacher_dashboard')
    else:
        form = AttendanceForm()
    return render(request, 'forms/record_form.html', {'form': form, 'title': 'Record Attendance'})
