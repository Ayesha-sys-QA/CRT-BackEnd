from django.db import models

# Create your models here.
from users.models import User
from patients.models import Patient
import uuid

class UploadFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    size = models.BigIntegerField()  # in bytes
    file_type = models.CharField(max_length=100)
    last_modified = models.BigIntegerField(default=0)
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('uploading', 'Uploading'),
        ('uploaded', 'Uploaded'),
        ('error', 'Error'),
    ]
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress = models.IntegerField(default=0)  # percentage
    error_message = models.TextField(blank=True)
    
    # Patient association
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='uploads', null=True, blank=True)
    
    # File storage
    file = models.FileField(upload_to='patient_uploads/%Y/%m/%d/')
    
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    uploaded_by = models.ForeignKey(
        User,  # Adjust based on your User model
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploads',
        verbose_name='Uploaded by'
    )
    
    # File category for medical classification
    CATEGORY_CHOICES = [
        ('xray', 'X-Ray'),
        ('ct', 'CT Scan'),
        ('mri', 'MRI'),
        ('ultrasound', 'Ultrasound'),
        ('photo', 'Clinical Photo'),
        ('document', 'Document'),
        ('other', 'Other'),
    ]
    category = models.CharField(
        max_length=20, 
        choices=CATEGORY_CHOICES, 
        default='other'
    )
    
    # For integrity checking
    file_hash = models.CharField(max_length=64, blank=True)  # SHA256 hash
    
    # Access logs
    last_accessed = models.DateTimeField(null=True, blank=True)
    accessed_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accessed_uploads'
    )
    
    # Consent tracking (HIPAA/GDPR)
    patient_consent = models.BooleanField(default=False)
    consent_date = models.DateTimeField(null=True, blank=True)
    
    # Processing status
    PROCESSING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    processing_status = models.CharField(
        max_length=20, 
        choices=PROCESSING_STATUS_CHOICES, 
        default='pending'
    )
    
    
    class Meta:
        ordering = ['-created_at']
        db_table = 'upload_files'
        
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['patient', 'created_at']),
            models.Index(fields=['category']),
            models.Index(fields=['uploaded_by', 'created_at']),
        ]
        # ADD PERMISSIONS:
        permissions = [
            ('can_view_all_uploads', 'Can view all uploads'),
            ('can_process_uploads', 'Can process uploads'),
            ('can_export_uploads', 'Can export uploads'),
        ]
    
    def __str__(self):
        return self.name


class ProcessingOptions(models.Model):
    upload = models.OneToOneField(UploadFile, on_delete=models.CASCADE, related_name='processing_options')
    auto_anonymize = models.BooleanField(default=True)
    ai_analysis = models.BooleanField(default=False)
    auto_3d = models.BooleanField(default=False)
    send_notifications = models.BooleanField(default=True)
    archive = models.BooleanField(default=True)
    compression_level = models.CharField(
        max_length=20,
        choices=[('none', 'None'), ('lossless', 'Lossless'), ('lossy', 'Lossy')],
        default='lossless'
    )
    output_format = models.CharField(
        max_length=20,
        choices=[
            ('original', 'Original'),
            ('jpeg', 'JPEG'),
            ('png', 'PNG'),
            ('dicom', 'DICOM'),
            ('pdf', 'PDF')
        ],
        default='original'
    )
    priority = models.CharField(
        max_length=20,
        choices=[('low', 'Low'), ('normal', 'Normal'), ('high', 'High'), ('emergency', 'Emergency')],
        default='normal'
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def clean(self):
        """Validate processing option dependencies"""
        from django.core.exceptions import ValidationError
        
        if self.auto_3d and not self.ai_analysis:
            raise ValidationError({
                'auto_3d': '3D processing requires AI analysis to be enabled.'
            })
            
    def __str__(self):
        return f"Processing options for {self.upload.name}"
    
    
# Add after ProcessingOptions model
class DICOMMetadata(models.Model):
    """Store extracted DICOM metadata for medical imaging files"""
    upload = models.OneToOneField(
        UploadFile, 
        on_delete=models.CASCADE, 
        related_name='dicom_metadata'
    )
    
    # Patient info (from DICOM)
    patient_name = models.CharField(max_length=255, blank=True)
    patient_id = models.CharField(max_length=64, blank=True)
    patient_birth_date = models.DateField(null=True, blank=True)
    patient_sex = models.CharField(max_length=10, blank=True)
    
    # Study info
    study_instance_uid = models.CharField(max_length=64, blank=True)
    study_date = models.DateField(null=True, blank=True)
    study_description = models.TextField(blank=True)
    accession_number = models.CharField(max_length=64, blank=True)
    
    # Series info
    series_instance_uid = models.CharField(max_length=64, blank=True)
    series_number = models.IntegerField(null=True, blank=True)
    series_description = models.TextField(blank=True)
    modality = models.CharField(max_length=20, blank=True)  # CT, MR, XR, etc.
    
    # Image info
    rows = models.IntegerField(null=True, blank=True)
    columns = models.IntegerField(null=True, blank=True)
    bits_allocated = models.IntegerField(null=True, blank=True)
    pixel_spacing = models.CharField(max_length=50, blank=True)
    slice_thickness = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    
    # Equipment
    manufacturer = models.CharField(max_length=100, blank=True)
    institution_name = models.CharField(max_length=200, blank=True)
    
    # Anonymization status
    is_anonymized = models.BooleanField(default=False)
    anonymization_date = models.DateTimeField(null=True, blank=True)
    
    # Extracted metadata as JSON for flexibility
    raw_metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'DICOM Metadata'
        verbose_name_plural = 'DICOM Metadata'
        db_table = 'dicom_metadata'
    
    def __str__(self):
        return f"DICOM Metadata for {self.upload.name}"
    
    

class UploadAccessLog(models.Model):
    """Track who accesses medical files (HIPAA requirement)"""
    ACTION_CHOICES = [
        ('viewed', 'Viewed'),
        ('downloaded', 'Downloaded'),
        ('shared', 'Shared'),
        ('modified', 'Modified'),
        ('deleted', 'Deleted'),
    ]
    
    upload = models.ForeignKey(
        UploadFile, 
        on_delete=models.CASCADE, 
        related_name='access_logs'
    )
    user = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='upload_access_logs'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-timestamp']
        db_table = 'upload_access_logs'
        indexes = [
            models.Index(fields=['upload', 'timestamp']),
            models.Index(fields=['user', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user} {self.action} {self.upload.name} at {self.timestamp}"