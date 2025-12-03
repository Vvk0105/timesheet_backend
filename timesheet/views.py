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
from datetime import date, datetime
from rest_framework import serializers
import calendar

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
        category = None

        # Employee login
        if hasattr(user, 'employee'):
            employee = user.employee
            if employee.is_suspended:
                return Response({'error': 'Your account is suspended'}, status=403)
            role = "employee"
            category = employee.category

        # Admin login
        elif user.is_superuser:
            user.is_staff = True  # ensures DRF admin permission
            user.save(update_fields=['is_staff'])
            role = "admin"

        else:
            return Response({'error': 'Invalid role'}, status=403)
 
        current_date = datetime.now().strftime("%A %d %B %Y")
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'username': user.username,
            'role': role,
            'category': category,
            'current_date': current_date
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
        job_no = self.request.query_params.get('job_no')

        if job_no:
            queryset = queryset.filter(job_no__icontains=job_no)

        # ✅ Non-admin users see only their own jobs
        if not user.is_superuser:
            queryset = queryset.filter(attendance__employee__user=user)

        # ✅ Apply filters from query params
        employee_id = self.request.query_params.get("employee")
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")
        status_value = self.request.query_params.get("status")

        if employee_id:
            queryset = queryset.filter(attendance__employee__id=employee_id)

        if status_value:
            queryset = queryset.filter(status=status_value)

        if start_date and end_date:
            queryset = queryset.filter(created_at__date__range=[start_date, end_date])

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        employee = self.request.user.employee
        data = self.request.data
        status_value = data.get("status")
        leave_type = data.get("leave_type")

        # ✅ Find the employee's current attendance
        attendance = Attendance.objects.filter(employee=employee, logout_time__isnull=True).last()
        if not attendance:
            return Response({"error": "No active login session found."}, status=400)

        # ✅ Check if the employee already has on-duty work today
        today = timezone.now().date()
        if status_value == 'leave' and Job.objects.filter(
            attendance__employee=employee,
            attendance__login_time__date=today,
            status='on_duty'
        ).exists():
            raise serializers.ValidationError(
                {"error": "You are already marked as On Duty today. Leave not allowed."}
            )

        # ✅ Check if the employee already has leave for today
        if status_value == 'on_duty' and Job.objects.filter(
            attendance__employee=employee,
            attendance__login_time__date=today,
            status='leave'
        ).exists():
            raise serializers.ValidationError(
                {"error": "You have already marked Leave today. On-duty not allowed."}
            )

        # ✅ Deduct leave if type = leave
        if status_value == 'leave':
            try:
                balance = LeaveBalance.objects.get(employee=employee, leave_type=leave_type)
            except LeaveBalance.DoesNotExist:
                raise serializers.ValidationError({"error": f"No leave balance found for {leave_type}"})

            if balance.remaining() <= 0:
                raise serializers.ValidationError({"error": f"No {leave_type} leaves remaining!"})

            balance.used += 1
            balance.save()

             # save leave history record
            LeaveRecord.objects.create(
                employee=employee,
                date=today,
                leave_type=leave_type,
                reason=data.get("leave_reason", ""),
                count=1
            )

        # ✅ Save job entry
        serializer.save(attendance=attendance)


