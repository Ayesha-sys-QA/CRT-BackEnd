from django.shortcuts import render

# Create your views here.
# schedules/views.py
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Prefetch
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime, time, timedelta
import json

from .models import Shift, ScheduleDay, UserSchedule
from .serializers import (
    ShiftSerializer, ShiftCreateSerializer,
    ScheduleDaySerializer, ScheduleDayCreateSerializer,
    UserScheduleSerializer, UserScheduleCreateSerializer,
    UserScheduleBulkSerializer, UserWeeklyScheduleSerializer,
    DayScheduleSerializer, ShiftAssignmentSerializer
)
from users.models import User
import logging

logger = logging.getLogger(__name__)


# ==================== SHIFT MANAGEMENT VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def shift_list(request):
    """
    List all shifts with filtering
    """
    shifts = Shift.objects.all().order_by('start_time')
    
    # Apply filters
    shift_type = request.query_params.get('shift_type')
    search = request.query_params.get('search')
    
    if shift_type:
        shifts = shifts.filter(shift_type__icontains=shift_type)
    
    if search:
        shifts = shifts.filter(
            Q(shift_type__icontains=search) |
            Q(start_time__icontains=search) |
            Q(end_time__icontains=search)
        )
    
    serializer = ShiftSerializer(shifts, many=True)
    
    return Response({
        'count': shifts.count(),
        'shifts': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def create_shift(request):
    """
    Create a new shift (admin only)
    """
    serializer = ShiftCreateSerializer(data=request.data)
    
    if serializer.is_valid():
        shift = serializer.save()
        
        return Response({
            'message': 'Shift created successfully',
            'shift': ShiftSerializer(shift).data
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def shift_detail(request, shift_id):
    """
    Retrieve, update, or delete a shift
    """
    shift = get_object_or_404(Shift, id=shift_id)
    
    if request.method == 'GET':
        serializer = ShiftSerializer(shift)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method in ['PUT', 'PATCH']:
        if not request.user.is_staff:
            return Response({
                'error': 'Only administrators can update shifts'
            }, status=status.HTTP_403_FORBIDDEN)
        
        partial = request.method == 'PATCH'
        serializer = ShiftSerializer(shift, data=request.data, partial=partial)
        
        if serializer.is_valid():
            shift = serializer.save()
            return Response({
                'message': 'Shift updated successfully',
                'shift': ShiftSerializer(shift).data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        if not request.user.is_staff:
            return Response({
                'error': 'Only administrators can delete shifts'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if shift is used in any schedule day
        if shift.scheduleday_set.exists():
            return Response({
                'error': 'Cannot delete shift that is assigned to schedule days'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        shift.delete()
        return Response({
            'message': 'Shift deleted successfully'
        }, status=status.HTTP_200_OK)


# ==================== SCHEDULE DAY MANAGEMENT VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def schedule_day_list(request):
    """
    List all schedule days
    """
    days = ScheduleDay.objects.select_related('shift').prefetch_related(
        'user_schedules__user'
    ).order_by('day_name')
    
    # Apply filters
    day_name = request.query_params.get('day')
    has_shift = request.query_params.get('has_shift')
    
    if day_name:
        days = days.filter(day_name=day_name)
    
    if has_shift and has_shift.lower() in ['true', 'false']:
        if has_shift.lower() == 'true':
            days = days.filter(shift__isnull=False)
        else:
            days = days.filter(shift__isnull=True)
    
    serializer = ScheduleDaySerializer(days, many=True, context={'request': request})
    
    return Response({
        'count': days.count(),
        'days': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def create_schedule_day(request):
    """
    Create a new schedule day (admin only)
    """
    serializer = ScheduleDayCreateSerializer(data=request.data)
    
    if serializer.is_valid():
        day = serializer.save()
        
        return Response({
            'message': 'Schedule day created successfully',
            'day': ScheduleDaySerializer(day, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def schedule_day_detail(request, day_id):
    """
    Retrieve, update, or delete a schedule day
    """
    day = get_object_or_404(
        ScheduleDay.objects.select_related('shift').prefetch_related('user_schedules__user'),
        id=day_id
    )
    
    if request.method == 'GET':
        serializer = ScheduleDaySerializer(day, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method in ['PUT', 'PATCH']:
        if not request.user.is_staff:
            return Response({
                'error': 'Only administrators can update schedule days'
            }, status=status.HTTP_403_FORBIDDEN)
        
        partial = request.method == 'PATCH'
        serializer = ScheduleDaySerializer(day, data=request.data, partial=partial, context={'request': request})
        
        if serializer.is_valid():
            day = serializer.save()
            return Response({
                'message': 'Schedule day updated successfully',
                'day': ScheduleDaySerializer(day, context={'request': request}).data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        if not request.user.is_staff:
            return Response({
                'error': 'Only administrators can delete schedule days'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if day has any user assignments
        if day.user_schedules.exists():
            return Response({
                'error': 'Cannot delete schedule day that has user assignments'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        day.delete()
        return Response({
            'message': 'Schedule day deleted successfully'
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def assign_shift_to_day(request):
    """
    Assign or remove shift from a schedule day
    """
    serializer = ShiftAssignmentSerializer(data=request.data)
    
    if serializer.is_valid():
        schedule_day = serializer.validated_data['schedule_day']
        shift = serializer.validated_data.get('shift')
        
        schedule_day.shift = shift
        schedule_day.save()
        
        action = 'assigned' if shift else 'removed'
        
        return Response({
            'message': f'Shift {action} successfully',
            'day': ScheduleDaySerializer(schedule_day, context={'request': request}).data
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================== USER SCHEDULE ASSIGNMENT VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_schedule_list(request):
    """
    List all user schedule assignments
    """
    user_schedules = UserSchedule.objects.select_related(
        'user', 'schedule_day', 'schedule_day__shift'
    ).order_by('schedule_day__day_name', 'user__first_name')
    
    # Apply filters
    user_id = request.query_params.get('user_id')
    day_id = request.query_params.get('day_id')
    
    if user_id:
        user_schedules = user_schedules.filter(user_id=user_id)
    
    if day_id:
        user_schedules = user_schedules.filter(schedule_day_id=day_id)
    
    serializer = UserScheduleSerializer(user_schedules, many=True, context={'request': request})
    
    return Response({
        'count': user_schedules.count(),
        'assignments': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def assign_user_to_schedule(request):
    """
    Assign a user to a schedule day
    """
    serializer = UserScheduleCreateSerializer(data=request.data)
    
    if serializer.is_valid():
        user_schedule = serializer.save()
        
        return Response({
            'message': 'User assigned to schedule successfully',
            'assignment': UserScheduleSerializer(user_schedule, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def bulk_assign_users(request):
    """
    Bulk assign multiple users to a schedule day
    """
    serializer = UserScheduleBulkSerializer(data=request.data)
    
    if serializer.is_valid():
        schedule_day = serializer.validated_data['schedule_day']
        users = serializer.validated_data['users']
        
        created_count = 0
        assignments = []
        
        for user in users:
            # Check if assignment already exists
            if not UserSchedule.objects.filter(user=user, schedule_day=schedule_day).exists():
                user_schedule = UserSchedule.objects.create(
                    user=user,
                    schedule_day=schedule_day
                )
                created_count += 1
                assignments.append(UserScheduleSerializer(user_schedule, context={'request': request}).data)
        
        return Response({
            'message': f'{created_count} users assigned to schedule',
            'created_count': created_count,
            'assignments': assignments
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_user_from_schedule(request, assignment_id):
    """
    Remove a user from a schedule day
    """
    user_schedule = get_object_or_404(UserSchedule, id=assignment_id)
    
    # Check permissions - admin or the user themselves
    if not request.user.is_staff and request.user != user_schedule.user:
        return Response({
            'error': 'You can only remove your own schedule assignments'
        }, status=status.HTTP_403_FORBIDDEN)
    
    user_schedule.delete()
    
    return Response({
        'message': 'User removed from schedule successfully'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def bulk_remove_users_from_schedule(request):
    """
    Bulk remove users from a schedule day
    """
    schedule_day_id = request.data.get('schedule_day_id')
    user_ids = request.data.get('user_ids', [])
    
    if not schedule_day_id:
        return Response({
            'error': 'schedule_day_id is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not isinstance(user_ids, list):
        return Response({
            'error': 'user_ids must be a list'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        schedule_day = ScheduleDay.objects.get(id=schedule_day_id)
    except ScheduleDay.DoesNotExist:
        return Response({
            'error': 'Schedule day not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    deleted_count = UserSchedule.objects.filter(
        schedule_day=schedule_day,
        user_id__in=user_ids
    ).delete()[0]
    
    return Response({
        'message': f'{deleted_count} users removed from schedule',
        'deleted_count': deleted_count
    }, status=status.HTTP_200_OK)


# ==================== USER SCHEDULE VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_schedule(request):
    """
    Get current user's schedule
    """
    user = request.user
    
    # Get all schedule days with user's assignments
    days = ScheduleDay.objects.all().order_by('day_name')
    
    weekly_schedule = []
    for day in days:
        user_assignment = day.user_schedules.filter(user=user).first()
        weekly_schedule.append({
            'day': day.day_name,
            'has_assignment': user_assignment is not None,
            'schedule_day': ScheduleDaySerializer(day, context={'request': request}).data if user_assignment else None
        })
    
    return Response({
        'user_id': str(user.id),
        'user_name': user.get_full_name(),
        'weekly_schedule': weekly_schedule
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_weekly_schedule(request, user_id=None):
    """
    Get a user's complete weekly schedule
    """
    if user_id:
        user = get_object_or_404(User, id=user_id)
    else:
        user = request.user
    
    # Check permissions - users can see their own schedule, admins can see anyone's
    if user != request.user and not request.user.is_staff:
        return Response({
            'error': 'You can only view your own schedule'
        }, status=status.HTTP_403_FORBIDDEN)
    
    serializer = UserWeeklyScheduleSerializer(user, context={'request': request})
    
    return Response({
        'user_id': str(user.id),
        'user_name': user.get_full_name(),
        'weekly_schedule': serializer.data['weekly_schedule']
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def today_schedule(request):
    """
    Get today's schedule for current user
    """
    user = request.user
    today = timezone.now().strftime('%A')  # Get day name
    
    try:
        schedule_day = ScheduleDay.objects.get(day_name=today)
        user_assignment = schedule_day.user_schedules.filter(user=user).first()
        
        if user_assignment:
            return Response({
                'today': today,
                'has_shift': True,
                'schedule': ScheduleDaySerializer(schedule_day, context={'request': request}).data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'today': today,
                'has_shift': False,
                'message': 'No shift scheduled for today'
            }, status=status.HTTP_200_OK)
            
    except ScheduleDay.DoesNotExist:
        return Response({
            'today': today,
            'has_shift': False,
            'message': 'No schedule defined for today'
        }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def upcoming_shifts(request):
    """
    Get upcoming shifts for current user
    """
    user = request.user
    
    # Get all days with user assignments
    user_assignments = UserSchedule.objects.filter(
        user=user
    ).select_related('schedule_day', 'schedule_day__shift')
    
    # Map day names to numbers for sorting
    day_order = {
        'Monday': 0,
        'Tuesday': 1,
        'Wednesday': 2,
        'Thursday': 3,
        'Friday': 4,
        'Saturday': 5,
        'Sunday': 6
    }
    
    # Sort by day order
    sorted_assignments = sorted(
        user_assignments,
        key=lambda x: day_order.get(x.schedule_day.day_name, 7)
    )
    
    # Get current day
    today = timezone.now().strftime('%A')
    today_order = day_order.get(today, 7)
    
    # Filter upcoming shifts (including today)
    upcoming = []
    for assignment in sorted_assignments:
        day_order_num = day_order.get(assignment.schedule_day.day_name, 7)
        if day_order_num >= today_order and assignment.schedule_day.shift:
            upcoming.append({
                'day': assignment.schedule_day.day_name,
                'shift': ShiftSerializer(assignment.schedule_day.shift).data,
                'schedule_day_id': str(assignment.schedule_day.id)
            })
    
    return Response({
        'user_id': str(user.id),
        'user_name': user.get_full_name(),
        'today': today,
        'upcoming_shifts': upcoming,
        'count': len(upcoming)
    }, status=status.HTTP_200_OK)


# ==================== DEPARTMENT & TEAM SCHEDULE VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def department_schedule(request):
    """
    Get schedule for users in the same department
    """
    user = request.user
    
    if not user.department:
        return Response({
            'error': 'You are not assigned to any department'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Get all users in the same department
    department_users = User.objects.filter(department=user.department, is_active=True)
    
    # Get all schedule days
    days = ScheduleDay.objects.all().order_by('day_name')
    
    department_schedule = []
    for day in days:
        day_assignments = day.user_schedules.filter(user__in=department_users).select_related('user')
        
        if day_assignments.exists():
            users_on_shift = [assignment.user for assignment in day_assignments]
            department_schedule.append({
                'day': day.day_name,
                'has_shift': day.shift is not None,
                'shift': ShiftSerializer(day.shift).data if day.shift else None,
                'assigned_users': [
                    {
                        'id': str(user.id),
                        'name': user.get_full_name(),
                        'email': user.email
                    } for user in users_on_shift
                ],
                'assigned_count': len(users_on_shift)
            })
    
    return Response({
        'department': user.department,
        'schedule': department_schedule
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def day_schedule_detail(request, day_id):
    """
    Get detailed schedule for a specific day
    """
    day = get_object_or_404(
        ScheduleDay.objects.select_related('shift').prefetch_related('user_schedules__user'),
        id=day_id
    )
    
    serializer = DayScheduleSerializer(day, context={'request': request})
    
    return Response({
        'day': day.day_name,
        'schedule': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def available_users_for_day(request, day_id):
    """
    Get users not assigned to a specific day
    """
    day = get_object_or_404(ScheduleDay, id=day_id)
    
    # Get users already assigned to this day
    assigned_user_ids = day.user_schedules.values_list('user_id', flat=True)
    
    # Get available users (not assigned and active)
    available_users = User.objects.filter(
        is_active=True
    ).exclude(
        id__in=assigned_user_ids
    ).order_by('first_name', 'last_name')
    
    # Apply department filter if provided
    department = request.query_params.get('department')
    if department:
        available_users = available_users.filter(department=department)
    
    from users.serializers import UserMinimalSerializer
    serializer = UserMinimalSerializer(available_users, many=True, context={'request': request})
    
    return Response({
        'day': day.day_name,
        'available_users': serializer.data,
        'count': available_users.count()
    }, status=status.HTTP_200_OK)


# ==================== SCHEDULE CONFLICT CHECKING ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_schedule_conflicts(request):
    """
    Check for schedule conflicts for multiple users
    """
    user_ids = request.data.get('user_ids', [])
    schedule_day_ids = request.data.get('schedule_day_ids', [])
    
    if not isinstance(user_ids, list) or not isinstance(schedule_day_ids, list):
        return Response({
            'error': 'user_ids and schedule_day_ids must be lists'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not user_ids or not schedule_day_ids:
        return Response({
            'error': 'Both user_ids and schedule_day_ids are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    conflicts = []
    
    for user_id in user_ids:
        for day_id in schedule_day_ids:
            # Check if assignment already exists
            if UserSchedule.objects.filter(user_id=user_id, schedule_day_id=day_id).exists():
                try:
                    user = User.objects.get(id=user_id)
                    day = ScheduleDay.objects.get(id=day_id)
                    
                    conflicts.append({
                        'user_id': user_id,
                        'user_name': user.get_full_name(),
                        'day_id': day_id,
                        'day_name': day.day_name,
                        'conflict': 'User already assigned to this day'
                    })
                except (User.DoesNotExist, ScheduleDay.DoesNotExist):
                    pass
    
    return Response({
        'has_conflicts': len(conflicts) > 0,
        'conflicts': conflicts,
        'conflict_count': len(conflicts)
    }, status=status.HTTP_200_OK)


# ==================== SCHEDULE GENERATION & TEMPLATES ====================
@api_view(['POST'])
@permission_classes([IsAdminUser])
def generate_weekly_schedule(request):
    """
    Generate a weekly schedule based on a template
    """
    template_name = request.data.get('template_name', 'Default Weekly Schedule')
    
    # Days of the week
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    created_days = []
    
    for day_name in days:
        # Check if day already exists
        if not ScheduleDay.objects.filter(day_name=day_name).exists():
            day = ScheduleDay.objects.create(day_name=day_name)
            created_days.append({
                'day': day.day_name,
                'id': str(day.id)
            })
    
    return Response({
        'message': f'Weekly schedule template "{template_name}" created',
        'created_days': created_days,
        'total_created': len(created_days)
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def copy_schedule_week(request):
    """
    Copy schedule assignments from one week to another
    """
    source_day_ids = request.data.get('source_day_ids', [])
    target_day_ids = request.data.get('target_day_ids', [])
    
    if not isinstance(source_day_ids, list) or not isinstance(target_day_ids, list):
        return Response({
            'error': 'source_day_ids and target_day_ids must be lists'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if len(source_day_ids) != len(target_day_ids):
        return Response({
            'error': 'source_day_ids and target_day_ids must have the same length'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    copied_count = 0
    
    for source_id, target_id in zip(source_day_ids, target_day_ids):
        try:
            source_day = ScheduleDay.objects.get(id=source_id)
            target_day = ScheduleDay.objects.get(id=target_id)
            
            # Get all assignments from source day
            source_assignments = UserSchedule.objects.filter(schedule_day=source_day)
            
            # Copy assignments to target day
            for assignment in source_assignments:
                # Check if assignment already exists in target day
                if not UserSchedule.objects.filter(
                    user=assignment.user,
                    schedule_day=target_day
                ).exists():
                    UserSchedule.objects.create(
                        user=assignment.user,
                        schedule_day=target_day
                    )
                    copied_count += 1
            
            # Copy shift assignment if exists
            if source_day.shift and not target_day.shift:
                target_day.shift = source_day.shift
                target_day.save()
                
        except ScheduleDay.DoesNotExist:
            continue
    
    return Response({
        'message': f'{copied_count} schedule assignments copied',
        'copied_count': copied_count
    }, status=status.HTTP_200_OK)


# ==================== STATISTICS & REPORTS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def schedule_statistics(request):
    """
    Get schedule statistics
    """
    if not request.user.is_staff:
        return Response({
            'error': 'Only administrators can view schedule statistics'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Total counts
    total_shifts = Shift.objects.count()
    total_schedule_days = ScheduleDay.objects.count()
    total_assignments = UserSchedule.objects.count()
    
    # Users with assignments
    users_with_assignments = User.objects.filter(
        schedules__isnull=False
    ).distinct().count()
    
    total_users = User.objects.filter(is_active=True).count()
    
    # Schedule days by shift assignment
    days_with_shift = ScheduleDay.objects.filter(shift__isnull=False).count()
    days_without_shift = ScheduleDay.objects.filter(shift__isnull=True).count()
    
    # Most assigned users
    from django.db.models import Count
    most_assigned_users = User.objects.filter(
        schedules__isnull=False
    ).annotate(
        assignment_count=Count('schedules')
    ).order_by('-assignment_count')[:10]
    
    most_assigned_data = []
    for user in most_assigned_users:
        most_assigned_data.append({
            'id': str(user.id),
            'name': user.get_full_name(),
            'department': user.department,
            'assignment_count': user.assignment_count
        })
    
    # Days with most assignments
    days_most_assignments = ScheduleDay.objects.annotate(
        assignment_count=Count('user_schedules')
    ).order_by('-assignment_count')[:5]
    
    days_most_data = []
    for day in days_most_assignments:
        days_most_data.append({
            'id': str(day.id),
            'day': day.day_name,
            'has_shift': day.shift is not None,
            'assignment_count': day.assignment_count
        })
    
    return Response({
        'total_shifts': total_shifts,
        'total_schedule_days': total_schedule_days,
        'total_assignments': total_assignments,
        'users_with_assignments': users_with_assignments,
        'total_active_users': total_users,
        'coverage_percentage': round((users_with_assignments / total_users * 100), 2) if total_users > 0 else 0,
        'days_with_shift': days_with_shift,
        'days_without_shift': days_without_shift,
        'most_assigned_users': most_assigned_data,
        'days_most_assignments': days_most_data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_schedule_statistics(request, user_id=None):
    """
    Get schedule statistics for a specific user
    """
    if user_id:
        user = get_object_or_404(User, id=user_id)
    else:
        user = request.user
    
    # Check permissions
    if user != request.user and not request.user.is_staff:
        return Response({
            'error': 'You can only view your own schedule statistics'
        }, status=status.HTTP_403_FORBIDDEN)
    
    total_assignments = user.schedules.count()
    
    # Days with assignments
    assigned_days = user.schedules.values_list('schedule_day__day_name', flat=True)
    
    # Calculate weekly hours
    weekly_hours = 0
    for assignment in user.schedules.select_related('schedule_day__shift'):
        if assignment.schedule_day.shift:
            start = assignment.schedule_day.shift.start_time
            end = assignment.schedule_day.shift.end_time
            
            # Calculate duration (handle overnight shifts)
            if end < start:
                # Overnight shift - calculate hours past midnight
                duration = ((24 * 3600) - (start.hour * 3600 + start.minute * 60 + start.second) +
                           (end.hour * 3600 + end.minute * 60 + end.second)) / 3600
            else:
                duration = (end.hour * 3600 + end.minute * 60 + end.second -
                           (start.hour * 3600 + start.minute * 60 + start.second)) / 3600
            
            weekly_hours += duration
    
    return Response({
        'user_id': str(user.id),
        'user_name': user.get_full_name(),
        'total_assignments': total_assignments,
        'assigned_days': list(assigned_days),
        'weekly_hours': round(weekly_hours, 2),
        'average_daily_hours': round(weekly_hours / max(len(assigned_days), 1), 2)
    }, status=status.HTTP_200_OK)


# ==================== HEALTH CHECK ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def schedules_health_check(request):
    """
    Health check for schedules app
    """
    from django.db import connection
    
    try:
        # Check database
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM schedules_shift")
            shift_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM schedules_scheduleday")
            day_count = cursor.fetchone()[0]
        
        return Response({
            'status': 'healthy',
            'database': 'connected',
            'total_shifts': shift_count,
            'total_schedule_days': day_count,
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)