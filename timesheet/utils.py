from datetime import date
from .models import LeaveRecord

def is_employee_on_leave(employee, check_date=None):
    check_date = check_date or date.today()
    return LeaveRecord.objects.filter(
        employee=employee,
        start_date__lte=check_date,
        end_date__gte=check_date
    ).exists()