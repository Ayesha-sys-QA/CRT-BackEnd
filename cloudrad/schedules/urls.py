# schedules/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # ==================== SHIFT MANAGEMENT ====================
    path('shifts/', views.shift_list, name='shift-list'),
    path('shifts/create/', views.create_shift, name='create-shift'),
    path('shifts/<uuid:shift_id>/', views.shift_detail, name='shift-detail'),
    
    # ==================== SCHEDULE DAY MANAGEMENT ====================
    path('days/', views.schedule_day_list, name='schedule-day-list'),
    path('days/create/', views.create_schedule_day, name='create-schedule-day'),
    path('days/<uuid:day_id>/', views.schedule_day_detail, name='schedule-day-detail'),
    path('days/assign-shift/', views.assign_shift_to_day, name='assign-shift-to-day'),
    
    # ==================== USER SCHEDULE ASSIGNMENTS ====================
    path('assignments/', views.user_schedule_list, name='user-schedule-list'),
    path('assignments/assign/', views.assign_user_to_schedule, name='assign-user-to-schedule'),
    path('assignments/bulk-assign/', views.bulk_assign_users, name='bulk-assign-users'),
    path('assignments/<uuid:assignment_id>/remove/', views.remove_user_from_schedule, name='remove-user-from-schedule'),
    path('assignments/bulk-remove/', views.bulk_remove_users_from_schedule, name='bulk-remove-users-from-schedule'),
    
    # ==================== USER SCHEDULE VIEWS ====================
    path('my-schedule/', views.my_schedule, name='my-schedule'),
    path('users/<uuid:user_id>/schedule/', views.user_weekly_schedule, name='user-weekly-schedule'),
    path('my-weekly-schedule/', views.user_weekly_schedule, name='my-weekly-schedule'),
    path('today/', views.today_schedule, name='today-schedule'),
    path('upcoming/', views.upcoming_shifts, name='upcoming-shifts'),
    
    # ==================== DEPARTMENT & TEAM SCHEDULES ====================
    path('department/', views.department_schedule, name='department-schedule'),
    path('days/<uuid:day_id>/detail/', views.day_schedule_detail, name='day-schedule-detail'),
    path('days/<uuid:day_id>/available-users/', views.available_users_for_day, name='available-users-for-day'),
    
    # ==================== SCHEDULE CONFLICT CHECKING ====================
    path('check-conflicts/', views.check_schedule_conflicts, name='check-schedule-conflicts'),
    
    # ==================== SCHEDULE GENERATION ====================
    path('generate-weekly/', views.generate_weekly_schedule, name='generate-weekly-schedule'),
    path('copy-week/', views.copy_schedule_week, name='copy-schedule-week'),
    
    # ==================== STATISTICS & REPORTS ====================
    path('stats/system/', views.schedule_statistics, name='schedule-statistics'),
    path('stats/users/<uuid:user_id>/', views.user_schedule_statistics, name='user-schedule-statistics'),
    path('stats/my/', views.user_schedule_statistics, name='my-schedule-statistics'),
    
    # ==================== HEALTH CHECK ====================
    path('health/', views.schedules_health_check, name='schedules-health-check'),
]