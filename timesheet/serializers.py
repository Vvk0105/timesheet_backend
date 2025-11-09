from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Employee, Attendance, Job


# 🔹 User serializer (no major change)
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']


# 🔹 Employee serializer
class EmployeeSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    username = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Employee
        fields = [
            "id", "user", "username", "password", "emp_no",
            "mobile", "category", "designation", "department", "is_suspended"
        ]

    def create(self, validated_data):
        username = validated_data.pop("username")
        password = validated_data.pop("password", "123456")
        user = User.objects.create_user(username=username, password=password)
        employee = Employee.objects.create(user=user, **validated_data)
        return employee

    def update(self, instance, validated_data):
        username = validated_data.pop("username", None)
        password = validated_data.pop("password", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if username:
            instance.user.username = username
        if password:
            instance.user.set_password(password)
        instance.user.save()

        return instance


# 🔹 Attendance Serializer
class AttendanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attendance
        fields = ['id', 'employee', 'login_time', 'selected_time', 'logout_time', 'duration']
        read_only_fields = ['employee', 'login_time', 'duration']


# 🔹 Work Entry Serializer
class WorkEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = '__all__'
        read_only_fields = ['employee', 'created_at', 'date']
