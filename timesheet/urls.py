from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AttendanceLoginView, AttendanceLogoutView, JobListCreateView,
    JobDetailView, AdminManageEmployee, LoginView, SuspendEmployeeView,AdminLeaveViewSet, AdminLeaveBalanceViewSet,EmployeeTimeSheetView,employee_profile, AttendanceStatusView,daywise_report,monthly_timesheet,monthly_leave_report_employee,my_leave_balances, ProfileView, ApplyLeaveAPIView, dashboard_today
)
from .admin_profile_views import (
    AdminProfileView,
    AdminProfileUpdateView,
    ChangePasswordView,
    CreateAdminView,
)

from .views_admin_manage import ManageAdminsView, DeleteAdminView

router = DefaultRouter()
router.register(r'employees', AdminManageEmployee, basename='employee')
router.register(r'leaves', AdminLeaveViewSet, basename='leave') 
router.register(r'leavebalances', AdminLeaveBalanceViewSet, basename='leavebalance')

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('attendance/login/', AttendanceLoginView.as_view(), name='attendance-login'),
    path('attendance/logout/', AttendanceLogoutView.as_view(), name='attendance-logout'),
    path('attendance/status/', AttendanceStatusView.as_view(), name='attendance-status'),
    path("profile/", ProfileView.as_view(), name="user-profile"),
    path("dashboard/today/", dashboard_today),



    path('workentries/', JobListCreateView.as_view(), name='workentry-list'),
    path('workentries/<int:pk>/', JobDetailView.as_view(), name='workentry-detail'),

    path('employees/<int:pk>/suspend/', SuspendEmployeeView.as_view(), name='suspend-employee'),
    path("employees/me/", employee_profile, name="employee-profile"),

    path('timesheet/<int:employee_id>/', EmployeeTimeSheetView.as_view(), name='employee-timesheet'),
    path("leaves/apply/", ApplyLeaveAPIView.as_view()),
    path("leavebalances/", AdminLeaveBalanceViewSet.as_view({'post': 'create', 'get': 'list'})),
    path("leavebalances/me/", my_leave_balances, name="my-leave-balances"),

    path("timesheet/monthly/", monthly_timesheet),

    path("daywise-report/", daywise_report),
    path("leaves/report/employee/", monthly_leave_report_employee),

    path('', include(router.urls)),

    path("admin/profile/", AdminProfileView.as_view()),
    path("admin/profile/update/", AdminProfileUpdateView.as_view()),
    path("admin/profile/change-password/", ChangePasswordView.as_view()),
    path("admin/create/", CreateAdminView.as_view()),

    path("admin/manage-admins/", ManageAdminsView.as_view()),
    path("admin/manage-admins/<int:user_id>/delete/", DeleteAdminView.as_view()),

]
