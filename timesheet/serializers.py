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
    username = serializers.CharField(write_only=True, required=False) 
    
    class Meta:
        model = Employee
        fields = ["id", "user", "username", "designation", "department"]

    def create(self, validated_data):
        username = validated_data.pop("username")
        password = validated_data.pop("password", "123456")

        user = User.objects.create_user(username=username, password=password)
        employee = Employee.objects.create(user=user, **validated_data)
        return employee

    def update(self, instance, validated_data):
        username = validated_data.pop("username", None)
        password = validated_data.pop("password", None)

        instance.designation = validated_data.get("designation", instance.designation)
        instance.department = validated_data.get("department", instance.department)
        instance.save()

        if username:
            instance.user.username = username
        if password:
            instance.user.set_password(password)
        instance.user.save()

        return instance