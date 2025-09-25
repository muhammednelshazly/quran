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
    Review, ReviewSubmission
)

# ========= أدوات مساعدة =========
AR_HIJRI_MONTHS = [
    "محرم", "صفر", "ربيع الأول", "ربيع الآخر",
    "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان",
    "رمضان", "شوال", "ذو القعدة", "ذو الحجة",
]

# ==========================================================
#                  --- بداية التعديلات ---
# ==========================================================

def landing_page(request):
    """
    الصفحة الرئيسية (Landing Page).
    # تعديل: إذا كان المستخدم مسجلاً دخوله (وليس مشرفًا)، يتم تحويله مباشرةً
    # إلى بوابة التوجيه go التي سترسله إلى لوحة التحكم المناسبة.
    # المشرف (Admin) سيتمكن من رؤية الصفحة الرئيسية بشكل طبيعي.
    """
    if request.user.is_authenticated and not request.user.is_staff:
        return redirect('go')
    
    # إذا كان المستخدم زائرًا أو مشرفًا، اعرض له الصفحة الرئيسية
    return render(request, 'landing_page.html')


def go(request):
    """
    بوابة التوجيه من أزرار الصفحة الرئيسية.
    تقوم بتوجيه كل مستخدم إلى لوحة التحكم الخاصة به.
    """
    user = request.user

    # تعديل: أضفنا التحقق من المشرف (Admin) كأول خطوة
    # إذا كان المستخدم مشرفًا أو أدمن، وجهه إلى لوحة تحكم الأدمن الرئيسية.
    if user.is_staff or user.is_superuser:
        return redirect('admin:index')

    # باقي المنطق يبقى كما هو للطلاب والمعلمين
    role = getattr(user, 'role', None)
    if role is None and hasattr(user, 'profile'):
        role = getattr(user.profile, 'role', None)

    if role == 'student' or user.groups.filter(name__iexact='student').exists():
        return redirect('accounts:student_dashboard')

    if role == 'teacher' or user.groups.filter(name__iexact='teacher').exists():
        return redirect('accounts:teacher_dashboard')

    # إذا كان المستخدم مسجلاً ولكن ليس له دور (أو أي مشكلة أخرى)،
    # رجّعه إلى صفحة تسجيل الدخول.
    return redirect('accounts:login')

# ==========================================================
#                  --- نهاية التعديلات ---
# ==========================================================


def home_view(request):
    return render(request, "home.html")


# ========= تسجيل الدخول / الخروج =========

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

        # تم نقل منطق توجيه الأدمن إلى دالة go ليكون مركزيًا
        if user.is_staff or user.is_superuser:
            login(request, user) # يجب تسجيل الدخول أولاً
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
        messages.success(request, "تم تسجيل الدخول بنجاح.")
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
            halaqa_obj = None

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
                    profile.teacher_status = Profile.TEACHER_APPROVED
                else:
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

    return render(request, "accounts/register.html", {"halaqas": Halaqa.objects.all().order_by("name")})


# ========= لوحات التحكم =========

def start_of_sat_week(d):
    delta = (d.weekday() - 5) % 7
    return d - timedelta(days=delta)


def _range_len(obj):
    try:
        s = int(getattr(obj, "start_ayah", 0) or 0)
        e = int(getattr(obj, "end_ayah", 0) or 0)
        return (e - s + 1) if (s and e and e >= s) else 0
    except Exception:
        return 0


