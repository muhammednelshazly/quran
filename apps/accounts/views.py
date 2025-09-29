# apps/accounts/views.py
from datetime import datetime, timedelta, date
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.db.models import Q, Count, Avg, Max
from itertools import chain
from operator import attrgetter
from django.db.models import Q, Count, Avg, Max, F, Subquery, OuterRef
from .forms import ProfileUpdateForm, CustomPasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from .forms import ProfileUpdateForm, PasswordChangeForm
from django.contrib.sessions.models import Session
import types
from django.template.loader import render_to_string
try:
    from hijri_converter import Gregorian as _Gregorian
    HIJRI_OK = True
except Exception:
    HIJRI_OK = False

from django.db.models import Sum, F, IntegerField, ExpressionWrapper

from apps.accounts.models import (
    Recitation,
    RecitationSubmission,
    Attendance,
    Profile, Halaqa,
    Review, ReviewSubmission,
    Surah
)

# ========= أدوات مساعدة =========
AR_HIJRI_MONTHS = [
    "محرم", "صفر", "ربيع الأول", "ربيع الآخر",
    "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان",
    "رمضان", "شوال", "ذو القعدة", "ذو الحجة",
]


def landing_page(request):
    # if request.user.is_authenticated: return redirect('go')
    return render(request, 'landing_page.html')


def go(request):

    user = request.user

    role = getattr(user, 'role', None)
    if role is None and hasattr(user, 'profile'):
        role = getattr(user.profile, 'role', None)

    if role == 'student' or user.groups.filter(name__iexact='student').exists():
        return HttpResponseRedirect('/dashboard/')

    if role == 'teacher' or user.groups.filter(name__iexact='teacher').exists():
        return HttpResponseRedirect('/teacher/dashboard/')

    return HttpResponseRedirect('/login/')


def home_view(request):
    return render(request, "home.html")



def login_view(request):
    if request.method == "POST":
        identifier = request.POST.get("username", "").strip()
        password   = request.POST.get("password", "")
        role       = request.POST.get("role", "")
        remember_me = request.POST.get("remember-me")

        if not identifier or not password or role not in (Profile.ROLE_STUDENT, Profile.ROLE_TEACHER):
            messages.error(request, "من فضلك أكمل كل الحقول واختر نوع الحساب (طالب/معلم).")
            return render(request, "accounts/login.html", {"selected_role": role})

        username = identifier
        if "@" in identifier:
            user_obj = User.objects.filter(email__iexact=identifier).first()
            username = user_obj.username if user_obj else None

        user = authenticate(request, username=username, password=password) if username else None
        if user is None:
            messages.error(request, "بيانات الدخول غير صحيحة.")
            return render(request, "accounts/login.html", {"selected_role": role})

        if user.is_staff or user.is_superuser:
            return redirect("/admin/")

        if not hasattr(user, "profile"):
            Profile.objects.create(user=user)

        if user.profile.role != role:
            messages.error(request, "نوع الحساب لا يطابق الاختيار (طالب/معلم).")
            return render(request, "accounts/login.html", {"selected_role": role})

        if role == Profile.ROLE_TEACHER and user.profile.teacher_status != Profile.TEACHER_APPROVED:
            messages.error(request, "حساب المعلم قيد المراجعة من المشرف. سيتم إشعارك عند الاعتماد.")
            return render(request, "accounts/login.html", {"selected_role": role})

        login(request, user)
        request.session.set_expiry(0 if not remember_me else 14 * 24 * 3600)
        # messages.success(request, "تم تسجيل الدخول بنجاح.")
        if user.profile.role == Profile.ROLE_STUDENT:
            return redirect("accounts:student_dashboard")
        elif user.profile.role == Profile.ROLE_TEACHER:
            return redirect("accounts:teacher_dashboard")
        return redirect("home")

    return render(request, "accounts/login.html")


def logout_view(request):
    logout(request)
    messages.success(request, "تم تسجيل الخروج.")
    return redirect("accounts:login")


# ========= التسجيل =========

def register_view(request):
    def ctx(extra=None):
        base = {"halaqas": Halaqa.objects.all().order_by("name")}
        if extra:
            base.update(extra)
        return base

    if request.method == "POST":
        # 1) الحقول الأساسية
        username = request.POST.get("username", "").strip()
        email    = request.POST.get("email", "").strip().lower()
        pw1      = request.POST.get("password1", "")
        pw2      = request.POST.get("password2", "")
        role     = request.POST.get("role", "")

        # حقول الطالب
        birth_date_str  = request.POST.get("birth_date", "").strip()
        gender          = request.POST.get("gender") or None
        guardian_phone  = request.POST.get("guardian_phone") or None
        halaqa_input    = request.POST.get("halaqa") or None  # id أو اسم

        # حقول المعلّم
        institution     = request.POST.get("institution") or None
        bio             = request.POST.get("bio") or None
        certificate     = request.FILES.get("certificate")  # اختياري

        # 2) تحققات أساسية
        if not all([username, email, pw1, pw2, role]):
            messages.error(request, "من فضلك أكمل جميع الحقول الأساسية.")
            return render(request, "accounts/register.html", ctx({"selected_role": role}))

        if role not in (Profile.ROLE_STUDENT, Profile.ROLE_TEACHER):
            messages.error(request, "برجاء اختيار نوع حساب صحيح (طالب/معلم).")
            return render(request, "accounts/register.html", ctx({"selected_role": role}))

        if pw1 != pw2:
            messages.error(request, "كلمتا المرور غير متطابقتين.")
            return render(request, "accounts/register.html", ctx({"selected_role": role}))

        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, "اسم المستخدم مستخدم من قبل.")
            return render(request, "accounts/register.html", ctx({"selected_role": role}))

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, "البريد الإلكتروني مسجل من قبل.")
            return render(request, "accounts/register.html", ctx({"selected_role": role}))

        # 3) تحققات خاصة بالطالب
        birth_date = None
        if role == Profile.ROLE_STUDENT:
            if not birth_date_str or not gender:
                messages.error(request, "تاريخ الميلاد والجنس مطلوبان للطالب.")
                return render(request, "accounts/register.html", ctx({"selected_role": role}))
            try:
                birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
            except ValueError:
                messages.error(request, "صيغة تاريخ الميلاد غير صحيحة.")
                return render(request, "accounts/register.html", ctx({"selected_role": role}))

            # لازم يختار حلقة صحيحة
            halaqa_obj = None
            if halaqa_input:
                if str(halaqa_input).isdigit():
                    halaqa_obj = Halaqa.objects.filter(id=int(halaqa_input)).first()
                if not halaqa_obj:
                    halaqa_obj = Halaqa.objects.filter(name=halaqa_input).first()
            if not halaqa_obj:
                messages.error(request, "من فضلك اختر حلقة صحيحة من القائمة.")
                return render(request, "accounts/register.html", ctx({"selected_role": role}))
        else:
            halaqa_obj = None  # المعلم لا يُربط بحلقة هنا

        # 4) إنشاء المستخدم + البروفايل
        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, email=email, password=pw1)
                profile, _ = Profile.objects.get_or_create(user=user)
                profile.role = role

                if role == Profile.ROLE_STUDENT:
                    profile.halaqa = halaqa_obj
                    profile.birth_date = birth_date
                    profile.gender = gender
                    profile.guardian_phone = guardian_phone
                    profile.institution = None
                    profile.bio = None
                    if getattr(profile, "certificate", None):
                        profile.certificate.delete(save=False)
                    profile.certificate = None
                    # الطالب دائمًا Approved
                    profile.teacher_status = Profile.TEACHER_APPROVED
                else:
                    # المعلّم Pending لحين اعتماد المشرف
                    profile.teacher_status = Profile.TEACHER_PENDING
                    profile.institution = institution
                    profile.bio = bio
                    if certificate:
                        profile.certificate = certificate
                    profile.halaqa = None
                    profile.birth_date = None
                    profile.gender = None
                    profile.guardian_phone = None

                profile.save()

        except IntegrityError:
            try:
                user.delete()
            except Exception:
                pass
            messages.error(request, "حدث خطأ أثناء إنشاء الحساب. حاول مرة أخرى.")
            return render(request, "accounts/register.html", ctx({"selected_role": role}))

        # 5) نجاح
        if role == Profile.ROLE_TEACHER:
            messages.success(request, "تم إنشاء الحساب! طلبك كمعلم قيد المراجعة من المشرف.")
        else:
            messages.success(request, "تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن.")
        return redirect("accounts:login")

    # GET
    return render(request, "accounts/register.html", {"halaqas": Halaqa.objects.all().order_by("name")})


