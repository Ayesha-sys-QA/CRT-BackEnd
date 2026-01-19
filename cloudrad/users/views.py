from datetime import date
import secrets
# from time import timezone
from django.utils import timezone
from django.shortcuts import render
from django.db.models import Q
from django.contrib.auth.password_validation import validate_password

# Create your views here.
# users/views.py
from django.shortcuts import get_object_or_404
from django.contrib.auth import authenticate, logout
from django.core.exceptions import ValidationError
from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.views import APIView

from .models import (
    User, Address, EmergencyContact, HospitalInfo, Affiliation,
    License, Qualification, Certification, UserStats, SecuritySettings,
    Session, PrivacySettings, UserPreferences, NotificationPreferences,
    DICOMPreferences
)
from .serializers import (
    # User serializers
    SimpleUserCreateSerializer, UnifiedLoginSerializer, UserSerializer, UserCreateSerializer, UserUpdateSerializer,
    UserListSerializer, UserProfileSerializer, UserMinimalSerializer,
    AdminUserCreateSerializer,
    
    # Authentication serializers
    # EmailLoginSerializer, FirstTimeLoginSerializer,
    # PasswordLoginSerializer, 
    PasswordResetSerializer,
    PasswordResetConfirmSerializer,
    
    # Related object serializers
    AddressSerializer, EmergencyContactSerializer,
    HospitalInfoSerializer, AffiliationSerializer,
    LicenseSerializer, QualificationSerializer, CertificationSerializer,
    UserStatsSerializer, SecuritySettingsSerializer,
    PrivacySettingsSerializer, UserPreferencesSerializer,
    NotificationPreferencesSerializer, DICOMPreferencesSerializer,
    SessionSerializer
)
import logging

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """
    Unified login endpoint for both first-time and regular login
    
    For first-time login (user.first_time_login = True):
    - Only email required in request
    - Returns message to set password
    - After setting password, first_time_login becomes False
    
    For regular login (user.first_time_login = False):
    - Email and password required
    - Authenticates and returns tokens
    """
    serializer = UnifiedLoginSerializer(data=request.data)
    
    if serializer.is_valid():
        result = serializer.save()
        user = result['user']
        is_first_time = result['is_first_time']
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        # Create session record (only for regular login)
        if not is_first_time:
            # Generate a unique session ID
            session_id = secrets.token_urlsafe(32)
            Session.objects.create(
                user=user,
                # session_id=str(refresh.access_token),
                session_id=session_id,
                device=request.META.get('HTTP_USER_AGENT', 'Unknown'),
                location=request.META.get('REMOTE_ADDR', 'Unknown'),
                ip_address=request.META.get('REMOTE_ADDR'),
                is_current=True
            )
            
            # Update user status to active
            user.status = 'active'
            user.save()
        
        response_data = {
            'message': result['message'],
            'user': UserSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
            'first_time_login': is_first_time
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def user_logout(request):
    """
    Logout user and invalidate current session
    """
    try:
        # Invalidate refresh token
        refresh_token = request.data.get('refresh')
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
        
        # Update current session
        Session.objects.filter(
            user=request.user,
            is_current=True
        ).update(is_current=False)
        
        # Update user status
        request.user.status = 'offline'
        request.user.save()
        
        return Response({
            'message': 'Logout successful'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Logout failed',
            'details': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_request(request):
    """
    Request password reset (send reset email)
    """
    serializer = PasswordResetSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        
        # Here you would:
        # 1. Generate reset token
        # 2. Send reset email
        # 3. Store token in cache/database
        
        # For now, just return success
        return Response({
            'message': f'Password reset instructions sent to {email}'
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_confirm(request):
    """
    Confirm password reset with token
    """
    serializer = PasswordResetConfirmSerializer(data=request.data)
    if serializer.is_valid():
        # Here you would:
        # 1. Validate token
        # 2. Update password
        # 3. Invalidate token
        
        return Response({
            'message': 'Password reset successful'
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================== USER MANAGEMENT VIEWS ====================
@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def current_user_profile(request):
    """
    Get, update, or partially update current user profile
    """
    user = request.user
    
    if request.method == 'GET':
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        serializer = UserUpdateSerializer(user, data=request.data, partial=partial)
        
        if serializer.is_valid():
            serializer.save()
            
            # Return full updated user data
            updated_user = UserSerializer(user).data
            return Response({
                'message': 'Profile updated successfully',
                'user': updated_user
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_list(request):
    """
    List all users (with filtering options)
    """
    users = User.objects.all().order_by('-created_at')
    
    # Apply filters
    department = request.query_params.get('department')
    status_filter = request.query_params.get('status')
    search = request.query_params.get('search')
    
    if department:
        users = users.filter(department__icontains=department)
    
    if status_filter:
        users = users.filter(status=status_filter)
    
    if search:
        users = users.filter(
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(national_id__icontains=search)
        )
    
    # Pagination
    page = request.query_params.get('page', 1)
    page_size = request.query_params.get('page_size', 20)
    
    try:
        page = int(page)
        page_size = int(page_size)
    except ValueError:
        return Response({
            'error': 'Invalid page or page_size parameter'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    
    paginated_users = users[start_index:end_index]
    
    serializer = UserListSerializer(paginated_users, many=True)
    
    return Response({
        'count': users.count(),
        'page': page,
        'page_size': page_size,
        'results': serializer.data
    }, status=status.HTTP_200_OK)


# @api_view(['POST'])
# @permission_classes([IsAdminUser])
# def create_user(request):
#     """
#     Create new user (admin only) - Minimal data required
#     """
#     serializer = SimpleUserCreateSerializer(data=request.data)  # Use SimpleUserCreateSerializer
    
#     if serializer.is_valid():
#         user = serializer.save()
        
#         return Response({
#             'message': 'User created successfully. User must complete profile on first login.',
#             'user': {
#                 'id': str(user.id),
#                 'email': user.email,
#                 'national_id': user.national_id,
#                 'role': user.role,
#                 'first_time_login': user.first_time_login
#             }
#         }, status=status.HTTP_201_CREATED)
    
#     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def create_user(request):
    """
    Create new user (admin only) - Minimal data required
    """
    serializer = SimpleUserCreateSerializer(data=request.data)  # Use SimpleUserCreateSerializer
    
    if serializer.is_valid():
        user = serializer.save()
        
        return Response({
            'message': 'User created successfully. User must complete profile on first login.',
            'user': {
                'id': str(user.id),
                'email': user.email,
                'national_id': user.national_id,
                'role': user.role,
                'first_time_login': user.first_time_login
            }
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def complete_profile(request):
    """
    Complete user profile on first login - includes password setting
    """
    user = request.user
    
    if not user.first_time_login:
        return Response({
            'error': 'Profile already completed'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if password is included in request
    password = request.data.get('password')
    confirm_password = request.data.get('confirm_password')
    
    if password and confirm_password:
        # Validate password
        if password != confirm_password:
            return Response({
                'error': 'Passwords do not match.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            validate_password(password, user)
        except ValidationError as e:
            return Response({
                'error': ' '.join(e.messages)
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Set password
        user.set_password(password)
    
    elif password or confirm_password:
        # Only one password field provided
        return Response({
            'error': 'Both password and confirm_password are required if setting password.'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Update profile data (excluding password fields)
    profile_data = {k: v for k, v in request.data.items() 
                   if k not in ['password', 'confirm_password']}
    
    serializer = UserUpdateSerializer(user, data=profile_data, partial=True)
    
    if serializer.is_valid():
        serializer.save()
        
        # Mark first_time_login as False if profile is complete
        # Define required fields for profile completion
        required_fields = ['first_name', 'last_name', 'national_id', 'phone', 'department']
        has_all_required = all(
            getattr(user, field, None) for field in required_fields
        )
        
        # Also require password to be set
        has_password = user.has_usable_password()
        
        if has_all_required and has_password:
            user.first_time_login = False
            user.save()
        
        return Response({
            'message': 'Profile updated successfully',
            'profile_completed': not user.first_time_login,
            'password_set': has_password,
            'user': UserSerializer(user).data
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def user_detail(request, user_id):
    """
    Retrieve, update, or delete a user
    """
    user = get_object_or_404(User, id=user_id)
    
    # Check permissions
    if request.user != user and not request.user.is_staff:
        return Response({
            'error': 'You do not have permission to access this user'
        }, status=status.HTTP_403_FORBIDDEN)
    
    if request.method == 'GET':
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method in ['PUT', 'PATCH']:
        # Only allow self-update or admin
        if request.user != user and not request.user.is_staff:
            return Response({
                'error': 'You can only update your own profile'
            }, status=status.HTTP_403_FORBIDDEN)
        
        partial = request.method == 'PATCH'
        serializer = UserUpdateSerializer(user, data=request.data, partial=partial)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'User updated successfully',
                'user': UserSerializer(user).data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        # Only allow admin to delete users
        if not request.user.is_staff:
            return Response({
                'error': 'Only administrators can delete users'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Prevent self-deletion
        if request.user == user:
            return Response({
                'error': 'You cannot delete your own account'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user.delete()
        return Response({
            'message': 'User deleted successfully'
        }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile_public(request, user_id):
    """
    Get public profile of a user
    """
    user = get_object_or_404(User, id=user_id)
    
    # Check privacy settings
    if user.privacy.profile_visibility == 'private' and request.user != user:
        return Response({
            'error': 'This profile is private'
        }, status=status.HTTP_403_FORBIDDEN)
    
    serializer = UserProfileSerializer(user)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def bulk_create_users(request):
    """
    Bulk create users from CSV or list (admin only)
    """
    users_data = request.data.get('users', [])
    
    if not isinstance(users_data, list):
        return Response({
            'error': 'Users data must be a list'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    created_users = []
    errors = []
    
    for index, user_data in enumerate(users_data):
        serializer = UserCreateSerializer(data=user_data)
        
        if serializer.is_valid():
            try:
                user = serializer.save()
                created_users.append(UserSerializer(user).data)
            except Exception as e:
                errors.append({
                    'index': index,
                    'error': str(e),
                    'data': user_data
                })
        else:
            errors.append({
                'index': index,
                'error': serializer.errors,
                'data': user_data
            })
    
    return Response({
        'created': len(created_users),
        'errors': len(errors),
        'created_users': created_users,
        'errors_detail': errors
    }, status=status.HTTP_200_OK)


# ==================== USER STATUS & ACTIVITY ====================
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_user_status(request):
    """
    Update user status (active, offline, away, on-call)
    """
    status_value = request.data.get('status')
    
    if not status_value:
        return Response({
            'error': 'Status is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    valid_statuses = ['active', 'offline', 'away', 'on-call']
    if status_value not in valid_statuses:
        return Response({
            'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    request.user.status = status_value
    request.user.save()
    
    return Response({
        'message': f'Status updated to {status_value}',
        'status': status_value
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_favorite(request, user_id):
    """
    Toggle favorite status for a user (admin only)
    """
    if not request.user.is_staff:
        return Response({
            'error': 'Only administrators can mark users as favorite'
        }, status=status.HTTP_403_FORBIDDEN)
    
    user = get_object_or_404(User, id=user_id)
    user.is_favorite = not user.is_favorite
    user.save()
    
    action = 'added to' if user.is_favorite else 'removed from'
    
    return Response({
        'message': f'User {action} favorites',
        'is_favorite': user.is_favorite
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def active_users(request):
    """
    Get list of currently active users
    """
    active_users = User.objects.filter(status='active').order_by('-last_login')
    
    department = request.query_params.get('department')
    if department:
        active_users = active_users.filter(department=department)
    
    serializer = UserMinimalSerializer(active_users, many=True)
    
    return Response({
        'count': active_users.count(),
        'users': serializer.data
    }, status=status.HTTP_200_OK)


# ==================== RELATED OBJECT VIEWS ====================
@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def user_address(request):
    """
    Get or update user's address
    """
    user = request.user
    
    if request.method == 'GET':
        try:
            address = user.address
            serializer = AddressSerializer(address)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Address.DoesNotExist:
            return Response({
                'message': 'No address found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    elif request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        
        try:
            address = user.address
            serializer = AddressSerializer(address, data=request.data, partial=partial)
        except Address.DoesNotExist:
            serializer = AddressSerializer(data=request.data)
        
        if serializer.is_valid():
            address = serializer.save(user=user)
            return Response({
                'message': 'Address updated successfully',
                'address': AddressSerializer(address).data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def user_emergency_contact(request):
    """
    Get or update user's emergency contact
    """
    user = request.user
    
    if request.method == 'GET':
        try:
            emergency_contact = user.emergency_contact
            serializer = EmergencyContactSerializer(emergency_contact)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except EmergencyContact.DoesNotExist:
            return Response({
                'message': 'No emergency contact found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    elif request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        
        try:
            emergency_contact = user.emergency_contact
            serializer = EmergencyContactSerializer(emergency_contact, data=request.data, partial=partial)
        except EmergencyContact.DoesNotExist:
            serializer = EmergencyContactSerializer(data=request.data)
        
        if serializer.is_valid():
            emergency_contact = serializer.save(user=user)
            return Response({
                'message': 'Emergency contact updated successfully',
                'emergency_contact': EmergencyContactSerializer(emergency_contact).data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def user_hospital_info(request):
    """
    Get or update user's hospital information
    """
    user = request.user
    
    if request.method == 'GET':
        try:
            hospital_info = user.hospital
            serializer = HospitalInfoSerializer(hospital_info)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except HospitalInfo.DoesNotExist:
            return Response({
                'message': 'No hospital information found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    elif request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        
        try:
            hospital_info = user.hospital
            serializer = HospitalInfoSerializer(hospital_info, data=request.data, partial=partial)
        except HospitalInfo.DoesNotExist:
            serializer = HospitalInfoSerializer(data=request.data)
        
        if serializer.is_valid():
            hospital_info = serializer.save(user=user)
            return Response({
                'message': 'Hospital information updated successfully',
                'hospital_info': HospitalInfoSerializer(hospital_info).data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def user_qualifications(request):
    """
    List or add user qualifications
    """
    user = request.user
    
    if request.method == 'GET':
        qualifications = user.qualifications.all()
        serializer = QualificationSerializer(qualifications, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        serializer = QualificationSerializer(data=request.data)
        
        if serializer.is_valid():
            qualification = serializer.save(user=user)
            return Response({
                'message': 'Qualification added successfully',
                'qualification': QualificationSerializer(qualification).data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_qualification(request, qualification_id):
    """
    Delete a qualification
    """
    qualification = get_object_or_404(Qualification, id=qualification_id)
    
    if qualification.user != request.user:
        return Response({
            'error': 'You can only delete your own qualifications'
        }, status=status.HTTP_403_FORBIDDEN)
    
    qualification.delete()
    return Response({
        'message': 'Qualification deleted successfully'
    }, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def user_certifications(request):
    """
    List or add user certifications
    """
    user = request.user
    
    if request.method == 'GET':
        certifications = user.certifications.all()
        serializer = CertificationSerializer(certifications, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        serializer = CertificationSerializer(data=request.data)
        
        if serializer.is_valid():
            certification = serializer.save(user=user)
            return Response({
                'message': 'Certification added successfully',
                'certification': CertificationSerializer(certification).data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_certification(request, certification_id):
    """
    Delete a certification
    """
    certification = get_object_or_404(Certification, id=certification_id)
    
    if certification.user != request.user:
        return Response({
            'error': 'You can only delete your own certifications'
        }, status=status.HTTP_403_FORBIDDEN)
    
    certification.delete()
    return Response({
        'message': 'Certification deleted successfully'
    }, status=status.HTTP_200_OK)


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def user_license(request):
    """
    Get or update user's medical license
    """
    user = request.user
    
    if request.method == 'GET':
        try:
            _license = user.license
            serializer = LicenseSerializer(_license)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except License.DoesNotExist:
            return Response({
                'message': 'No license information found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    elif request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        
        try:
            _license = user.license
            serializer = LicenseSerializer(_license, data=request.data, partial=partial)
        except License.DoesNotExist:
            serializer = LicenseSerializer(data=request.data)
        
        if serializer.is_valid():
            _license = serializer.save(user=user)
            return Response({
                'message': 'License information updated successfully',
                'license': LicenseSerializer(_license).data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def user_security_settings(request):
    """
    Get or update user's security settings
    """
    user = request.user
    
    if request.method == 'GET':
        try:
            security_settings = user.security
            serializer = SecuritySettingsSerializer(security_settings)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except SecuritySettings.DoesNotExist:
            return Response({
                'message': 'No security settings found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    elif request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        
        try:
            security_settings = user.security
            serializer = SecuritySettingsSerializer(security_settings, data=request.data, partial=partial)
        except SecuritySettings.DoesNotExist:
            serializer = SecuritySettingsSerializer(data=request.data)
        
        if serializer.is_valid():
            security_settings = serializer.save(user=user)
            return Response({
                'message': 'Security settings updated successfully',
                'security_settings': SecuritySettingsSerializer(security_settings).data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def user_privacy_settings(request):
    """
    Get or update user's privacy settings
    """
    user = request.user
    
    if request.method == 'GET':
        try:
            privacy_settings = user.privacy
            serializer = PrivacySettingsSerializer(privacy_settings)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except PrivacySettings.DoesNotExist:
            return Response({
                'message': 'No privacy settings found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    elif request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        
        try:
            privacy_settings = user.privacy
            serializer = PrivacySettingsSerializer(privacy_settings, data=request.data, partial=partial)
        except PrivacySettings.DoesNotExist:
            serializer = PrivacySettingsSerializer(data=request.data)
        
        if serializer.is_valid():
            privacy_settings = serializer.save(user=user)
            return Response({
                'message': 'Privacy settings updated successfully',
                'privacy_settings': PrivacySettingsSerializer(privacy_settings).data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def user_preferences(request):
    """
    Get or update user's preferences
    """
    user = request.user
    
    if request.method == 'GET':
        try:
            preferences = user.preferences
            serializer = UserPreferencesSerializer(preferences)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except UserPreferences.DoesNotExist:
            return Response({
                'message': 'No preferences found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    elif request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        
        try:
            preferences = user.preferences
            serializer = UserPreferencesSerializer(preferences, data=request.data, partial=partial)
        except UserPreferences.DoesNotExist:
            serializer = UserPreferencesSerializer(data=request.data)
        
        if serializer.is_valid():
            preferences = serializer.save(user=user)
            return Response({
                'message': 'Preferences updated successfully',
                'preferences': UserPreferencesSerializer(preferences).data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_sessions(request):
    """
    Get user's active sessions
    """
    sessions = Session.objects.filter(user=request.user).order_by('-last_active')
    serializer = SessionSerializer(sessions, many=True)
    
    return Response({
        'sessions': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def terminate_session(request, session_id):
    """
    Terminate a specific session
    """
    session = get_object_or_404(Session, id=session_id)
    
    if session.user != request.user:
        return Response({
            'error': 'You can only terminate your own sessions'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Don't allow terminating current session through this endpoint
    if session.is_current:
        return Response({
            'error': 'Cannot terminate current session. Please use logout instead.'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    session.delete()
    
    return Response({
        'message': 'Session terminated successfully'
    }, status=status.HTTP_200_OK)


# ==================== STATISTICS & ANALYTICS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_stats(request):
    """
    Get user's statistics
    """
    user = request.user
    
    try:
        stats = user.stats
        serializer = UserStatsSerializer(stats)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except UserStats.DoesNotExist:
        return Response({
            'message': 'No statistics found'
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def system_stats(request):
    """
    Get system-wide statistics (admin only)
    """
    from django.db.models import Count, Q
    
    total_users = User.objects.count()
    active_users = User.objects.filter(status='active').count()
    new_users_today = User.objects.filter(
        created_at__date=date.today()
    ).count()
    
    # Users by department
    users_by_department = User.objects.values('department').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Users by status
    users_by_status = User.objects.values('status').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # First-time login users
    first_time_users = User.objects.filter(first_time_login=True).count()
    
    return Response({
        'total_users': total_users,
        'active_users': active_users,
        'new_users_today': new_users_today,
        'first_time_login_users': first_time_users,
        'users_by_department': list(users_by_department),
        'users_by_status': list(users_by_status)
    }, status=status.HTTP_200_OK)


# ==================== UTILITY VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_users(request):
    """
    Search users by name, email, or national ID
    """
    query = request.query_params.get('q', '').strip()
    
    if not query or len(query) < 2:
        return Response({
            'error': 'Search query must be at least 2 characters long'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    users = User.objects.filter(
        Q(email__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(national_id__icontains=query)
    ).order_by('-created_at')[:50]  # Limit results
    
    serializer = UserMinimalSerializer(users, many=True)
    
    return Response({
        'count': users.count(),
        'query': query,
        'results': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def validate_email_availability(request):
    """
    Check if email is available
    """
    email = request.query_params.get('email')
    
    if not email:
        return Response({
            'error': 'Email parameter is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    email = email.lower()
    exists = User.objects.filter(email=email).exists()
    
    return Response({
        'email': email,
        'available': not exists,
        'exists': exists
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def validate_national_id_availability(request):
    """
    Check if national ID is available
    """
    national_id = request.query_params.get('national_id')
    
    if not national_id:
        return Response({
            'error': 'National ID parameter is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    exists = User.objects.filter(national_id=national_id).exists()
    
    return Response({
        'national_id': national_id,
        'available': not exists,
        'exists': exists
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    Change user password
    """
    user = request.user
    current_password = request.data.get('current_password')
    new_password = request.data.get('new_password')
    confirm_password = request.data.get('confirm_password')
    
    if not all([current_password, new_password, confirm_password]):
        return Response({
            'error': 'All password fields are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Verify current password
    if not user.check_password(current_password):
        return Response({
            'error': 'Current password is incorrect'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if new passwords match
    if new_password != confirm_password:
        return Response({
            'error': 'New passwords do not match'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate new password
    try:
        validate_password(new_password, user)
    except ValidationError as e:
        return Response({
            'error': ' '.join(e.messages)
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Update password
    user.set_password(new_password)
    user.save()
    
    # Invalidate all sessions except current
    Session.objects.filter(user=user).exclude(is_current=True).delete()
    
    return Response({
        'message': 'Password changed successfully'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_profile_picture(request):
    """
    Upload profile picture (placeholder - you'll need to implement file handling)
    """
    # This is a placeholder - implement file upload logic based on your needs
    return Response({
        'message': 'Profile picture upload endpoint',
        'note': 'Implement file upload logic here'
    }, status=status.HTTP_200_OK)


# ==================== HEALTH CHECK ====================
@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Health check endpoint
    """
    from django.db import connection
    from django.core.cache import cache
    
    # Check database
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_status = 'healthy'
    except Exception as e:
        db_status = f'unhealthy: {str(e)}'
    
    # Check cache
    try:
        cache.set('health_check', 'test', 10)
        cache.get('health_check')
        cache_status = 'healthy'
    except Exception as e:
        cache_status = f'unhealthy: {str(e)}'
    
    return Response({
        'status': 'ok',
        'timestamp': timezone.now().isoformat(),
        'database': db_status,
        'cache': cache_status,
        'version': '1.0.0'
    }, status=status.HTTP_200_OK)
    
    
    
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def user_hospitals(request):
    """
    List or add hospitals for the current user
    """
    user = request.user
    
    if request.method == 'GET':
        hospitals = user.hospitals.all()
        serializer = HospitalInfoSerializer(hospitals, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        serializer = HospitalInfoSerializer(data=request.data)
        
        if serializer.is_valid():
            # If marking as primary, unmark others
            if serializer.validated_data.get('is_primary', False):
                user.hospitals.filter(is_primary=True).update(is_primary=False)
            
            hospital = serializer.save(user=user)
            return Response({
                'message': 'Hospital added successfully',
                'hospital': HospitalInfoSerializer(hospital).data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def user_hospital_detail(request, hospital_id):
    """
    Retrieve, update, or delete a specific hospital record
    """
    hospital = get_object_or_404(HospitalInfo, id=hospital_id)
    
    # Check permissions
    if hospital.user != request.user:
        return Response({
            'error': 'You can only manage your own hospital records'
        }, status=status.HTTP_403_FORBIDDEN)
    
    if request.method == 'GET':
        serializer = HospitalInfoSerializer(hospital)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        serializer = HospitalInfoSerializer(hospital, data=request.data, partial=partial)
        
        if serializer.is_valid():
            # If marking as primary, unmark others
            if serializer.validated_data.get('is_primary', False):
                request.user.hospitals.filter(is_primary=True).exclude(id=hospital_id).update(is_primary=False)
            
            hospital = serializer.save()
            return Response({
                'message': 'Hospital updated successfully',
                'hospital': HospitalInfoSerializer(hospital).data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        # Don't allow deletion if it's the only hospital
        if request.user.hospitals.count() <= 1:
            return Response({
                'error': 'Cannot delete the only hospital record'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        hospital.delete()
        return Response({
            'message': 'Hospital record deleted successfully'
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_primary_hospital(request, hospital_id):
    """
    Set a hospital as primary
    """
    hospital = get_object_or_404(HospitalInfo, id=hospital_id)
    
    if hospital.user != request.user:
        return Response({
            'error': 'You can only set your own hospitals as primary'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Unmark all other hospitals as primary
    request.user.hospitals.filter(is_primary=True).exclude(id=hospital_id).update(is_primary=False)
    
    # Mark this one as primary
    hospital.is_primary = True
    hospital.save()
    
    return Response({
        'message': f'{hospital.name} set as primary hospital',
        'hospital': HospitalInfoSerializer(hospital).data
    }, status=status.HTTP_200_OK)