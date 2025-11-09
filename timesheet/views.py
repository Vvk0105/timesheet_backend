from rest_framework import generics, permissions, viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Attendance, WorkEntry, Employee
from .serializers import AttendanceSerializer, WorkEntrySerializer, EmployeeSerializer
from rest_framework.permissions import AllowAny
from rest_framework.authentication import BasicAuthentication

# 🔹 Unified Login (admin + employee)
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        user = authenticate(username=username, password=password)
        if not user:
            return Response({'error': 'Invalid username or password'}, status=401)

        # Employee check
        if hasattr(user, 'employee'):
            employee = user.employee
            if employee.is_suspended:
                return Response({'error': 'Your account is suspended'}, status=403)
            role = "employee"
        elif user.is_superuser:
            role = "admin"
        else:
            return Response({'error': 'Invalid role'}, status=403)

        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'username': user.username,
            'role': role
        })


# 🔹 Attendance
class AttendanceLoginView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        employee = request.user.employee
        selected_time = request.data.get('selected_time')
        attendance = Attendance.objects.create(employee=employee, selected_time=selected_time)
        return Response({"message": "Login recorded successfully", "attendance_id": attendance.id})


class AttendanceLogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        employee = request.user.employee
        attendance = Attendance.objects.filter(employee=employee, logout_time__isnull=True).last()
        if not attendance:
            return Response({"error": "No active session found"}, status=400)
        attendance.logout_time = timezone.now()
        attendance.save()
        return Response({"message": "Logout recorded successfully", "duration": attendance.duration})


# 🔹 Work Entries (Employee)
class WorkEntryListCreateView(generics.ListCreateAPIView):
    serializer_class = WorkEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return WorkEntry.objects.all()
        return WorkEntry.objects.filter(employee__user=user)

    def perform_create(self, serializer):
        employee = self.request.user.employee
        serializer.save(employee=employee)


# 🔹 Work Entry Detail (update/delete)
class WorkEntryDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = WorkEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return WorkEntry.objects.all()
        return WorkEntry.objects.filter(employee__user=user)


# 🔹 Admin Manage Employees
class AdminManageEmployee(viewsets.ModelViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAdminUser]


# 🔹 Suspend/Reactivate Employee
class SuspendEmployeeView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        try:
            employee = Employee.objects.get(pk=pk)
            employee.is_suspended = not employee.is_suspended
            employee.save()
            status_text = "suspended" if employee.is_suspended else "reactivated"
            return Response({"message": f"Employee {status_text} successfully"})
        except Employee.DoesNotExist:
            return Response({"error": "Employee not found"}, status=404)
