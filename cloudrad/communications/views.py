from django.shortcuts import render

# Create your views here.
# communications/views.py
from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime, timedelta

from .models import Message, Attachment
from .serializers import (
    MessageSerializer, MessageCreateSerializer, MessageUpdateSerializer,
    InboxMessageSerializer, SentMessageSerializer, AnnouncementSerializer,
    AttachmentSerializer, AttachmentCreateSerializer
)
from users.models import User
from patients.models import Patient
import logging

logger = logging.getLogger(__name__)

# Define a constant for the error message
INVALID_PAGE_ERROR = 'Invalid page or page_size parameter'

# Define a constant for the invalid page number error
INVALID_PAGE_NUMBER_ERROR = 'Invalid page number'


# ==================== MESSAGE VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def inbox_messages(request):
    """
    Get user's inbox messages
    """
    user = request.user
    
    # Get messages where user is recipient
    messages = Message.objects.filter(
        recipient=user,
        message_type__in=['inbox', 'announcement']
    ).select_related('sender', 'patient').order_by('-timestamp')
    
    # Apply filters
    category = request.query_params.get('category')
    priority = request.query_params.get('priority')
    is_read = request.query_params.get('is_read')
    is_important = request.query_params.get('is_important')
    search = request.query_params.get('search')
    
    if category:
        messages = messages.filter(category=category)
    
    if priority:
        messages = messages.filter(priority=priority)
    
    if is_read and is_read.lower() in ['true', 'false']:
        messages = messages.filter(is_read=is_read.lower() == 'true')
    
    if is_important and is_important.lower() in ['true', 'false']:
        messages = messages.filter(is_important=is_important.lower() == 'true')
    
    if search:
        messages = messages.filter(
            Q(subject__icontains=search) |
            Q(content__icontains=search) |
            Q(sender__email__icontains=search) |
            Q(sender__first_name__icontains=search) |
            Q(sender__last_name__icontains=search)
        )
    
    # Pagination
    page = request.query_params.get('page', 1)
    page_size = request.query_params.get('page_size', 20)
    
    try:
        page = int(page)
        page_size = int(page_size)
    except ValueError:
        return Response({
            'error': INVALID_PAGE_ERROR
        }, status=status.HTTP_400_BAD_REQUEST)
    
    paginator = Paginator(messages, page_size)
    try:
        paginated_messages = paginator.page(page)
    except:
        return Response({
            'error': INVALID_PAGE_NUMBER_ERROR
        }, status=status.HTTP_400_BAD_REQUEST)
        raise
    
    serializer = InboxMessageSerializer(paginated_messages, many=True, context={'request': request})
    
    # Get counts for filters
    unread_count = messages.filter(is_read=False).count()
    important_count = messages.filter(is_important=True).count()
    
    return Response({
        'count': messages.count(),
        'page': page,
        'page_size': page_size,
        'total_pages': paginator.num_pages,
        'unread_count': unread_count,
        'important_count': important_count,
        'results': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sent_messages(request):
    """
    Get user's sent messages
    """
    user = request.user
    
    messages = Message.objects.filter(
        sender=user,
        message_type='sent'
    ).select_related('recipient', 'patient').order_by('-timestamp')
    
    # Apply filters
    status_filter = request.query_params.get('status')
    search = request.query_params.get('search')
    
    if status_filter:
        messages = messages.filter(status=status_filter)
    
    if search:
        messages = messages.filter(
            Q(subject__icontains=search) |
            Q(content__icontains=search) |
            Q(recipient__email__icontains=search) |
            Q(recipient__first_name__icontains=search) |
            Q(recipient__last_name__icontains=search)
        )
    
    # Pagination
    page = request.query_params.get('page', 1)
    page_size = request.query_params.get('page_size', 20)
    
    try:
        page = int(page)
        page_size = int(page_size)
    except ValueError:
        return Response({
            'error': INVALID_PAGE_ERROR
        }, status=status.HTTP_400_BAD_REQUEST)
    
    paginator = Paginator(messages, page_size)
    try:
        paginated_messages = paginator.page(page)
    except:
        return Response({
            'error': INVALID_PAGE_NUMBER_ERROR
        }, status=status.HTTP_400_BAD_REQUEST)
        raise
    
    serializer = SentMessageSerializer(paginated_messages, many=True, context={'request': request})
    
    return Response({
        'count': messages.count(),
        'page': page,
        'page_size': page_size,
        'total_pages': paginator.num_pages,
        'results': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def announcements(request):
    """
    Get all announcements
    """
    announcements = Message.objects.filter(
        message_type='announcement'
    ).select_related('sender').order_by('-timestamp')
    
    # Apply filters
    announcement_type = request.query_params.get('type')
    priority = request.query_params.get('priority')
    
    if announcement_type:
        announcements = announcements.filter(announcement_type=announcement_type)
    
    if priority:
        announcements = announcements.filter(priority=priority)
    
    # Date filters
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            announcements = announcements.filter(timestamp__date__gte=start_date)
        except ValueError:
            return Response({
                'error': 'Invalid start_date format. Use YYYY-MM-DD'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            announcements = announcements.filter(timestamp__date__lte=end_date)
        except ValueError:
            return Response({
                'error': 'Invalid end_date format. Use YYYY-MM-DD'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    # Pagination
    page = request.query_params.get('page', 1)
    page_size = request.query_params.get('page_size', 20)
    
    try:
        page = int(page)
        page_size = int(page_size)
    except ValueError:
        return Response({
            'error': INVALID_PAGE_ERROR
        }, status=status.HTTP_400_BAD_REQUEST)
    
    paginator = Paginator(announcements, page_size)
    try:
        paginated_announcements = paginator.page(page)
    except:
        return Response({
            'error': INVALID_PAGE_NUMBER_ERROR
        }, status=status.HTTP_400_BAD_REQUEST)
        raise
    
    serializer = AnnouncementSerializer(paginated_announcements, many=True, context={'request': request})
    
    return Response({
        'count': announcements.count(),
        'page': page,
        'page_size': page_size,
        'total_pages': paginator.num_pages,
        'results': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_message(request):
    """
    Send a new message
    """
    serializer = MessageCreateSerializer(data=request.data, context={'request': request})
    
    if serializer.is_valid():
        message = serializer.save()
        
        # Update message type to 'sent' for the sender
        message.message_type = 'sent'
        message.save()
        
        # If there's a recipient, create an 'inbox' copy for them
        if message.recipient:
            inbox_message = Message.objects.create(
                sender=message.sender,
                recipient=message.recipient,
                message_type='inbox',
                subject=message.subject,
                content=message.content,
                is_important=message.is_important,
                priority=message.priority,
                category=message.category,
                patient=message.patient,
                status='delivered'
            )
            
            # Copy attachments if any
            if message.attachments.exists():
                for attachment in message.attachments.all():
                    Attachment.objects.create(
                        message=inbox_message,
                        file=attachment.file,
                        file_name=attachment.file_name,
                        file_type=attachment.file_type,
                        file_size=attachment.file_size
                    )
                inbox_message.attachments_count = message.attachments_count
                inbox_message.save()
        
        return Response({
            'message': 'Message sent successfully',
            'message_data': MessageSerializer(message, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_announcement(request):
    """
    Send an announcement (admin only)
    """
    if not request.user.is_staff:
        return Response({
            'error': 'Only administrators can send announcements'
        }, status=status.HTTP_403_FORBIDDEN)
    
    data = request.data.copy()
    data['message_type'] = 'announcement'
    
    serializer = MessageCreateSerializer(data=data, context={'request': request})
    
    if serializer.is_valid():
        announcement = serializer.save()
        
        return Response({
            'message': 'Announcement sent successfully',
            'announcement': AnnouncementSerializer(announcement, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def message_detail(request, message_id):
    """
    Get message details
    """
    message = get_object_or_404(Message, id=message_id)
    
    # Check permissions
    if message.recipient != request.user and message.sender != request.user and not request.user.is_staff:
        return Response({
            'error': 'You do not have permission to view this message'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Mark as read if recipient is viewing
    if message.recipient == request.user and not message.is_read:
        message.is_read = True
        message.save()
    
    serializer = MessageSerializer(message, context={'request': request})
    
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_message(request, message_id):
    """
    Update message (mainly status, read flag, importance)
    """
    message = get_object_or_404(Message, id=message_id)
    
    # Check permissions - only recipient can update read status
    if message.recipient != request.user:
        return Response({
            'error': 'You can only update messages sent to you'
        }, status=status.HTTP_403_FORBIDDEN)
    
    serializer = MessageUpdateSerializer(message, data=request.data, partial=True)
    
    if serializer.is_valid():
        serializer.save()
        return Response({
            'message': 'Message updated successfully',
            'message_data': MessageSerializer(message, context={'request': request}).data
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_message(request, message_id):
    """
    Delete a message
    """
    message = get_object_or_404(Message, id=message_id)
    
    # Check permissions
    if message.recipient != request.user and message.sender != request.user and not request.user.is_staff:
        return Response({
            'error': 'You do not have permission to delete this message'
        }, status=status.HTTP_403_FORBIDDEN)
    
    message.delete()
    
    return Response({
        'message': 'Message deleted successfully'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_as_read(request, message_id):
    """
    Mark a message as read
    """
    message = get_object_or_404(Message, id=message_id)
    
    if message.recipient != request.user:
        return Response({
            'error': 'You can only mark messages sent to you as read'
        }, status=status.HTTP_403_FORBIDDEN)
    
    message.is_read = True
    message.save()
    
    return Response({
        'message': 'Message marked as read',
        'is_read': True
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_as_unread(request, message_id):
    """
    Mark a message as unread
    """
    message = get_object_or_404(Message, id=message_id)
    
    if message.recipient != request.user:
        return Response({
            'error': 'You can only mark messages sent to you as unread'
        }, status=status.HTTP_403_FORBIDDEN)
    
    message.is_read = False
    message.save()
    
    return Response({
        'message': 'Message marked as unread',
        'is_read': False
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_importance(request, message_id):
    """
    Toggle message importance
    """
    message = get_object_or_404(Message, id=message_id)
    
    if message.recipient != request.user:
        return Response({
            'error': 'You can only change importance of messages sent to you'
        }, status=status.HTTP_403_FORBIDDEN)
    
    message.is_important = not message.is_important
    message.save()
    
    action = 'marked as important' if message.is_important else 'unmarked as important'
    
    return Response({
        'message': f'Message {action}',
        'is_important': message.is_important
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_mark_as_read(request):
    """
    Mark multiple messages as read
    """
    message_ids = request.data.get('message_ids', [])
    
    if not isinstance(message_ids, list):
        return Response({
            'error': 'message_ids must be a list'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not message_ids:
        return Response({
            'error': 'No message IDs provided'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Get messages where user is recipient
    messages = Message.objects.filter(
        id__in=message_ids,
        recipient=request.user
    )
    
    updated_count = messages.update(is_read=True)
    
    return Response({
        'message': f'{updated_count} messages marked as read',
        'updated_count': updated_count
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_delete_messages(request):
    """
    Delete multiple messages
    """
    message_ids = request.data.get('message_ids', [])
    
    if not isinstance(message_ids, list):
        return Response({
            'error': 'message_ids must be a list'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not message_ids:
        return Response({
            'error': 'No message IDs provided'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Get messages where user is either sender or recipient
    messages = Message.objects.filter(
        id__in=message_ids
    ).filter(
        Q(recipient=request.user) | Q(sender=request.user)
    )
    
    deleted_count = messages.count()
    messages.delete()
    
    return Response({
        'message': f'{deleted_count} messages deleted',
        'deleted_count': deleted_count
    }, status=status.HTTP_200_OK)


# ==================== ATTACHMENT VIEWS ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_attachment(request, message_id):
    """
    Upload attachment to a message
    """
    message = get_object_or_404(Message, id=message_id)
    
    # Check permissions - only sender can add attachments
    if message.sender != request.user:
        return Response({
            'error': 'You can only add attachments to messages you sent'
        }, status=status.HTTP_403_FORBIDDEN)
    
    serializer = AttachmentCreateSerializer(data=request.data)
    
    if serializer.is_valid():
        attachment = serializer.save(message=message)
        
        return Response({
            'message': 'Attachment uploaded successfully',
            'attachment': AttachmentSerializer(attachment, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def message_attachments(request, message_id):
    """
    Get all attachments for a message
    """
    message = get_object_or_404(Message, id=message_id)
    
    # Check permissions
    if message.recipient != request.user and message.sender != request.user and not request.user.is_staff:
        return Response({
            'error': 'You do not have permission to view these attachments'
        }, status=status.HTTP_403_FORBIDDEN)
    
    attachments = message.attachments.all()
    serializer = AttachmentSerializer(attachments, many=True, context={'request': request})
    
    return Response({
        'count': attachments.count(),
        'attachments': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_attachment(request, attachment_id):
    """
    Delete an attachment
    """
    attachment = get_object_or_404(Attachment, id=attachment_id)
    
    # Check permissions - only sender can delete attachments
    if attachment.message.sender != request.user:
        return Response({
            'error': 'You can only delete attachments from messages you sent'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Update message attachments count
    message = attachment.message
    message.attachments_count -= 1
    message.save()
    
    attachment.delete()
    
    return Response({
        'message': 'Attachment deleted successfully'
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_attachment(request, attachment_id):
    """
    Download an attachment
    """
    attachment = get_object_or_404(Attachment, id=attachment_id)
    
    # Check permissions
    message = attachment.message
    if message.recipient != request.user and message.sender != request.user and not request.user.is_staff:
        return Response({
            'error': 'You do not have permission to download this attachment'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # This would typically return a FileResponse
    # For now, return the file URL
    from django.http import HttpResponse
    import os
    
    file_path = attachment.file.path
    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type=attachment.file_type)
            response['Content-Disposition'] = f'attachment; filename="{attachment.file_name}"'
            return response
    else:
        return Response({
            'error': 'File not found'
        }, status=status.HTTP_404_NOT_FOUND)


# ==================== STATISTICS & ANALYTICS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def message_statistics(request):
    """
    Get message statistics for current user
    """
    user = request.user
    
    # Calculate statistics
    total_received = Message.objects.filter(recipient=user, message_type='inbox').count()
    total_sent = Message.objects.filter(sender=user, message_type='sent').count()
    unread_count = Message.objects.filter(recipient=user, is_read=False).count()
    important_count = Message.objects.filter(recipient=user, is_important=True).count()
    
    # Recent activity
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    
    received_today = Message.objects.filter(
        recipient=user,
        timestamp__date=today
    ).count()
    
    sent_today = Message.objects.filter(
        sender=user,
        timestamp__date=today
    ).count()
    
    received_this_week = Message.objects.filter(
        recipient=user,
        timestamp__date__gte=week_ago
    ).count()
    
    sent_this_week = Message.objects.filter(
        sender=user,
        timestamp__date__gte=week_ago
    ).count()
    
    # Messages by category
    from django.db.models import Count
    categories = Message.objects.filter(
        recipient=user
    ).exclude(category='').values('category').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    return Response({
        'total_received': total_received,
        'total_sent': total_sent,
        'unread_count': unread_count,
        'important_count': important_count,
        'today': {
            'received': received_today,
            'sent': sent_today
        },
        'this_week': {
            'received': received_this_week,
            'sent': sent_this_week
        },
        'categories': list(categories)
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def system_message_statistics(request):
    """
    Get system-wide message statistics (admin only)
    """
    from django.db.models import Count, Avg
    
    # Basic counts
    total_messages = Message.objects.count()
    total_announcements = Message.objects.filter(message_type='announcement').count()
    total_attachments = Attachment.objects.count()
    
    # Messages by type
    messages_by_type = Message.objects.values('message_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Messages by status
    messages_by_status = Message.objects.values('status').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Average attachments per message
    avg_attachments = Message.objects.filter(attachments_count__gt=0).aggregate(
        avg=Avg('attachments_count')
    )
    
    # Recent activity
    today = timezone.now().date()
    messages_today = Message.objects.filter(timestamp__date=today).count()
    
    return Response({
        'total_messages': total_messages,
        'total_announcements': total_announcements,
        'total_attachments': total_attachments,
        'messages_today': messages_today,
        'avg_attachments_per_message': avg_attachments['avg'] or 0,
        'messages_by_type': list(messages_by_type),
        'messages_by_status': list(messages_by_status)
    }, status=status.HTTP_200_OK)


# ==================== SEARCH & FILTER ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_messages(request):
    """
    Search through messages
    """
    user = request.user
    query = request.query_params.get('q', '').strip()
    
    if not query or len(query) < 2:
        return Response({
            'error': 'Search query must be at least 2 characters long'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Search in received messages
    received_messages = Message.objects.filter(
        recipient=user,
        message_type='inbox'
    ).filter(
        Q(subject__icontains=query) |
        Q(content__icontains=query) |
        Q(sender__email__icontains=query) |
        Q(sender__first_name__icontains=query) |
        Q(sender__last_name__icontains=query)
    ).select_related('sender').order_by('-timestamp')[:50]
    
    # Search in sent messages
    sent_messages = Message.objects.filter(
        sender=user,
        message_type='sent'
    ).filter(
        Q(subject__icontains=query) |
        Q(content__icontains=query) |
        Q(recipient__email__icontains=query) |
        Q(recipient__first_name__icontains=query) |
        Q(recipient__last_name__icontains=query)
    ).select_related('recipient').order_by('-timestamp')[:50]
    
    received_serializer = InboxMessageSerializer(received_messages, many=True, context={'request': request})
    sent_serializer = SentMessageSerializer(sent_messages, many=True, context={'request': request})
    
    return Response({
        'query': query,
        'received': {
            'count': received_messages.count(),
            'results': received_serializer.data
        },
        'sent': {
            'count': sent_messages.count(),
            'results': sent_serializer.data
        }
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def patient_messages(request, patient_id):
    """
    Get all messages related to a specific patient
    """
    patient = get_object_or_404(Patient, id=patient_id)
    
    # Check if user has permission to view patient messages
    # (Assuming doctors can see messages for their patients)
    if patient.primary_doctor != request.user and not request.user.is_staff:
        return Response({
            'error': 'You do not have permission to view messages for this patient'
        }, status=status.HTTP_403_FORBIDDEN)
    
    messages = Message.objects.filter(
        patient=patient
    ).select_related('sender', 'recipient').order_by('-timestamp')
    
    serializer = MessageSerializer(messages, many=True, context={'request': request})
    
    return Response({
        'patient_id': str(patient.id),
        'patient_name': patient.full_name,
        'count': messages.count(),
        'messages': serializer.data
    }, status=status.HTTP_200_OK)


# ==================== NOTIFICATION VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def unread_count(request):
    """
    Get count of unread messages
    """
    user = request.user
    
    unread_count = Message.objects.filter(
        recipient=user,
        is_read=False,
        message_type='inbox'
    ).count()
    
    return Response({
        'unread_count': unread_count
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def recent_messages(request):
    """
    Get recent messages (for notifications)
    """
    user = request.user
    
    recent_messages = Message.objects.filter(
        recipient=user,
        message_type='inbox'
    ).select_related('sender').order_by('-timestamp')[:10]
    
    serializer = InboxMessageSerializer(recent_messages, many=True, context={'request': request})
    
    return Response({
        'messages': serializer.data
    }, status=status.HTTP_200_OK)


# ==================== HEALTH CHECK ====================
@api_view(['GET'])
@permission_classes([AllowAny])
def communications_health_check(request):
    """
    Health check for communications app
    """
    from django.db import connection
    
    try:
        # Check database
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM messages")
            message_count = cursor.fetchone()[0]
        
        return Response({
            'status': 'healthy',
            'database': 'connected',
            'total_messages': message_count,
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)