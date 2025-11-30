from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import timedelta
from .models import User
from .serializers import (
    RegisterSerializer,
    VerifyOTPSerializer,
    LoginSerializer,
    GoogleLoginSerializer,
    RequestPasswordResetSerializer,
    VerifyResetOTPSerializer,
    ResetPasswordSerializer,
    ProfileSerializer,
    ChangePasswordSerializer
)
from accounts.services.utils import send_otp_email, generate_otp
from .services.google_auth import verify_google_token


# Registration + OTP
class RegisterView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "message": "OTP sent to your email"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyOTPView(APIView):
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if serializer.is_valid():
            return Response({"success": True, "message": "Email verified successfully"}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Login
class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            user = data.get("user")

            # Fetch shop details if they exist
            shop = getattr(user, 'shop', None)
            shop_id = shop.id if shop else None
            shop_niche = shop.primary_niche if shop else None  # Deprecated - use shop_niches
            shop_niches = shop.niches if shop and shop.niches else ([shop.niche] if shop and shop.niche else [])
            
            # New Dashboard Spec
            primary_niche = shop.primary_niche if shop else None
            capabilities = shop.niches[1:] if shop and shop.niches and len(shop.niches) > 1 else []

            return Response({
                "success": True,
                "message": data.get("message"),
                "email": user.email,
                "role": user.role,
                "shop_id": shop_id,
                "shop_niche": shop_niche,    # Deprecated
                "shop_niches": shop_niches,  # Array
                "primary_niche": primary_niche, # New Spec
                "capabilities": capabilities,   # New Spec
                "accessToken": data.get("accessToken"),
                "refreshToken": data.get("refreshToken"),
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Google login
class GoogleLoginView(APIView):
    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        token = serializer.validated_data['token']
        role = serializer.validated_data.get('role')

        user_info = verify_google_token(token)
        if not user_info:
            return Response({"error": "Invalid Google token"}, status=status.HTTP_400_BAD_REQUEST)

        email = user_info["email"]

        try:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "is_verified": True,
                    "is_active": True,
                    "role": role if role in dict(User.ROLE_CHOICES) else "user"
                }
            )
        except Exception as e:
            return Response({"error": "User creation failed", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not created:
            role = user.role

        if not user.is_active:
            return Response({"error": "User account is inactive"}, status=status.HTTP_403_FORBIDDEN)

        refresh = RefreshToken.for_user(user)
        message = "Registration successful" if created else "Login successful"

        # Fetch shop details if they exist
        shop = getattr(user, 'shop', None)
        shop_id = shop.id if shop else None
        shop_niche = shop.primary_niche if shop else None  # Deprecated - use shop_niches
        shop_niches = shop.niches if shop and shop.niches else ([shop.niche] if shop and shop.niche else [])
        
        # New Dashboard Spec
        primary_niche = shop.primary_niche if shop else None
        capabilities = shop.niches[1:] if shop and shop.niches and len(shop.niches) > 1 else []

        return Response({
            "success": True,
            "message": message,
            "email": user.email,
            "role": role,
            "shop_id": shop_id,
            "shop_niche": shop_niche,    # Deprecated
            "shop_niches": shop_niches,  # Array
            "primary_niche": primary_niche, # New Spec
            "capabilities": capabilities,   # New Spec
            "accessToken": str(refresh.access_token),
            "refreshToken": str(refresh),
        }, status=status.HTTP_200_OK)


# Password reset flow
class RequestPasswordResetView(APIView):
    def post(self, request):
        serializer = RequestPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = User.objects.get(email=serializer.validated_data['email'])
            otp = generate_otp()
            user.otp = otp
            user.otp_created_at = timezone.now()
            user.is_verified = False  # reset verification for password reset
            user.save()
            send_otp_email(user.email, otp)
            return Response({"success": True, 'message': 'OTP sent to your email'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"success": False,'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


class VerifyResetOTPView(APIView):
    def post(self, request):
        serializer = VerifyResetOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = User.objects.get(email=serializer.validated_data['email'])
            if not user.is_otp_valid(serializer.validated_data['otp']):
                return Response({"success": False,'error': 'Invalid or expired OTP'}, status=status.HTTP_400_BAD_REQUEST)
            user.is_verified = True  # OTP verified, ready for password reset
            user.save()
            return Response({"success": True,'message': 'OTP verified'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"success": False,'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


class ResetPasswordView(APIView):
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = User.objects.get(email=serializer.validated_data['email'])
            if not user.is_verified:
                return Response({"success": False, 'error': 'OTP not verified'}, status=status.HTTP_400_BAD_REQUEST)
            user.set_password(serializer.validated_data['new_password'])
            user.otp = None
            user.otp_created_at = None
            # user.is_verified = False
            user.save()
            return Response({"success": True, 'message': 'Password reset successful'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"success": False, 'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = ProfileSerializer(request.user, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        serializer = ProfileSerializer(request.user, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Profile updated successfully", "profile": serializer.data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            old_password = serializer.validated_data['old_password']
            new_password = serializer.validated_data['new_password']

            if not user.check_password(old_password):
                return Response(
                    {"detail": "Old password is incorrect"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if old_password == new_password:
                return Response(
                    {"detail": "New password cannot be the same as old password"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            user.set_password(new_password)
            user.save()
            return Response({"detail": "Password changed successfully"}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)