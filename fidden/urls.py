"""
URL configuration for Fidden project.
"""

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse

from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from payments.views import StripeWebhookView

# -----------------------------
# Swagger / Redoc schema setup
# -----------------------------
schema_view = get_schema_view(
    openapi.Info(
        title="Fidden",
        default_version='v1',
        description=(
            "Comprehensive API for managing multi-owner salon operations, "
            "including bookings, services, customers, and payments."
        ),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

# -----------------------------
# Health check endpoint
# -----------------------------
def health(request):
    return JsonResponse({"status": "ok"})

# -----------------------------
# URL patterns
# -----------------------------
urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # Apps
    path('accounts/', include('accounts.urls')),
    path('api/', include('api.urls')),
    path('payments/', include('payments.urls')),

    # Health check
    path('health/', health, name='health'),

    # Stripe webhook
    path('stripe-webhook/', StripeWebhookView.as_view(), name='stripe-webhook'),

    # Swagger / Redoc docs
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)