# ========= لوحات التحكم =========

def start_of_sat_week(d):
    # Mon=0..Sun=6  → Saturday=5
    delta = (d.weekday() - 5) % 7
    return d - timedelta(days=delta)


def _range_len(obj):
    """
    يعيد عدد الآيات للمهمة (Recitation/Review) لو عندك start_ayah/end_ayah.
    لو غير موجودين، يرجّع 0 (أو تقدر تعمل fallback لحقل آخر لو موجود).
    """
    try:
        s = int(getattr(obj, "start_ayah", 0) or 0)
        e = int(getattr(obj, "end_ayah", 0) or 0)
        return (e - s + 1) if (s and e and e >= s) else 0
    except Exception:
        return 0





@login_required(login_url="accounts:login")
def student_dashboard(request):
    profile = get_object_or_404(Profile, user=request.user)
    if profile.role != Profile.ROLE_STUDENT:
        return redirect("accounts:teacher_dashboard")

    now = timezone.now()
    today = timezone.localdate()
    
    # --- 1. Attendance Logic ---
    Attendance.objects.get_or_create(student=profile, date=today, defaults={"status": "present"})
    start_date = today - timedelta(days=6)
    existing_attendance = Attendance.objects.filter(student=profile, date__gte=start_date, date__lte=today)
    attendance_map = {att.date: att for att in existing_attendance}
    week_attendance = []
    for i in range(7):
        day_date = start_date + timedelta(days=i)
        if day_date in attendance_map:
            week_attendance.append(attendance_map[day_date])
        else:
            week_attendance.append(types.SimpleNamespace(date=day_date, status=None))

    # --- 2. Fetch All Tasks & Submissions ---
    recitations = Recitation.objects.filter(halaqa=profile.halaqa).select_related("halaqa", "created_by__user")
    reviews = Review.objects.filter(halaqa=profile.halaqa).select_related("halaqa", "created_by__user")
    rec_subs = RecitationSubmission.objects.filter(student=profile, recitation__in=recitations)
    rev_subs = ReviewSubmission.objects.filter(student=profile, review__in=reviews)
    
    sub_map = {f"recitation_{s.recitation_id}": s for s in rec_subs}
    sub_map.update({f"review_{s.review_id}": s for s in rev_subs})

    all_tasks = []
    for r in recitations:
        setattr(r, "type", "recitation")
        setattr(r, "sub", sub_map.get(f"recitation_{r.id}"))
        setattr(r, "is_late", r.deadline and r.deadline < now and not r.sub)
        all_tasks.append(r)
    for rv in reviews:
        setattr(rv, "type", "review")
        setattr(rv, "sub", sub_map.get(f"review_{rv.id}"))
        setattr(rv, "is_late", rv.deadline and rv.deadline < now and not rv.sub)
        all_tasks.append(rv)

    all_tasks.sort(key=lambda x: x.created_at, reverse=True)

    for task in all_tasks:
        if task.sub and task.sub.status == 'graded':
            task.sub.score_percentage = (task.sub.score or 0) * 10
            task.sub.hifdh_percentage = (task.sub.hifdh or 0) * 20
            task.sub.rules_percentage = (task.sub.rules or 0) * 20
            
    # --- 3. Filter Tasks for Tabs ---
    pending_tasks = [
        t for t in all_tasks 
        if not t.sub or (t.sub.status == 'graded' and t.sub.score is not None and t.sub.score < 5)
    ]
    submitted_tasks = [
        t for t in all_tasks 
        if t.sub and t.sub.status == 'submitted'
    ]
    graded_tasks = [
        t for t in all_tasks 
        if t.sub and t.sub.status == 'graded' and t.sub.score is not None and t.sub.score >= 5
    ]
    
    # --- 4. Calculate All Statistics ---
    week_ago = now - timedelta(days=7)
    
    all_graded_recitations = RecitationSubmission.objects.filter(student=profile, status="graded")
    all_graded_reviews = ReviewSubmission.objects.filter(student=profile, status="graded")
    total_rec_score = all_graded_recitations.aggregate(total=Sum('score'))['total'] or 0
    total_rev_score = all_graded_reviews.aggregate(total=Sum('score'))['total'] or 0
    count_graded = all_graded_recitations.count() + all_graded_reviews.count()
    total_score = total_rec_score + total_rev_score
    accuracy_pct = round((total_score / (count_graded * 10)) * 100) if count_graded > 0 else 0
    present_days = sum(1 for a in week_attendance if a.status == "present")
    presence_pct = round((present_days / 7) * 100) if week_attendance else 0
    
    successful_recitations = RecitationSubmission.objects.filter(
        student=profile, status="graded", score__gte=5
    ).select_related('recitation')
    ayah_count = sum(
        (s.recitation.end_ayah - s.recitation.start_ayah + 1) 
        for s in successful_recitations 
        if s.recitation and s.recitation.start_ayah and s.recitation.end_ayah
    )
    
    pending_tasks_count = len(pending_tasks)
    weekly_hifdh_subs = RecitationSubmission.objects.filter(student=profile, created_at__gte=week_ago, status='graded')
    hifdh_avg = weekly_hifdh_subs.aggregate(avg=Avg('score'))['avg'] or 0
    weekly_hifdh_score = round((hifdh_avg / 10) * 100)
    weekly_review_subs = ReviewSubmission.objects.filter(student=profile, created_at__gte=week_ago, status='graded')
    review_avg = weekly_review_subs.aggregate(avg=Avg('score'))['avg'] or 0
    weekly_review_score = round((review_avg / 10) * 100)

    # --- **START OF CHANGE: Add teacher's name to context** ---
    halaqa_teacher = profile.halaqa.teachers.first() if profile.halaqa else None
    # --- **END OF CHANGE** ---

    # --- 5. Final Context for Template ---
    ctx = {
        "profile": profile,
        "pending_tasks": pending_tasks,
        "submitted_tasks": submitted_tasks,
        "graded_tasks": graded_tasks,
        "week_attendance": week_attendance,
        "pending_tasks_count": pending_tasks_count,
        "accuracy_pct": accuracy_pct,
        "presence_pct": presence_pct,
        "ayah_count": ayah_count,
        "weekly_hifdh_score": weekly_hifdh_score,
        "weekly_review_score": weekly_review_score,
        "halaqa_teacher_name": halaqa_teacher.user.username if halaqa_teacher else "غير محدد", # ADD THIS
        "now": now,
    }
    return render(request, "students/student_dashboard.html", ctx)







