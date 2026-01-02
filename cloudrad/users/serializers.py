# users/serializers.py
from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from rest_framework.validators import UniqueValidator
from .models import (
    User, Address, EmergencyContact, HospitalInfo, Affiliation,
    License, Qualification, Certification, UserStats, SecuritySettings,
    Session, PrivacySettings, UserPreferences, NotificationPreferences,
    DICOMPreferences
)
import uuid
from datetime import date

# Define a constant for the repeated error message
PASSWORD_MISMATCH_ERROR = 'Passwords do not match.'
USER_NOT_FOUND_ERROR = 'No user found with this email.'
ACCOUNT_NOT_ACTIVE_ERROR = 'Account is not active.'


# ==================== HELPER SERIALIZERS ====================
class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ['street', 'city', 'state', 'zip_code', 'country']
        read_only_fields = ['user']


class EmergencyContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmergencyContact
        fields = ['name', 'phone', 'relationship']
        read_only_fields = ['user']


class AffiliationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Affiliation
        fields = ['id', 'name', 'role']
        read_only_fields = ['hospital']


class HospitalInfoSerializer(serializers.ModelSerializer):
    affiliations = AffiliationSerializer(many=True, read_only=True)
    is_primary = serializers.BooleanField(default=False)
    
    class Meta:
        model = HospitalInfo
        fields = [
            'id', 'name', 'address', 'department', 'position',
            'employee_id', 'join_date', 'contact', 'is_primary', 'affiliations'
        ]
        read_only_fields = ['user', 'id']

    def validate(self, data):
        # If marking as primary, we'll handle it in the view
        return data

class LicenseSerializer(serializers.ModelSerializer):
    is_valid = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = License
        fields = [
            'number', 'type', 'authority', 'issue_date',
            'expiry_date', 'specialization', 'status', 'is_valid'
        ]
        read_only_fields = ['user']
    
    def validate(self, data):
        # Validate dates
        issue_date = data.get('issue_date')
        expiry_date = data.get('expiry_date')
        
        if issue_date and expiry_date:
            if issue_date > expiry_date:
                raise serializers.ValidationError({
                    'issue_date': 'Issue date cannot be after expiry date.'
                })
            if issue_date > date.today():
                raise serializers.ValidationError({
                    'issue_date': 'Issue date cannot be in the future.'
                })
        
        return data


class QualificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Qualification
        fields = ['id', 'degree', 'institution', 'year']
        read_only_fields = ['user']


class CertificationSerializer(serializers.ModelSerializer):
    is_expired = serializers.SerializerMethodField()
    
    class Meta:
        model = Certification
        fields = [
            'id', 'name', 'issuer', 'year', 'cert_id',
            'expiry_date', 'is_expired'
        ]
        read_only_fields = ['user']
    
    def get_is_expired(self, obj):
        if obj.expiry_date:
            return obj.expiry_date < date.today()
        return False


class UserStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserStats
        fields = ['patients', 'studies', 'years']


class SecuritySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecuritySettings
        fields = ['two_factor_enabled', 'two_factor_method']
        read_only_fields = ['user']


class PrivacySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrivacySettings
        fields = [
            'profile_visibility', 'show_activity',
            'allow_data_sharing', 'email_notifications'
        ]
        read_only_fields = ['user']


class NotificationPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreferences
        fields = [
            'new_patients', 'critical_results', 'follow_ups',
            'platform_updates', 'maintenance', 'training'
        ]
        read_only_fields = ['user_preferences']


class DICOMPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = DICOMPreferences
        fields = [
            'layout', 'window_preset', 'measurement_units',
            'annotation_color'
        ]
        read_only_fields = ['user_preferences']


class UserPreferencesSerializer(serializers.ModelSerializer):
    notifications = NotificationPreferencesSerializer(read_only=True)
    dicom = DICOMPreferencesSerializer(read_only=True)
    
    class Meta:
        model = UserPreferences
        fields = ['theme', 'language', 'timezone', 'date_format', 'notifications', 'dicom']
        read_only_fields = ['user']


