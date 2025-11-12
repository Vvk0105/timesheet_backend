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
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Prefetch
from collections import defaultdict
from rest_framework.permissions import IsAuthenticated
from datetime import date

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
        today = date.today()

        # 🔒 Check if user already marked leave today
        if Job.objects.filter(
            attendance__employee=employee,
            created_at__date=today,
            status='leave'
        ).exists():
            return Response(
                {"error": "You have already marked leave for today. Attendance not allowed."},
                status=400
            )

        # 🔍 Check if attendance exists for today
        existing = Attendance.objects.filter(employee=employee, login_time__date=today).last()

        if existing and existing.logout_time is None:
            # ✅ Resume ongoing session
            return Response({
                "message": "Resuming your existing attendance session.",
                "attendance_id": existing.id,
                "selected_time": existing.selected_time
            })

        if existing and existing.logout_time:
            return Response(
                {"error": "You have already completed attendance today."},
                status=400
            )

        # ✅ Create new attendance
        attendance = Attendance.objects.create(employee=employee, selected_time=selected_time)
        return Response({
            "message": "Login recorded successfully",
            "attendance_id": attendance.id
        })


class AttendanceLogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        employee = request.user.employee

        attendance = Attendance.objects.filter(
            employee=employee, 
            logout_time__isnull=True
        ).last()

        if not attendance:
            return Response({"error": "No active session found"}, status=400)

        attendance.logout_time = timezone.now()
        attendance.save()  # Triggers duration calculation
        attendance.refresh_from_db()  # ✅ Ensure updated duration is loaded

        return Response({
            "message": "Logout recorded successfully",
            "logout_time": attendance.logout_time,
            "duration": str(attendance.duration) if attendance.duration else "0:00:00"
        })


class AttendanceStatusView(APIView):
    """
    Check if the employee already has an active attendance session today.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        employee = request.user.employee
        today = date.today()

        # Find today's attendance with no logout
        attendance = Attendance.objects.filter(
            employee=employee,
            login_time__date=today,
            logout_time__isnull=True
        ).last()

        if attendance:
            return Response({
                "active_attendance": True,
                "attendance_id": attendance.id,
                "login_time": attendance.login_time,
                "selected_time": attendance.selected_time,
            })

        return Response({"active_attendance": False})

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
        today = date.today()

        # 🔹 If the user tries to create a LEAVE entry
        if status_value == "leave":
            # Already logged in today?
            if Attendance.objects.filter(employee=employee, login_time__date=today).exists():
                raise ValueError("You are already marked as On Duty today. Leave not allowed.")
            
            # Already taken leave today?
            if Job.objects.filter(
                attendance__employee=employee,
                created_at__date=today,
                status="leave"
            ).exists():
                raise ValueError("You have already marked leave for today.")

            # Deduct leave balance if valid
            try:
                balance = LeaveBalance.objects.get(employee=employee, leave_type=leave_type)
            except LeaveBalance.DoesNotExist:
                raise ValueError(f"No leave balance found for {leave_type}")

            if balance.remaining() <= 0:
                raise ValueError(f"No {leave_type} leaves remaining!")

            balance.used += 1
            balance.save()

            # ✅ Create a dummy attendance for internal linking consistency
            attendance = Attendance.objects.create(employee=employee, selected_time=None)
            serializer.save(attendance=attendance)
            return

        # 🔹 If On Duty, check if attendance session exists
        attendance = Attendance.objects.filter(employee=employee, logout_time__isnull=True).last()
        if not attendance:
            raise ValueError("No active login session found. Please log in first.")

        # ✅ Create job entry linked to the current attendance
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

class EmployeeTimeSheetView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, employee_id):
        try:
            employee = Employee.objects.get(pk=employee_id)
        except Employee.DoesNotExist:
            return Response({"error": "Employee not found"}, status=404)

        attendances = Attendance.objects.filter(employee=employee).prefetch_related(
            Prefetch('jobs', queryset=Job.objects.all())
        ).order_by('-login_time')

        grouped_data = defaultdict(lambda: {
            "date": None,
            "day": None,
            "job_details": [],
            "job_no": [],
            "worked_on": set(),
            "duration": None
        })

        for attendance in attendances:
            date_str = str(attendance.login_time.date())
            group = grouped_data[date_str]

            group["date"] = attendance.login_time.date()
            group["day"] = attendance.login_time.strftime("%A")
            group["duration"] = str(attendance.duration) if attendance.duration else None

            for job in attendance.jobs.all():
                if job.description:
                    group["job_details"].append(job.description)
                if job.job_no:
                    group["job_no"].append(job.job_no)
                if job.holiday_worked:
                    group["worked_on"].add("Holiday Worked")
                if job.off_station:
                    group["worked_on"].add("Off Station")
                if job.local_site:
                    group["worked_on"].add("Local Site")
                if job.driv:
                    group["worked_on"].add("Driving")

        result = []
        for date, data in grouped_data.items():
            result.append({
                "date": data["date"],
                "day": data["day"],
                "job_details": ", ".join(data["job_details"]) or "-",
                "job_no": ", ".join(data["job_no"]) or "-",
                "worked_on": ", ".join(sorted(data["worked_on"])) or "-",
                "duration": data["duration"] or "-"
            })

        # Sort by latest date first
        result.sort(key=lambda x: x["date"], reverse=True)

        return Response(result)
    
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def employee_profile(request):
    """Fetch logged-in employee's category and info"""
    user = request.user
    if not hasattr(user, 'employee'):
        return Response({"error": "User is not an employee"}, status=400)

    emp = user.employee
    return Response({
        "id": emp.id,
        "username": user.username,
        "category": emp.category,
        "designation": emp.designation,
        "department": emp.department,
        "emp_no": emp.emp_no,
    })