@require_POST
@login_required(login_url="accounts:login")
def submit_task(request, task_type, task_id):
    if request.user.profile.role != Profile.ROLE_STUDENT:
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

    audio_file = request.FILES.get('audio')
    if not audio_file:
        return JsonResponse({"status": "error", "message": "لم يصل ملف الصوت."}, status=400)

    student = request.user.profile
    task = None
    submission = None

    try:
        if task_type == 'recitation':
            task = get_object_or_404(Recitation, id=task_id, halaqa=student.halaqa)
            submission, _ = RecitationSubmission.objects.update_or_create(
                recitation=task, student=student,
                defaults={'audio': audio_file, 'status': 'submitted', 'updated_at': timezone.now()}
            )
        elif task_type == 'review':
            task = get_object_or_404(Review, id=task_id, halaqa=student.halaqa)
            submission, _ = ReviewSubmission.objects.update_or_create(
                review=task, student=student,
                defaults={'audio': audio_file, 'status': 'submitted', 'updated_at': timezone.now()}
            )
        else:
            return JsonResponse({'status': 'error', 'message': 'نوع المهمة غير صالح.'}, status=400)
            
        setattr(task, "type", task_type)
        setattr(task, "sub", submission)
        setattr(task, "is_late", task.deadline and task.deadline < timezone.now() and not task.sub)

        task_card_html = render_to_string(
            'students/partials/_task_item.html', 
            {'task': task, 'sub': submission, 'request': request}
        )
        
        # --- بداية الإصلاح النهائي ---
        # حساب عدد المهام المطلوبة بشكل صحيح بعد التسليم
        
        pending_recitations = Recitation.objects.filter(
            halaqa=student.halaqa
        ).exclude(
            submissions__student=student
        ).count()

        # تم تصحيح الخطأ هنا بناءً على رسالة الخطأ الجديدة
        # اسم العلاقة الصحيح هو 'submissions' وليس 'reviewsubmission'
        pending_reviews = Review.objects.filter(
            halaqa=student.halaqa
        ).exclude(
            submissions__student=student 
        ).count()
        # --- نهاية الإصلاح النهائي ---

        new_pending_count = pending_recitations + pending_reviews

        return JsonResponse({
            'status': 'success',
            'message': 'تم التسليم بنجاح!',
            'task_card_html': task_card_html,
            'new_stats': {
                'pending_tasks_count': new_pending_count
            }
        })

    except Exception as e:
        print(f"Error in submit_task: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    








# ولا تنس تحديث دالة لوحة تحكم المعلم الرئيسية
@login_required(login_url="accounts:login")
def teacher_dashboard(request):
    # --- التحقق من صلاحيات المعلم (لا تغيير هنا) ---
    if request.user.is_staff:
        return redirect('admin:index')
    profile = request.user.profile
    if profile.role != Profile.ROLE_TEACHER:
        return redirect("accounts:student_dashboard")
    if profile.teacher_status != Profile.TEACHER_APPROVED:
        return redirect("accounts:login")

    # --- جلب البيانات (لا تغيير هنا) ---
    my_halaqat = Halaqa.objects.filter(teachers=profile).prefetch_related('students')
    pending_submissions_count = RecitationSubmission.objects.filter(recitation__halaqa__in=my_halaqat, status='submitted').count()
    total_students_count = Profile.objects.filter(halaqa__in=my_halaqat, role=Profile.ROLE_STUDENT).count()
    active_halaqat_count = my_halaqat.count()
    
    avg_performance_rec = RecitationSubmission.objects.filter(recitation__halaqa__in=my_halaqat, status='graded').aggregate(avg_score=Avg('score'))['avg_score'] or 0
    average_performance = round(avg_performance_rec * 10, 1) if avg_performance_rec else 0

    latest_rec_subs = RecitationSubmission.objects.filter(recitation__halaqa__in=my_halaqat, status='submitted').order_by('-created_at')[:5]

    halaqat_with_stats = []
    for halaqa in my_halaqat:
        # ---- 👇 بداية التعديل 👇 ----
        last_recitation = Recitation.objects.filter(halaqa=halaqa).order_by('-created_at').first()
        last_review = Review.objects.filter(halaqa=halaqa).order_by('-created_at').first()
        
        halaqat_with_stats.append({
            'halaqa': halaqa,
            'student_count': halaqa.students.count(),
            'last_recitation_date': last_recitation.created_at if last_recitation else None,
            'last_review_date': last_review.created_at if last_review else None,
        })

    # --- تحويل التاريخ إلى هجري ---
    today_gregorian = date.today()
    hijri_date = _Gregorian(today_gregorian.year, today_gregorian.month, today_gregorian.day).to_hijri()
    
    # 👇 --- هذا هو السطر الذي تم تصحيحه --- 👇
    formatted_hijri_date = f"{hijri_date.day_name('ar')}، {hijri_date.day} {hijri_date.month_name('ar')} {hijri_date.year}"



    # --- إرسال البيانات بالأسماء الصحيحة للقالب ---
    context = {
        'pending_submissions_count': pending_submissions_count,
        'total_students_count': total_students_count,
        'active_halaqat_count': active_halaqat_count,
        'average_performance': average_performance,
        'latest_submissions': latest_rec_subs,
        'halaqat_list': halaqat_with_stats,
        'today_date': formatted_hijri_date

    }
    
    return render(request, 'teachers/teacher_dashboard.html', context)



# في ملف: apps/accounts/views.py

@login_required
def teacher_halaqat(request):
    profile = request.user.profile
    if profile.role != Profile.ROLE_TEACHER:
        return redirect("accounts:student_dashboard")

    # جلب الحلقات مع حساب عدد الطلاب لكل حلقة
    my_halaqat_query = Halaqa.objects.filter(teachers=profile).annotate(
        student_count=Count('students', distinct=True)
    )

    # --- منطق الفرز (تم تحسينه ليعمل مع anntotations) ---
    sort_option = request.GET.get('sort', 'name_asc')

    if sort_option == 'name_desc':
        my_halaqat_query = my_halaqat_query.order_by('-name')
    elif sort_option == 'students_desc':
        my_halaqat_query = my_halaqat_query.order_by('-student_count')
    elif sort_option == 'students_asc':
        my_halaqat_query = my_halaqat_query.order_by('student_count')
    else: # name_asc هو الافتراضي
        my_halaqat_query = my_halaqat_query.order_by('name')

    # --- حساب متوسط الأداء (كنسبة إنجاز) لكل حلقة ---
    halaqat_with_stats = []
    for halaqa in my_halaqat_query:
        # حساب متوسط الدرجات من تسليمات التسميع فقط
        avg_score_query = RecitationSubmission.objects.filter(
            recitation__halaqa=halaqa, status='graded'
        ).aggregate(avg=Avg('score'))
        
        # تحويل المتوسط (من 10) إلى نسبة مئوية
        avg_performance_percentage = round((avg_score_query['avg'] or 0) * 10, 1)

        halaqat_with_stats.append({
            'halaqa': halaqa,
            'student_count': halaqa.student_count,
            'completion_percentage': avg_performance_percentage,
        })

    context = {
        'halaqat_list': halaqat_with_stats,
        'current_sort': sort_option
    }
    
    return render(request, 'teachers/halaqat.html', context)




# في ملف: apps/accounts/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Max, Avg, Q
from .models import Profile, Halaqa # تأكد من أن المسار صحيح لنماذجك

@login_required
def teacher_students(request):
    # --- 1. التحقق من أن المستخدم هو معلم ---
    profile = get_object_or_404(Profile, user=request.user)
    if profile.role != Profile.ROLE_TEACHER:
        return redirect("accounts:student_dashboard") # أو أي صفحة أخرى مناسبة

    # --- 2. بناء الاستعلام الأساسي لجلب الطلاب ---
    # نبدأ بجلب كل الطلاب المرتبطين بالحلقات التي يشرف عليها هذا المعلم
    students_query = Profile.objects.filter(
        role=Profile.ROLE_STUDENT,
        halaqa__teachers=profile
    ).distinct()

    # --- 3. تطبيق فلترة الحلقة (إذا تم اختيار حلقة من القائمة) ---
    halaqa_id = request.GET.get('halaqa')
    if halaqa_id:
        students_query = students_query.filter(halaqa__id=halaqa_id)
        
    # --- 4. إضافة البيانات الإضافية (تاريخ التسليم ومتوسط الأداء) ---
    students_query = students_query.annotate(
        # جلب تاريخ آخر تسليم للتسميعات
        last_submission_date=Max('recitation_submissions__created_at'),
        # جلب متوسط الأداء (الدرجات) من التسميعات المصححة فقط
        avg_performance=Avg('recitation_submissions__score', filter=Q(recitation_submissions__status='graded'))
    )

    # --- 5. تطبيق الفرز ---
    sort_by = request.GET.get('sort', 'name_asc') # الفرز الافتراضي حسب الاسم تصاعديًا
    
    if sort_by == 'name_desc':
        students_query = students_query.order_by('-user__username')
    elif sort_by == 'performance_desc':
        students_query = students_query.order_by('-avg_performance')
    elif sort_by == 'performance_asc':
        students_query = students_query.order_by('avg_performance')
    elif sort_by == 'submission_desc':
        students_query = students_query.order_by('-last_submission_date')
    else: # name_asc هو الخيار الافتراضي
        students_query = students_query.order_by('user__username')

    # --- 6. (الأهم) جلب قائمة حلقات المعلم لعرضها في الفلتر ---
    # هذا هو الجزء الذي يحل مشكلة الفلتر الفارغ
    teacher_halaqas = Halaqa.objects.filter(teachers=profile)

    # --- 7. تجهيز وإرسال البيانات إلى القالب ---
    context = {
        'students_list': students_query,
        'teacher_halaqas': teacher_halaqas, # إرسال قائمة الحلقات إلى القالب
    }
    
    return render(request, 'teachers/students.html', context)




from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import Profile, Halaqa # تأكد من استيراد النماذج الصحيحة

@login_required
def teacher_students_view(request):
    # نتأكد من أن المستخدم الحالي هو معلم مسجل دخوله
    teacher_profile = get_object_or_404(Profile, user=request.user, role='teacher')
    
    # نبدأ بجلب كل الطلاب الموجودين في حلقات هذا المعلم
    students_list = Profile.objects.filter(
        role='student',
        halaqa__teachers=teacher_profile
    ).distinct()

    # --- (هذا الجزء خاص بالفلترة عند اختيار حلقة من النافذة) ---
    halaqa_id = request.GET.get('halaqa')
    if halaqa_id:
        students_list = students_list.filter(halaqa__id=halaqa_id)
    
    # --- (هذا الجزء خاص بالفرز) ---
    sort_by = request.GET.get('sort', 'name_asc') # فرز افتراضي حسب الاسم
    if sort_by == 'name_desc':
        students_list = students_list.order_by('-user__username')
    else:
        students_list = students_list.order_by('user__username')

    # ✅✅ الجزء الأهم لحل مشكلتك ✅✅
    # هنا نقوم بجلب قائمة الحلقات التي يشرف عليها المعلم فقط
    teacher_halaqas = Halaqa.objects.filter(teachers=teacher_profile)

    context = {
        'students_list': students_list,
        'teacher_halaqas': teacher_halaqas, # نقوم بتمرير قائمة الحلقات إلى القالب
    }
    # تأكد من أن مسار القالب صحيح
    return render(request, 'tracker/teacher_students.html', context)



# في ملف views.py

@login_required
@require_POST # لضمان أن هذا الطلب لا يتم إلا من خلال POST لمزيد من الأمان
def unassign_student_from_halaqa(request, student_id):
    # التأكد من أن المستخدم الحالي هو معلم
    if not request.user.profile.role == 'teacher':
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

    try:
        student_to_unassign = Profile.objects.get(id=student_id, role='student')
        
        # التأكد من أن هذا الطالب يتبع للمعلم الحالي (إجراء أمني إضافي)
        if student_to_unassign.halaqa and request.user.profile in student_to_unassign.halaqa.teachers.all():
            student_to_unassign.halaqa = None # تعيين الحلقة إلى "لا شيء"
            student_to_unassign.save()
            return JsonResponse({'status': 'success', 'message': 'Student unassigned successfully.'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Student not found in your halaqas.'}, status=404)
            
    except Profile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Student not found.'}, status=404)



# ========= التسجيل/الرفع للتسميع =========

@login_required(login_url="accounts:login")
def recitation_start(request, pk):
    """صفحة واجهة التسجيل (لو بتستخدم صفحة منفصلة)."""
    profile = get_object_or_404(Profile, user=request.user, role=Profile.ROLE_STUDENT)
    recitation = get_object_or_404(Recitation, pk=pk, halaqa=profile.halaqa)
    return render(request, "students/recitation_record.html", {
        "recitation": recitation,
        "profile": profile,
    })


@require_POST
@login_required(login_url="accounts:login")
def recitation_submit(request, pk):
    """رفع تسجيل صوت التسميع وحفظ/تحديث التسليم."""
    student = request.user.profile
    if student.role != Profile.ROLE_STUDENT:
        return HttpResponseForbidden()

    rec = get_object_or_404(Recitation, pk=pk, halaqa=student.halaqa)
    audio_file = request.FILES.get('audio')
    if not audio_file:
        return JsonResponse({"ok": False, "msg": "لم يصل ملف الصوت."}, status=400)

    sub, created = RecitationSubmission.objects.get_or_create(
        recitation=rec, student=student,
        defaults={'audio': audio_file, 'status': 'submitted'}
    )
    if not created:
        sub.audio = audio_file
        sub.status = 'submitted'
        sub.save()

    return JsonResponse({"ok": True})


# ========= أزرار الحالة (Retry … إلخ) =========

@require_POST
@login_required(login_url="accounts:login")
def recitation_action(request, pk):
    """
    زر "إعادة التسميع"
    """
    profile = get_object_or_404(Profile, user=request.user, role=Profile.ROLE_STUDENT)
    recitation = get_object_or_404(Recitation, pk=pk, halaqa=profile.halaqa)

    action = request.POST.get("action")
    if action == "retry":
        RecitationSubmission.objects.filter(recitation=recitation, student=profile).delete()
        messages.success(request, "تمت إعادة ضبط التسميع. يمكنك البدء من جديد.")
    else:
        messages.info(request, "إجراء غير معروف.")

    return redirect("accounts:student_dashboard")


@require_POST
@login_required(login_url="accounts:login")
def review_action(request, pk):
    """
    زر "إعادة المراجعة"
    """
    profile = get_object_or_404(Profile, user=request.user, role=Profile.ROLE_STUDENT)
    review = get_object_or_404(Review, pk=pk, halaqa=profile.halaqa)

    action = request.POST.get("action")
    if action == "retry":
        ReviewSubmission.objects.filter(review=review, student=profile).delete()
        messages.success(request, "تمت إعادة ضبط المراجعة. يمكنك البدء من جديد.")
    else:
        messages.info(request, "إجراء غير معروف.")

    return redirect("accounts:student_dashboard")





# accounts/views.py

# ... (أضف هذه الدوال مع باقي دوال العرض في ملفك)

@login_required
def get_halaqa_surahs(request, halaqa_id):
    """
    هذه الدالة تعمل كـ API صغير.
    عندما يطلبها الـ JavaScript، تقوم بإرجاع قائمة السور المرتبطة بالحلقة
    بناءً على نفس منطق نطاق الأجزاء الموجود في لوحة تحكم الأدمن.
    """
    try:
        # تأكد أن المعلم الحالي هو المسؤول عن هذه الحلقة
        halaqa = Halaqa.objects.get(id=halaqa_id, teachers=request.user.profile)
        
        # نفس منطق الفلترة الذكي من ملف admin.py
        if halaqa.juz_from and halaqa.juz_to:
            surahs = Surah.objects.filter(
                juz_from__lte=halaqa.juz_to,
                juz_to__gte=halaqa.juz_from
            ).order_by("id")
        else:
            surahs = Surah.objects.none() # لا ترجع أي سور إذا لم يتم تحديد نطاق أجزاء للحلقة

        surahs_list = [{'id': surah.id, 'name': surah.name} for surah in surahs]
        return JsonResponse({'surahs': surahs_list})
        
    except Halaqa.DoesNotExist:
        return JsonResponse({'error': 'Halaqa not found or you do not have permission.'}, status=404)





@login_required
@require_POST
def add_halaqa_task(request):
    try:
        from django.utils.dateparse import parse_datetime

        halaqa_id   = request.POST.get('halaqa_id')
        task_type   = request.POST.get('task_type', 'recitation')
        surah_id    = request.POST.get('surah_id')   # يفضل تبقي بالاسم ده
        start_ayah  = request.POST.get('start_ayah')
        end_ayah    = request.POST.get('end_ayah')
        deadline_s  = request.POST.get('deadline')

        halaqa = Halaqa.objects.get(id=halaqa_id, teachers=request.user.profile)
        surah  = get_object_or_404(Surah, pk=surah_id)
        deadline = parse_datetime(deadline_s) if deadline_s else None

        task_data = {
            'halaqa': halaqa,
            'created_by': request.user.profile,
            'surah': surah.name,   # ← احفظ الاسم كنص
            'start_ayah': start_ayah,
            'end_ayah': end_ayah,
            'deadline': deadline,
        }

        if task_type == 'review':
            Review.objects.create(**task_data)
        else:
            Recitation.objects.create(**task_data)

        return JsonResponse({'status': 'success', 'message': f'تمت إضافة المهمة بنجاح لحلقة {halaqa.name}.'})
    except Halaqa.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'الحلقة غير موجودة أو ليس لديك صلاحية.'}, status=403)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'حدث خطأ غير متوقع: {str(e)}'}, status=500)






