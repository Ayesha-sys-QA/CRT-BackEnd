

from django.db import models
import uuid
from django.core.exceptions import ValidationError
from django.utils import timezone

class Shift(models.Model):
    """Fixed shift templates (Morning, Evening, Night, etc.)"""
    SHIFT_TYPE_CHOICES = [
        ('morning', 'Morning (8AM-4PM)'),
        ('evening', 'Evening (4PM-12AM)'),
        ('night', 'Night (12AM-8AM)'),
        ('on_call', 'On-Call'),
        ('split', 'Split Shift'),
        ('custom', 'Custom'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, default="Default Shift")  # e.g., "Morning Shift"
    shift_type = models.CharField(max_length=20, choices=SHIFT_TYPE_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    color = models.CharField(max_length=7, default='#3B82F6')  # For UI display
    description = models.TextField(blank=True)
    
    class Meta:
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['shift_type']),
        ]
    
    def clean(self):
        if self.end_time <= self.start_time:
            # Allow overnight shifts but check duration
            from datetime import datetime, timedelta
            start = datetime.combine(datetime.today(), self.start_time)
            end = datetime.combine(datetime.today(), self.end_time)
            if end <= start:
                end += timedelta(days=1)
            duration = (end - start).seconds / 3600
            if duration > 24:
                raise ValidationError("Shift duration cannot exceed 24 hours.")
    
    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')})"

class ScheduleEvent(models.Model):
    """Individual calendar events for specific dates"""
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
    
    EVENT_TYPE_CHOICES = [
        ('shift', 'Regular Shift'),
        ('on_call', 'On-Call Duty'),
        ('meeting', 'Meeting'),
        ('training', 'Training'),
        ('vacation', 'Vacation'),
        ('sick_leave', 'Sick Leave'),
        ('conference', 'Conference'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='schedule_events')
    
    # Event details
    title = models.CharField(max_length=200)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES, default='shift')
    description = models.TextField(blank=True)
    
    # Date and time
    start_date = models.DateField()
    end_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    all_day = models.BooleanField(default=False)
    
    # Shift reference (if applicable)
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Status and metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    location = models.CharField(max_length=200, blank=True)
    color = models.CharField(max_length=7, default='#3B82F6')
    
    # Relationships
    patient = models.ForeignKey('patients.Patient', on_delete=models.SET_NULL, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True)  # Or ForeignKey if you have Department model
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, related_name='created_events')
    
    class Meta:
        ordering = ['start_date', 'start_time']
        indexes = [
            models.Index(fields=['user', 'start_date']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['event_type', 'status']),
            models.Index(fields=['department', 'start_date']),
        ]
    
    def clean(self):
        # Validate date range
        if self.end_date < self.start_date:
            raise ValidationError("End date cannot be before start date")
        
        # Validate time for non-all-day events
        if not self.all_day and self.end_time <= self.start_time:
            # Allow overnight shifts within same day
            pass
    
    def __str__(self):
        return f"{self.title} - {self.user.name} ({self.start_date})"
    
    @property
    def duration_hours(self):
        """Calculate total hours for the event"""
        if self.all_day:
            return 8.0  # Standard work day
        
        from datetime import datetime, timedelta
        start_dt = datetime.combine(self.start_date, self.start_time)
        end_dt = datetime.combine(self.end_date, self.end_time)
        
        # Handle overnight within same day
        if self.end_date == self.start_date and self.end_time < self.start_time:
            end_dt += timedelta(days=1)
        
        duration = (end_dt - start_dt).total_seconds() / 3600
        return round(duration, 2)

class ScheduleTemplate(models.Model):
    """Template for recurring weekly schedules"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)  # e.g., "Cardiology Winter Schedule"
    description = models.TextField(blank=True)
    department = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']

class TemplateDay(models.Model):
    """Day template within a schedule template"""
    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(ScheduleTemplate, on_delete=models.CASCADE, related_name='days')
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['day_of_week']
        unique_together = ['template', 'day_of_week']
    
    def __str__(self):
        return f"{self.get_day_of_week_display()} - {self.template.name}"