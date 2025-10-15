from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Employee(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    designation = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.user.username

class Attendance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    login_time = models.DateTimeField(default=timezone.now)
    selected_time = models.TimeField(null=True, blank=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.logout_time and self.login_time:
            self.duration = self.logout_time - self.login_time
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee.user.username} | {self.login_time.date()}"

class Job(models.Model):
    attendance = models.ForeignKey(Attendance, on_delete=models.CASCADE, related_name='jobs')
    task_title = models.CharField(max_length=200)
    description = models.TextField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.task_title} - {self.attendance.employee.user.username}"
