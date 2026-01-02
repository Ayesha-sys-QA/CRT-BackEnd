# patients/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # ==================== PATIENT CRUD ====================
    path('', views.patient_list, name='patient-list'),
    path('create/', views.create_patient, name='create-patient'),
    path('<uuid:patient_id>/', views.patient_detail, name='patient-detail'),
    path('<uuid:patient_id>/update/', views.update_patient, name='update-patient'),
    path('<uuid:patient_id>/delete/', views.delete_patient, name='delete-patient'),
    path('<uuid:patient_id>/restore/', views.restore_patient, name='restore-patient'),
    path('<uuid:patient_id>/permanent-delete/', views.permanent_delete_patient, name='permanent-delete-patient'),
    
    # ==================== BULK OPERATIONS ====================
    path('bulk/update/', views.bulk_update_patients, name='bulk-update-patients'),
    path('bulk/archive/', views.bulk_archive_patients, name='bulk-archive-patients'),
    
    # ==================== SEARCH & FILTER ====================
    path('search/', views.search_patients, name='search-patients'),
    path('doctors/<uuid:doctor_id>/patients/', views.doctor_patients, name='doctor-patients'),
    path('my-patients/', views.doctor_patients, name='my-patients'),  # Current doctor's patients
    
    # ==================== PATIENT STATS ====================
    path('<uuid:patient_id>/stats/', views.patient_stats, name='patient-stats'),
    path('<uuid:patient_id>/stats/appointment-rate/', views.update_appointment_rate, name='update-appointment-rate'),
    
    # ==================== MEDICAL INFORMATION ====================
    path('<uuid:patient_id>/insurances/', views.patient_insurances, name='patient-insurances'),
    path('<uuid:patient_id>/allergies/', views.patient_allergies, name='patient-allergies'),
    path('<uuid:patient_id>/medical-history/', views.patient_medical_history, name='patient-medical-history'),
    path('<uuid:patient_id>/emergency-contact/', views.patient_emergency_contact, name='patient-emergency-contact'),
    
    # ==================== STATISTICS & ANALYTICS ====================
    path('stats/system/', views.patient_statistics, name='patient-statistics'),
    path('stats/doctor/<uuid:doctor_id>/', views.doctor_patient_statistics, name='doctor-patient-statistics'),
    path('stats/my/', views.doctor_patient_statistics, name='my-patient-statistics'),  # Current doctor's stats
    
    # ==================== EXPORT & IMPORT ====================
    path('export/', views.export_patients, name='export-patients'),
    
    # ==================== DASHBOARD ====================
    path('dashboard/summary/', views.dashboard_summary, name='dashboard-summary'),
    
    # ==================== HEALTH CHECK ====================
    path('health/', views.patients_health_check, name='patients-health-check'),
]