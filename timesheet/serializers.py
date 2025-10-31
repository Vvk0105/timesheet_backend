from rest_framework import serializers
from .models import Employee, Attendance, Job
from django.contrib.auth.models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']

class AttendanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attendance
        fields = ['id', 'employee', 'login_time', 'selected_time', 'logout_time', 'duration']
        read_only_fields = ['employee', 'login_time', 'duration']

class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = ['id', 'attendance', 'task_title', 'description', 'start_time', 'end_time', 'created_at']
        read_only_fields = ['attendance']

class EmployeeSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    class Meta:
        model = Employee
        fields = ["id", "user", "designation", "department"]