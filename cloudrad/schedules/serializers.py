# schedules/serializers.py
from rest_framework import serializers

from users.models import User
from .models import Shift, ScheduleDay, UserSchedule
from users.serializers import UserMinimalSerializer  # Assuming you'll create this
import uuid
from datetime import datetime, time


class ShiftSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    duration_hours = serializers.SerializerMethodField()
    formatted_start_time = serializers.SerializerMethodField()
    formatted_end_time = serializers.SerializerMethodField()
    
    class Meta:
        model = Shift
        fields = [
            'id',
            'start_time',
            'end_time',
            'shift_type',
            'duration_hours',
            'formatted_start_time',
            'formatted_end_time'
        ]
        read_only_fields = ['id']
    
    def get_duration_hours(self, obj):
        """Calculate shift duration in hours"""
        start = datetime.combine(datetime.today(), obj.start_time)
        end = datetime.combine(datetime.today(), obj.end_time)
        
        # Handle overnight shifts
        if end < start:
            end = datetime.combine(datetime.today(), time(23, 59, 59))
        
        duration = (end - start).seconds / 3600
        return round(duration, 2)
    
    def get_formatted_start_time(self, obj):
        return obj.start_time.strftime('%I:%M %p')
    
    def get_formatted_end_time(self, obj):
        return obj.end_time.strftime('%I:%M %p')
    
    def validate(self, data):
        # Validate that end time is after start time
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        
        if start_time and end_time:
            # Handle overnight shifts (end_time < start_time means overnight)
            # For overnight shifts, we'll allow it but add a note
            if end_time < start_time:
                # Check if it's a valid overnight shift (not too long)
                start_dt = datetime.combine(datetime.today(), start_time)
                end_dt = datetime.combine(datetime.today(), end_time)
                # Add one day to end time for overnight calculation
                end_dt = end_dt.replace(day=end_dt.day + 1)
                
                duration_hours = (end_dt - start_dt).seconds / 3600
                if duration_hours > 24:
                    raise serializers.ValidationError({
                        'end_time': 'Shift duration cannot exceed 24 hours.'
                    })
            
            elif end_time == start_time:
                raise serializers.ValidationError({
                    'end_time': 'End time cannot be the same as start time.'
                })
        
        return data


class ShiftCreateSerializer(serializers.ModelSerializer):
    """Serializer specifically for creating shifts"""
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    
    class Meta:
        model = Shift
        fields = ['id', 'start_time', 'end_time', 'shift_type']
        read_only_fields = ['id']


class ScheduleDaySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    shift_details = ShiftSerializer(source='shift', read_only=True)
    shift = serializers.PrimaryKeyRelatedField(
        queryset=Shift.objects.all(),
        required=False,
        allow_null=True
    )
    assigned_users_count = serializers.SerializerMethodField()
    assigned_users = serializers.SerializerMethodField()
    
    class Meta:
        model = ScheduleDay
        fields = [
            'id',
            'day_name',
            'shift',
            'shift_details',
            'assigned_users_count',
            'assigned_users'
        ]
        read_only_fields = ['id', 'assigned_users_count', 'assigned_users']
    
    def get_assigned_users_count(self, obj):
        return obj.user_schedules.count()
    
    def get_assigned_users(self, obj):
        users = obj.user_schedules.all().select_related('user')
        return UserMinimalSerializer([us.user for us in users], many=True).data
    
    def validate(self, data):
        # Ensure unique day_name (optional, depending on your requirements)
        day_name = data.get('day_name')
        
        
        # If you want to ensure each day has only one schedule entry
        # (comment out if you want multiple shifts per day)
        instance = self.instance
        if instance:
            # Update case
            if ScheduleDay.objects.filter(
                day_name=day_name
            ).exclude(id=instance.id).exists():
                raise serializers.ValidationError({
                    'day_name': f'A schedule day already exists for {day_name}.'
                })
        else:
            # Create case
            if ScheduleDay.objects.filter(day_name=day_name).exists():
                raise serializers.ValidationError({
                    'day_name': f'A schedule day already exists for {day_name}.'
                })
        
        return data


class ScheduleDayCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating schedule days"""
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    
    class Meta:
        model = ScheduleDay
        fields = ['id', 'day_name', 'shift']
        read_only_fields = ['id']


class UserScheduleSerializer(serializers.ModelSerializer):
    user_details = UserMinimalSerializer(source='user', read_only=True)
    schedule_day_details = ScheduleDaySerializer(source='schedule_day', read_only=True)
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        write_only=True
    )
    schedule_day = serializers.PrimaryKeyRelatedField(
        queryset=ScheduleDay.objects.all(),
        write_only=True
    )
    
    # Computed fields
    day_name = serializers.CharField(source='schedule_day.day_name', read_only=True)
    shift_details = serializers.SerializerMethodField()
    
    class Meta:
        model = UserSchedule
        fields = [
            'id',
            'user',
            'user_details',
            'schedule_day',
            'schedule_day_details',
            'day_name',
            'shift_details'
        ]
        read_only_fields = ['id', 'day_name', 'shift_details']
    
    def get_shift_details(self, obj):
        if obj.schedule_day.shift:
            return ShiftSerializer(obj.schedule_day.shift).data
        return None
    
    def validate(self, data):
        user = data.get('user')
        schedule_day = data.get('schedule_day')
        
        # Check for duplicate assignment
        if UserSchedule.objects.filter(user=user, schedule_day=schedule_day).exists():
            raise serializers.ValidationError({
                'user': f'User is already assigned to this schedule day:{user}.'
            })
        # 
        return data


class UserScheduleCreateSerializer(serializers.ModelSerializer):
    """Bulk assignment serializer"""
    class Meta:
        model = UserSchedule
        fields = ['user', 'schedule_day']
    
    def validate(self, data):
        return UserScheduleSerializer().validate(data)


class UserScheduleBulkSerializer(serializers.Serializer):
    """Serializer for bulk assignment of users to schedule days"""
    user_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1
    )
    schedule_day_id = serializers.UUIDField()
    
    def validate(self, data):
        # Validate that schedule day exists
        schedule_day_id = data.get('schedule_day_id')
        try:
            schedule_day = ScheduleDay.objects.get(id=schedule_day_id)
            data['schedule_day'] = schedule_day
        except ScheduleDay.DoesNotExist:
            raise serializers.ValidationError({
                'schedule_day_id': 'Schedule day not found.'
            })
        
        # Validate that users exist
        user_ids = data.get('user_ids')
        users = User.objects.filter(id__in=user_ids)
        if len(users) != len(user_ids):
            raise serializers.ValidationError({
                'user_ids': 'One or more users not found.'
            })
        
        data['users'] = users
        return data


class UserWeeklyScheduleSerializer(serializers.ModelSerializer):
    """Serializer for displaying a user's weekly schedule"""
    weekly_schedule = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'weekly_schedule']
    
    def get_weekly_schedule(self, obj):
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekly_data = []
        
        for day_name in days:
            try:
                schedule_day = ScheduleDay.objects.get(day_name=day_name)
                user_schedule = obj.schedules.filter(schedule_day=schedule_day).first()
                
                if user_schedule:
                    shift_data = ShiftSerializer(user_schedule.schedule_day.shift).data if user_schedule.schedule_day.shift else None
                    weekly_data.append({
                        'day': day_name,
                        'has_shift': True,
                        'shift': shift_data,
                        'schedule_day_id': schedule_day.id
                    })
                else:
                    weekly_data.append({
                        'day': day_name,
                        'has_shift': False,
                        'shift': None,
                        'schedule_day_id': None
                    })
            except ScheduleDay.DoesNotExist:
                weekly_data.append({
                    'day': day_name,
                    'has_shift': False,
                    'shift': None,
                    'schedule_day_id': None
                })
        
        return weekly_data


class DayScheduleSerializer(serializers.Serializer):
    """Serializer for displaying all users assigned to a specific day"""
    day_name = serializers.CharField()
    shift = ShiftSerializer(read_only=True)
    assigned_users = serializers.SerializerMethodField()
    
    def get_assigned_users(self, obj):
        user_schedules = obj.user_schedules.all().select_related('user')
        users = [us.user for us in user_schedules]
        return UserMinimalSerializer(users, many=True).data


class ShiftAssignmentSerializer(serializers.Serializer):
    """Serializer for assigning shifts to schedule days"""
    schedule_day_id = serializers.UUIDField()
    shift_id = serializers.UUIDField(required=False, allow_null=True)
    
    def validate(self, data):
        schedule_day_id = data.get('schedule_day_id')
        shift_id = data.get('shift_id')
        
        try:
            schedule_day = ScheduleDay.objects.get(id=schedule_day_id)
            data['schedule_day'] = schedule_day
        except ScheduleDay.DoesNotExist:
            raise serializers.ValidationError({
                'schedule_day_id': 'Schedule day not found.'
            })
        
        if shift_id:
            try:
                shift = Shift.objects.get(id=shift_id)
                data['shift'] = shift
            except Shift.DoesNotExist:
                raise serializers.ValidationError({
                    'shift_id': 'Shift not found.'
                })
        else:
            data['shift'] = None
        
        return data