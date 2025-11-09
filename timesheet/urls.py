from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AttendanceLoginView, AttendanceLogoutView, WorkEntryListCreateView,
    WorkEntryDetailView, AdminManageEmployee, LoginView, SuspendEmployeeView
)

router = DefaultRouter()
router.register(r'employees', AdminManageEmployee, basename='employee')

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('attendance/login/', AttendanceLoginView.as_view(), name='attendance-login'),
    path('attendance/logout/', AttendanceLogoutView.as_view(), name='attendance-logout'),

    path('workentries/', WorkEntryListCreateView.as_view(), name='workentry-list'),
    path('workentries/<int:pk>/', WorkEntryDetailView.as_view(), name='workentry-detail'),

    path('employees/<int:pk>/suspend/', SuspendEmployeeView.as_view(), name='suspend-employee'),

    path('', include(router.urls)),
]
