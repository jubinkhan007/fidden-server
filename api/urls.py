from django.urls import path, include
from .views import (
    AIReportView,
    GenerateMarketingCaptionView,
    LatestWeeklySummaryView,
    PerformanceAnalyticsView,
    SendLoyaltyEmailView,
    ShopListCreateView,
    ShopRetrieveUpdateDestroyView,
    ServiceListCreateView,
    ServiceRetrieveUpdateDestroyView,
    UserRatingReviewView,
    ServiceCategoryListView,
    # SlotListView,
    SlotBookingView,
    CancelSlotBookingView,
    AllShopsListView,
    ShopDetailView,
    AllServicesListView,
    ServiceDetailView,
    FavoriteShopView,
    PromotionListView,
    ServiceWishlistView,
    GlobalSearchView,
    ReplyCreateView,
    ShopRatingReviewsView, 
    UserMessageView, 
    OwnerMessageView, 
    ThreadListView, 
    RegisterDeviceView,
    NotificationsView,
    NotificationDetailView,
    WeeklyShopRevenueView,
    GrowthSuggestionView,
    CouponListCreateAPIView,
    CouponRetrieveUpdateDestroyAPIView,
    UserCouponRetrieveAPIView,
    BestServicePerShopView,
    ThreadDetailsView,
    AIAutoFillSettingsView,
    HoldSlotAndBookView,
    GalleryItemView,
    GalleryItemDetailView,
    PublicGalleryView,
)
from payments.views import ShopSlotsView

urlpatterns = [
    path('shop/', ShopListCreateView.as_view(), name='shop-list-create'),
    path('shop/<int:pk>/', ShopRetrieveUpdateDestroyView.as_view(), name='shop-detail'),
    path('services/', ServiceListCreateView.as_view(), name='service-list-create'),
    path('services/<int:pk>/', ServiceRetrieveUpdateDestroyView.as_view(), name='service-detail'),
    path('reviews/', UserRatingReviewView.as_view(), name='user-reviews'),
    path('categories/', ServiceCategoryListView.as_view(), name='category-list'),
    path('shops/<int:shop_id>/slots/', ShopSlotsView.as_view(), name='slot-list'),
    path('slot-booking/', SlotBookingView.as_view(), name='slot-booking-create'),
    path('slot-booking/<int:booking_id>/cancel/', CancelSlotBookingView.as_view(), name='slot-booking-cancel'),
    path('users/shops/', AllShopsListView.as_view(), name='all-shops-list-user'),
    path('users/shops/details/<int:shop_id>/', ShopDetailView.as_view(), name='shop-detail-user'),
    path("users/services/", AllServicesListView.as_view(), name="all-services"),
    path("users/services/<int:service_id>/", ServiceDetailView.as_view(), name="service-detail"),
    path('users/favorite-shop/', FavoriteShopView.as_view(), name='favorite-shop'),
    path('promotions/', PromotionListView.as_view(), name='promotion-list'),
    path('users/service-wishlist/', ServiceWishlistView.as_view(), name='service-wishlist'),
    path('global-search/', GlobalSearchView.as_view(), name='global-search'),
    path('create-reply/<int:rating_review_id>/', ReplyCreateView.as_view(), name='reply-create'),
    path('shops/rating-reviews/<int:shop_id>/', ShopRatingReviewsView.as_view(), name='shop-rating-reviews'),
    path("threads/", ThreadListView.as_view(), name="thread-list"),
    path("threads/<int:thread_id>/", ThreadDetailsView.as_view(), name="thread-detail"),
    path("threads/<int:shop_id>/send/", UserMessageView.as_view(), name="user-send-message"),
    path("threads/<int:thread_id>/reply/", OwnerMessageView.as_view(), name="owner-reply-message"),
    path('register-device/', RegisterDeviceView.as_view(), name='register-device'),
    path("notifications/", NotificationsView.as_view(), name="user-notifications"),
    path("notifications/<int:pk>/", NotificationDetailView.as_view(), name="notification-detail"),
    path('shop/<int:shop_id>/revenues/', WeeklyShopRevenueView.as_view(), name='weekly-shop-revenues'),
    path("growth-suggestions/", GrowthSuggestionView.as_view(), name="growth-suggestions"),
    path('coupons/', CouponListCreateAPIView.as_view(), name='coupon-list-create'),
    path('coupons/<int:coupon_id>/', CouponRetrieveUpdateDestroyAPIView.as_view(), name='coupon-detail'),
    path('users/coupons/', UserCouponRetrieveAPIView.as_view(), name='user-get-coupon'),
    path('best-service/<int:shop_id>/', BestServicePerShopView.as_view(), name="best-service-per-shop"),
    path('analytics/', PerformanceAnalyticsView.as_view(), name='performance-analytics'),
    path('ai-settings/', AIAutoFillSettingsView.as_view(), name='ai-settings'),
    path('slots/<int:slot_id>/hold/', HoldSlotAndBookView.as_view(), name='hold-slot'),
    path('ai-report/', AIReportView.as_view(), name='ai-report'),
    # api/urls.py
    path("weekly-summary/latest/", LatestWeeklySummaryView.as_view(),name="weekly-summary-latest"),
    path("weekly-summary/generate_marketing_caption/", GenerateMarketingCaptionView.as_view()),
    path("weekly-summary/send_loyalty_email/", SendLoyaltyEmailView.as_view()),
    
    # 🆕 Gallery endpoints
    path('gallery/', GalleryItemView.as_view(), name='gallery-list-create'),
    path('gallery/<int:pk>/', GalleryItemDetailView.as_view(), name='gallery-detail'),
    path('shops/<int:shop_id>/gallery/', PublicGalleryView.as_view(), name='public-gallery'),
]

