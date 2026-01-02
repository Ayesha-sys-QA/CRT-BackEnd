# communications/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # ==================== MESSAGES ====================
    path('inbox/', views.inbox_messages, name='inbox-messages'),
    path('sent/', views.sent_messages, name='sent-messages'),
    path('announcements/', views.announcements, name='announcements'),
    path('send/', views.send_message, name='send-message'),
    path('send-announcement/', views.send_announcement, name='send-announcement'),
    path('<uuid:message_id>/', views.message_detail, name='message-detail'),
    path('<uuid:message_id>/update/', views.update_message, name='update-message'),
    path('<uuid:message_id>/delete/', views.delete_message, name='delete-message'),
    path('<uuid:message_id>/mark-read/', views.mark_as_read, name='mark-as-read'),
    path('<uuid:message_id>/mark-unread/', views.mark_as_unread, name='mark-as-unread'),
    path('<uuid:message_id>/toggle-importance/', views.toggle_importance, name='toggle-importance'),
    
    # ==================== BULK OPERATIONS ====================
    path('bulk/mark-read/', views.bulk_mark_as_read, name='bulk-mark-read'),
    path('bulk/delete/', views.bulk_delete_messages, name='bulk-delete-messages'),
    
    # ==================== ATTACHMENTS ====================
    path('<uuid:message_id>/attachments/', views.message_attachments, name='message-attachments'),
    path('<uuid:message_id>/attachments/upload/', views.upload_attachment, name='upload-attachment'),
    path('attachments/<uuid:attachment_id>/', views.delete_attachment, name='delete-attachment'),
    path('attachments/<uuid:attachment_id>/download/', views.download_attachment, name='download-attachment'),
    
    # ==================== STATISTICS ====================
    path('stats/', views.message_statistics, name='message-statistics'),
    path('stats/system/', views.system_message_statistics, name='system-message-statistics'),
    
    # ==================== SEARCH & FILTER ====================
    path('search/', views.search_messages, name='search-messages'),
    path('patients/<uuid:patient_id>/messages/', views.patient_messages, name='patient-messages'),
    
    # ==================== NOTIFICATIONS ====================
    path('notifications/unread-count/', views.unread_count, name='unread-count'),
    path('notifications/recent/', views.recent_messages, name='recent-messages'),
    
    # ==================== HEALTH CHECK ====================
    path('health/', views.communications_health_check, name='communications-health-check'),
]