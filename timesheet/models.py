from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date

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
    is_suspended = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username


class Attendance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    login_time = models.DateTimeField(default=timezone.now)
    selected_time = models.TimeField(null=True, blank=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Calculate duration safely with timezone-aware datetimes
        if self.logout_time and self.login_time:
            login = self.login_time
            logout = self.logout_time
            if timezone.is_naive(login):
                login = timezone.make_aware(login)
            if timezone.is_naive(logout):
                logout = timezone.make_aware(logout)
            self.duration = logout - login

        super().save(*args, **kwargs)

    def __str__(self):
        date_str = str(self.login_time.date()) if self.login_time else 'No date'
        return f"{self.employee.user.username} - {date_str}"
    
    @property
    def computed_duration(self):
        if self.logout_time and self.login_time:
            return self.logout_time - self.login_time
        return None


class Job(models.Model):
    STATUS_CHOICES = [
        ('on_duty', 'On Duty'),
        ('leave', 'Leave'),
    ]

    LEAVE_TYPES = [
        ('sick', 'Sick'),
        ('casual', 'Casual'),
        ('annual', 'Annual Leave'),
        ('compoff', 'Comp-Off'),
        ('lossofpay', 'Loss of Pay'),
        ('restrictedholiday', 'Restricted Holiday'),
    ]

    attendance = models.ForeignKey(Attendance, on_delete=models.CASCADE, related_name='jobs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='on_duty')

    # On-Duty Fields
    description = models.TextField(blank=True, null=True)
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    job_no = models.CharField(max_length=100, blank=True, null=True)
    ship_name = models.CharField(max_length=100, blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)

    # Leave Fields
    leave_type = models.CharField(max_length=50, choices=LEAVE_TYPES, blank=True, null=True)
    leave_reason = models.TextField(blank=True, null=True)

    # 🔹 Worked On (for Type A employees)
    holiday_worked = models.BooleanField(default=False)
    off_station = models.BooleanField(default=False)
    local_site = models.BooleanField(default=False)
    driv = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.attendance.employee.user.username} - {self.status}"

class LeaveRecord(models.Model):
    LEAVE_TYPES = [
        ('sick', 'Sick Leave'),
        ('personal', 'Personal Leave'),
        ('annual', 'Annual Leave'),
        ('compensatory', 'Compensatory Leave'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_records')
    leave_type = models.CharField(max_length=50, choices=LEAVE_TYPES)
    reason = models.TextField(blank=True, null=True)
    count = models.PositiveIntegerField(default=1, help_text="Number of leave days")
    date = models.DateField(default=date.today)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee.user.username} - {self.leave_type} ({self.count} days)"

class LeaveBalance(models.Model):
    LEAVE_TYPES = [
        ('sick', 'Sick Leave'),
        ('personal', 'Personal Leave'),
        ('annual', 'Annual Leave'),
        ('compensatory', 'Compensatory Leave'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_balances')
    leave_type = models.CharField(max_length=50, choices=LEAVE_TYPES)
    total_allocated = models.PositiveIntegerField(default=0)
    used = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('employee', 'leave_type')
        ordering = ['employee__user__username', 'leave_type']

    def remaining(self):
        return self.total_allocated - self.used

    def __str__(self):
        return f"{self.employee.user.username} - {self.leave_type}: {self.remaining()} left"

