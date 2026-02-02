from rest_framework import generics, permissions, viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Attendance, Job, Employee, LeaveRecord, LeaveBalance
from .serializers import AttendanceSerializer, JobSerializer, EmployeeSerializer, LeaveRecordSerializer,LeaveBalanceSerializer,LeaveApplySerializer
from rest_framework.permissions import AllowAny
from rest_framework.authentication import BasicAuthentication
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Prefetch
from collections import defaultdict
from rest_framework.permissions import IsAuthenticated
from datetime import date, datetime, timedelta
from rest_framework import serializers
import calendar
from django.db import transaction
from .utils import is_employee_on_leave


def auto_close_old_attendance(employee):
    today = timezone.localdate()

    Attendance.objects.filter(
        employee=employee,
        logout_time__isnull=True,
        login_time__date__lt=today
    ).update(
        logout_time=timezone.make_aware(
            datetime.combine(
                today - timedelta(days=1),
                datetime.max.time()
            )
        )
    )

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

        today = timezone.localdate()
        category = None
        role = None

        # SUPERADMIN LOGIN
        if user.is_superuser:
            role = "superadmin"

        # STAFF LOGIN
        elif user.is_staff:
            role = "staff"

        # EMPLOYEE LOGIN
        elif hasattr(user, 'employee'):
            employee = user.employee
            category = employee.category

            # ✅ AUTO-CLOSE PREVIOUS DAY ATTENDANCE
            auto_close_old_attendance(employee)

            # ❌ Suspend check
            if employee.is_suspended:
                return Response(
                    {'error': 'Your account is suspended'},
                    status=403
                )

            # ❌ BLOCK if today is inside approved leave
            if LeaveRecord.objects.filter(
                employee=employee,
                start_date__lte=today,
                end_date__gte=today
            ).exists():
                return Response(
                    {"error": "You are on approved leave today. Login not allowed."},
                    status=403
                )

            # 🔍 Check today attendance
            attendance_today = Attendance.objects.filter(
                employee=employee,
                login_time__date=today
            ).last()

            # ❌ Block only if attendance is COMPLETED
            if attendance_today and attendance_today.logout_time is not None:
                return Response(
                    {"error": "You have already completed attendance today."},
                    status=400
                )

            role = "employee"

        else:
            return Response({'error': 'Invalid role'}, status=403)

        # SUCCESS
        refresh = RefreshToken.for_user(user)
        current_date = timezone.localtime().strftime("%A %d %B %Y")

        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'username': user.username,
            'role': role,
            'category': category,
            'employee_id': user.employee.id if hasattr(user, 'employee') else None,
            'current_date': current_date
        })

    
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_today_stats(request):
    now = timezone.localtime()
    today = timezone.localdate()

    total_employees = Employee.objects.count()
    suspended = Employee.objects.filter(is_suspended=True).count()
    active_employees = total_employees - suspended

    attendance_ids = set(
        Attendance.objects.filter(
            login_time__date=today,
            employee_id__isnull=False
        ).values_list("employee_id", flat=True)
    )

    daily_leave_ids = set(
        Job.objects.filter(
            status="leave",
            attendance__login_time__date=today,
            attendance__employee_id__isnull=False
        ).values_list("attendance__employee_id", flat=True)
    )

    annual_leave_ids = set(
        LeaveRecord.objects.filter(
            start_date__lte=today,
            end_date__gte=today,
            employee_id__isnull=False
        ).values_list("employee_id", flat=True)
    )

    attendance_coverage = attendance_ids | daily_leave_ids | annual_leave_ids

    total_work_entries = Job.objects.filter(
        attendance__login_time__date=today,
        status="on_duty"
    ).count()

    total_leave_today = len(daily_leave_ids | annual_leave_ids)

    THRESHOLD_PERCENT = 80
    required_attendance = max(1, round(active_employees * THRESHOLD_PERCENT / 100))
    alert = len(attendance_coverage) < required_attendance

    return Response({
        "date": str(today),
        "business_datetime": now.isoformat(),
        "business_date": today.isoformat(),
        "business_timezone": "Asia/Dubai",
        "total_employees": total_employees,
        "active_employees": active_employees,
        "attendance_coverage": len(attendance_coverage),
        "required_attendance": required_attendance,
        "total_work_entries": total_work_entries,
        "total_leave_today": total_leave_today,
        "alert": alert,
    })


