from rest_framework import serializers
from django.contrib.auth import authenticate
from datetime import timedelta
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from .models import User
from accounts.services.utils import generate_otp, send_otp_email

class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'password', 'role']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            role=validated_data.get('role', 'user')
        )
        otp = generate_otp()
        user.otp = otp
        user.otp_created_at = timezone.now()
        user.save()

        send_otp_email(user.email, otp)

        return user


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

    def validate(self, attrs):
        try:
            user = User.objects.get(email=attrs['email'])
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User not found"})

        # Check OTP match
        if user.otp != attrs['otp']:
            raise serializers.ValidationError({"otp": "Invalid OTP"})

        # Check OTP expiry (5 minutes)
        if not user.otp_created_at or timezone.now() > user.otp_created_at + timedelta(minutes=5):
            raise serializers.ValidationError({"otp": "OTP expired"})

        # Mark user verified and clear OTP
        user.is_verified = True
        user.otp = None
        user.otp_created_at = None
        user.save()

        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(email=attrs['email'], password=attrs['password'])
        if not user:
            raise serializers.ValidationError({"non_field_errors": "Invalid credentials"})
        if not user.is_verified:
            raise serializers.ValidationError({"non_field_errors": "Email not verified"})

        refresh = RefreshToken.for_user(user)

        return {
            "message": "Login Successful",
            "accessToken": str(refresh.access_token),
            "refreshToken": str(refresh),
        }


class GoogleLoginSerializer(serializers.Serializer):
    token = serializers.CharField(required=True, allow_blank=False)
    role = serializers.ChoiceField(
        choices=User.ROLE_CHOICES,
        required=False,  # optional for existing users
        allow_blank=True
    )

