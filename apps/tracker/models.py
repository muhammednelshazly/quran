from django.db import models
from django.contrib.auth.models import User

class Halaqa(models.Model):
    name = models.CharField(max_length=100)
    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='halaqat')
    start_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.name

class Student(models.Model):
    student_no = models.CharField(max_length=20, unique=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    age = models.PositiveIntegerField(null=True, blank=True)
    joined_at = models.DateField()
    halaqa = models.ForeignKey(Halaqa, on_delete=models.SET_NULL, null=True, related_name='students')

    def __str__(self):
        return self.user.get_full_name() or self.user.username

class DailyMemorization(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='memorization_records')
    date = models.DateField()
    from_surah = models.CharField(max_length=100)
    from_ayah = models.PositiveIntegerField()
    to_surah = models.CharField(max_length=100)
    to_ayah = models.PositiveIntegerField()
    mastery = models.IntegerField(help_text="0-100%")

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.student} {self.date} {self.from_surah}:{self.from_ayah}-{self.to_surah}:{self.to_ayah}"

class Review(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='reviews')
    date = models.DateField()
    surah_or_juz = models.CharField(max_length=100)
    mastery = models.IntegerField(help_text="0-100%")

    class Meta:
        ordering = ['-date']

class Attendance(models.Model):
    STATUS = (('present','Present'), ('absent','Absent'))
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS)

    class Meta:
        unique_together = ('student','date')
        ordering = ['-date']

class WeeklyEvaluation(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='weekly_evaluations')
    week_start = models.DateField()
    score = models.IntegerField(help_text="0-100%")

    class Meta:
        unique_together = ('student','week_start')
        ordering = ['-week_start']

class MonthlyReport(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='monthly_reports')
    month = models.DateField(help_text="Use the first day of the month")
    memorized_count = models.IntegerField(default=0)
    mastery_avg = models.FloatField(default=0.0)
    attendance_rate = models.FloatField(default=0.0)

    class Meta:
        unique_together = ('student','month')
        ordering = ['-month']
