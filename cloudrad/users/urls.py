# users/urls.py
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # ==================== AUTHENTICATION ====================
    # path('auth/check-email/', views.check_email_login, name='check-email-login'),
    # path('auth/first-time-login/', views.first_time_login, name='first-time-login'),
    path('auth/login/', views.login, name='login'),
    path('auth/logout/', views.user_logout, name='logout'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('auth/password-reset/', views.password_reset_request, name='password-reset'),
    path('auth/password-reset-confirm/', views.password_reset_confirm, name='password-reset-confirm'),
    
    # ==================== CURRENT USER PROFILE ====================
    path('me/', views.current_user_profile, name='current-user-profile'),
    path('me/change-password/', views.change_password, name='change-password'),
    path('me/update-status/', views.update_user_status, name='update-user-status'),
    path('me/upload-profile-picture/', views.upload_profile_picture, name='upload-profile-picture'),
    path('me/complete-profile/', views.complete_profile, name='complete-profile'),
    
    # ==================== CURRENT USER RELATED OBJECTS ====================
    path('me/address/', views.user_address, name='user-address'),
    path('me/emergency-contact/', views.user_emergency_contact, name='user-emergency-contact'),
    path('me/hospital-info/', views.user_hospital_info, name='user-hospital-info'),
    path('me/license/', views.user_license, name='user-license'),
    path('me/security/', views.user_security_settings, name='user-security-settings'),
    path('me/privacy/', views.user_privacy_settings, name='user-privacy-settings'),
    path('me/preferences/', views.user_preferences, name='user-preferences'),
    path('me/stats/', views.user_stats, name='user-stats'),
    
    # ==================== QUALIFICATIONS ====================
    path('me/qualifications/', views.user_qualifications, name='user-qualifications'),
    path('me/qualifications/<uuid:qualification_id>/', views.delete_qualification, name='delete-qualification'),
    
    # ==================== CERTIFICATIONS ====================
    path('me/certifications/', views.user_certifications, name='user-certifications'),
    path('me/certifications/<uuid:certification_id>/', views.delete_certification, name='delete-certification'),
    
    # ==================== SESSIONS ====================
    path('me/sessions/', views.user_sessions, name='user-sessions'),
    path('me/sessions/<uuid:session_id>/terminate/', views.terminate_session, name='terminate-session'),
    
    # ==================== USER MANAGEMENT ====================
    path('users/', views.user_list, name='user-list'),
    path('users/create/', views.create_user, name='create-user'),
    path('users/bulk-create/', views.bulk_create_users, name='bulk-create-users'),
    path('users/active/', views.active_users, name='active-users'),
    path('users/search/', views.search_users, name='search-users'),
    path('users/<uuid:user_id>/', views.user_detail, name='user-detail'),
    path('users/<uuid:user_id>/profile/', views.user_profile_public, name='user-profile-public'),
    path('users/<uuid:user_id>/toggle-favorite/', views.toggle_favorite, name='toggle-favorite'),
    
    # ==================== SYSTEM & UTILITIES ====================
    path('system/stats/', views.system_stats, name='system-stats'),
    path('validate/email/', views.validate_email_availability, name='validate-email'),
    path('validate/national-id/', views.validate_national_id_availability, name='validate-national-id'),
    
    # ==================== HEALTH CHECK ====================
    path('health/', views.health_check, name='health-check'),
    
    path('me/hospitals/', views.user_hospitals, name='user-hospitals'),
    path('me/hospitals/<int:hospital_id>/', views.user_hospital_detail, name='user-hospital-detail'),
    path('me/hospitals/<int:hospital_id>/set-primary/', views.set_primary_hospital, name='set-primary-hospital'),
]