
# schedules/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # ==================== SHIFT MANAGEMENT ====================
    path('shifts/', views.shift_list, name='shift-list'),
    path('shifts/create/', views.create_shift, name='create-shift'),
    path('shifts/<uuid:shift_id>/', views.shift_detail, name='shift-detail'),
    
    # ==================== SCHEDULE EVENT MANAGEMENT ====================
    path('events/', views.schedule_event_list, name='schedule-event-list'),
    path('events/create/', views.create_schedule_event, name='create-schedule-event'),
    path('events/bulk-create/', views.bulk_create_schedule_events, name='bulk-create-schedule-events'),
    path('events/<uuid:event_id>/', views.schedule_event_detail, name='schedule-event-detail'),
    
    # ==================== USER SCHEDULE VIEWS ====================
    path('me/schedule/', views.my_schedule, name='my-schedule'),
    path('me/upcoming-shifts/', views.my_upcoming_shifts, name='my-upcoming-shifts'),
    path('users/<uuid:user_id>/schedule/', views.user_schedule_view, name='user-schedule-view'),
    
    # ==================== CALENDAR VIEWS ====================
    path('calendar/', views.calendar_view, name='calendar-view'),
    
    # ==================== DEPARTMENT SCHEDULE VIEWS ====================
    path('department/<str:department>/schedule/', views.department_schedule, name='department-schedule'),
    path('department/<str:department>/today/', views.department_today, name='department-today'),
    
    # ==================== SCHEDULE TEMPLATE MANAGEMENT ====================
    path('templates/', views.schedule_template_list, name='schedule-template-list'),
    path('templates/create/', views.create_schedule_template, name='create-schedule-template'),
    path('templates/<uuid:template_id>/', views.schedule_template_detail, name='schedule-template-detail'),
    path('templates/<uuid:template_id>/apply/', views.apply_schedule_template, name='apply-schedule-template'),
    
    # ==================== AVAILABILITY & CONFLICT CHECKING ====================
    path('availability/check/', views.check_availability, name='check-availability'),
    path('conflicts/check/', views.check_conflicts, name='check-conflicts'),
    
    # ==================== STATISTICS & REPORTS ====================
    path('stats/', views.schedule_statistics, name='schedule-statistics'),
    path('stats/users/<uuid:user_id>/', views.user_schedule_statistics, name='user-schedule-statistics'),
    path('stats/department/<str:department>/', views.department_statistics, name='department-statistics'),
    path('export/', views.export_schedule, name='export-schedule'),
    
    # ==================== HEALTH CHECK ====================
    path('health/', views.schedules_health_check, name='schedules-health-check'),
]