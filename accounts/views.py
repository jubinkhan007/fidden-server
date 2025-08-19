from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import RegisterSerializer, VerifyOTPSerializer, LoginSerializer, GoogleLoginSerializer
from .services.google_auth import verify_google_token
from .models import User

class RegisterView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"success": True, "message": "OTP sent to your email"},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyOTPView(APIView):
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if serializer.is_valid():
            return Response(
                {"success": True, "message": "Email verified successfully"},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            return Response(
                {
                    "success": True,
                    "message": data.get("message"),
                    "accessToken": data.get("accessToken"),
                    "refreshToken": data.get("refreshToken"),
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GoogleLoginView(APIView):
    def post(self, request):
        # Validate input
        serializer = GoogleLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        token = serializer.validated_data['token']
        role = serializer.validated_data.get('role')  # optional, only used for first login

        # Verify Google token
        user_info = verify_google_token(token)
        if not user_info:
            return Response({"error": "Invalid Google token"}, status=status.HTTP_400_BAD_REQUEST)

        email = user_info["email"]

        try:
            # Create user if not exists
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "is_verified": True,
                    "is_active": True,
                    "role": role if role in dict(User.ROLE_CHOICES) else "user"
                }
            )
        except Exception as e:
            return Response(
                {"error": "User creation failed", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # For returning users, always use existing role
        if not created:
            role = user.role

        # Check if user is active
        if not user.is_active:
            return Response({"error": "User account is inactive"}, status=status.HTTP_403_FORBIDDEN)

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        message = "Registration successful" if created else "Login successful"

        return Response({
            "success": True,
            "message": message,
            "email": user.email,
            "role": role,  # role from DB or newly saved
            "accessToken": str(refresh.access_token),
            "refreshToken": str(refresh),
        }, status=status.HTTP_200_OK)
