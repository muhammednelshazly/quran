from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.templatetags.static import static








class Halaqa(models.Model):
    """حلقة تحفيظ: يشارك فيها طلاب، ويشرف عليها معلم/أكثر."""
    name = models.CharField(max_length=150, unique=True)

    # المعلمين المربوطين بالحَلَقة (توزيع من الأدمن)
    teachers = models.ManyToManyField(
        "Profile",
        related_name="halaqat_as_teacher",
        blank=True,
        limit_choices_to={"role": "teacher"},
    )

    def __str__(self):
        return self.name


class Profile(models.Model):
    """بروفايل المستخدم (طالب/معلّم)."""

    ROLE_STUDENT = "student"
    ROLE_TEACHER = "teacher"
    ROLE_CHOICES = (
        (ROLE_STUDENT, "Student"),
        (ROLE_TEACHER, "Teacher"),
    )

    GENDER_MALE = "male"
    GENDER_FEMALE = "female"
    GENDER_CHOICES = (
        (GENDER_MALE, "Male"),
        (GENDER_FEMALE, "Female"),
    )

    TEACHER_PENDING = "pending"
    TEACHER_APPROVED = "approved"
    TEACHER_REJECTED = "rejected"
    TEACHER_STATUS_CHOICES = (
        (TEACHER_PENDING, "Pending"),
        (TEACHER_APPROVED, "Approved"),
        (TEACHER_REJECTED, "Rejected"),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_STUDENT)

    # الطالب: يرتبط بحلقة واحدة
    halaqa = models.ForeignKey(
        Halaqa,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="students",
    )

    # بيانات إضافية
    gender = models.CharField(max_length=6, choices=GENDER_CHOICES, null=True, blank=True)
    photo = models.ImageField(upload_to="avatars/", null=True, blank=True)

    birth_date = models.DateField(null=True, blank=True)
    guardian_phone = models.CharField(max_length=30, null=True, blank=True)

    # بيانات خاصة بالمعلم
    institution = models.CharField(max_length=255, null=True, blank=True)
    bio = models.TextField(null=True, blank=True)
    certificate = models.FileField(upload_to="certificates/", null=True, blank=True)

    teacher_status = models.CharField(
        max_length=10,
        choices=TEACHER_STATUS_CHOICES,
        default=TEACHER_PENDING,
    )

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def avatar_url(self):
        if self.photo:
            try:
                return self.photo.url
            except Exception:
                pass
        g = (self.gender or "").lower()
        default_path = "img/avatars/female.png" if g == "female" else "img/avatars/male.png"
        return static(default_path)

    def clean(self):
        """لو المستخدم طالب: اجبر teacher_status = approved."""
        super().clean()
        if self.role != self.ROLE_TEACHER:
            self.teacher_status = self.TEACHER_APPROVED

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Recitation(models.Model):
    """مهمة تسميع جديدة ينشئها المعلّم."""

    halaqa = models.ForeignKey(Halaqa, on_delete=models.CASCADE, related_name="recitations")
    created_by = models.ForeignKey(
        Profile,
        on_delete=models.PROTECT,
        related_name="created_recitations",
        limit_choices_to={"role": "teacher"},
    )

    surah = models.CharField(max_length=100)
    range_text = models.CharField(max_length=50)
    deadline = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.surah} {self.range_text} – {self.halaqa.name}"


class RecitationSubmission(models.Model):
    """تسليم الطالب لمهمة تسميع."""

    STATUS_CHOICES = [
        ("submitted", "تم التسليم"),
        ("reviewing", "قيد المراجعة"),
        ("graded", "متصحّح"),
    ]

    recitation = models.ForeignKey(Recitation, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="recitation_submissions",
        limit_choices_to={"role": "student"},
    )
    audio = models.FileField(upload_to="recitations/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="submitted")

    score = models.PositiveSmallIntegerField(null=True, blank=True)
    rules = models.PositiveSmallIntegerField(null=True, blank=True)
    hifdh = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("recitation", "student")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student.user.username} → {self.recitation}"


class Review(models.Model):
    """مهمة مراجعة (قديمة) ينشئها المعلّم."""

    halaqa = models.ForeignKey(Halaqa, on_delete=models.CASCADE, related_name="reviews")
    created_by = models.ForeignKey(
        Profile,
        on_delete=models.PROTECT,
        related_name="created_reviews",
        limit_choices_to={"role": "teacher"},
    )

    surah = models.CharField(max_length=100)
    range_text = models.CharField(max_length=50)
    deadline = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.surah} {self.range_text} – {self.halaqa.name}"


class ReviewSubmission(models.Model):
    """تسليم الطالب لمهمة مراجعة."""

    STATUS_CHOICES = [
        ("submitted", "تم التسليم"),
        ("reviewing", "قيد المراجعة"),
        ("graded", "متصحّح"),
    ]

    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="review_submissions",
        limit_choices_to={"role": "student"},
    )
    audio = models.FileField(upload_to="reviews/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="submitted")

    score = models.PositiveSmallIntegerField(null=True, blank=True)
    rules = models.PositiveSmallIntegerField(null=True, blank=True)
    hifdh = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("review", "student")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student.user.username} → {self.review}"


class Attendance(models.Model):
    STATUS_CHOICES = [("present","حاضر"),("absent","غائب"),("late","متأخر")]
    student = models.ForeignKey(Profile, on_delete=models.CASCADE,
                               limit_choices_to={"role": Profile.ROLE_STUDENT})
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="present")

    class Meta:
        unique_together = ("student","date")
        ordering = ["-date"]