# ==================== USER SERIALIZERS ====================
class UserMinimalSerializer(serializers.ModelSerializer):
    """Minimal user serializer for references"""
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'title', 'department', 'status']


class UserSerializer(serializers.ModelSerializer):
    """Full user serializer with all related data"""
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    
    # Related data
    address = AddressSerializer(read_only=True)
    emergency_contact = EmergencyContactSerializer(read_only=True)
    hospitals = HospitalInfoSerializer(many=True, read_only=True)
    primary_hospital = HospitalInfoSerializer(source='primary_hospital', read_only=True)
    license = LicenseSerializer( read_only=True)
    qualifications = QualificationSerializer(many=True, read_only=True)
    certifications = CertificationSerializer(many=True, read_only=True)
    stats = UserStatsSerializer(read_only=True)
    security = SecuritySettingsSerializer(read_only=True)
    privacy = PrivacySettingsSerializer(read_only=True)
    preferences = UserPreferencesSerializer(read_only=True)
    
    # Computed fields
    age = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'full_name', 'national_id', 'phone', 'title',
            'dob', 'age', 'gender', 'bio', 'avatar_color',
            'department', 'experience', 'total_patients',
            'specialties', 'office', 'is_favorite', 'status',
            'first_time_login', 'created_at', 'updated_at',
            'role', 'primary_hospital',
            
            # Related data
            'address', 'emergency_contact', 'hospitals',
            'license', 'qualifications', 'certifications',
            'stats', 'security', 'privacy', 'preferences'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'first_time_login',
            'address', 'emergency_contact', 'hospitals', 'primary_hospital', 'license',
            'qualifications', 'certifications', 'stats', 'security',
            'privacy', 'preferences'
        ]
    
    def get_age(self, obj):
        if obj.dob:
            today = date.today()
            return today.year - obj.dob.year - ((today.month, today.day) < (obj.dob.month, obj.dob.day))
        return None
    
    def get_full_name(self, obj):
        return obj.get_full_name()


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new users (by admin)"""
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    email = serializers.EmailField(
        validators=[UniqueValidator(queryset=User.objects.all())]
    )
    national_id = serializers.CharField(
        validators=[UniqueValidator(queryset=User.objects.all())]
    )
    hospital_name = serializers.CharField(write_only=True, required=False)
    hospital_department = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'national_id', 'first_name', 'last_name',
            'phone', 'title', 'dob', 'gender', 'department',
            'office','role', 'hospital_name', 'hospital_department'
        ]
        read_only_fields = ['id', 'first_time_login']
    
    def validate_email(self, value):
        try:
            validate_email(value)
        except ValidationError:
            raise serializers.ValidationError("Enter a valid email address.")
        return value.lower()
    
    def create(self, validated_data):
        # Extract hospital data if provided
        hospital_name = validated_data.pop('hospital_name', None)
        hospital_department = validated_data.pop('hospital_department', None)
        
        # Generate username from email (before @)
        email = validated_data['email']
        username = email.split('@')[0]
        
        # Ensure username is unique
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        
        # Create user with random password (will be set on first login)
        import random
        import string
        
        random_password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        
        user = User.objects.create_user(
            username=username,
            email=validated_data['email'],
            password=random_password,
            first_time_login=True,  # Set first time login flag
            **{k: v for k, v in validated_data.items() if k not in ['email']}
        )
        
        # Create related objects with default values
        self._create_related_objects(user)
        
        # Create initial hospital record if provided
        if hospital_name:
            HospitalInfo.objects.create(
                user=user,
                name=hospital_name,
                department=hospital_department or user.department,
                position='Doctor',
                employee_id=f"EMP{user.national_id[-6:]}" if user.national_id else f"EMP{user.id.hex[:6]}",
                join_date=date.today(),
                is_primary=True  # First hospital is primary by default
            )
        
        return user

    
    def _create_related_objects(self, user):
        """Create default related objects for new user"""
        # UserStats
        UserStats.objects.create(user=user)
        
        # SecuritySettings
        SecuritySettings.objects.create(user=user)
        
        # PrivacySettings
        PrivacySettings.objects.create(user=user)
        
        # UserPreferences with nested preferences
        preferences = UserPreferences.objects.create(user=user)
        NotificationPreferences.objects.create(user_preferences=preferences)
        DICOMPreferences.objects.create(user_preferences=preferences)


class SimpleUserCreateSerializer(serializers.ModelSerializer):
    """Simplified serializer for admin creating users with minimal data"""
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    email = serializers.EmailField(
        validators=[UniqueValidator(queryset=User.objects.all())]
    )
    national_id = serializers.CharField(
        validators=[UniqueValidator(queryset=User.objects.all())],
        required=False,  # Make it optional
        allow_blank=True  # Allow blank
    )
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES, default='doctor')
    
    class Meta:
        model = User
        fields = ['id', 'email', 'national_id', 'role']
        read_only_fields = ['id']
    
    def validate_email(self, value):
        try:
            validate_email(value)
        except ValidationError:
            raise serializers.ValidationError("Enter a valid email address.")
        return value.lower()
    
    def create(self, validated_data):
        email = validated_data['email']
        
        # Generate username from email
        username = email.split('@')[0]
        
        # Ensure username is unique
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        
        # Generate random password
        import random
        import string
        random_password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        
        # Extract role
        role = validated_data.pop('role', 'doctor')
        
        # Create user with minimal data
        user = User.objects.create_user(
            username=username,
            email=email,
            password=random_password,
            first_time_login=True,
            role=role,
            **{k: v for k, v in validated_data.items() if k != 'email'}
        )
        
        # Set user as active
        user.is_active = True
        
        # Set role-based permissions
        if role == 'admin':
            user.is_staff = True
        elif role == 'superadmin':
            user.is_staff = True
            user.is_superuser = True
        
        user.save()
        
        # Create related objects with default values
        self._create_related_objects(user)
        
        return user
    
    def _create_related_objects(self, user):
        """Create default related objects for new user"""
        # UserStats
        UserStats.objects.create(user=user)
        
        # SecuritySettings
        SecuritySettings.objects.create(user=user)
        
        # PrivacySettings
        PrivacySettings.objects.create(user=user)
        
        # UserPreferences with nested preferences
        preferences = UserPreferences.objects.create(user=user)
        NotificationPreferences.objects.create(user_preferences=preferences)
        DICOMPreferences.objects.create(user_preferences=preferences)


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile"""
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone', 'title',
            'dob', 'gender', 'bio', 'avatar_color',
            'department', 'experience', 'office',
            'is_favorite', 'status'
        ]
    
    def validate_phone(self, value):
        if value and not value.replace('+', '').replace(' ', '').isdigit():
            raise serializers.ValidationError("Phone number must contain only digits.")
        return value


