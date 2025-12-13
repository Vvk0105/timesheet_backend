from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Employee, Attendance, Job, LeaveRecord, LeaveBalance
from datetime import date

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
            "mobile", "category", "is_suspended"
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
class AttendanceSummarySerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.user.username', read_only=True)
    duration = serializers.DurationField(read_only=True)
    login_time = serializers.DateTimeField(read_only=True)
    logout_time = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Attendance
        fields = ['id', 'employee_name', 'login_time', 'logout_time', 'duration']


class JobSerializer(serializers.ModelSerializer):
    attendance = AttendanceSummarySerializer(read_only=True)
    employee_name = serializers.CharField(source='attendance.employee.user.username', read_only=True)
    date = serializers.DateTimeField(source='attendance.login_time', read_only=True)
    day = serializers.SerializerMethodField()
    category = serializers.CharField(source='attendance.employee.category', read_only=True)

    class Meta:
        model = Job
        fields = [
            'id', 'employee_name', 'attendance', 'status', 'description',
            'start_time', 'end_time', 'job_no', 'ship_name', 'location',
            'holiday_worked', 'off_station', 'local_site', 'driv',
            'leave_type', 'leave_reason', 'date', 'day', 'created_at', 'category'
        ]

    def validate(self, data):
        employee = self.context['request'].user.employee
        category = employee.category

        if data.get("status") == "leave":
            leave_type = data.get("leave_type")

            if not data.get("leave_type"):
                raise serializers.ValidationError({"error": "Leave type is required."})
            
            DAILY_LEAVES = ["sick", "casual", "restrictedholiday", "lossofpay", "compoff"]
            
            if leave_type not in DAILY_LEAVES:
                raise serializers.ValidationError({
                    "error": f"{leave_type} cannot be applied via daily work entry"
                })

            return data

        if data.get("status") == "on_duty":

            if category == "A":
                required_fields = [
                    "start_time", "end_time", "description",
                    "ship_name", "job_no", "location"
                ]

                missing = [f for f in required_fields if not data.get(f)]
                if missing:
                    raise serializers.ValidationError(
                        {"error": f"Missing required fields for Category A: {', '.join(missing)}"}
                    )

            elif category in ["B", "C"]:
                required_fields = ["start_time", "end_time", "description"]

                missing = [f for f in required_fields if not data.get(f)]
                if missing:
                    raise serializers.ValidationError(
                        {"error": f"Missing required fields for Category {category}: {', '.join(missing)}"}
                    )

        return data


    def get_day(self, obj):
        if obj.attendance and obj.attendance.login_time:
            return obj.attendance.login_time.strftime("%A")
        return ""

class LeaveRecordSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.user.username', read_only=True)

    class Meta:
        model = LeaveRecord
        fields = ['id', 'employee', 'employee_name', 'leave_type', 'reason', 'count', 'date', 'created_at']

class LeaveBalanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.user.username", read_only=True)
    remaining = serializers.SerializerMethodField()

    class Meta:
        model = LeaveBalance
        fields = ["id", "employee", "employee_name", "leave_type", "total_allocated", "used", "remaining"]

    def get_remaining(self, obj):
        return obj.remaining()

class LeaveApplySerializer(serializers.Serializer):
    leave_type = serializers.ChoiceField(choices=LeaveRecord.LEAVE_TYPES)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        start = data['start_date']
        end = data['end_date']

        if start > end:
            raise serializers.ValidationError("Start date cannot be after end date")

        if start < date.today():
            raise serializers.ValidationError("Leave cannot start in the past")

        total_days = (end - start).days + 1
        employee = self.context['employee']

        balance = LeaveBalance.objects.filter(
            employee=employee,
            leave_type=data['leave_type']
        ).first()

        if not balance:
            raise serializers.ValidationError("Leave balance not found")

        if balance.used + total_days > balance.total_allocated:
            raise serializers.ValidationError("Insufficient leave balance")

        data['total_days'] = total_days
        return data