@login_required(login_url="accounts:login")
def halaqa_details_view(request, halaqa_id):
    """
    صفحة تفاصيل الحلقة مع إحصائيات محسوبة بكفاءة.
    """
    # صلاحية المعلم
    halaqa = get_object_or_404(Halaqa, id=halaqa_id, teachers=request.user.profile)

    # --- 1) الإحصائيات العامة للكروت العلوية ---
    student_count = halaqa.students.count()
    
    # متوسط الأداء العام للحلقة (من التسليمات المصححة فقط)
    avg_performance_query = RecitationSubmission.objects.filter(
        recitation__halaqa=halaqa, status='graded'
    ).aggregate(avg=Avg('score'))
    avg_performance = round((avg_performance_query['avg'] or 0) * 10, 1)

    # ✅ تسليمات قيد التصحيح (التسميع + المراجعة) لحلقة واحدة
    pending_submissions_halaqa = (
        RecitationSubmission.objects.filter(recitation__halaqa=halaqa, status='submitted').count()
        + ReviewSubmission.objects.filter(review__halaqa=halaqa, status='submitted').count()
    )

    # --- 2) سجل المهام الأخيرة ---
    recitations = Recitation.objects.filter(halaqa=halaqa).select_related('created_by__user')
    reviews     = Review.objects.filter(halaqa=halaqa).select_related('created_by__user')
    for r in recitations: r.type = 'تسميع'
    for v in reviews:     v.type = 'مراجعة'
    all_tasks = sorted(chain(recitations, reviews), key=attrgetter('created_at'), reverse=True)
    recent_tasks = all_tasks[:30]

    # --- 3) إحصائيات لكل طالب ---
    from django.db.models import Subquery, OuterRef, Count

    avg_score_subquery = RecitationSubmission.objects.filter(
        student=OuterRef('pk'),
        status='graded'
    ).values('student').annotate(avg_s=Avg('score')).values('avg_s')

    late_tasks_subquery = Recitation.objects.filter(
        halaqa=halaqa,
        deadline__lt=timezone.now()
    ).exclude(
        submissions__student=OuterRef('pk')
    ).values('halaqa').annotate(count=Count('id')).values('count')

    students_list = halaqa.students.select_related('user').annotate(
        avg_score=Subquery(avg_score_subquery),
        late_submissions_count=Subquery(late_tasks_subquery)
    ).order_by('user__username')

    # --- 4) السياق ---
    context = {
        'halaqa': halaqa,
        'student_count': student_count,
        'avg_performance': avg_performance,
        'recent_tasks': recent_tasks,
        'students_list': students_list,
        'pending_submissions_halaqa': pending_submissions_halaqa,
    }
    return render(request, 'teachers/halaqa_details.html', context)