# 🔹 Attendance
class AttendanceLoginView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        employee = request.user.employee
        selected_time = request.data.get('selected_time')
        today = timezone.localdate()

        if is_employee_on_leave(employee, today):
            return Response(
                {"error": "You are on leave today"},
                status=400
            )

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
            existing.logged = True
            existing.save()
            # ✅ Resume ongoing session
            return Response({
                "message": "Resuming your existing attendance session.",
                "attendance_id": existing.id,
                "selected_time": existing.selected_time,
                "logged": existing.logged
            })

        if existing and existing.logout_time:
            return Response(
                {"error": "You have already completed attendance today."},
                status=400
            )

        # ✅ Create new attendance
        attendance = Attendance.objects.create(employee=employee, selected_time=selected_time, logged=True)
        return Response({
            "message": "Login recorded successfully",
            "attendance_id": attendance.id,
            "logged": attendance.logged
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
            return Response({"error": "No active session found", "logged": False}, status=400)

        attendance.logout_time = timezone.now()
        attendance.logged = False
        attendance.save()  # Triggers duration calculation
        attendance.refresh_from_db()  # ✅ Ensure updated duration is loaded

        return Response({
            "message": "Logout recorded successfully",
            "logout_time": attendance.logout_time,
            "logged": attendance.logged,
            "duration": str(attendance.duration) if attendance.duration else "0:00:00"
        })


class AttendanceStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        employee = request.user.employee
        today = timezone.localdate()

        # Debug logs
        print("Checking attendance for:", employee.id, employee.user.username)
        print("Today:", today)

        attendance = Attendance.objects.filter(
            employee=employee,
            login_time__date=today,
            logout_time__isnull=True
        ).last()

        print("Found attendance:", attendance)

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

        if is_employee_on_leave(employee, date.today()):
            raise serializers.ValidationError(
                {"error": "Cannot create job while on leave"}
            )
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
            today = timezone.localdate()

            LeaveRecord.objects.create(
                employee=employee,
                leave_type=leave_type,
                start_date=today,
                end_date=today,
                total_days=1,
                reason=data.get("leave_reason", "")
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
    
    def update(self, request, *args, **kwargs):
        job = self.get_object()
        if job.is_approved  and not request.user.is_superuser:
            return Response(
                {"error": "The Job is approved and cannot be edited"},
                status=403
            )
        return super().update(request, *args, **kwargs) 
    
    def destroy(self, request, *args, **kwargs):
        job = self.get_object()

        # ❌ Block employee delete
        if job.is_approved and not request.user.is_superuser:
            return Response(
                {"error": "This job is approved and cannot be deleted"},
                status=403
            )
        
        instance = self.get_object()
        self.perform_destroy(instance)

        return Response({"message": "Job entry deleted successfully"}, status=200)
    
class ApproveJobAPIView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, job_id):
        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return Response({"error": "Job not found"}, status=404)

        if job.is_approved:
            return Response({"message": "Job already approved"})

        job.is_approved = True
        job.approved_at = timezone.now()
        job.approved_by = request.user
        job.save()

        return Response({
            "message": "Job approved successfully",
            "approved_at": job.approved_at,
            "approved_by": request.user.username
        })

class UnapproveJobAPIView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, job_id):
        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return Response({"error": "Job not found"}, status=404)

        if not job.is_approved:
            return Response({"message": "Job is already unapproved"})

        job.is_approved = False
        job.approved_at = None
        job.approved_by = None
        job.save()

        return Response({"message": "Job approval reverted successfully"})


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
def work_reports(request):
    date_str = request.GET.get("date")
    month_str = request.GET.get("month")
    employee_id = request.GET.get("employee")
    job_no = request.GET.get("job_no")

    # ❌ validation
    if date_str and month_str:
        return Response(
            {"error": "Use either date OR month, not both"},
            status=400
        )

    if not date_str and not month_str:
        return Response(
            {"error": "Either date or month is required"},
            status=400
        )

    # ❌ prevent duplicate query params
    for key in request.GET:
        if len(request.GET.getlist(key)) > 1:
            return Response(
                {"error": f"Duplicate query param: {key}"},
                status=400
            )

    data = []

    # ======================================================
    # 🟦 DAY-WISE REPORT
    # ======================================================
    if date_str:
        report_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        # Annual leave first
        leave_qs = LeaveRecord.objects.filter(
            start_date__lte=report_date,
            end_date__gte=report_date
        ).select_related("employee__user")

        if employee_id:
            leave_qs = leave_qs.filter(employee_id=employee_id)

        annual_leave_employees = set()

        for leave in leave_qs:
            annual_leave_employees.add(leave.employee_id)

            desc = leave.leave_type.capitalize()
            if leave.reason:
                desc += f" - {leave.reason}"

            data.append({
                "employee": leave.employee.user.username,
                "status": "leave",
                "description": desc,
                "job_no": "-",
                "ship_name": "-",
                "location": "-",
                "worked_on": "-",
                "start_time": "-",
                "end_time": "-",
                "is_approved": True,
            })

        filters = {"attendance__login_time__date": report_date}

        if employee_id:
            filters["attendance__employee_id"] = employee_id
        if job_no:
            filters["job_no__icontains"] = job_no

        jobs = Job.objects.filter(**filters).select_related(
            "attendance__employee__user"
        )

        for job in jobs:
            emp = job.attendance.employee
            if emp.id in annual_leave_employees:
                continue

            worked_on = []
            if job.holiday_worked: worked_on.append("Holiday Worked")
            if job.off_station: worked_on.append("Off Station")
            if job.local_site: worked_on.append("Local Site")
            if job.driv: worked_on.append("Driving")

            if job.status == "leave":
                desc = job.leave_type.capitalize()
                if job.leave_reason:
                    desc += f" - {job.leave_reason}"
            else:
                desc = job.description or "-"

            data.append({
                "id": job.id,
                "employee": emp.user.username,
                "status": job.status,
                "description": desc,
                "job_no": job.job_no or "-",
                "ship_name": job.ship_name or "-",
                "location": job.location or "-",
                "worked_on": ", ".join(worked_on) or "-",
                "start_time": job.start_time or "-",
                "end_time": job.end_time or "-",
                "is_approved": job.is_approved,
            })

        return Response(data)

    # ======================================================
    # 🟩 MONTH-WISE REPORT
    # ======================================================
    year, month = map(int, month_str.split("-"))
    start_date = date(year, month, 1)
    end_date = date(year, month, calendar.monthrange(year, month)[1])

    filters = {
        "attendance__login_time__date__range": [start_date, end_date]
    }

    if employee_id:
        filters["attendance__employee_id"] = employee_id
    if job_no:
        filters["job_no__icontains"] = job_no

    jobs = Job.objects.filter(**filters).select_related(
        "attendance__employee__user"
    )

    for job in jobs:
        worked_on = []
        if job.holiday_worked: worked_on.append("Holiday Worked")
        if job.off_station: worked_on.append("Off Station")
        if job.local_site: worked_on.append("Local Site")
        if job.driv: worked_on.append("Driving")

        data.append({
            "id": job.id,
            "date": job.attendance.login_time.date(),
            "employee": job.attendance.employee.user.username,
            "status": job.status,
            "description": job.description or "-",
            "job_no": job.job_no or "-",
            "worked_on": ", ".join(worked_on) or "-",
            "start_time": job.start_time or "-",
            "end_time": job.end_time or "-",
            "is_approved": job.is_approved,
        })

    return Response(data)

from datetime import timedelta
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def monthly_timesheet(request):
    employee_id = request.GET.get("employee")
    month_str = request.GET.get("month")

    year, month = map(int, month_str.split("-"))
    days_in_month = calendar.monthrange(year, month)[1]

    employee = Employee.objects.get(id=employee_id)

    # ----------------------------------
    # Initialize data for each day
    # ----------------------------------
    data = {
        d: {
            "date": d,
            "day": date(year, month, d).strftime("%A"),
            "job_details": "",
            "job_no": "",
            "holiday_worked": False,
            "off_station": False,
            "local_site": False,
            "driv": False,
            "is_approved": False,
        }
        for d in range(1, days_in_month + 1)
    }

    # ----------------------------------
    # 1️⃣ Fill attendance jobs
    # ----------------------------------
    attendances = Attendance.objects.filter(
        employee=employee,
        login_time__year=year,
        login_time__month=month
    ).prefetch_related("jobs")

    for att in attendances:
        day = att.login_time.day

        for job in att.jobs.all():

            # ---- LEAVE ENTRY ----
            if job.status == "leave":
                leave_text = f"Leave: {job.leave_type.capitalize()}"
                if job.leave_reason:
                    leave_text += f" - {job.leave_reason}"

                data[day]["job_details"] = leave_text
                continue

            # ---- DUTY ENTRY (ACCUMULATE) ----
            if job.description:
                if data[day]["job_details"] not in ("", "-"):
                    data[day]["job_details"] += ", "
                data[day]["job_details"] += job.description

            if job.job_no:
                if data[day]["job_no"] not in ("", "-"):
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
            
            if job.is_approved:
                data[day]["is_approved"] = True

    # ----------------------------------
    # 2️⃣ Inject annual leave
    # ----------------------------------
    leaves = LeaveRecord.objects.filter(
        employee=employee,
        leave_type="annual",
        start_date__year__lte=year,
        end_date__year__gte=year
    )

    for leave in leaves:
        cur = leave.start_date
        while cur <= leave.end_date:
            if cur.month == month:
                data[cur.day]["job_details"] = "Annual Leave"
            cur += timedelta(days=1)

    # ----------------------------------
    # Response
    # ----------------------------------
    return Response({
        "employee": employee.user.username,
        "emp_no": employee.emp_no,
        "month": month_str,
        "data": list(data.values())
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
        today = timezone.localdate()
        employee = None
        employee_no = None
        category_code = None
        category_label = None
        login_time = None
        selected_time = None

        # If employee exists
        if hasattr(user, "employee"):
            employee = user.employee
            employee_no = employee.emp_no
            category_code = employee.category
            category_label = employee.get_category_display() 
        
        attendance = Attendance.objects.filter(
            employee=employee,
            login_time__date=today,
            logout_time__isnull=True
        ).last()

        if attendance:
            login_time = attendance.login_time
            selected_time = attendance.selected_time            

        return Response({
            "username": user.username,
            "employee_no": employee_no,
            "category": category_code,
            "category_label": category_label,
            "login_time": login_time,
            "selected_time": selected_time
        })
    
class ApplyLeaveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        employee = request.user.employee

        serializer = LeaveApplySerializer(
            data=request.data,
            context={'employee': employee}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            leave = LeaveRecord.objects.create(
                employee=employee,
                leave_type=data['leave_type'],
                start_date=data['start_date'],
                end_date=data['end_date'],
                total_days=data['total_days'],
                reason=data.get('reason')
            )

            balance = LeaveBalance.objects.get(
                employee=employee,
                leave_type=data['leave_type']
            )
            balance.used += data['total_days']
            balance.save()

        return Response({
            "message": "Leave applied successfully",
            "days": data['total_days']
        }, status=201)