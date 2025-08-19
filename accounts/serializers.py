from rest_framework import serializers
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from .models import User
from accounts.services.utils import send_otp_email

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
        otp = user.generate_otp()
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

        if not user.is_otp_valid(attrs['otp']):
            raise serializers.ValidationError({"otp": "Invalid or expired OTP"})

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
        if not user.is_active:
            raise serializers.ValidationError({"non_field_errors": "User account inactive"})

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
        required=False,
        allow_blank=True
    )


class RequestPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyResetOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match")
        return data
