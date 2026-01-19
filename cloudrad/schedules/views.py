
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
from django.db import transaction
import json

from .models import Shift, ScheduleEvent, ScheduleTemplate, TemplateDay
from .serializers import (
    ShiftSerializer, ScheduleEventSerializer, ScheduleEventCreateSerializer,
    ScheduleEventBulkCreateSerializer, ScheduleTemplateSerializer,
    TemplateDaySerializer, UserScheduleViewSerializer
)
from users.models import User
from patients.models import Patient
import logging

logger = logging.getLogger(__name__)

INVALID_DATE_FORMAT_ERROR = 'Invalid date format. Use YYYY-MM-DD'


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
            Q(name__icontains=search) |
            Q(description__icontains=search)
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
    serializer = ShiftSerializer(data=request.data)
    
    if serializer.is_valid():
        serializer.save()
        
        return Response({
            'message': 'Shift created successfully',
            'shift': serializer.data
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
            serializer.save()
            return Response({
                'message': 'Shift updated successfully',
                'shift': serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        if not request.user.is_staff:
            return Response({
                'error': 'Only administrators can delete shifts'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if shift is used in any schedule events
        if ScheduleEvent.objects.filter(shift=shift).exists():
            return Response({
                'error': 'Cannot delete shift that is used in schedule events'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        shift.delete()
        return Response({
            'message': 'Shift deleted successfully'
        }, status=status.HTTP_200_OK)


# ==================== SCHEDULE EVENT VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def schedule_event_list(request):
    """
    List all schedule events with filtering
    """
    # Start with base queryset
    if request.user.is_staff:
        events = ScheduleEvent.objects.all()
    else:
        events = ScheduleEvent.objects.filter(user=request.user)
    
    events = events.select_related('user', 'shift', 'patient', 'created_by')
    
    # Apply filters
    user_id = request.query_params.get('user_id')
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    event_type = request.query_params.get('event_type')
    department = request.query_params.get('department')
    status_filter = request.query_params.get('status')
    
    if user_id and request.user.is_staff:
        events = events.filter(user_id=user_id)
    
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            events = events.filter(end_date__gte=start_date)
        except ValueError:
            return Response({
                'error': INVALID_DATE_FORMAT_ERROR
            }, status=status.HTTP_400_BAD_REQUEST)
    
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            events = events.filter(start_date__lte=end_date)
        except ValueError:
            return Response({
                'error': INVALID_DATE_FORMAT_ERROR
            }, status=status.HTTP_400_BAD_REQUEST)
    
    if event_type:
        events = events.filter(event_type=event_type)
    
    if department:
        events = events.filter(department=department)
    
    if status_filter:
        events = events.filter(status=status_filter)
    
    # Pagination
    page = request.query_params.get('page', 1)
    page_size = request.query_params.get('page_size', 20)
    
    try:
        page = int(page)
        page_size = int(page_size)
    except ValueError:
        return Response({
            'error': 'Invalid page or page_size parameter'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    paginator = Paginator(events.order_by('start_date', 'start_time'), page_size)
    try:
        paginated_events = paginator.page(page)
    except:
        return Response({
            'error': 'Invalid page number'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    serializer = ScheduleEventSerializer(paginated_events, many=True, context={'request': request})
    
    return Response({
        'count': events.count(),
        'page': page,
        'page_size': page_size,
        'total_pages': paginator.num_pages,
        'results': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_schedule_event(request):
    """
    Create a new schedule event
    """
    # Users can only create events for themselves unless they're admin
    data = request.data.copy()
    if not request.user.is_staff:
        data['user'] = str(request.user.id)
    
    serializer = ScheduleEventCreateSerializer(data=data, context={'request': request})
    
    if serializer.is_valid():
        event = serializer.save(created_by=request.user)
        
        return Response({
            'message': 'Schedule event created successfully',
            'event': ScheduleEventSerializer(event, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def schedule_event_detail(request, event_id):
    """
    Retrieve, update, or delete a schedule event
    """
    event = get_object_or_404(
        ScheduleEvent.objects.select_related('user', 'shift', 'patient'),
        id=event_id
    )
    
    # Check permissions
    if event.user != request.user and not request.user.is_staff:
        return Response({
            'error': 'You do not have permission to access this event'
        }, status=status.HTTP_403_FORBIDDEN)
    
    if request.method == 'GET':
        serializer = ScheduleEventSerializer(event, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method in ['PUT', 'PATCH']:
        # Users can only update their own events unless they're admin
        if event.user != request.user and not request.user.is_staff:
            return Response({
                'error': 'You can only update your own schedule events'
            }, status=status.HTTP_403_FORBIDDEN)
        
        partial = request.method == 'PATCH'
        serializer = ScheduleEventSerializer(event, data=request.data, partial=partial, context={'request': request})
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Schedule event updated successfully',
                'event': serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        # Users can only delete their own events unless they're admin
        if event.user != request.user and not request.user.is_staff:
            return Response({
                'error': 'You can only delete your own schedule events'
            }, status=status.HTTP_403_FORBIDDEN)
        
        event.delete()
        return Response({
            'message': 'Schedule event deleted successfully'
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def bulk_create_schedule_events(request):
    """
    Bulk create schedule events for multiple users (admin only)
    """
    serializer = ScheduleEventBulkCreateSerializer(data=request.data)
    
    if serializer.is_valid():
        data = serializer.validated_data
        user_ids = data['user_ids']
        start_date = data['start_date']
        end_date = data['end_date']
        event_type = data.get('event_type', 'shift')
        
        created_events = []
        skipped_users = []
        
        with transaction.atomic():
            for user_id in user_ids:
                user = get_object_or_404(User, id=user_id)
                
                # Check for conflicts
                conflicts = ScheduleEvent.objects.filter(
                    user=user,
                    status__in=['scheduled', 'confirmed'],
                    start_date__lte=end_date,
                    end_date__gte=start_date
                )
                
                if conflicts.exists():
                    skipped_users.append({
                        'user_id': str(user.id),
                        'user_name': user.get_full_name(),
                        'reason': 'Schedule conflict'
                    })
                    continue
                
                # Create the event
                event = ScheduleEvent.objects.create(
                    user=user,
                    title=f"{Shift.name} - {user.get_full_name()}",
                    event_type=event_type,
                    start_date=start_date,
                    end_date=end_date,
                    start_time=Shift.start_time,
                    end_time=Shift.end_time,
                    shift=Shift,
                    status='scheduled',
                    department=user.department if hasattr(user, 'department') else '',
                    created_by=request.user
                )
                created_events.append(ScheduleEventSerializer(event, context={'request': request}).data)
        
        return Response({
            'message': f'{len(created_events)} events created successfully',
            'created_count': len(created_events),
            'skipped_count': len(skipped_users),
            'created_events': created_events,
            'skipped_users': skipped_users
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================== USER SCHEDULE VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_schedule(request):
    """
    Get current user's schedule
    """
    user = request.user
    
    # Get date range (default: next 30 days)
    start_date = request.query_params.get('start_date', timezone.now().date().isoformat())
    end_date = request.query_params.get('end_date', 
                                       (timezone.now() + timedelta(days=30)).date().isoformat())
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        return Response({
            'error': INVALID_DATE_FORMAT_ERROR
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Get events
    events = ScheduleEvent.objects.filter(
        user=user,
        start_date__lte=end_date,
        end_date__gte=start_date,
        status__in=['scheduled', 'confirmed']
    ).select_related('shift', 'patient').order_by('start_date', 'start_time')
    
    serializer = ScheduleEventSerializer(events, many=True, context={'request': request})
    
    # Get today's events
    today = timezone.now().date()
    today_events = events.filter(start_date__lte=today, end_date__gte=today)
    
    # Get upcoming events
    upcoming_events = events.filter(start_date__gt=today)
    
    # Calculate total hours
    total_hours = sum(event.duration_hours for event in events)
    
    return Response({
        'user': {
            'id': str(user.id),
            'name': user.get_full_name(),
            'email': user.email
        },
        'date_range': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        },
        'today': {
            'date': today.isoformat(),
            'events': ScheduleEventSerializer(today_events, many=True, context={'request': request}).data,
            'count': today_events.count()
        },
        'upcoming': {
            'events': ScheduleEventSerializer(upcoming_events, many=True, context={'request': request}).data,
            'count': upcoming_events.count()
        },
        'all_events': serializer.data,
        'total_events': events.count(),
        'total_hours': round(total_hours, 2)
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_upcoming_shifts(request):
    """
    Get current user's upcoming shifts
    """
    user = request.user
    today = timezone.now().date()
    
    shifts = ScheduleEvent.objects.filter(
        user=user,
        end_date__gte=today,
        event_type='shift',
        status__in=['scheduled', 'confirmed']
    ).select_related('shift').order_by('start_date', 'start_time')
    
    # Limit to 20 shifts
    shifts = shifts[:20]
    
    serializer = ScheduleEventSerializer(shifts, many=True, context={'request': request})
    
    # Get next shift
    next_shift = shifts.first() if shifts.exists() else None
    
    return Response({
        'user_id': str(user.id),
        'user_name': user.get_full_name(),
        'shifts': serializer.data,
        'count': shifts.count(),
        'next_shift': ScheduleEventSerializer(next_shift).data if next_shift else None
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_schedule_view(request, user_id):
    """
    Get a user's schedule (admin can view any user, users can only view their own)
    """
    if user_id != str(request.user.id) and not request.user.is_staff:
        return Response({
            'error': 'You can only view your own schedule'
        }, status=status.HTTP_403_FORBIDDEN)
    
    user = get_object_or_404(User, id=user_id)
    
    # Get date range from query params or default to next 30 days
    start_date = request.query_params.get('start_date', timezone.now().date().isoformat())
    end_date = request.query_params.get('end_date', 
                                       (timezone.now() + timedelta(days=30)).date().isoformat())
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        return Response({
            'error': INVALID_DATE_FORMAT_ERROR
        }, status=status.HTTP_400_BAD_REQUEST)
    
    events = ScheduleEvent.objects.filter(
        user=user,
        start_date__lte=end_date,
        end_date__gte=start_date,
        status__in=['scheduled', 'confirmed']
    ).select_related('shift', 'patient').order_by('start_date', 'start_time')
    
    serializer = ScheduleEventSerializer(events, many=True, context={'request': request})
    
    # Calculate statistics
    total_hours = sum(event.duration_hours for event in events)
    shift_events = events.filter(event_type='shift')
    shift_hours = sum(event.duration_hours for event in shift_events)
    
    return Response({
        'user': {
            'id': str(user.id),
            'name': user.get_full_name(),
            'email': user.email,
            'department': user.department if hasattr(user, 'department') else ''
        },
        'date_range': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        },
        'events': serializer.data,
        'total_events': events.count(),
        'shift_events': shift_events.count(),
        'total_hours': round(total_hours, 2),
        'shift_hours': round(shift_hours, 2)
    }, status=status.HTTP_200_OK)


# ==================== CALENDAR VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def calendar_view(request):
    """
    Calendar view with different view types (month, week, day)
    """
    view_type = request.query_params.get('view', 'month')  # month, week, day
    date_str = request.query_params.get('date', timezone.now().date().isoformat())
    
    try:
        current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        current_date = timezone.now().date()
    
    # Determine date range based on view type
    if view_type == 'month':
        start_date = current_date.replace(day=1)
        if start_date.month == 12:
            next_month = start_date.replace(year=start_date.year + 1, month=1)
        else:
            next_month = start_date.replace(month=start_date.month + 1)
        end_date = next_month - timedelta(days=1)
    elif view_type == 'week':
        start_date = current_date - timedelta(days=current_date.weekday())
        end_date = start_date + timedelta(days=6)
    else:  # day
        start_date = current_date
        end_date = current_date
    
    # Get events for current user
    events = ScheduleEvent.objects.filter(
        user=request.user,
        start_date__lte=end_date,
        end_date__gte=start_date,
        status__in=['scheduled', 'confirmed']
    ).select_related('shift').order_by('start_date', 'start_time')
    
    serializer = ScheduleEventSerializer(events, many=True, context={'request': request})
    
    # Group events by date for easier frontend rendering
    events_by_date = {}
    for event in events:
        date_key = event.start_date.isoformat()
        if date_key not in events_by_date:
            events_by_date[date_key] = []
        events_by_date[date_key].append(ScheduleEventSerializer(event, context={'request': request}).data)
    
    return Response({
        'view_type': view_type,
        'current_date': current_date.isoformat(),
        'date_range': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        },
        'events': serializer.data,
        'events_by_date': events_by_date
    }, status=status.HTTP_200_OK)


# ==================== DEPARTMENT SCHEDULE VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def department_schedule(request, department):
    """
    Get schedule for a specific department
    """
    # Check if user has access to this department
    user = request.user
    if not user.is_staff and (not hasattr(user, 'department') or user.department != department):
        return Response({
            'error': 'You do not have access to this department schedule'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Get date range
    start_date = request.query_params.get('start_date', timezone.now().date().isoformat())
    end_date = request.query_params.get('end_date', 
                                       (timezone.now() + timedelta(days=7)).date().isoformat())
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        return Response({
            'error': INVALID_DATE_FORMAT_ERROR
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Get users in department
    users = User.objects.filter(
        department=department,
        is_active=True
    )
    
    # Get events for these users
    events = ScheduleEvent.objects.filter(
        user__in=users,
        start_date__lte=end_date,
        end_date__gte=start_date,
        status__in=['scheduled', 'confirmed']
    ).select_related('user', 'shift').order_by('start_date', 'start_time')
    
    # Group by date
    schedule_by_date = {}
    for event in events:
        date_str = event.start_date.isoformat()
        if date_str not in schedule_by_date:
            schedule_by_date[date_str] = {
                'date': event.start_date.isoformat(),
                'events': []
            }
        
        schedule_by_date[date_str]['events'].append(
            ScheduleEventSerializer(event, context={'request': request}).data
        )
    
    # Convert to list and sort by date
    schedule_list = sorted(schedule_by_date.values(), key=lambda x: x['date'])
    
    return Response({
        'department': department,
        'date_range': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        },
        'total_users': users.count(),
        'schedule': schedule_list
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def department_today(request, department):
    """
    Get today's schedule for a department
    """
    # Check if user has access to this department
    user = request.user
    if not user.is_staff and (not hasattr(user, 'department') or user.department != department):
        return Response({
            'error': 'You do not have access to this department schedule'
        }, status=status.HTTP_403_FORBIDDEN)
    
    today = timezone.now().date()
    
    # Get users in department
    users = User.objects.filter(
        department=department,
        is_active=True
    )
    
    # Get today's events
    events = ScheduleEvent.objects.filter(
        user__in=users,
        start_date__lte=today,
        end_date__gte=today,
        status__in=['scheduled', 'confirmed']
    ).select_related('user', 'shift').order_by('start_time')
    
    serializer = ScheduleEventSerializer(events, many=True, context={'request': request})
    
    # Group by event type
    events_by_type = {}
    for event in events:
        event_type = event.event_type
        if event_type not in events_by_type:
            events_by_type[event_type] = []
        events_by_type[event_type].append(
            ScheduleEventSerializer(event, context={'request': request}).data
        )
    
    return Response({
        'department': department,
        'date': today.isoformat(),
        'total_events': events.count(),
        'total_users': users.count(),
        'users_on_duty': events.values('user').distinct().count(),
        'events': serializer.data,
        'events_by_type': events_by_type
    }, status=status.HTTP_200_OK)


# ==================== SCHEDULE TEMPLATE VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def schedule_template_list(request):
    """
    List all schedule templates
    """
    templates = ScheduleTemplate.objects.prefetch_related('days__shift')
    
    # Apply filters
    department = request.query_params.get('department')
    is_active = request.query_params.get('is_active')
    
    if department:
        templates = templates.filter(department=department)
    
    if is_active and is_active.lower() in ['true', 'false']:
        templates = templates.filter(is_active=is_active.lower() == 'true')
    
    serializer = ScheduleTemplateSerializer(templates, many=True, context={'request': request})
    
    return Response({
        'count': templates.count(),
        'templates': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def create_schedule_template(request):
    """
    Create a new schedule template (admin only)
    """
    serializer = ScheduleTemplateSerializer(data=request.data, context={'request': request})
    
    if serializer.is_valid():
        serializer.save()
        
        return Response({
            'message': 'Schedule template created successfully',
            'template': serializer.data
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def schedule_template_detail(request, template_id):
    """
    Retrieve, update, or delete a schedule template
    """
    template = get_object_or_404(
        ScheduleTemplate.objects.prefetch_related('days__shift'),
        id=template_id
    )
    
    if request.method == 'GET':
        serializer = ScheduleTemplateSerializer(template, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method in ['PUT', 'PATCH']:
        if not request.user.is_staff:
            return Response({
                'error': 'Only administrators can update schedule templates'
            }, status=status.HTTP_403_FORBIDDEN)
        
        partial = request.method == 'PATCH'
        serializer = ScheduleTemplateSerializer(template, data=request.data, partial=partial, context={'request': request})
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Schedule template updated successfully',
                'template': serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        if not request.user.is_staff:
            return Response({
                'error': 'Only administrators can delete schedule templates'
            }, status=status.HTTP_403_FORBIDDEN)
        
        template.delete()
        return Response({
            'message': 'Schedule template deleted successfully'
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def apply_schedule_template(request, template_id):
    """
    Apply a schedule template to create actual schedule events
    """
    start_date, user_ids, error_response = validate_apply_template_request(request)
    if error_response:
        return error_response

    created_events, skipped_users = process_template_application(template_id, start_date, user_ids, request.user)

    return Response({
        'message': f'Template applied. {len(created_events)} events created.',
        'created_count': len(created_events),
        'skipped_count': len(skipped_users),
        'created_events': created_events,
        'skipped_users': skipped_users
    }, status=status.HTTP_200_OK)

def validate_apply_template_request(request):
    start_date = request.data.get('start_date')
    user_ids = request.data.get('user_ids', [])

    if not start_date:
        return None, None, Response({'error': 'start_date is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    except ValueError:
        return None, None, Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

    if not isinstance(user_ids, list) or len(user_ids) == 0:
        return None, None, Response({'error': 'user_ids must be a non-empty list'}, status=status.HTTP_400_BAD_REQUEST)

    return start_date, user_ids, None

def process_template_application(template_id, start_date, user_ids, created_by):
    template = get_object_or_404(ScheduleTemplate, id=template_id)
    created_events = []
    skipped_users = []

    with transaction.atomic():
        for user_id in user_ids:
            user = get_object_or_404(User, id=user_id)
            process_user_template_days(template, user, start_date, created_by, created_events, skipped_users)

    return created_events, skipped_users

def process_user_template_days(template, user, start_date, created_by, created_events, skipped_users):
    for template_day in template.days.all():
        if template_day.shift:
            event_date = calculate_event_date(template_day, start_date)
            if check_schedule_conflicts(user, event_date):
                skipped_users.append({
                    'user_id': str(user.id),
                    'user_name': user.get_full_name(),
                    'date': event_date.isoformat(),
                    'reason': 'Schedule conflict'
                })
                continue

            create_schedule_event(template_day, user, event_date, created_by, created_events)

def calculate_event_date(template_day, start_date):
    days_to_add = (template_day.day_of_week - start_date.weekday()) % 7
    return start_date + timedelta(days=days_to_add)

def check_schedule_conflicts(user, event_date):
    return ScheduleEvent.objects.filter(
        user=user,
        status__in=['scheduled', 'confirmed'],
        start_date__lte=event_date,
        end_date__gte=event_date
    ).exists()

def create_schedule_event(template_day, user, event_date, created_by, created_events):
    event = ScheduleEvent.objects.create(
        user=user,
        title=f"{template_day.shift.name} - {user.get_full_name()}",
        event_type='shift',
        start_date=event_date,
        end_date=event_date,
        start_time=template_day.shift.start_time,
        end_time=template_day.shift.end_time,
        shift=template_day.shift,
        status='scheduled',
        department=user.department if hasattr(user, 'department') else '',
        created_by=created_by
    )
    created_events.append(ScheduleEventSerializer(event, context={'request': None}).data)

# ==================== AVAILABILITY & CONFLICT CHECKING ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_availability(request):
    """
    Check user availability for given dates
    """
    user_ids = request.data.get('user_ids', [])
    start_date = request.data.get('start_date')
    end_date = request.data.get('end_date')
    
    if not user_ids or not start_date or not end_date:
        return Response({
            'error': 'user_ids, start_date, and end_date are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        return Response({
            'error': INVALID_DATE_FORMAT_ERROR
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not isinstance(user_ids, list):
        return Response({
            'error': 'user_ids must be a list'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    availability_results = []
    
    for user_id in user_ids:
        try:
            user = User.objects.get(id=user_id)
            
            # Check for existing events in this date range
            conflicts = ScheduleEvent.objects.filter(
                user=user,
                status__in=['scheduled', 'confirmed'],
                start_date__lte=end_date,
                end_date__gte=start_date
            )
            
            availability_results.append({
                'user_id': str(user.id),
                'user_name': user.get_full_name(),
                'is_available': not conflicts.exists(),
                'conflicts': ScheduleEventSerializer(conflicts, many=True, context={'request': request}).data if conflicts.exists() else [],
                'conflict_count': conflicts.count()
            })
            
        except User.DoesNotExist:
            availability_results.append({
                'user_id': user_id,
                'user_name': 'Unknown',
                'is_available': False,
                'conflicts': [],
                'conflict_count': 0,
                'error': 'User not found'
            })
    
    return Response({
        'date_range': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        },
        'results': availability_results
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_conflicts(request):
    """
    Check for schedule conflicts
    """
    user_id = request.data.get('user_id')
    start_date = request.data.get('start_date')
    end_date = request.data.get('end_date')
    event_id = request.data.get('event_id')  # For updates, exclude current event
    
    if not user_id or not start_date or not end_date:
        return Response({
            'error': 'user_id, start_date, and end_date are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = User.objects.get(id=user_id)
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except (User.DoesNotExist, ValueError):
        return Response({
            'error': 'Invalid user_id or date format'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Check for conflicts
    conflicts = ScheduleEvent.objects.filter(
        user=user,
        status__in=['scheduled', 'confirmed'],
        start_date__lte=end_date,
        end_date__gte=start_date
    )
    
    if event_id:
        conflicts = conflicts.exclude(id=event_id)
    
    serializer = ScheduleEventSerializer(conflicts, many=True, context={'request': request})
    
    return Response({
        'has_conflicts': conflicts.exists(),
        'conflict_count': conflicts.count(),
        'conflicts': serializer.data
    }, status=status.HTTP_200_OK)


# ==================== STATISTICS VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAdminUser])
def schedule_statistics(request):
    """
    Get system-wide schedule statistics (admin only)
    """
    today = timezone.now().date()
    
    # Basic counts
    total_events = ScheduleEvent.objects.count()
    total_shifts = ScheduleEvent.objects.filter(event_type='shift').count()
    upcoming_events = ScheduleEvent.objects.filter(end_date__gte=today).count()
    
    # Events by type
    events_by_type = ScheduleEvent.objects.values('event_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Events by status
    events_by_status = ScheduleEvent.objects.values('status').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Users with most events
    busy_users = User.objects.annotate(
        event_count=Count('schedule_events')
    ).order_by('-event_count')[:10]
    
    busy_users_data = []
    for user in busy_users:
        busy_users_data.append({
            'id': str(user.id),
            'name': user.get_full_name(),
            'event_count': user.event_count
        })
    
    # Department statistics
    department_stats = ScheduleEvent.objects.exclude(department='').values('department').annotate(
        event_count=Count('id'),
        user_count=Count('user', distinct=True)
    ).order_by('-event_count')[:10]
    
    return Response({
        'total_events': total_events,
        'total_shifts': total_shifts,
        'upcoming_events': upcoming_events,
        'events_by_type': list(events_by_type),
        'events_by_status': list(events_by_status),
        'busiest_users': busy_users_data,
        'department_stats': list(department_stats)
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_schedule_statistics(request, user_id=None):
    """
    Get schedule statistics for a user
    """
    if user_id:
        user = get_object_or_404(User, id=user_id)
        # Check permissions
        if user != request.user and not request.user.is_staff:
            return Response({
                'error': 'You can only view your own schedule statistics'
            }, status=status.HTTP_403_FORBIDDEN)
    else:
        user = request.user
    
    today = timezone.now().date()
    
    # Monthly statistics (current month)
    start_of_month = today.replace(day=1)
    if today.month == 12:
        end_of_month = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end_of_month = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    
    monthly_events = ScheduleEvent.objects.filter(
        user=user,
        start_date__gte=start_of_month,
        end_date__lte=end_of_month,
        status__in=['scheduled', 'confirmed']
    )
    
    # Weekly statistics
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    weekly_events = ScheduleEvent.objects.filter(
        user=user,
        start_date__gte=start_of_week,
        end_date__lte=end_of_week,
        status__in=['scheduled', 'confirmed']
    )
    
    # Calculate hours
    monthly_hours = sum(event.duration_hours for event in monthly_events)
    weekly_hours = sum(event.duration_hours for event in weekly_events)
    
    # Events by type
    events_by_type = ScheduleEvent.objects.filter(user=user).values('event_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    return Response({
        'user': {
            'id': str(user.id),
            'name': user.get_full_name()
        },
        'monthly': {
            'period': {
                'start': start_of_month.isoformat(),
                'end': end_of_month.isoformat()
            },
            'total_events': monthly_events.count(),
            'total_hours': round(monthly_hours, 2)
        },
        'weekly': {
            'period': {
                'start': start_of_week.isoformat(),
                'end': end_of_week.isoformat()
            },
            'total_events': weekly_events.count(),
            'total_hours': round(weekly_hours, 2)
        },
        'events_by_type': list(events_by_type)
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def department_statistics(request, department):
    """
    Get statistics for a department
    """
    # Check if user has access
    user = request.user
    if not user.is_staff and (not hasattr(user, 'department') or user.department != department):
        return Response({
            'error': 'You do not have access to this department statistics'
        }, status=status.HTTP_403_FORBIDDEN)
    
    today = timezone.now().date()
    
    # Get users in department
    users = User.objects.filter(department=department, is_active=True)
    
    # Current week events
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    weekly_events = ScheduleEvent.objects.filter(
        user__in=users,
        start_date__gte=start_of_week,
        end_date__lte=end_of_week,
        status__in=['scheduled', 'confirmed']
    )
    
    # Today's events
    today_events = ScheduleEvent.objects.filter(
        user__in=users,
        start_date__lte=today,
        end_date__gte=today,
        status__in=['scheduled', 'confirmed']
    )
    
    # Calculate statistics
    weekly_hours = sum(event.duration_hours for event in weekly_events)
    users_on_duty_today = today_events.values('user').distinct().count()
    
    # Events by type for the week
    events_by_type = weekly_events.values('event_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    return Response({
        'department': department,
        'total_users': users.count(),
        'weekly': {
            'period': {
                'start': start_of_week.isoformat(),
                'end': end_of_week.isoformat()
            },
            'total_events': weekly_events.count(),
            'total_hours': round(weekly_hours, 2),
            'average_hours_per_user': round(weekly_hours / users.count(), 2) if users.count() > 0 else 0
        },
        'today': {
            'date': today.isoformat(),
            'total_events': today_events.count(),
            'users_on_duty': users_on_duty_today,
            'coverage_percentage': round((users_on_duty_today / users.count() * 100), 2) if users.count() > 0 else 0
        },
        'events_by_type': list(events_by_type)
    }, status=status.HTTP_200_OK)


# ==================== EXPORT VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_schedule(request):
    """
    Export schedule data
    """
    format_type = request.query_params.get('format', 'json')  # json, csv
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    user_id = request.query_params.get('user_id')
    
    # Base queryset
    if user_id and request.user.is_staff:
        events = ScheduleEvent.objects.filter(user_id=user_id)
    else:
        events = ScheduleEvent.objects.filter(user=request.user)
    
    # Apply date filters
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            events = events.filter(end_date__gte=start_date)
        except ValueError:
            pass
    
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            events = events.filter(start_date__lte=end_date)
        except ValueError:
            pass
    
    events = events.select_related('user', 'shift').order_by('start_date', 'start_time')
    
    if format_type == 'csv':
        # Simple CSV export
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="schedule_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Date', 'Start Time', 'End Time', 'Title', 'Event Type', 'Status', 'Location', 'Duration (hours)'])
        
        for event in events:
            writer.writerow([
                event.start_date,
                event.start_time,
                event.end_time,
                event.title,
                event.event_type,
                event.status,
                event.location or '',
                event.duration_hours
            ])
        
        return response
    
    else:  # JSON format
        serializer = ScheduleEventSerializer(events, many=True, context={'request': request})
        
        return Response({
            'format': 'json',
            'count': events.count(),
            'export_date': timezone.now().isoformat(),
            'data': serializer.data
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
            
            cursor.execute("SELECT COUNT(*) FROM schedules_scheduleevent")
            event_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM schedules_scheduletemplate")
            template_count = cursor.fetchone()[0]
        
        # Get recent activity
        recent_events = ScheduleEvent.objects.filter(
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).count()
        
        return Response({
            'status': 'healthy',
            'database': 'connected',
            'total_shifts': shift_count,
            'total_events': event_count,
            'total_templates': template_count,
            'recent_activity': {
                'events_last_24h': recent_events
            },
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)