@login_required
@require_POST
def add_student_task(request):
    try:
        from django.utils.dateparse import parse_datetime

        halaqa_id   = request.POST.get('halaqa_id')
        student_id  = request.POST.get('student_id')
        task_type   = request.POST.get('task_type', 'recitation')
        surah_id    = request.POST.get('surah_id')
        start_ayah  = request.POST.get('start_ayah')
        end_ayah    = request.POST.get('end_ayah')
        deadline_s  = request.POST.get('deadline')

        halaqa  = get_object_or_404(Halaqa, id=halaqa_id, teachers=request.user.profile)
        student = get_object_or_404(Profile, id=student_id, role=Profile.ROLE_STUDENT)
        if student.halaqa_id != halaqa.id:
            return JsonResponse({'status': 'error', 'message': 'الطالب ليس ضمن هذه الحلقة.'}, status=400)

        surah    = get_object_or_404(Surah, pk=surah_id)
        deadline = parse_datetime(deadline_s) if deadline_s else None

        base = {
            'halaqa': halaqa,
            'created_by': request.user.profile,
            'surah': surah.name,   # ← اسم السورة كنص
            'start_ayah': start_ayah,
            'end_ayah': end_ayah,
            'deadline': deadline,
        }

        obj = Review(**base) if task_type == 'review' else Recitation(**base)
        if hasattr(obj, 'assigned_to'):
            setattr(obj, 'assigned_to', student)
        obj.save()

        return JsonResponse({'status': 'success', 'message': f'تمت إضافة المهمة للطالب {student.user.username}.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'{e}'}, status=500)






import json
from .models import Halaqa, Profile, Notification 

# ... باقي دوال الـ views الخاصة بك ...


@require_POST
@login_required(login_url="accounts:login")
def send_halaqa_notification(request, halaqa_id):
    """
    View لإرسال إشعار لجميع طلاب حلقة معينة.
    يستقبل الطلب عبر AJAX ويقوم بإنشاء الإشعارات بشكل مجمع.
    """
    profile = request.user.profile
    if profile.role != Profile.ROLE_TEACHER:
        return JsonResponse({'status': 'error', 'message': 'ليس لديك صلاحية للقيام بهذا الإجراء.'}, status=403)

    try:
        data = json.loads(request.body)
        title = data.get('title', '').strip()
        message = data.get('message', '').strip()

        if not message:
            return JsonResponse({'status': 'error', 'message': 'محتوى الرسالة لا يمكن أن يكون فارغًا.'}, status=400)

        halaqa = get_object_or_404(Halaqa, id=halaqa_id)

        # خطوة أمان هامة: التأكد من أن المعلم الحالي يدير هذه الحلقة
        if not halaqa.teachers.filter(id=profile.id).exists():
            return JsonResponse({'status': 'error', 'message': 'أنت غير مسجل كمعلم في هذه الحلقة.'}, status=403)

        students = halaqa.students.all()
        if not students.exists():
             return JsonResponse({'status': 'error', 'message': 'لا يوجد طلاب في هذه الحلقة لإرسال الإشعار إليهم.'}, status=400)

        final_title = title if title else f'رسالة جديدة بخصوص حلقة {halaqa.name}'

        notifications_to_create = [
            Notification(
                recipient=student,
                title=final_title,
                message=message
            )
            for student in students
        ]

        # استخدام bulk_create لحفظ كل الإشعارات في استعلام واحد (أداء أفضل)
        Notification.objects.bulk_create(notifications_to_create)

        return JsonResponse({
            'status': 'success',
            'message': f'تم إرسال الإشعار بنجاح إلى {len(students)} طالب.'
        })

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'بيانات الطلب غير صالحة.'}, status=400)
    except Halaqa.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'الحلقة المطلوبة غير موجودة.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': 'حدث خطأ غير متوقع في الخادم.'}, status=500)
        


