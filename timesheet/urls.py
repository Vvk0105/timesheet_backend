from django.urls import path
from .views import AttendanceLoginView, AttendanceLogoutView, JobCreateView, AdminAttendanceListView

urlpatterns = [
    path('attendance/login/', AttendanceLoginView.as_view(), name='attendance-login'),
    path('attendance/logout/', AttendanceLogoutView.as_view(), name='attendance-logout'),
    path('jobs/', JobCreateView.as_view(), name='job-create'),
    path('admin/attendance/', AdminAttendanceListView.as_view(), name='admin-attendance-list'),
]
