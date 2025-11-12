from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AttendanceLoginView, AttendanceLogoutView, JobListCreateView,
    JobDetailView, AdminManageEmployee, LoginView, SuspendEmployeeView,AdminLeaveViewSet, AdminLeaveBalanceViewSet,EmployeeTimeSheetView,employee_profile, AttendanceStatusView
)

router = DefaultRouter()
router.register(r'employees', AdminManageEmployee, basename='employee')
router.register(r'leaves', AdminLeaveViewSet, basename='leave') 
router.register(r'leavebalances', AdminLeaveBalanceViewSet, basename='leavebalance')

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('attendance/login/', AttendanceLoginView.as_view(), name='attendance-login'),
    path('attendance/logout/', AttendanceLogoutView.as_view(), name='attendance-logout'),
    path('attendance/status/', AttendanceStatusView.as_view(), name='attendance-status'),


    path('workentries/', JobListCreateView.as_view(), name='workentry-list'),
    path('workentries/<int:pk>/', JobDetailView.as_view(), name='workentry-detail'),

    path('employees/<int:pk>/suspend/', SuspendEmployeeView.as_view(), name='suspend-employee'),
    path("employees/me/", employee_profile, name="employee-profile"),

    path('timesheet/<int:employee_id>/', EmployeeTimeSheetView.as_view(), name='employee-timesheet'),

    path('', include(router.urls)),
]