@login_required(login_url="accounts:login")
def student_dashboard(request):
    # تعديل: أضفنا هذا الشرط كحماية
    # إذا حاول المشرف (Admin) الدخول إلى هذه الصفحة، يتم تحويله إلى لوحة تحكم الأدمن.
    if request.user.is_staff:
        return redirect('admin:index')

    profile = request.user.profile
    if profile.role != Profile.ROLE_STUDENT:
        return redirect("accounts:teacher_dashboard")

    # ===== تسجيل حضور اليوم تلقائيًا =====
    today = timezone.localdate()

    if today.weekday() == 5:
        Attendance.objects.filter(student=profile, date__lt=today).delete()

    Attendance.objects.get_or_create(
        student=profile,
        date=today,
        defaults={"status": "present"}
    )

    week_attendance = Attendance.objects.filter(
        student=profile
    ).order_by("-date")[:7][::-1]

    # ===== المهام المعروضة للطالب =====
    recitations = (
        Recitation.objects
        .filter(halaqa=profile.halaqa)
        .select_related("halaqa", "created_by")
    )
    rec_subs = RecitationSubmission.objects.filter(
        student=profile, recitation__in=recitations
    )
    rec_sub_map = {s.recitation_id: s for s in rec_subs}
    for r in recitations:
        setattr(r, "sub", rec_sub_map.get(r.id))

    reviews = (
        Review.objects
        .filter(halaqa=profile.halaqa)
        .select_related("halaqa", "created_by")
    )
    rev_subs = ReviewSubmission.objects.filter(
        student=profile, review__in=reviews
    )
    rev_sub_map = {s.review_id: s for s in rev_subs}
    for rv in reviews:
        setattr(rv, "sub", rev_sub_map.get(rv.id))

    # ===== التاريخ الميلادي/الهجري (اختياري) =====
    g_date = today.strftime("%Y-%m-%d")
    if HIJRI_OK:
        h = _Gregorian(today.year, today.month, today.day).to_hijri()
        try:
            h_date = f"{h.day} {h.month_name('ar')} {h.year}هـ"
        except Exception:
            h_date = f"{h.day}-{h.month}-{h.year}هـ"
    else:
        h_date = ""

    # ===== إحصائيات الأسبوع (من Submissions فقط) =====
    now = timezone.now()
    week_ago = now - timedelta(days=7)

    rec_subs_week = RecitationSubmission.objects.filter(
        student=profile, created_at__gte=week_ago, created_at__lte=now
    ).select_related("recitation")

    rev_subs_week = ReviewSubmission.objects.filter(
        student=profile, created_at__gte=week_ago, created_at__lte=now
    ).select_related("review")

    ACCEPTED_STATUSES = ["accepted", "approved", "graded"]
    accepted_rec = rec_subs_week.filter(status__in=ACCEPTED_STATUSES)
    accepted_rev = rev_subs_week.filter(status__in=ACCEPTED_STATUSES)
    
    # تم نقل الدالة المساعدة لداخل النطاق أو تعريفها في الأعلى
    # def _range_len(obj): ...

    ayahs_memorized = 0
    for s in accepted_rec:
        ayahs_memorized += _range_len(s.recitation)
    for s in accepted_rev:
        ayahs_memorized += _range_len(s.review)

    attempted = rec_subs_week.count() + rev_subs_week.count()
    accepted  = accepted_rec.count() + accepted_rev.count()
    proficiency_pct = round((accepted / attempted) * 100, 1) if attempted else 0.0

    held = len(week_attendance)
    present = sum(1 for a in week_attendance if getattr(a, "status", "") == "present")
    attendance_pct = round((present / held) * 100, 1) if held else 0.0

    ctx = {
        "user": request.user,
        "profile": profile,
        "recitations": recitations,
        "reviews": reviews,
        "week_attendance": week_attendance,
        "weekly_score": proficiency_pct,
        "ayah_count": ayahs_memorized,
        "accuracy_pct": proficiency_pct,
        "presence_pct": attendance_pct,
        "g_date": g_date,
        "h_date": h_date,
        "now": timezone.now(),
    }
    return render(request, "students/student_dashboard.html", ctx)


@login_required(login_url="accounts:login")
def teacher_dashboard(request):
    # تعديل: أضفنا هذا الشرط كحماية
    # إذا حاول المشرف (Admin) الدخول إلى هذه الصفحة، يتم تحويله إلى لوحة تحكم الأدمن.
    if request.user.is_staff:
        return redirect('admin:index')

    profile = request.user.profile
    if profile.role != Profile.ROLE_TEACHER:
        return redirect("accounts:student_dashboard")

    if profile.teacher_status != Profile.TEACHER_APPROVED:
        return redirect("accounts:login")

    my_halaqat = Halaqa.objects.filter(teachers=profile).distinct()
    recitations = (Recitation.objects
                   .filter(halaqa__in=my_halaqat)
                   .select_related("halaqa", "created_by")
                   .order_by("-id"))
    
    ctx = {
        "profile": profile,
        "halaqat": my_halaqat,
        "recitations": recitations,
    }
    return render(request, "teachers/teacher_dashboard.html", ctx)


# ========= التسجيل/الرفع للتسميع =========

@login_required(login_url="accounts:login")
def recitation_start(request, pk):
    profile = get_object_or_404(Profile, user=request.user, role=Profile.ROLE_STUDENT)
    recitation = get_object_or_404(Recitation, pk=pk, halaqa=profile.halaqa)
    return render(request, "students/recitation_record.html", {
        "recitation": recitation,
        "profile": profile,
    })


@require_POST
@login_required(login_url="accounts:login")
def recitation_submit(request, pk):
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
    profile = get_object_or_404(Profile, user=request.user, role=Profile.ROLE_STUDENT)
    review = get_object_or_404(Review, pk=pk, halaqa=profile.halaqa)

    action = request.POST.get("action")
    if action == "retry":
        ReviewSubmission.objects.filter(review=review, student=profile).delete()
        messages.success(request, "تمت إعادة ضبط المراجعة. يمكنك البدء من جديد.")
    else:
        messages.info(request, "إجراء غير معروف.")

    return redirect("accounts:student_dashboard")