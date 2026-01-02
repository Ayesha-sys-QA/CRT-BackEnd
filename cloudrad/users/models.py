from django.db import models

# Create your models here.
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator, EmailValidator
import uuid
from datetime import date

class User(AbstractUser):
    """
    Combined User/Doctor model - all users in this system are doctors
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Core Identity
    national_id = models.CharField(max_length=20, unique=True)
    email = models.EmailField(
        unique=True,
        validators=[EmailValidator()]
    )
    phone = models.CharField(
        max_length=20,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$')],
        blank=True
    )
    
    # Login tracking
    first_time_login = models.BooleanField(default=True)
    
    # Personal Information
    title = models.CharField(max_length=50, blank=True)  # Dr., Prof., etc.
    dob = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=10,
        choices=[('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')],
        blank=True
    )
    bio = models.TextField(blank=True)
    avatar_color = models.CharField(max_length=7, default='#4F46E5')
    
    # Professional Information
    department = models.CharField(max_length=255, blank=True)
    experience = models.IntegerField(default=0)  # in years
    total_patients = models.IntegerField(default=0)
    specialties = models.JSONField(default=list, blank=True)
    office = models.CharField(max_length=100, blank=True)
    is_favorite = models.BooleanField(default=False)
    
    # Professional Status
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('on-call', 'On Call'),
        ('offline', 'Offline'),
        ('away', 'Away'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offline')
    
    ROLE_CHOICES = [
        ('doctor', 'Doctor'),
        ('admin', 'Administrator'),
        ('superadmin', 'Super Administrator'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='doctor')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'users'
        ordering = ['-created_at']
        
    def __str__(self):
        return f"Dr. {self.get_full_name()}"
    
    @property
    def name(self):
        return self.get_full_name()
    
    @property
    def weekly_schedule(self):
        """Get user's schedule for the week"""
        schedules = {}
        for schedule in self.schedules.all():
            schedules[schedule.schedule_day.day_name] = {
                'shift': schedule.schedule_day.shift,
                'schedule_day_id': schedule.schedule_day.id
            }
        return schedules
    
    @property
    def primary_hospital(self):
        """Get the primary hospital (if marked as primary)"""
        try:
            return self.hospitals.filter(is_primary=True).first()
        except:
            return self.hospitals.first()
            raise  # Return first if no primary marked
    
    @property
    def hospital_names(self):
        """Get list of all hospital names where this doctor works"""
        return list(self.hospitals.values_list('name', flat=True))
    
    @property
    def current_hospital_info(self):
        """Get current/primary hospital details"""
        primary = self.primary_hospital
        if primary:
            return {
                'name': primary.name,
                'address': primary.address,
                'department': primary.department,
                'position': primary.position,
                'employee_id': primary.employee_id,
                'join_date': primary.join_date,
                'contact': primary.contact,
                'is_primary': primary.is_primary
            }
        return None
    
    @property
    def all_hospitals_info(self):
        """Get information for all hospitals"""
        return [
            {
                'id': hospital.id,
                'name': hospital.name,
                'address': hospital.address,
                'department': hospital.department,
                'position': hospital.position,
                'employee_id': hospital.employee_id,
                'join_date': hospital.join_date,
                'contact': hospital.contact,
                'is_primary': hospital.is_primary
            }
            for hospital in self.hospitals.all()
        ]


class Address(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='address')
    street = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    
    def __str__(self):
        return f"{self.street}, {self.city}"


class EmergencyContact(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='emergency_contact')
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    relationship = models.CharField(max_length=50)
    
    def __str__(self):
        return f"{self.name} ({self.relationship})"


class HospitalInfo(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hospital')
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    department = models.CharField(max_length=255)
    position = models.CharField(max_length=255)
    employee_id = models.CharField(max_length=100)
    join_date = models.DateField()
    contact = models.CharField(max_length=100, blank=True)
    is_primary = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.name} - {self.department}"