class UnifiedLoginSerializer(serializers.Serializer):
    """Unified login serializer for both first-time and regular login"""
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=False,  # Optional for first-time login
        write_only=True,
        style={'input_type': 'password'}
    )
    new_password = serializers.CharField(
        required=False,  # Only for first-time login when setting password
        write_only=True,
        min_length=8,
        style={'input_type': 'password'}
    )
    confirm_password = serializers.CharField(
        required=False,  # Only for first-time login
        write_only=True,
        style={'input_type': 'password'}
    )
    
    def validate(self, data):
        email = data.get('email').lower()
        password = data.get('password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')

        user = self._get_user_by_email(email)
        self._check_user_active(user)

        if user.first_time_login:
            self._validate_first_time_login(password, new_password, confirm_password, user)
            data['is_first_time'] = True
        else:
            self._validate_regular_login(email, password, user)
            data['is_first_time'] = False

        data['user'] = user
        return data

    def _get_user_by_email(self, email):
        try:
            return User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({'email': USER_NOT_FOUND_ERROR})

    def _check_user_active(self, user):
        if not user.is_active:
            raise serializers.ValidationError({'email': ACCOUNT_NOT_ACTIVE_ERROR})

    def _validate_first_time_login(self, password, new_password, confirm_password, user):
        if password:
            raise serializers.ValidationError({'password': 'Please use first-time login to set your password.'})

        if not new_password or not confirm_password:
            raise serializers.ValidationError({'new_password': 'New password and confirmation required for first-time login.'})

        if new_password != confirm_password:
            raise serializers.ValidationError({'new_password': PASSWORD_MISMATCH_ERROR})

        try:
            validate_password(new_password, user)
        except ValidationError as e:
            raise serializers.ValidationError({'new_password': list(e.messages)})

    def _validate_regular_login(self, email, password, user):
        if not password:
            raise serializers.ValidationError({'password': 'Password is required.'})

        auth_user = authenticate(username=email, password=password) or authenticate(username=email.split('@')[0], password=password)

        if auth_user is None or auth_user != user:
            raise serializers.ValidationError({'password': 'Invalid password.'})


