from django.urls import path
from .views import AttendanceLoginView, AttendanceLogoutView, JobCreateListView, AdminAttendanceListView, JobDetailView, AdminLoginView

urlpatterns = [
    path('attendance/login/', AttendanceLoginView.as_view(), name='attendance-login'),
    path('attendance/logout/', AttendanceLogoutView.as_view(), name='attendance-logout'),
    path('jobs/', JobCreateListView.as_view(), name='job-create'),
    path('jobs/<int:pk>/', JobDetailView.as_view(), name='job-detail'),
    path('admin/attendance/', AdminAttendanceListView.as_view(), name='admin-attendance-list'),
    path('admin/login/', AdminLoginView.as_view(), name='admin-login'),

]
