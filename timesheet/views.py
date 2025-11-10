from rest_framework import generics, permissions, viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Attendance, Job, Employee, LeaveRecord, LeaveBalance
from .serializers import AttendanceSerializer, JobSerializer, EmployeeSerializer, LeaveRecordSerializer,LeaveBalanceSerializer
from rest_framework.permissions import AllowAny
from rest_framework.authentication import BasicAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response

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

        # Employee login
        if hasattr(user, 'employee'):
            employee = user.employee
            if employee.is_suspended:
                return Response({'error': 'Your account is suspended'}, status=403)
            role = "employee"

        # Admin login
        elif user.is_superuser:
            user.is_staff = True  # ensures DRF admin permission
            user.save(update_fields=['is_staff'])
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
        attendance.save()  # this triggers duration calculation

        # ✅ Re-fetch the updated record to include calculated duration
        attendance.refresh_from_db()

        return Response({
            "message": "Logout recorded successfully",
            "duration": str(attendance.duration)
        })



# 🔹 Work Entries (Employee)
class JobListCreateView(generics.ListCreateAPIView):
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Job.objects.select_related("attendance__employee__user").all()

        # ✅ Non-admin users see only their own jobs
        if not user.is_superuser:
            queryset = queryset.filter(attendance__employee__user=user)

        # ✅ Apply filters from query params
        employee_id = self.request.query_params.get("employee")
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")

        if employee_id:
            queryset = queryset.filter(attendance__employee__id=employee_id)

        if start_date and end_date:
            queryset = queryset.filter(created_at__date__range=[start_date, end_date])

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        employee = self.request.user.employee
        data = self.request.data
        status_value = data.get("status")
        leave_type = data.get("leave_type")

        attendance = Attendance.objects.filter(employee=employee, logout_time__isnull=True).last()
        if not attendance:
            raise ValueError("No active login session found")

        # ✅ Deduct leave if type = leave
        if status_value == 'leave':
            try:
                balance = LeaveBalance.objects.get(employee=employee, leave_type=leave_type)
            except LeaveBalance.DoesNotExist:
                raise ValueError(f"No leave balance found for {leave_type}")

            if balance.remaining() <= 0:
                raise ValueError(f"No {leave_type} leaves remaining!")

            balance.used += 1
            balance.save()

        serializer.save(attendance=attendance)


# 🔹 Work Entry Detail (update/delete)
class JobDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Job.objects.all()
        return Job.objects.filter(employee__user=user)


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


# 🔹 Admin Manage Leaves
class AdminLeaveViewSet(viewsets.ModelViewSet):
    queryset = LeaveRecord.objects.select_related('employee__user').all()
    serializer_class = LeaveRecordSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        # Optionally filter by employee in query params: ?employee=<id>
        queryset = super().get_queryset()
        employee_id = self.request.query_params.get('employee')
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        return queryset

# 🔹 Admin Manage Leave Balances
class AdminLeaveBalanceViewSet(viewsets.ModelViewSet):
    queryset = LeaveBalance.objects.select_related('employee__user').all()
    serializer_class = LeaveBalanceSerializer
    permission_classes = [permissions.IsAdminUser]

    def create(self, request, *args, **kwargs):
        employee_id = request.data.get("employee")
        leave_type = request.data.get("leave_type")
        action = request.data.get("action", "set")  # can be 'add', 'deduct', or 'set'
        amount = int(request.data.get("amount", request.data.get("total_allocated", 0)))

        # Get or create the leave balance record
        balance, created = LeaveBalance.objects.get_or_create(
            employee_id=employee_id,
            leave_type=leave_type,
            defaults={"total_allocated": amount}
        )

        # If already exists, modify based on action
        if not created:
            if action == "add":
                balance.total_allocated += amount
            elif action == "deduct":
                balance.total_allocated = max(0, balance.total_allocated - amount)
            else:
                balance.total_allocated = amount  # direct set/update
            balance.save()

        serializer = self.get_serializer(balance)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class EmployeeViewSet(AdminManageEmployee):  # reuse admin employee view
    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAdminUser])
    def attendances(self, request, pk=None):
        """Fetch all attendance records for a specific employee"""
        employee = self.get_object()
        attendances = Attendance.objects.filter(employee=employee).order_by("-login_time")
        serializer = AttendanceSerializer(attendances, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAdminUser])
    def jobs(self, request, pk=None):
        """Fetch all jobs done by a specific employee"""
        employee = self.get_object()
        jobs = Job.objects.filter(attendance__employee=employee).select_related("attendance").order_by("-created_at")
        serializer = JobSerializer(jobs, many=True)
        return Response(serializer.data)
    
class EmployeeViewSet(AdminManageEmployee):  # reuse admin employee view
    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAdminUser])
    def attendances(self, request, pk=None):
        """Fetch all attendance records for a specific employee"""
        employee = self.get_object()
        attendances = Attendance.objects.filter(employee=employee).order_by("-login_time")
        serializer = AttendanceSerializer(attendances, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAdminUser])
    def jobs(self, request, pk=None):
        """Fetch all jobs done by a specific employee"""
        employee = self.get_object()
        jobs = Job.objects.filter(attendance__employee=employee).select_related("attendance").order_by("-created_at")
        serializer = JobSerializer(jobs, many=True)
        return Response(serializer.data)
    
class AdminManageEmployee(viewsets.ModelViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAdminUser]

    # 🔹 Custom route: /api/employees/<id>/attendances/
    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAdminUser])
    def attendances(self, request, pk=None):
        """Fetch all attendance records for a specific employee"""
        try:
            employee = self.get_object()
            attendances = Attendance.objects.filter(employee=employee).order_by("-login_time")
            serializer = AttendanceSerializer(attendances, many=True)
            return Response(serializer.data)
        except Employee.DoesNotExist:
            return Response({"error": "Employee not found"}, status=404)

    # 🔹 Custom route: /api/employees/<id>/jobs/
    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAdminUser])
    def jobs(self, request, pk=None):
        """Fetch all jobs done by a specific employee"""
        try:
            employee = self.get_object()
            jobs = Job.objects.filter(attendance__employee=employee).select_related("attendance").order_by("-created_at")
            serializer = JobSerializer(jobs, many=True)
            return Response(serializer.data)
        except Employee.DoesNotExist:
            return Response({"error": "Employee not found"}, status=404)
