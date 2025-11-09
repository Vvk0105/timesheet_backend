from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Employee(models.Model):
    CATEGORY_CHOICES = [
        ('A', 'Supervisor / Technician'),
        ('B', 'Office Staff'),
        ('C', 'Manager / Coordinator / Marketing'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    emp_no = models.CharField(max_length=50, unique=True, default='0')
    mobile = models.CharField(max_length=15, null=True, blank=True)  
    category = models.CharField(max_length=1, choices=CATEGORY_CHOICES, null=True, blank=True)
    designation = models.CharField(max_length=100, blank=True, null=True) 
    department = models.CharField(max_length=100, blank=True, null=True)  
    is_suspended = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username


class Attendance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    login_time = models.DateTimeField(default=timezone.now)
    selected_time = models.TimeField(null=True, blank=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)


class Job(models.Model):
    STATUS_CHOICES = [
        ('on_duty', 'On Duty'),
        ('leave', 'Leave'),
    ]

    LEAVE_TYPES = [
        ('sick', 'Sick Leave'),
        ('personal', 'Personal Leave'),
        ('annual', 'Annual Leave'),
        ('compensatory', 'Compensatory Leave'),
    ]

    attendance = models.ForeignKey(Attendance, on_delete=models.CASCADE, related_name='jobs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='on_duty')

    # On-Duty Fields
    task_title = models.CharField(max_length=200, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    job_no = models.CharField(max_length=100, blank=True, null=True)
    ship_name = models.CharField(max_length=100, blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)

    # Leave Fields
    leave_type = models.CharField(max_length=50, choices=LEAVE_TYPES, blank=True, null=True)
    leave_reason = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.attendance.employee.user.username} - {self.status}"

