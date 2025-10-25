from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from .models import Attendance, Job
from .serializers import AttendanceSerializer, JobSerializer

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

class JobCreateListView(generics.ListCreateAPIView):
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Job.objects.all()

    def get_queryset(self):
        employee = self.request.user.employee
        return Job.objects.filter(attendance__employee=employee)

    def perform_create(self, serializer):
        employee = self.request.user.employee
        attendance = Attendance.objects.filter(employee=employee, logout_time__isnull=True).last()
        if not attendance:
            raise ValueError("No active login session found")
        serializer.save(attendance=attendance)

class JobDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Job.objects.all()

    def get_queryset(self):
        employee = self.request.user.employee
        return Job.objects.filter(attendance__employee=employee)

class AdminAttendanceListView(generics.ListAPIView):
    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        queryset = Attendance.objects.all().select_related('employee')
        employee_id = self.request.query_params.get('employee')
        start = self.request.query_params.get('start_date')
        end = self.request.query_params.get('end_date')

        if employee_id:
            queryset = queryset.filter(employee__id=employee_id)
        if start and end:
            queryset = queryset.filter(login_time__date__range=[start, end])
        return queryset
