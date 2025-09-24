# apps/accounts/views.py
from datetime import datetime, timedelta
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.db import transaction, IntegrityError
from django.utils import timezone
from hijri_converter import convert
from django.http import HttpResponseRedirect

from datetime import date
from django.utils import timezone
try:
    from hijri_converter import Gregorian as _Gregorian
    HIJRI_OK = True

except Exception:
    HIJRI_OK = False


from apps.accounts.models import (
    Recitation,
    RecitationSubmission,
    Attendance,
    Profile, Halaqa,        # إن كنت تستخدمه في الفيوز
    Review, ReviewSubmission
)




# ========= أدوات مساعدة =========
AR_HIJRI_MONTHS = [
    "محرم", "صفر", "ربيع الأول", "ربيع الآخر",
    "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان",
    "رمضان", "شوال", "ذو القعدة", "ذو الحجة",
]





def landing_page(request):
    # لو عايز تحول تلقائيًا للدashboard بمجرد دخول مستخدم مسجل:
    # if request.user.is_authenticated:
    #     return redirect('go')
    return render(request, 'landing_page.html')

def go(request):
    """
    بوابة التوجيه من أزرار الصفحة الرئيسية.
    """
    user = request.user

    # لو الدور موجود كـ attribute أو في profile
    role = getattr(user, 'role', None)
    if role is None and hasattr(user, 'profile'):
        role = getattr(user.profile, 'role', None)

    # لو الطالب
    if role == 'student' or user.groups.filter(name__iexact='student').exists():
        return HttpResponseRedirect('/dashboard/')

    # لو المعلّم
    if role == 'teacher' or user.groups.filter(name__iexact='teacher').exists():
        return HttpResponseRedirect('/teacher/dashboard/')

    # لو مفيش دور أو أي مشكلة → رجّعه على اللوجين
    return HttpResponseRedirect('/login/')



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

        # السماح بتسجيل الدخول عبر البريد أو اسم المستخدم
        username = identifier
        if "@" in identifier:
            user_obj = User.objects.filter(email__iexact=identifier).first()
            username = user_obj.username if user_obj else None

        user = authenticate(request, username=username, password=password) if username else None
        if user is None:
            messages.error(request, "بيانات الدخول غير صحيحة.")
            return render(request, "accounts/login.html", {"selected_role": role})

        # الإدمن يروح للوحة /admin
        if user.is_staff or user.is_superuser:
            return redirect("/admin/")

        # تأكيد البروفايل
        if not hasattr(user, "profile"):
            Profile.objects.create(user=user)

        # نوع الحساب لازم يطابق الاختيار
        if user.profile.role != role:
            messages.error(request, "نوع الحساب لا يطابق الاختيار (طالب/معلم).")
            return render(request, "accounts/login.html", {"selected_role": role})

        # معلم غير معتمد؟
        if role == Profile.ROLE_TEACHER and user.profile.teacher_status != Profile.TEACHER_APPROVED:
            messages.error(request, "حساب المعلم قيد المراجعة من المشرف. سيتم إشعارك عند الاعتماد.")
            return render(request, "accounts/login.html", {"selected_role": role})

        login(request, user)
        # الجلسة: 0 = تُغلق بخروج المتصفح، أو 14 يوم لو Remember me
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
    # وفي أي return بسبب خطأ أثناء POST:
    return render(request, "accounts/register.html", {"halaqas": Halaqa.objects.all().order_by("name"),
                                                    "selected_role": role})


# ========= لوحات التحكم =========

def start_of_sat_week(d):
    # Mon=0..Sun=6  → Saturday=5
    delta = (d.weekday() - 5) % 7
    return d - timedelta(days=delta)