@login_required
def get_submission_details(request, submission_id):
    """
    API لجلب بيانات تسليم معين بصيغة JSON.
    """
    # تأكد أن المعلم له صلاحية على هذا التسليم
    submission = get_object_or_404(
        RecitationSubmission.objects.select_related('student__user', 'recitation'),
        pk=submission_id,
        recitation__halaqa__teachers=request.user.profile
    )

    data = {
        'student_name': submission.student.user.username,
        'avatar_url': submission.student.avatar_url,
        'recitation_title': str(submission.recitation),
        'deadline': submission.recitation.deadline.strftime('%Y-%m-%d %H:%M') if submission.recitation.deadline else 'غير محدد',
        'submitted_at': submission.created_at.strftime('%Y-%m-%d %H:%M'),
        'audio_url': submission.audio.url if submission.audio else '',
        'current_notes': submission.notes or '',
        'current_hifdh': submission.hifdh or 5,
        'current_rules': submission.rules or 5,
    }
    return JsonResponse(data)




@require_POST
@login_required
@transaction.atomic
def grade_submission(request, submission_id):
    """
    حفظ التقييم القادم من نافذة التقييم + إرجاع إحصائيات محدثة
    متطابقة مع teacher_dashboard.
    """
    submission = get_object_or_404(
        RecitationSubmission,
        pk=submission_id,
        recitation__halaqa__teachers=request.user.profile
    )

    # قراءة بيانات JSON
    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "صيغة البيانات غير صالحة."}, status=400)

    try:
        hifdh = float(data.get("hifdh", 0))
        rules = float(data.get("rules", 0))
        notes = (data.get("notes") or "").strip()
    except (TypeError, ValueError):
        return JsonResponse({"status": "error", "message": "قيم التقييم غير صالحة."}, status=400)

    # تحقق من الحدود (0..5)
    if not (0 <= hifdh <= 5) or not (0 <= rules <= 5):
        return JsonResponse({"status": "error", "message": "قيم التقييم يجب أن تكون بين 0 و 5."}, status=400)

    # الدرجة الإجمالية من 10
    total_score = hifdh + rules

    # حفظ التقييم
    submission.hifdh = hifdh
    submission.rules = rules
    submission.score = total_score
    submission.notes = notes
    submission.status = "graded"
    submission.save()

    # ===== إحصائيات محدثة (بنفس منطق لوحة المعلم) =====
    teacher = request.user.profile
    my_halaqat = Halaqa.objects.filter(teachers=teacher)  # نفس التجميعة المستخدمة في اللوحة

    # 1) تسليمات قيد التصحيح (لاحظ: الحالة 'submitted' وليست 'pending')
    pending_submissions_count = RecitationSubmission.objects.filter(
        recitation__halaqa__in=my_halaqat,
        status='submitted'
    ).count()

    # 2) إجمالي الطلاب في حلقات المعلم
    total_students_count = Profile.objects.filter(
        halaqa__in=my_halaqat,
        role=Profile.ROLE_STUDENT
    ).count()

    # 3) عدد الحلقات النشطة (لو عندك is_active استخدمه، وإلا استخدم العدد الكلي)
    # في teacher_dashboard أنت بتحسب count() مباشرة بدون فلتر is_active
    active_halaqat_count = my_halaqat.count()

    # 4) متوسط الأداء (من التسميعات المصححة فقط) ثم ×10 ليصبح نسبة مئوية
    avg_performance_rec = RecitationSubmission.objects.filter(
        recitation__halaqa__in=my_halaqat,
        status='graded'
    ).aggregate(avg_score=Avg('score'))['avg_score'] or 0
    average_performance = round(avg_performance_rec * 10, 1) if avg_performance_rec else 0

    return JsonResponse({
        "status": "success",
        "message": "تم حفظ التقييم بنجاح!",
        "stats": {
            "pending_submissions_count": pending_submissions_count,
            "total_students_count": total_students_count,
            "active_halaqat_count": active_halaqat_count,
            "average_performance": average_performance,
        }
    })






