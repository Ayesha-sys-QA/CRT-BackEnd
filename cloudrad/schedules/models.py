from django.db import models

# Create your models here.
import uuid

from users.models import User

class Shift(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    start_time = models.TimeField()
    end_time = models.TimeField()
    shift_type = models.CharField(max_length=50)
    
    def __str__(self):
        return f"{self.shift_type}: {self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"


class ScheduleDay(models.Model):
    DAY_CHOICES = [
        ('Monday', 'Monday'),
        ('Tuesday', 'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'),
        ('Friday', 'Friday'),
        ('Saturday', 'Saturday'),
        ('Sunday', 'Sunday'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    day_name = models.CharField(max_length=10, choices=DAY_CHOICES)
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['day_name']
       
    
    @property
    def assigned_users(self):
        return [us.user for us in self.user_schedules.all()]
    
    @property
    def has_shift(self):
        return self.shift is not None
    
    def __str__(self):
        if self.shift:
            return f"{self.day_name}: {self.shift}"
        return f"{self.day_name}: No shift"
      
      

class UserSchedule(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='schedules')
    schedule_day = models.ForeignKey(ScheduleDay, on_delete=models.CASCADE, related_name='user_schedules')
    
    class Meta:
        unique_together = ['user', 'schedule_day']
        ordering = ['schedule_day__day_name']
    
    def __str__(self):
        return f"{self.user.name} - {self.schedule_day}"
