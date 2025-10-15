from django.contrib import admin
from django.contrib.auth.models import User
from .models import Employee, Attendance, Job

# Inline Employee for User creation
class EmployeeInline(admin.StackedInline):
    model = Employee
    can_delete = False
    verbose_name_plural = 'Employee Details'

# Extend User admin to include Employee info
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

class UserAdmin(BaseUserAdmin):
    inlines = (EmployeeInline,)

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

# Register Attendance and Job for admin view
@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'login_time', 'logout_time', 'duration')
    list_filter = ('employee', 'login_time')
    search_fields = ('employee__user__username',)

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('attendance', 'task_title', 'start_time', 'end_time')
    list_filter = ('attendance__employee',)
    search_fields = ('task_title', 'attendance__employee__user__username')