@login_required(login_url="accounts:login")
def student_dashboard(request):
    profile = request.user.profile
    if profile.role != Profile.ROLE_STUDENT:
        return redirect("accounts:teacher_dashboard")

    # ===== تسجيل حضور اليوم تلقائيًا =====
    today = timezone.localdate()

    # لو النهارده "سبت" نبدأ أسبوع جديد: نمسح أي أيام أقدم من النهارده
    # (كده بننظّف أسابيع قديمة مرة واحدة كل سبت)
    if today.weekday() == 5:  # Monday=0 ... Saturday=5
        Attendance.objects.filter(student=profile, date__lt=today).delete()

    Attendance.objects.get_or_create(
        student=profile,
        date=today,
        defaults={"status": "present"}
    )

    # نعرض في الواجهة آخر 7 أيام (الأحدث للأقدم ثم نعكس للنظام)
    week_attendance = Attendance.objects.filter(
        student=profile
    ).order_by("-date")[:7][::-1]

    # ===== المهام والتسليمات =====
    recitations = (
        Recitation.objects
        .filter(halaqa=profile.halaqa)
        .select_related("halaqa", "created_by")
    )
    subs = RecitationSubmission.objects.filter(
        student=profile, recitation__in=recitations
    )
    sub_map = {s.recitation_id: s for s in subs}
    for r in recitations:
        setattr(r, "sub", sub_map.get(r.id))

    # ===== التاريخ الميلادي/الهجري =====
    g_date = today.strftime("%Y-%m-%d")
    if HIJRI_OK:
        h = _Gregorian(today.year, today.month, today.day).to_hijri()
        try:
            h_date = f"{h.day} {h.month_name('ar')} {h.year}هـ"
        except Exception:
            h_date = f"{h.day}-{h.month}-{h.year}هـ"
    else:
        h_date = ""

    ctx = {
        "user": request.user,
        "profile": profile,
        "recitations": recitations,
        "week_attendance": week_attendance,
        "weekly_score": 90, "ayah_count": 120, "accuracy_pct": 90, "presence_pct": 86,
        "g_date": g_date,
        "h_date": h_date,
        "now": timezone.now(),
    }
    return render(request, "students/student_dashboard.html", ctx)





@login_required(login_url="accounts:login")
def teacher_dashboard(request):
    profile = request.user.profile
    if profile.role != Profile.ROLE_TEACHER:
        return redirect("accounts:student_dashboard")

    if profile.teacher_status != Profile.TEACHER_APPROVED:
        messages.error(request, "حسابك كمعلم قيد المراجعة. تواصل مع المشرف لاعتماد الحساب وإسناد الحلقات.")
        return redirect("accounts:login")

    # الحلقات المسندة لهذا المعلم بواسطة المشرف (M2M)
    my_halaqat = Halaqa.objects.filter(teachers=profile).distinct()

    # إنشاء تسميع جديد
    if request.method == "POST":
        halaqa_id = request.POST.get("halaqa_id")
        surah = request.POST.get("surah", "").strip()
        range_text = request.POST.get("range_text", "").strip()
        deadline_str = request.POST.get("deadline")  # اختياري

        if not (halaqa_id and surah and range_text):
            messages.error(request, "برجاء إدخال بيانات التسميع كاملة.")
            return redirect("accounts:teacher_dashboard")

        halaqa = get_object_or_404(Halaqa, id=halaqa_id, teachers=profile)
        Recitation.objects.create(
            halaqa=halaqa, created_by=profile,
            surah=surah, range_text=range_text,
            # deadline: ممكن تحوّل deadline_str إلى datetime لو فعّلت المدخل
        )
        messages.success(request, "تم إنشاء التسميع.")
        return redirect("accounts:teacher_dashboard")

    recs = Recitation.objects.filter(halaqa__in=my_halaqat).select_related('halaqa', 'created_by')
    return render(request, "teachers/teacher_dashboard.html", {"halaqat": my_halaqat, "recitations": recs})


# ========= التسجيل/الرفع للتسميع =========

@login_required(login_url="accounts:login")
def recitation_start(request, pk):
    """صفحة واجهة التسجيل (لو بتستخدم صفحة منفصلة)."""
    profile = get_object_or_404(Profile, user=request.user, role=Profile.ROLE_STUDENT)
    recitation = get_object_or_404(Recitation, pk=pk, halaqa=profile.halaqa)

    # لو يوجد تسليم سابق "submitted" أو "graded"، المودال في الـ UI بيدير الحاله.
    # الصفحة نفسها بتعرض المعلومات فقط.
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
    زر "إعادة التسميع": احذف التسليم الحالي (لو موجود) علشان
    الـ submissions_map ما يبقاش فيه العنصر، وساعتها يظهر زر "ابدأ التسميع".
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
    زر "إعادة المراجعة": احذف تسليم المراجعة (لو موجود)
    علشان ترجع بطاقة المراجعة لحالة البداية.
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