# 🔹 Work Entry Detail (update/delete)
class JobDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Job.objects.all()
        return Job.objects.filter(attendance__employee__user=user)
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)

        return Response({"message": "Job entry deleted successfully"}, status=200)


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

        # Optional filters
        start_date = request.GET.get("start")
        end_date = request.GET.get("end")

        attendances = Attendance.objects.filter(employee=employee)

        # Apply date range if given
        if start_date and end_date:
            attendances = attendances.filter(
                login_time__date__range=[start_date, end_date]
            )

        attendances = attendances.prefetch_related(
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
        "emp_no": emp.emp_no,
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def daywise_report(request):
    """
    Returns work entries for a specific date.
    Optional: filter by employee.
    """
    report_date = request.GET.get("date")
    employee_id = request.GET.get("employee")
    job_no = request.GET.get("job_no") 

    if not report_date:
        return Response({"error": "date parameter is required (YYYY-MM-DD)"}, status=400)

    # Correct filter: use attendance date, not created_at
    filters = {"attendance__login_time__date": report_date}

    if employee_id:
        filters["attendance__employee_id"] = employee_id
    
    if job_no:
        filters["job_no__icontains"] = job_no 

    jobs = Job.objects.filter(**filters).select_related(
        "attendance__employee__user"
    )

    data = []
    for job in jobs:
        worked_on_list = []
        if job.holiday_worked:
            worked_on_list.append("Holiday Worked")
        if job.off_station:
            worked_on_list.append("Off Station")
        if job.local_site:
            worked_on_list.append("Local Site")
        if job.driv:
            worked_on_list.append("Driving")

        data.append({
            "employee": job.attendance.employee.user.username,
            "status": job.status,
            "description": job.description or "-",
            "job_no": job.job_no or "-",
            "location": job.location or "-",
            "worked_on": ", ".join(worked_on_list) or "-",
            "start_time": job.start_time or "-",
            "end_time": job.end_time or "-",
        })

    return Response(data)



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def monthly_timesheet(request):
    employee_id = request.GET.get("employee")
    month_str = request.GET.get("month")  # format: YYYY-MM

    if not employee_id or not month_str:
        return Response({"error": "employee and month (YYYY-MM) are required"}, status=400)

    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return Response({"error": "Employee not found"}, status=404)

    # Extract year + month
    year, month = map(int, month_str.split("-"))

    # 🔥 FIX: Find number of days in month
    days_in_month = calendar.monthrange(year, month)[1]  # e.g. 30 for November

    attendances = Attendance.objects.filter(
        employee=employee,
        login_time__year=year,
        login_time__month=month
    ).prefetch_related("jobs").order_by("login_time")

    # Initialize empty data for each valid day
    data = {
        d: {
            "date": d,
            "day": date(year, month, d).strftime("%A"),
            "job_details": [],
            "job_no": [],
            "holiday_worked": False,
            "off_station": False,
            "local_site": False,
            "driv": False,
        }
        for d in range(1, days_in_month + 1)
    }

    for att in attendances:
        day = att.login_time.day

        for job in att.jobs.all():

            # --- LEAVE ENTRY ---
            if job.status == "leave":
                leave_text = f"Leave: {job.leave_type.capitalize()}"
                if job.leave_reason:
                    leave_text += f" - {job.leave_reason}"
                data[day]["job_details"] = leave_text
                continue

            # --- DUTY ENTRY ---
            if job.description:
                if data[day]["job_details"]:
                    data[day]["job_details"] += ", "
                data[day]["job_details"] += job.description

            if job.job_no:
                if data[day]["job_no"]:
                    data[day]["job_no"] += ", "
                data[day]["job_no"] += job.job_no

            if job.holiday_worked:
                data[day]["holiday_worked"] = True
            if job.off_station:
                data[day]["off_station"] = True
            if job.local_site:
                data[day]["local_site"] = True
            if job.driv:
                data[day]["driv"] = True

    output = list(data.values())

    return Response({
        "employee": employee.user.username,
        "emp_no": employee.emp_no,
        "month": month_str,
        "days_in_month": days_in_month,
        "data": output,
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def monthly_leave_report_employee(request):
    """
    Returns leave report for one employee for a selected month.
    Example: /api/leaves/report/employee/?employee=4&month=2025-11
    """
    emp_id = request.GET.get("employee")
    month = request.GET.get("month")

    if not emp_id or not month:
        return Response({"error": "employee and month (YYYY-MM) are required"}, status=400)

    try:
        employee = Employee.objects.get(id=emp_id)
    except Employee.DoesNotExist:
        return Response({"error": "Employee not found"}, status=404)

    year, month_num = map(int, month.split("-"))

    leaves = LeaveRecord.objects.filter(
        employee=employee,
        date__year=year,
        date__month=month_num
    ).order_by("date")

    records = []
    total = 0

    for leave in leaves:
        records.append({
            "date": leave.date,
            "type": leave.leave_type,
            "reason": leave.reason,
            "count": leave.count
        })
        total += leave.count

    return Response({
        "employee": employee.user.username,
        "employee_id": employee.id,
        "month": month,
        "total_leaves": total,
        "records": records
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_leave_balances(request):
    """Return the logged-in employee's leave balances"""
    user = request.user
    if not hasattr(user, "employee"):
        return Response({"error": "User is not an employee"}, status=400)

    balances = LeaveBalance.objects.filter(employee=user.employee)
    serializer = LeaveBalanceSerializer(balances, many=True)
    return Response(serializer.data)


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        employee_id = None
        category = None

        # If employee exists
        if hasattr(user, "employee"):
            employee = user.employee
            employee_id = employee.id
            category = employee.category
        
        return Response({
            "username": user.username,
            "employee_id": employee_id,
            "category": category
        })