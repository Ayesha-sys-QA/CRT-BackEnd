from django.db import models

# Create your models here.
from users.models import User
import uuid
from datetime import date

class Insurance(models.Model):
    provider = models.CharField(max_length=255)
    policy_number = models.CharField(max_length=100)
    expiry_date = models.DateField()
    
    def __str__(self):
        return f"{self.provider} - {self.policy_number}"


class Patient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Linking to primary doctor
    primary_doctor = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='patients'
    )
    
    # Basic Information
    national_id = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=255)
    date_of_birth = models.DateField()
    
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other')
    ]
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    
    # Contact Information
    phone = models.CharField(max_length=20)
    country_code = models.CharField(max_length=5, default='+1')
    email = models.EmailField(blank=True)
    
    # Medical Information
    BLOOD_TYPE_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-')
    ]
    blood_type = models.CharField(max_length=3, choices=BLOOD_TYPE_CHOICES)
    allergies = models.JSONField(default=list)
    medications = models.TextField(blank=True)
    medical_history = models.TextField(blank=True)
    
    # Address
    address = models.TextField()
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    
    # Emergency Contact
    emergency_contact_name = models.CharField(max_length=255)
    emergency_contact_phone = models.CharField(max_length=20)
    emergency_contact_relationship = models.CharField(max_length=50)
    
    # Insurance
    insurance_provider = models.CharField(max_length=255, blank=True)
    insurance_policy_number = models.CharField(max_length=100, blank=True)
    insurance_expiry_date = models.DateField(null=True, blank=True)
    
    # Status
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
        ('Critical', 'Critical'),
        ('Pending', 'Pending'),
        ('Follow-up', 'Follow-up'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    is_active = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)
    
    # Timestamps
    last_visit = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        db_table = 'patients'
    
    @property
    def age(self):
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )
    
    def __str__(self):
        return f"{self.full_name} ({self.national_id})"


class PatientStats(models.Model):
    patient = models.OneToOneField(Patient, on_delete=models.CASCADE, related_name='stats')
    appointment_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    follow_up_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    medication_adherence = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    test_results_pending = models.IntegerField(default=0)
    
    class Meta:
        verbose_name_plural = "Patient Statistics"
    
    def __str__(self):
        return f"Stats for {self.patient.full_name}"