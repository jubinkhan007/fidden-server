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
        email = attrs.get("email")
        password = attrs.get("password")

        user = authenticate(email=email, password=password)
        if not user:
            raise serializers.ValidationError({"non_field_errors": "Invalid credentials"})
        if not user.is_verified:
            raise serializers.ValidationError({"non_field_errors": "Email not verified"})
        if not user.is_active:
            raise serializers.ValidationError({"non_field_errors": "User account inactive"})

        refresh = RefreshToken.for_user(user)

        return {
            "user": user,  #  add user object
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

class ProfileSerializer(serializers.ModelSerializer):
    profile_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = User
        fields = ['name', 'email','mobile_number', 'profile_image']

    def validate_mobile_number(self, value):
        if value:
            import re
            pattern = r'^\+?1?\d{9,15}$'
            if not re.match(pattern, value):
                raise serializers.ValidationError("Enter a valid mobile number")
        return value

    def to_representation(self, instance):
        """Customize output to return absolute URL for profile_image"""
        rep = super().to_representation(instance)
        request = self.context.get('request')
        if instance.profile_image:
            rep['profile_image'] = request.build_absolute_uri(instance.profile_image.url)
        else:
            rep['profile_image'] = None
        return rep
    
class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=6)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "email", 'mobile_number', 'profile_image']  