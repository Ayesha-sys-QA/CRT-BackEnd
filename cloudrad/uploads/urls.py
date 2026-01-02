# uploads/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # ==================== UPLOAD MANAGEMENT ====================
    path('', views.upload_list, name='upload-list'),
    path('create/', views.create_upload, name='create-upload'),
    path('<uuid:upload_id>/', views.upload_detail, name='upload-detail'),
    path('<uuid:upload_id>/delete/', views.delete_upload, name='delete-upload'),
    path('<uuid:upload_id>/retry/', views.retry_upload, name='retry-upload'),
    
    # ==================== CHUNKED UPLOADS ====================
    path('chunked/start/', views.start_chunked_upload, name='start-chunked-upload'),
    path('chunked/<uuid:upload_id>/upload/', views.upload_chunk, name='upload-chunk'),
    path('chunked/<uuid:upload_id>/status/', views.chunked_upload_status, name='chunked-upload-status'),
    
    # ==================== PATIENT UPLOADS ====================
    path('patients/<uuid:patient_id>/uploads/', views.patient_uploads, name='patient-uploads'),
    path('bulk/assign-patient/', views.bulk_assign_to_patient, name='bulk-assign-to-patient'),
    
    # ==================== FILE DOWNLOAD & PREVIEW ====================
    path('<uuid:upload_id>/download/', views.download_file, name='download-file'),
    path('<uuid:upload_id>/preview/', views.preview_file, name='preview-file'),
    
    # ==================== PROCESSING OPTIONS ====================
    path('<uuid:upload_id>/processing/', views.upload_processing_options, name='upload-processing-options'),
    path('<uuid:upload_id>/process/', views.start_processing, name='start-processing'),
    path('<uuid:upload_id>/processing-status/', views.processing_status, name='processing-status'),
    
    # ==================== BULK OPERATIONS ====================
    path('bulk/update-status/', views.bulk_update_status, name='bulk-update-status'),
    path('bulk/delete/', views.bulk_delete_uploads, name='bulk-delete-uploads'),
    
    # ==================== STATISTICS & ANALYTICS ====================
    path('stats/system/', views.upload_statistics, name='upload-statistics'),
    path('stats/patients/<uuid:patient_id>/', views.patient_upload_statistics, name='patient-upload-statistics'),
    path('stats/storage-usage/', views.storage_usage, name='storage-usage'),
    
    # ==================== FILE VALIDATION & UTILITIES ====================
    path('validate/', views.validate_file, name='validate-file'),
    
    # ==================== HEALTH CHECK ====================
    path('health/', views.uploads_health_check, name='uploads-health-check'),
]