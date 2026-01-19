from django.db import models

# Create your models here.
from users.models import User
from patients.models import Patient
import uuid

class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    MESSAGE_TYPE_CHOICES = [
        ('inbox', 'Inbox'),
        ('sent', 'Sent'),
        ('announcement', 'Announcement'),
        ('alert', 'Alert'),
    ]
    
    PRIORITY_CHOICES = [
        ('normal', 'Normal'),
        ('important', 'Important'),
        ('urgent', 'Urgent'),
        ('critical', 'Critical'),
    ]
    
    STATUS_CHOICES = [
        ('delivered', 'Delivered'),
        ('pending', 'Pending'),
        ('failed', 'Failed'),
    ]
    
    ANNOUNCEMENT_TYPE_CHOICES = [
        ('urgent', 'Urgent'),
        ('update', 'Update'),
        ('info', 'Information'),
    ]
    
    # Sender/Recipient
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages', null=True, blank=True)
    
    # Message details
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES)
    subject = models.CharField(max_length=255)
    content = models.TextField()
    
    # Metadata
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    is_important = models.BooleanField(default=False)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Optional fields
    category = models.CharField(max_length=100, blank=True)
    patient = models.ForeignKey(Patient, on_delete=models.SET_NULL, null=True, blank=True, related_name='messages')
    announcement_type = models.CharField(max_length=20, choices=ANNOUNCEMENT_TYPE_CHOICES,null=True, blank=True)
    
    attachments_count = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-timestamp']
        db_table = 'messages'
        indexes = [
            models.Index(fields=['sender', 'timestamp']),
            models.Index(fields=['recipient', 'is_read', 'timestamp']),
            models.Index(fields=['message_type', 'timestamp']),
            # Add this for patient-related queries if frequently used:
            models.Index(fields=['patient', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.subject} - {self.sender.name}"


class Attachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='message_attachments/%Y/%m/%d/')
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100)
    file_size = models.BigIntegerField()  # in bytes
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['uploaded_at']
        indexes = [
            models.Index(fields=['message', 'uploaded_at']),
        ]
    
    def __str__(self):
        return self.file_name