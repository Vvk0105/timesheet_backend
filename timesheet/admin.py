from django.contrib import admin
from django.contrib.auth.models import User
from .models import Employee, Attendance, Job, LeaveRecord, LeaveBalance

admin.site.register(Employee)
admin.site.register(Attendance)
admin.site.register(Job)
admin.site.register(LeaveRecord)
admin.site.register(LeaveBalance)