# ==========================================
# BARBER DASHBOARD ROUTES ✂️
# ==========================================
from .barber_views import (
    TodayAppointmentsView, DailyRevenueView, NoShowAlertsView,
    WalkInQueueView, WalkInEntryDetailView,
    LoyaltyProgramView, LoyaltyCustomersView, LoyaltyPointsAddView, LoyaltyRedeemView
)

urlpatterns += [
    # Core barber endpoints
    path('barber/today-appointments/', TodayAppointmentsView.as_view(), name='barber-today-appointments'),
    path('barber/daily-revenue/', DailyRevenueView.as_view(), name='barber-daily-revenue'),
    path('barber/no-show-alerts/', NoShowAlertsView.as_view(), name='barber-no-show-alerts'),
    
    # Walk-in Queue
    path('barber/walk-ins/', WalkInQueueView.as_view(), name='barber-walk-in-queue'),
    path('barber/walk-ins/<int:pk>/', WalkInEntryDetailView.as_view(), name='barber-walk-in-detail'),
    
    # Loyalty Program
    path('barber/loyalty/program/', LoyaltyProgramView.as_view(), name='barber-loyalty-program'),
    path('barber/loyalty/customers/', LoyaltyCustomersView.as_view(), name='barber-loyalty-customers'),
    path('barber/loyalty/add-points/', LoyaltyPointsAddView.as_view(), name='barber-loyalty-add'),
    path('barber/loyalty/redeem/', LoyaltyRedeemView.as_view(), name='barber-loyalty-redeem'),
]

# ==========================================
# PHASE 2: TATTOO ARTIST ROUTES 🖋️
# ==========================================
from rest_framework.routers import DefaultRouter
from .views import (
    PortfolioViewSet, DesignRequestViewSet, 
    ConsentFormViewSet, SignedConsentFormViewSet, 
    IDVerificationViewSet, ConsultationViewSet
)

router = DefaultRouter()
router.register(r'portfolio', PortfolioViewSet, basename='portfolio')
router.register(r'design-requests', DesignRequestViewSet, basename='design-requests')
router.register(r'consent-forms/templates', ConsentFormViewSet, basename='consent-templates')
router.register(r'consent-forms/signed', SignedConsentFormViewSet, basename='signed-consent-forms')
router.register(r'id-verification', IDVerificationViewSet, basename='id-verification')
router.register(r'consultations', ConsultationViewSet, basename='consultations')

urlpatterns += [
    path('', include(router.urls)),
]


# ==========================================
# NAIL TECH DASHBOARD ROUTES 💅
# ==========================================
from .nailtech_views import (
    StyleRequestViewSet, LookbookView, BookingsByStyleView,
    TipSummaryView, NailTechDashboardView
)

urlpatterns += [
    path('nailtech/dashboard/', NailTechDashboardView.as_view(), name='nailtech-dashboard'),
    path('nailtech/style-requests/', StyleRequestViewSet.as_view({'get': 'list', 'post': 'create'}), name='nailtech-style-requests'),
    path('nailtech/style-requests/<int:pk>/', StyleRequestViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='nailtech-style-request-detail'),
    path('nailtech/lookbook/', LookbookView.as_view(), name='nailtech-lookbook'),
    path('nailtech/bookings-by-style/', BookingsByStyleView.as_view(), name='nailtech-bookings-by-style'),
    path('nailtech/tip-summary/', TipSummaryView.as_view(), name='nailtech-tip-summary'),
]


