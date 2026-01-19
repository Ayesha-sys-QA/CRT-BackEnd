
from rest_framework import serializers
from datetime import datetime, timedelta
import uuid

from .models import Shift, ScheduleEvent, ScheduleTemplate, TemplateDay
from users.serializers import UserMinimalSerializer
from patients.serializers import PatientMinimalSerializer

class ShiftSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    duration_hours = serializers.SerializerMethodField()
    formatted_times = serializers.SerializerMethodField()
    
    class Meta:
        model = Shift
        fields = [
            'id', 'name', 'shift_type', 'start_time', 'end_time',
            'color', 'description', 'duration_hours', 'formatted_times'
        ]
    
    def get_duration_hours(self, obj):
        start = datetime.combine(datetime.today(), obj.start_time)
        end = datetime.combine(datetime.today(), obj.end_time)
        
        if end < start:
            end += timedelta(days=1)
        
        duration = (end - start).total_seconds() / 3600
        return round(duration, 2)
    
    def get_formatted_times(self, obj):
        return {
            'start': obj.start_time.strftime('%I:%M %p'),
            'end': obj.end_time.strftime('%I:%M %p')
        }

class ScheduleEventSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    user_details = UserMinimalSerializer(source='user', read_only=True)
    shift_details = ShiftSerializer(source='shift', read_only=True)
    patient_details = PatientMinimalSerializer(source='patient', read_only=True)
    
    # Computed fields
    duration_hours = serializers.SerializerMethodField()
    is_past = serializers.SerializerMethodField()
    is_today = serializers.SerializerMethodField()
    
    class Meta:
        model = ScheduleEvent
        fields = [
            'id', 'user', 'user_details', 'title', 'event_type', 'description',
            'start_date', 'end_date', 'start_time', 'end_time', 'all_day',
            'shift', 'shift_details', 'status', 'location', 'color',
            'patient', 'patient_details', 'department',
            'duration_hours', 'is_past', 'is_today',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_duration_hours(self, obj):
        return obj.duration_hours
    
    def get_is_past(self, obj):
        from django.utils import timezone
        today = timezone.now().date()
        return obj.end_date < today
    
    def get_is_today(self, obj):
        from django.utils import timezone
        today = timezone.now().date()
        return obj.start_date <= today <= obj.end_date
    
    def validate(self, data):
        # Check for scheduling conflicts
        if 'user' in data and 'start_date' in data and 'end_date' in data:
            user = data.get('user') or self.instance.user if self.instance else None
            start_date = data.get('start_date')
            end_date = data.get('end_date')
            
            if user and start_date and end_date:
                # Check for overlapping events (excluding current instance)
                overlapping = ScheduleEvent.objects.filter(
                    user=user,
                    status__in=['scheduled', 'confirmed'],
                    start_date__lte=end_date,
                    end_date__gte=start_date
                )
                
                if self.instance:
                    overlapping = overlapping.exclude(id=self.instance.id)
                
                if overlapping.exists():
                    raise serializers.ValidationError({
                        'non_field_errors': 'User has conflicting schedule events during this time.'
                    })
        
        return data

class ScheduleEventCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating schedule events"""
    class Meta:
        model = ScheduleEvent
        fields = [
            'user', 'title', 'event_type', 'description',
            'start_date', 'end_date', 'start_time', 'end_time', 'all_day',
            'shift', 'status', 'location', 'color',
            'patient', 'department'
        ]

class ScheduleEventBulkCreateSerializer(serializers.Serializer):
    """Bulk create schedule events for multiple users/dates"""
    user_ids = serializers.ListField(child=serializers.UUIDField())
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    shift_id = serializers.UUIDField()
    event_type = serializers.CharField(default='shift')
    
    def validate(self, data):
        from .models import Shift
        try:
            shift = Shift.objects.get(id=data['shift_id'])
            data['shift'] = shift
        except Shift.DoesNotExist:
            raise serializers.ValidationError({'shift_id': 'Shift not found.'})
        
        if data['end_date'] < data['start_date']:
            raise serializers.ValidationError({
                'end_date': 'End date must be on or after start date.'
            })
        
        return data

class ScheduleTemplateSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    days = serializers.SerializerMethodField()
    
    class Meta:
        model = ScheduleTemplate
        fields = ['id', 'name', 'description', 'department', 'is_active', 'days', 'created_at']
    
    def get_days(self, obj):
        days = obj.days.all().order_by('day_of_week')
        return TemplateDaySerializer(days, many=True).data

class TemplateDaySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    shift_details = ShiftSerializer(source='shift', read_only=True)
    
    class Meta:
        model = TemplateDay
        fields = ['id', 'day_of_week', 'shift', 'shift_details', 'notes']
        read_only_fields = ['id']

class UserScheduleViewSerializer(serializers.ModelSerializer):
    """Serializer for user's schedule view"""
    events = serializers.SerializerMethodField()
    upcoming_shifts = serializers.SerializerMethodField()
    monthly_hours = serializers.SerializerMethodField()
    
    class Meta:
        model = 'users.User'
        fields = ['id', 'name', 'email', 'events', 'upcoming_shifts', 'monthly_hours']
    
    def get_events(self, obj):
        # Get events for the next 30 days
        from django.utils import timezone
        from datetime import timedelta
        
        start_date = timezone.now().date()
        end_date = start_date + timedelta(days=30)
        
        events = obj.schedule_events.filter(
            start_date__lte=end_date,
            end_date__gte=start_date,
            status__in=['scheduled', 'confirmed']
        ).order_by('start_date', 'start_time')
        
        return ScheduleEventSerializer(events, many=True).data
    
    def get_upcoming_shifts(self, obj):
        from django.utils import timezone
        today = timezone.now().date()
        
        upcoming = obj.schedule_events.filter(
            end_date__gte=today,
            event_type='shift',
            status__in=['scheduled', 'confirmed']
        ).order_by('start_date')[:10]
        
        return ScheduleEventSerializer(upcoming, many=True).data
    
    def get_monthly_hours(self, obj):
        from django.utils import timezone
        from datetime import timedelta
        
        start_date = timezone.now().date().replace(day=1)
        next_month = start_date.replace(month=start_date.month+1) if start_date.month < 12 else start_date.replace(year=start_date.year+1, month=1)
        end_date = next_month - timedelta(days=1)
        
        events = obj.schedule_events.filter(
            start_date__gte=start_date,
            end_date__lte=end_date,
            status__in=['scheduled', 'confirmed']
        )
        
        total_hours = sum(event.duration_hours for event in events)
        return round(total_hours, 2)