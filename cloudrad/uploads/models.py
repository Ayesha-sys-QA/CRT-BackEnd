from django.db import models

# Create your models here.
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
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        db_table = 'upload_files'
    
    def __str__(self):
        return self.name


class ProcessingOptions(models.Model):
    upload = models.OneToOneField(UploadFile, on_delete=models.CASCADE, related_name='processing_options')
    auto_anonymize = models.BooleanField(default=False)
    ai_analysis = models.BooleanField(default=False)
    auto_3d = models.BooleanField(default=False)
    send_notifications = models.BooleanField(default=True)
    archive = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Processing options for {self.upload.name}"