# في ملف: apps/accounts/views.py

@login_required
def teacher_submissions(request):
    teacher_profile = request.user.profile
    now = timezone.now()
    one_week_ago = now - timedelta(days=7)
    
    # جلب كل التسليمات (التسميع والمراجعة) الخاصة بحلقات هذا المعلم
    recitation_subs = RecitationSubmission.objects.filter(
        recitation__halaqa__teachers=teacher_profile
    ).select_related('student__user', 'recitation', 'recitation__halaqa')

    review_subs = ReviewSubmission.objects.filter(
        review__halaqa__teachers=teacher_profile
    ).select_related('student__user', 'review', 'review__halaqa')

    all_submissions_unfiltered = list(chain(recitation_subs, review_subs))
    
    # =============================================================
    # ===== بداية: منطق الفلترة الجديد لنوع المهمة =====
    # =============================================================

    task_type_filter = request.GET.get('type', 'all') # الافتراضي هو 'all'
    if task_type_filter == 'recitation':
        # hasattr(s, 'recitation') للتحقق إذا كان الكائن من نوع RecitationSubmission
        all_submissions_filtered_by_type = [s for s in all_submissions_unfiltered if hasattr(s, 'recitation')]
    elif task_type_filter == 'review':
        # hasattr(s, 'review') للتحقق إذا كان الكائن من نوع ReviewSubmission
        all_submissions_filtered_by_type = [s for s in all_submissions_unfiltered if hasattr(s, 'review')]
    else: # 'all'
        all_submissions_filtered_by_type = all_submissions_unfiltered

    # ترتيب القائمة النهائية بعد فلترتها حسب النوع
    all_submissions = sorted(
        all_submissions_filtered_by_type,
        key=lambda x: x.created_at,
        reverse=True
    )

    # فلترة حسب الحالة (من الرابط) - تعمل على القائمة المفلترة بالفعل حسب النوع
    status_filter = request.GET.get('status', 'submitted')
    if status_filter in ['submitted', 'graded', 'reviewing']:
        submissions = [s for s in all_submissions if s.status == status_filter]
    else: # حالة 'all'
        submissions = all_submissions
        
    # ===== نهاية: منطق الفلترة الجديد =====

    # حسابات الإحصائيات (تبقى كما هي)
    pending_count = sum(1 for s in all_submissions_unfiltered if s.status == 'submitted')
    completed_this_week_count = sum(1 for s in all_submissions_unfiltered if s.status == 'graded' and s.updated_at >= one_week_ago)
    needs_resubmission_count = sum(1 for s in all_submissions_unfiltered if s.status == 'reviewing')
    
    graded_submissions = [s for s in all_submissions_unfiltered if s.status == 'graded' and s.updated_at > s.created_at]
    # ... (باقي كود حساب متوسط الوقت يبقى كما هو)
    total_grading_time = timedelta(0)
    if graded_submissions:
        for sub in graded_submissions:
            total_grading_time += sub.updated_at - sub.created_at
        
        average_seconds = total_grading_time.total_seconds() / len(graded_submissions)
        avg_days = int(average_seconds // 86400)
        avg_hours = int((average_seconds % 86400) // 3600)
        avg_minutes = int((average_seconds % 3600) // 60)

        if avg_days > 0:
            average_grading_time = f"{avg_days} يوم"
        elif avg_hours > 0:
            average_grading_time = f"{avg_hours} ساعة"
        else:
            average_grading_time = f"{avg_minutes} دقيقة"
    else:
        average_grading_time = "N/A"

    context = {
        'submissions': submissions,
        'pending_count': pending_count,
        'completed_this_week_count': completed_this_week_count,
        'needs_resubmission_count': needs_resubmission_count,
        'average_grading_time': average_grading_time,
        'active_filter': status_filter,
        'active_type_filter': task_type_filter, # <-- نرسل الفلتر الجديد للقالب
        'teacher_halaqas': Halaqa.objects.filter(teachers=teacher_profile)
    } 
    return render(request, 'teachers/submissions.html', context)




@login_required
def teacher_settings_view(request):
    user = request.user
    profile = user.profile

    if request.method == 'POST':
        profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=profile, initial={'username': user.username, 'email': user.email})
        password_form = PasswordChangeForm(user, request.POST)

        # التحقق أي زر تم الضغط عليه
        if 'update_profile' in request.POST:
            if profile_form.is_valid():
                user.username = profile_form.cleaned_data['username']
                user.email = profile_form.cleaned_data['email']
                user.save()
                profile_form.save()

                # تحديث تفضيلات الإشعارات
                profile.email_notifications = 'email_notifications' in request.POST
                profile.app_notifications = 'app_notifications' in request.POST
                profile.save()

                messages.success(request, 'تم حفظ التغييرات بنجاح.')
            else:
                messages.error(request, 'يرجى تصحيح الأخطاء في معلوماتك الشخصية.')

        elif 'change_password' in request.POST:
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'تم تغيير كلمة المرور بنجاح.')
            else:
                messages.error(request, 'فشل تغيير كلمة المرور، يرجى مراجعة الأخطاء.')
        
        return redirect('accounts:teacher_settings')

    else:
        profile_form = ProfileUpdateForm(instance=profile, initial={'username': user.username, 'email': user.email})
        password_form = PasswordChangeForm(user)

    context = {
        'profile_form': profile_form,
        'password_form': password_form,
    }
    return render(request, 'teachers/teacher_settings.html', context)




@require_POST
@login_required
def logout_other_devices_view(request):
    # الحصول على كل الجلسات الخاصة بالمستخدم الحالي ما عدا الجلسة الحالية
    current_session_key = request.session.session_key
    user_sessions = Session.objects.filter(get_decoded__user_id=request.user.id).exclude(session_key=current_session_key)
    
    # حذف الجلسات الأخرى
    user_sessions.delete()
    
    return JsonResponse({'status': 'success', 'message': 'تم تسجيل الخروج من جميع الأجهزة الأخرى بنجاح.'})


@require_POST
@login_required
def delete_account_view(request):
    user = request.user
    # بدلاً من الحذف الكامل، من الأفضل تعطيل الحساب
    user.is_active = False
    user.save()
    # يمكنك إضافة أي منطق آخر هنا (مثل تسجيل الخروج)
    
    return JsonResponse({'status': 'success', 'message': 'تم حذف حسابك بنجاح.'})


@login_required(login_url="accounts:login")
def student_settings_view(request):
    user = request.user
    profile = user.profile

    # التأكد من أن المستخدم طالب
    if profile.role != 'student':
        # يمكنك توجيهه إلى لوحة تحكم المعلم أو صفحة خطأ
        return redirect('accounts:teacher_dashboard') 
    
    password_form = PasswordChangeForm(user)

    if request.method == 'POST':
        # التحقق من أي فورم تم إرساله
        if 'update_profile' in request.POST:
            full_name = request.POST.get('full_name')
            user.first_name = full_name.split(' ')[0] if full_name else ''
            user.last_name = ' '.join(full_name.split(' ')[1:]) if ' ' in full_name else ''
            user.save()

            if request.FILES.get('avatar'):
                profile.avatar = request.FILES['avatar']
                profile.save()

            messages.success(request, 'تم تحديث ملفك الشخصي بنجاح!')
            return redirect('accounts:student_settings')

        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                # تحديث جلسة المستخدم لمنعه من تسجيل الخروج بعد تغيير كلمة المرور
                update_session_auth_hash(request, user)  
                messages.success(request, 'تم تغيير كلمة المرور بنجاح!')
                return redirect('accounts:student_settings')
            else:
                # إذا كانت هناك أخطاء في فورم كلمة المرور، سيتم عرضها في القالب
                messages.error(request, 'يرجى تصحيح الأخطاء أدناه.')

    context = {
        'profile': profile,
        'password_form': password_form
    }
    return render(request, 'students/student_settings.html', context)




@require_POST
@login_required
def review_submit_view(request, task_id):
    review = Review.objects.get(id=task_id)
    audio_file = request.FILES.get('audio')

    if not audio_file:
        return JsonResponse({'ok': False, 'msg': 'لم يتم رفع ملف صوتي.'}, status=400)

    # إنشاء أو تحديث التسليم
    submission, created = ReviewSubmission.objects.update_or_create(
        student=request.user.profile,
        review=review,
        defaults={'audio_file': audio_file, 'status': 'submitted'}
    )
    
    return JsonResponse({'ok': True, 'msg': 'تم تسليم المراجعة بنجاح.'})



@require_POST
@login_required
def recitation_submit_view(request, task_id):
    task = get_object_or_404(Recitation, id=task_id)
    # ... (نفس منطق التسليم لديك)
    submission, created = RecitationSubmission.objects.update_or_create(...)
    
    # --- التعديل الجديد: إرجاع JSON للتحديث الفوري ---
    # إعادة تجهيز بيانات المهمة بعد التسليم لإرسالها للواجهة الأمامية
    setattr(task, "type", "recitation")
    setattr(task, "sub", submission)
    
    # حساب عدد المهام المطلوبة الجديد
    pending_tasks_count = Recitation.objects.filter(...).count() + Review.objects.filter(...).count() # أكمل هذا بحسب منطق حساب المهام المطلوبة
    
    return JsonResponse({
        'status': 'success',
        'message': 'تم التسليم بنجاح!',
        'task_id': task.id,
        'task_type': 'recitation',
        'updated_stats': {
            'pending_tasks_count': pending_tasks_count
        }
    })