class Affiliation(models.Model):
    hospital = models.ForeignKey(HospitalInfo, on_delete=models.CASCADE, related_name='affiliations')
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=255)
    start_date = models.DateField(default=date.today)
    end_date = models.DateField(null=True, blank=True)  # For past affiliations
    is_current = models.BooleanField(default=True)

    
    def __str__(self):
        return f"{self.name} ({self.role})"


class License(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='license')
    number = models.CharField(max_length=100, unique=True)
    type = models.CharField(max_length=100)
    authority = models.CharField(max_length=255)
    issue_date = models.DateField()
    expiry_date = models.DateField()
    specialization = models.CharField(max_length=255)
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
        ('pending', 'Pending')
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    
    def is_valid(self):
        return self.expiry_date >= date.today() and self.status == 'active'
    
    def __str__(self):
        return f"License {self.number}"


class Qualification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='qualifications')
    degree = models.CharField(max_length=255)
    institution = models.CharField(max_length=255)
    year = models.CharField(max_length=4)
    
    class Meta:
        ordering = ['-year']
    
    def __str__(self):
        return f"{self.degree} - {self.institution} ({self.year})"


class Certification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='certifications')
    name = models.CharField(max_length=255)
    issuer = models.CharField(max_length=255)
    year = models.CharField(max_length=4)
    cert_id = models.CharField(max_length=100)
    expiry_date = models.DateField(null=True, blank=True)
    
    class Meta:
        ordering = ['-year']
    
    def __str__(self):
        return f"{self.name} - {self.issuer}"


class UserStats(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='stats')
    patients = models.IntegerField(default=0)
    studies = models.IntegerField(default=0)
    years = models.IntegerField(default=0)
    
    def __str__(self):
        return f"Stats for Dr. {self.user.get_full_name()}"


class SecuritySettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='security')
    two_factor_enabled = models.BooleanField(default=False)
    two_factor_method = models.CharField(
        max_length=10,
        choices=[('app', 'App'), ('sms', 'SMS')],
        null=True,
        blank=True
    )


class Session(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    session_id = models.CharField(max_length=255)
    device = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField()
    last_active = models.DateTimeField(auto_now=True)
    is_current = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-last_active']

    def __str__(self):
        return f"Session {self.session_id} - {self.user.name}"


class PrivacySettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='privacy')
    profile_visibility = models.CharField(
        max_length=20,
        choices=[
            ('public', 'Public'),
            ('private', 'Private'),
            ('contacts', 'Contacts Only')
        ],
        default='private'
    )
    show_activity = models.BooleanField(default=False)
    allow_data_sharing = models.BooleanField(default=False)
    email_notifications = models.BooleanField(default=True)


class UserPreferences(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferences')
    theme = models.CharField(max_length=50, default='light')
    language = models.CharField(max_length=10, default='en')
    timezone = models.CharField(max_length=50, default='UTC')
    date_format = models.CharField(max_length=20, default='YYYY-MM-DD')
    
    def __str__(self):
        return f"Preferences for Dr. {self.user.username}"


class NotificationPreferences(models.Model):
    user_preferences = models.OneToOneField(
        UserPreferences, 
        on_delete=models.CASCADE, 
        related_name='notifications'
    )
    new_patients = models.BooleanField(default=True)
    critical_results = models.BooleanField(default=True)
    follow_ups = models.BooleanField(default=True)
    platform_updates = models.BooleanField(default=False)
    maintenance = models.BooleanField(default=True)
    training = models.BooleanField(default=False)


class DICOMPreferences(models.Model):
    user_preferences = models.OneToOneField(
        UserPreferences, 
        on_delete=models.CASCADE, 
        related_name='dicom'
    )
    layout = models.CharField(max_length=50, default='2x2')
    window_preset = models.CharField(max_length=50, default='standard')
    measurement_units = models.CharField(max_length=20, default='mm')
    annotation_color = models.CharField(max_length=7, default='#FF0000')