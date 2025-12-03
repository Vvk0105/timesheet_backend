# views_admin_manage.py

from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from django.contrib.auth.models import User
from rest_framework.response import Response

class ManageAdminsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        admins = User.objects.filter(is_staff=True).values(
            "id", "username", "email", "is_superuser", "is_staff"
        )
        return Response(admins)

class DeleteAdminView(APIView):
    permission_classes = [IsAdminUser]

    def delete(self, request, user_id):
        try:
            user = User.objects.get(id=user_id, is_staff=True)
        except User.DoesNotExist:
            return Response({"error": "Admin not found"}, status=404)

        if user.is_superuser:
            return Response({"error": "Cannot delete superadmin"}, status=403)

        user.delete()
        return Response({"success": "Admin deleted"})