# class FirstTimeLoginSerializer(serializers.Serializer):
#     """Serializer for first-time login (setting password)"""
#     email = serializers.EmailField(required=True)
#     password = serializers.CharField(
#         required=True,
#         write_only=True,
#         min_length=8,
#         style={'input_type': 'password'}
#     )
#     confirm_password = serializers.CharField(
#         required=True,
#         write_only=True,
#         style={'input_type': 'password'}
#     )
    
#     def validate(self, data):
#         email = data.get('email')
#         password = data.get('password')
#         confirm_password = data.get('confirm_password')
        
#         # Check if passwords match
#         if password != confirm_password:
#             raise serializers.ValidationError({
#                 'password': PASSWORD_MISMATCH_ERROR
#             })
        
#         # Validate password strength
#         try:
#             validate_password(password)
#         except ValidationError as e:
#             raise serializers.ValidationError({'password': list(e.messages)})
        
#         # Check if user exists and is first time login
#         try:
#             user = User.objects.get(email=email.lower())
#         except User.DoesNotExist:
#             raise serializers.ValidationError({
#                 'email': 'No user found with this email {email}.'
#             })
        
#         if not user.first_time_login:
#             raise serializers.ValidationError({
#                 'email': 'This user has already completed first-time login.'
#             })
        
#         data['user'] = user
#         return data
    
#     def save(self):
#         user = self.validated_data['user']
#         password = self.validated_data['password']
        
#         # Set new password
#         user.set_password(password)
        
#         # Update first_time_login flag
#         user.first_time_login = False
        
#         # Set user as active
#         user.is_active = True
        
#         user.save()
#         return user


# class EmailLoginSerializer(serializers.Serializer):
#     """Serializer for email-only login (first time)"""
#     email = serializers.EmailField(required=True)
    
#     def validate(self, data):
#         email = data.get('email').lower()
        
#         try:
#             user = User.objects.get(email=email)
#         except User.DoesNotExist:
#             raise serializers.ValidationError({
#                 'email': USER_NOT_FOUND_ERROR
#             })
        
#         # Check if user can login with email only
#         if not user.first_time_login:
#             raise serializers.ValidationError({
#                 'email': 'Password required for this account.'
#             })
        
#         if not user.is_active:
#             raise serializers.ValidationError({
#                 'email': 'Account is not active.'
#             })
        
#         data['user'] = user
#         return data


# class PasswordLoginSerializer(serializers.Serializer):
#     """Serializer for regular password login"""
#     email = serializers.EmailField(required=True)
#     password = serializers.CharField(
#         required=True,
#         write_only=True,
#         style={'input_type': 'password'}
#     )
    
#     def validate(self, data):
#         email = data.get('email').lower()
#         password = data.get('password')
        
