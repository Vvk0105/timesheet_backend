from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .admin_profile_serializers import (
    AdminProfileSerializer,
    AdminUpdateSerializer,
    ChangePasswordSerializer,
    CreateAdminSerializer
)


class AdminProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = AdminProfileSerializer(request.user)
        return Response(serializer.data)


class AdminProfileUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        serializer = AdminUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Profile updated"})
        return Response(serializer.errors, status=400)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            old_password = serializer.validated_data["old_password"]
            new_password = serializer.validated_data["new_password"]

            if not request.user.check_password(old_password):
                return Response({"error": "Old password is incorrect"}, status=400)

            request.user.set_password(new_password)
            request.user.save()

            return Response({"message": "Password changed successfully"})

        return Response(serializer.errors, status=400)


class CreateAdminView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateAdminSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Admin created"})
        return Response(serializer.errors, status=400)