# ==========================================
# MUA (MAKEUP ARTIST) DASHBOARD ROUTES 💄
# ==========================================
from .mua_views import (
    MUADashboardView, FaceChartListView,
    ClientBeautyProfileViewSet, ProductKitViewSet
)

urlpatterns += [
    path('mua/dashboard/', MUADashboardView.as_view(), name='mua-dashboard'),
    path('mua/face-charts/', FaceChartListView.as_view(), name='mua-face-charts'),
    path('mua/client-profiles/', ClientBeautyProfileViewSet.as_view({'get': 'list', 'post': 'create'}), name='mua-client-profiles'),
    path('mua/client-profiles/<int:pk>/', ClientBeautyProfileViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='mua-client-profile-detail'),
    path('mua/product-kit/', ProductKitViewSet.as_view({'get': 'list', 'post': 'create'}), name='mua-product-kit'),
    path('mua/product-kit/<int:pk>/', ProductKitViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='mua-product-kit-detail'),
]


# ==========================================
# HAIRSTYLIST/LOCTICIAN DASHBOARD ROUTES 💇‍♀️
# ==========================================
from .hairstylist_views import (
    HairstylistDashboardView, WeeklyScheduleView, PrepNotesView,
    ClientHairProfileViewSet, ProductRecommendationViewSet, MyHairProfileView
)

urlpatterns += [
    path('hairstylist/dashboard/', HairstylistDashboardView.as_view(), name='hairstylist-dashboard'),
    path('hairstylist/weekly-schedule/', WeeklyScheduleView.as_view(), name='hairstylist-weekly-schedule'),
    path('hairstylist/prep-notes/', PrepNotesView.as_view(), name='hairstylist-prep-notes'),
    path('hairstylist/client-profiles/', ClientHairProfileViewSet.as_view({'get': 'list', 'post': 'create'}), name='hairstylist-client-profiles'),
    path('hairstylist/client-profiles/<int:pk>/', ClientHairProfileViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='hairstylist-client-profile-detail'),
    path('hairstylist/recommendations/', ProductRecommendationViewSet.as_view({'get': 'list', 'post': 'create'}), name='hairstylist-recommendations'),
    path('hairstylist/recommendations/<int:pk>/', ProductRecommendationViewSet.as_view({'get': 'retrieve', 'delete': 'destroy'}), name='hairstylist-recommendation-detail'),
    # Client self-service hair profile
    path('my-hair-profile/', MyHairProfileView.as_view(), name='my-hair-profile'),
]


# ==========================================
# ESTHETICIAN/MASSAGE THERAPIST ROUTES 🧖
# ==========================================
from .esthetician_views import (
    EstheticianDashboardView, ClientSkinProfileViewSet, MySkinProfileView,
    HealthDisclosureViewSet, MyHealthDisclosureView,
    TreatmentNoteViewSet, RetailProductViewSet
)

urlpatterns += [
    path('esthetician/dashboard/', EstheticianDashboardView.as_view(), name='esthetician-dashboard'),
    path('esthetician/client-profiles/', ClientSkinProfileViewSet.as_view({'get': 'list', 'post': 'create'}), name='esthetician-client-profiles'),
    path('esthetician/client-profiles/<int:pk>/', ClientSkinProfileViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='esthetician-client-profile-detail'),
    path('esthetician/health-disclosures/', HealthDisclosureViewSet.as_view({'get': 'list', 'post': 'create'}), name='esthetician-health-disclosures'),
    path('esthetician/health-disclosures/<int:pk>/', HealthDisclosureViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='esthetician-health-disclosure-detail'),
    path('esthetician/treatment-notes/', TreatmentNoteViewSet.as_view({'get': 'list', 'post': 'create'}), name='esthetician-treatment-notes'),
    path('esthetician/treatment-notes/<int:pk>/', TreatmentNoteViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='esthetician-treatment-note-detail'),
    path('esthetician/retail-products/', RetailProductViewSet.as_view({'get': 'list', 'post': 'create'}), name='esthetician-retail-products'),
    path('esthetician/retail-products/<int:pk>/', RetailProductViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='esthetician-retail-product-detail'),
    # Client self-service
    path('my-skin-profile/', MySkinProfileView.as_view(), name='my-skin-profile'),
    path('my-health-disclosure/', MyHealthDisclosureView.as_view(), name='my-health-disclosure'),
]