#         # Authenticate user
#         user = authenticate(username=email, password=password)
        
#         if user is None:
#             # Try with username as well
#             user = authenticate(username=email.split('@')[0], password=password)
        
#         if user is None:
#             raise serializers.ValidationError({
#                 'non_field_errors': 'Invalid email or password.'
#             })
        
#         if not user.is_active:
#             raise serializers.ValidationError({
#                 'non_field_errors': ACCOUNT_NOT_ACTIVE_ERROR
#             })
        
#         data['user'] = user
#         return data


class PasswordResetSerializer(serializers.Serializer):
    """Serializer for password reset"""
    email = serializers.EmailField(required=True)
    
    def validate_email(self, value):
        try:
            user = User.objects.get(email=value.lower())
        except User.DoesNotExist:
            raise serializers.ValidationError(USER_NOT_FOUND_ERROR)
        
        if user.first_time_login:
            raise serializers.ValidationError(
                'Please use first-time login instead of password reset.'
            )
        
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for confirming password reset"""
    email = serializers.EmailField(required=True)
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=8
    )
    confirm_password = serializers.CharField(
        required=True,
        write_only=True
    )
    
    def validate(self, data):
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        if new_password != confirm_password:
            raise serializers.ValidationError({
                'new_password': PASSWORD_MISMATCH_ERROR
            })
        
        try:
            validate_password(new_password)
        except ValidationError as e:
            raise serializers.ValidationError({'new_password': list(e.messages)})
        
        return data


class SessionSerializer(serializers.ModelSerializer):
    """Serializer for user sessions"""
    class Meta:
        model = Session
        fields = [
            'id', 'session_id', 'device', 'location',
            'ip_address', 'last_active', 'is_current',
            'created_at'
        ]
        read_only_fields = fields


class UserListSerializer(serializers.ModelSerializer):
    """Serializer for listing users"""
    full_name = serializers.SerializerMethodField()
    department = serializers.CharField(read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'title',
            'department', 'status', 'phone',
            'is_favorite', 'created_at'
        ]
        read_only_fields = fields
    
    def get_full_name(self, obj):
        return obj.get_full_name()


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for public profile view"""
    full_name = serializers.SerializerMethodField()
    address = AddressSerializer(read_only=True)
    hospitals = HospitalInfoSerializer(many=True,read_only=True)
    qualifications = QualificationSerializer(many=True, read_only=True)
    certifications = CertificationSerializer(many=True, read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'full_name', 'title', 'bio',
            'department', 'experience', 'specialties',
            'status', 'address', 'hospitals',
            'qualifications', 'certifications'
        ]
        read_only_fields = fields
    
    def get_full_name(self, obj):
        return obj.get_full_name()


class AdminUserCreateSerializer(UserCreateSerializer):
    """Serializer for admin to create users with more control"""
    role = serializers.ChoiceField(
        choices=[('doctor', 'Doctor'), ('admin', 'Admin'), ('superadmin', 'Super Admin')],
        default='doctor'
    )
    send_welcome_email = serializers.BooleanField(default=True)
    
    class Meta(UserCreateSerializer.Meta):
        fields = UserCreateSerializer.Meta.fields + ['role', 'send_welcome_email']
    
    def create(self, validated_data):
        role = validated_data.pop('role', 'doctor')
        send_welcome_email = validated_data.pop('send_welcome_email', True)
        
        # Create user using parent method
        user = super().create(validated_data)
        
        # Set role based permissions (you might have a different way to handle roles)
        if role == 'admin':
            user.is_staff = True
        elif role == 'superadmin':
            user.is_staff = True
            user.is_superuser = True
        
        user.save()
        
        # Send welcome email if requested
        if send_welcome_email:
            self._send_welcome_email(user, first_time_login=True)
        
        return user
    
    def _send_welcome_email(self, user, first_time_login=True):
        """Send welcome email to new user"""
        # Implement email sending logic here
        # You can use Django's send_mail or a third-party service
        pass