from django.shortcuts import render

# Create your views here.
# uploads/views.py
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Sum
from django.db import transaction
import pydicom
from pydicom.errors import InvalidDicomError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime, timedelta
import os
import hashlib
import json
from django.core.files.storage import default_storage
from django.conf import settings

from .models import DICOMMetadata, UploadAccessLog, UploadFile, ProcessingOptions
from .serializers import (
    ConsentUpdateSerializer, DICOMMetadataSerializer, UploadFileMinimalSerializer, UploadFileSerializer, UploadCreateSerializer, UploadUpdateSerializer,
    UploadStatusSerializer, PatientUploadsSerializer,
    ProcessingOptionsSerializer, ProcessingOptionsUpdateSerializer,
    ChunkedUploadSerializer
)
from patients.models import Patient
from users.models import User
import logging
from django.http import HttpResponse, FileResponse
from wsgiref.util import FileWrapper

logger = logging.getLogger(__name__)

# Define a constant for the error message
UPLOAD_IDS_MUST_BE_LIST_ERROR = 'upload_ids must be a list'

DICOM_MIME_TYPES = ['application/dicom', 'image/dicom']
DICOM_FILE_EXTENSION = '.dcm'

# ==================== UPLOAD MANAGEMENT VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def upload_list(request):
    """
    List all uploads with filtering and pagination
    """
    uploads = UploadFile.objects.select_related('patient').order_by('-created_at')
    
    # Apply filters
    status_filter = request.query_params.get('status')
    file_type = request.query_params.get('file_type')
    patient_id = request.query_params.get('patient_id')
    search = request.query_params.get('search')
    
    if status_filter:
        uploads = uploads.filter(status=status_filter)
    
    if file_type:
        uploads = uploads.filter(file_type__icontains=file_type)
    
    if patient_id:
        uploads = uploads.filter(patient_id=patient_id)
    
    if search:
        uploads = uploads.filter(
            Q(name__icontains=search) |
            Q(file_type__icontains=search) |
            Q(patient__full_name__icontains=search) |
            Q(patient__national_id__icontains=search)
        )
    
    # If not admin, only show uploads for current user's patients
    if not request.user.is_staff:
        # Get IDs of patients where current user is primary doctor
        patient_ids = Patient.objects.filter(
            primary_doctor=request.user
        ).values_list('id', flat=True)
        uploads = uploads.filter(patient_id__in=patient_ids)
    
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
    
    paginator = Paginator(uploads, page_size)
    try:
        paginated_uploads = paginator.page(page)
    except:
        return Response({
            'error': 'Invalid page number'
        }, status=status.HTTP_400_BAD_REQUEST)
        raise
    
    serializer = UploadFileSerializer(paginated_uploads, many=True, context={'request': request})
    
    # Get counts for filters
    total_count = uploads.count()
    uploaded_count = uploads.filter(status='uploaded').count()
    pending_count = uploads.filter(status='pending').count()
    error_count = uploads.filter(status='error').count()
    
    return Response({
        'count': total_count,
        'page': page,
        'page_size': page_size,
        'total_pages': paginator.num_pages,
        'uploaded_count': uploaded_count,
        'pending_count': pending_count,
        'error_count': error_count,
        'results': serializer.data
    }, status=status.HTTP_200_OK)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_upload(request):
    """
    Create a new upload record and handle file upload
    """
    serializer = UploadCreateSerializer(data=request.data, context={'request': request})
    
    if serializer.is_valid():
        with transaction.atomic():
            # Get the validated data
            validated_data = serializer.validated_data.copy()
            
            # ADD THIS: Set uploaded_by to current user
            validated_data['uploaded_by'] = request.user
            
            # Create upload with all data including uploaded_by
            upload = UploadFile.objects.create(**validated_data)
            
            # Set initial status
            upload.status = 'uploading'
            upload.progress = 10
            upload.save()
            
            # Check if this is a chunked upload
            upload_id = request.data.get('upload_id')
            chunk_index = request.data.get('chunk_index')
            total_chunks = request.data.get('total_chunks')
            
            if upload_id and chunk_index is not None and total_chunks:
                return _handle_chunked_upload(upload, upload_id, int(chunk_index), int(total_chunks))
            
            # Handle regular single file upload
            upload.progress = 100
            upload.status = 'uploaded'
            upload.save()
            
            # Create processing options
            ProcessingOptions.objects.create(upload=upload)
            
            # Check if it's a DICOM file and extract metadata
            if upload.file_type in DICOM_MIME_TYPES or upload.file.name.lower().endswith(DICOM_FILE_EXTENSION):
                try:
                    # Try to extract DICOM metadata
                    file_path = upload.file.path
                    ds = pydicom.dcmread(file_path, stop_before_pixels=True)
                    
                    DICOMMetadata.objects.create(
                        upload=upload,
                        modality=str(ds.get('Modality', '')),
                        study_description=str(ds.get('StudyDescription', '')),
                        series_description=str(ds.get('SeriesDescription', '')),
                        rows=ds.get('Rows', None),
                        columns=ds.get('Columns', None)
                    )
                except Exception as e:  # FIXED: Specify exception class
                    logger.warning(f"Failed to extract DICOM metadata for upload {upload.id}: {e}")
        
        return Response({
            'message': 'File uploaded successfully',
            'upload': UploadFileSerializer(upload, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



def _handle_chunked_upload(upload, upload_id, chunk_index, total_chunks):
    """
    Handle chunked file upload
    """
    # In a real implementation, you would:
    # 1. Save the chunk to a temporary location
    # 2. When all chunks are received, combine them
    # 3. Update the upload status
    
    upload.progress = int((chunk_index + 1) / total_chunks * 100)
    
    if chunk_index == total_chunks - 1:  # Last chunk
        upload.status = 'uploaded'
        upload.progress = 100
    
    upload.save()
    
    return Response({
        'message': f'Chunk {chunk_index + 1}/{total_chunks} received',
        'progress': upload.progress,
        'status': upload.status,
        'upload_id': str(upload.id)
    }, status=status.HTTP_200_OK)


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def upload_detail(request, upload_id):
    """
    Get, update, or partially update upload details
    """
    upload = get_object_or_404(UploadFile.objects.select_related('patient'), id=upload_id)
    
    # Check permissions
    if not request.user.is_staff and upload.patient and upload.patient.primary_doctor != request.user:
        return Response({
            'error': 'You do not have permission to access this upload'
        }, status=status.HTTP_403_FORBIDDEN)
    
    if request.method == 'GET':
        serializer = UploadFileSerializer(upload, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        serializer = UploadUpdateSerializer(upload, data=request.data, partial=partial)
        
        if serializer.is_valid():
            upload = serializer.save()
            return Response({
                'message': 'Upload updated successfully',
                'upload': UploadFileSerializer(upload, context={'request': request}).data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_upload(request, upload_id):
    """
    Delete an upload and its associated file
    """
    upload = get_object_or_404(UploadFile, id=upload_id)
    
    # Check permissions
    if not request.user.is_staff and upload.patient and upload.patient.primary_doctor != request.user:
        return Response({
            'error': 'You do not have permission to delete this upload'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Delete the file from storage
    if upload.file:
        try:
            upload.file.delete(save=False)
        except:
            logger.warning(f'Could not delete file for upload {upload_id}')
            raise
    
    upload.delete()
    
    return Response({
        'message': 'Upload deleted successfully'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def retry_upload(request, upload_id):
    """
    Retry a failed upload
    """
    upload = get_object_or_404(UploadFile, id=upload_id)
    
    # Check permissions
    if not request.user.is_staff and upload.patient and upload.patient.primary_doctor != request.user:
        return Response({
            'error': 'You do not have permission to retry this upload'
        }, status=status.HTTP_403_FORBIDDEN)
    
    if upload.status != 'error':
        return Response({
            'error': 'Only failed uploads can be retried'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    upload.status = 'pending'
    upload.progress = 0
    upload.error_message = ''
    upload.save()
    
    return Response({
        'message': 'Upload retry initiated',
        'status': 'pending',
        'progress': 0
    }, status=status.HTTP_200_OK)


# ==================== CHUNKED UPLOAD VIEWS ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_chunked_upload(request):
    """
    Start a new chunked upload session
    """
    serializer = ChunkedUploadSerializer(data=request.data)
    
    if serializer.is_valid():
        # Create upload record with initial status
        upload = UploadFile.objects.create(
            name=serializer.validated_data['name'],
            status='pending',
            progress=0,
            file_type='',  # Will be set when file is complete
            size=0,  # Will be calculated when file is complete
            patient=serializer.validated_data.get('patient')
        )
        
        # Create processing options
        ProcessingOptions.objects.create(upload=upload)
        
        return Response({
            'message': 'Chunked upload session started',
            'upload_id': str(upload.id),
            'chunk_size': 5 * 1024 * 1024,  # 5MB chunks (example)
            'max_file_size': 2 * 1024 * 1024 * 1024  # 2GB max
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_chunk(request, upload_id):
    """
    Upload a chunk for a chunked upload session
    """
    upload = get_object_or_404(UploadFile, id=upload_id)
    
    # Check permissions
    if not request.user.is_staff and upload.patient and upload.patient.primary_doctor != request.user:
        return Response({
            'error': 'You do not have permission to upload to this session'
        }, status=status.HTTP_403_FORBIDDEN)
    
    chunk_index = request.data.get('chunk_index')
    total_chunks = request.data.get('total_chunks')
    chunk_data = request.FILES.get('chunk')
    
    if not all([chunk_index, total_chunks, chunk_data]):
        return Response({
            'error': 'chunk_index, total_chunks, and chunk are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        chunk_index = int(chunk_index)
        total_chunks = int(total_chunks)
    except ValueError:
        return Response({
            'error': 'chunk_index and total_chunks must be integers'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Update upload progress
    upload.status = 'uploading'
    upload.progress = int((chunk_index + 1) / total_chunks * 100)
    
    # If this is the last chunk, mark as uploaded
    if chunk_index == total_chunks - 1:
        upload.status = 'uploaded'
        upload.progress = 100
        
        # Set file metadata from the chunk (in real implementation, combine chunks)
        if chunk_data:
            upload.file_type = chunk_data.content_type
            upload.size = chunk_data.size * total_chunks  # Approximate
    
    upload.save()
    
    return Response({
        'message': f'Chunk {chunk_index + 1}/{total_chunks} received',
        'progress': upload.progress,
        'status': upload.status,
        'next_chunk': chunk_index + 1 if chunk_index + 1 < total_chunks else None
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def chunked_upload_status(request, upload_id):
    """
    Get status of a chunked upload session
    """
    upload = get_object_or_404(UploadFile, id=upload_id)
    
    # Check permissions
    if not request.user.is_staff and upload.patient and upload.patient.primary_doctor != request.user:
        return Response({
            'error': 'You do not have permission to view this upload session'
        }, status=status.HTTP_403_FORBIDDEN)
    
    return Response({
        'upload_id': str(upload.id),
        'status': upload.status,
        'progress': upload.progress,
        'error_message': upload.error_message,
        'created_at': upload.created_at
    }, status=status.HTTP_200_OK)


# ==================== PATIENT UPLOADS VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def patient_uploads(request, patient_id):
    """
    Get all uploads for a specific patient
    """
    patient = get_object_or_404(Patient, id=patient_id)
    
    # Check permissions
    if not request.user.is_staff and patient.primary_doctor != request.user:
        return Response({
            'error': 'You do not have permission to view uploads for this patient'
        }, status=status.HTTP_403_FORBIDDEN)
    
    uploads = UploadFile.objects.filter(
        patient=patient
    ).order_by('-created_at')
    
    # Apply filters
    status_filter = request.query_params.get('status')
    file_type = request.query_params.get('file_type')
    
    if status_filter:
        uploads = uploads.filter(status=status_filter)
    
    if file_type:
        uploads = uploads.filter(file_type__icontains=file_type)
    
    serializer = PatientUploadsSerializer(uploads, many=True, context={'request': request})
    
    # Get statistics
    total_size_mb = sum(u.size for u in uploads) / (1024 * 1024) if uploads.exists() else 0
    
    return Response({
        'patient_id': str(patient.id),
        'patient_name': patient.full_name,
        'count': uploads.count(),
        'total_size_mb': round(total_size_mb, 2),
        'uploads': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_assign_to_patient(request):
    """
    Bulk assign uploads to a patient
    """
    if not request.user.is_staff:
        return Response({
            'error': 'Only administrators can perform bulk assignments'
        }, status=status.HTTP_403_FORBIDDEN)
    
    upload_ids = request.data.get('upload_ids', [])
    patient_id = request.data.get('patient_id')
    
    if not isinstance(upload_ids, list):
        return Response({
            'error': UPLOAD_IDS_MUST_BE_LIST_ERROR
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not patient_id:
        return Response({
            'error': 'patient_id is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        patient = Patient.objects.get(id=patient_id)
    except Patient.DoesNotExist:
        return Response({
            'error': 'Patient not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    uploads = UploadFile.objects.filter(id__in=upload_ids)
    updated_count = uploads.update(patient=patient)
    
    return Response({
        'message': f'{updated_count} uploads assigned to patient',
        'patient_id': str(patient.id),
        'patient_name': patient.full_name,
        'assigned_count': updated_count
    }, status=status.HTTP_200_OK)


# ==================== FILE DOWNLOAD VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_file(request, upload_id):
    """
    Download an uploaded file
    """
    upload = get_object_or_404(UploadFile, id=upload_id)
    
    # Check permissions
    if not request.user.is_staff and upload.patient and upload.patient.primary_doctor != request.user:
        return Response({
            'error': 'You do not have permission to download this file'
        }, status=status.HTTP_403_FORBIDDEN)
    
    if upload.status != 'uploaded':
        return Response({
            'error': 'File is not available for download'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not upload.file:
        return Response({
            'error': 'File not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Log download access (HIPAA requirement)
    UploadAccessLog.objects.create(
        upload=upload,
        user=request.user,
        action='downloaded',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    
    # Update last accessed info
    upload.last_accessed = timezone.now()
    upload.accessed_by = request.user
    upload.save()
    
    # [KEEP THE REST OF YOUR EXISTING DOWNLOAD CODE AS IS]
    try:
        file_path = upload.file.path
        if os.path.exists(file_path):
            response = FileResponse(
                open(file_path, 'rb'),
                content_type=upload.file_type or 'application/octet-stream'
            )
            response['Content-Disposition'] = f'attachment; filename="{upload.name}{os.path.splitext(upload.file.name)[1]}"'
            response['Content-Length'] = upload.size
            
            logger.info(f'File downloaded: {upload.name} by user {request.user.id}')
            
            return response
        else:
            return Response({
                'error': 'File not found on server'
            }, status=status.HTTP_404_NOT_FOUND)
            
    except Exception as e:
        logger.error(f'Error downloading file {upload_id}: {str(e)}')
        return Response({
            'error': 'Failed to download file',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def preview_file(request, upload_id):
    """
    Preview a file (for images, PDFs, etc.)
    """
    upload = get_object_or_404(UploadFile, id=upload_id)
    
    # Check permissions
    if not request.user.is_staff and upload.patient and upload.patient.primary_doctor != request.user:
        return Response({
            'error': 'You do not have permission to preview this file'
        }, status=status.HTTP_403_FORBIDDEN)
    
    if upload.status != 'uploaded':
        return Response({
            'error': 'File is not available for preview'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if file type is previewable
    previewable_types = [
        'image/jpeg', 'image/png', 'image/gif', 'image/bmp',
        'application/pdf',
        'text/plain', 'text/csv'
    ]
    
    if upload.file_type not in previewable_types:
        return Response({
            'error': 'File type not supported for preview'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Return file URL for preview
    if upload.file and hasattr(upload.file, 'url'):
        return Response({
            'preview_url': request.build_absolute_uri(upload.file.url),
            'file_type': upload.file_type,
            'file_name': upload.name
        }, status=status.HTTP_200_OK)
    
    return Response({
        'error': 'File not available for preview'
    }, status=status.HTTP_404_NOT_FOUND)


# ==================== PROCESSING OPTIONS VIEWS ====================
@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def upload_processing_options(request, upload_id):
    """
    Get or update processing options for an upload
    """
    upload = get_object_or_404(UploadFile, id=upload_id)
    
    # Check permissions
    if not request.user.is_staff and upload.patient and upload.patient.primary_doctor != request.user:
        return Response({
            'error': 'You do not have permission to modify processing options for this upload'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        processing_options = upload.processing_options
    except ProcessingOptions.DoesNotExist:
        processing_options = ProcessingOptions.objects.create(upload=upload)
    
    if request.method == 'GET':
        serializer = ProcessingOptionsSerializer(processing_options)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        serializer = ProcessingOptionsUpdateSerializer(processing_options, data=request.data, partial=partial)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Processing options updated',
                'options': ProcessingOptionsSerializer(processing_options).data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_processing(request, upload_id):
    """
    Start processing for an uploaded file
    """
    upload = get_object_or_404(UploadFile.objects.select_related('processing_options'), id=upload_id)
    
    # Check permissions
    if not request.user.is_staff and upload.patient and upload.patient.primary_doctor != request.user:
        return Response({
            'error': 'You do not have permission to process this upload'
        }, status=status.HTTP_403_FORBIDDEN)
    
    if upload.status != 'uploaded':
        return Response({
            'error': 'Only uploaded files can be processed'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # In a real implementation, you would:
    # 1. Start background processing tasks
    # 2. Update upload status to 'processing'
    # 3. Return processing ID
    
    # For now, simulate processing
    upload.status = 'processing'
    upload.save()
    
    processing_options = upload.processing_options
    
    # Log processing request
    logger.info(f'Processing started for upload {upload_id} with options: {processing_options.__dict__}')
    
    return Response({
        'message': 'Processing started',
        'upload_id': str(upload.id),
        'status': 'processing',
        'processing_options': {
            'auto_anonymize': processing_options.auto_anonymize,
            'ai_analysis': processing_options.ai_analysis,
            'auto_3d': processing_options.auto_3d
        }
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def processing_status(request, upload_id):
    """
    Get processing status for an upload
    """
    upload = get_object_or_404(UploadFile, id=upload_id)
    
    # Check permissions
    if not request.user.is_staff and upload.patient and upload.patient.primary_doctor != request.user:
        return Response({
            'error': 'You do not have permission to view processing status for this upload'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # In a real implementation, you would check the actual processing status
    # For now, return mock status based on upload status
    
    status_info = {
        'upload_id': str(upload.id),
        'file_name': upload.name,
        'overall_status': upload.status,
        'progress': upload.progress,
        'error_message': upload.error_message
    }
    
    if upload.status == 'uploaded':
        status_info['processing_available'] = True
        status_info['message'] = 'Ready for processing'
    elif upload.status == 'processing':
        status_info['processing_available'] = False
        status_info['message'] = 'Processing in progress'
        status_info['estimated_completion'] = (timezone.now() + timedelta(minutes=5)).isoformat()
    elif upload.status == 'error':
        status_info['processing_available'] = False
        status_info['message'] = 'Processing failed'
    else:
        status_info['processing_available'] = False
        status_info['message'] = 'Not ready for processing'
    
    return Response(status_info, status=status.HTTP_200_OK)


# ==================== BULK OPERATIONS VIEWS ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_update_status(request):
    """
    Bulk update upload status
    """
    if not request.user.is_staff:
        return Response({
            'error': 'Only administrators can perform bulk status updates'
        }, status=status.HTTP_403_FORBIDDEN)
    
    upload_ids = request.data.get('upload_ids', [])
    status_value = request.data.get('status')
    error_message = request.data.get('error_message', '')
    
    if not isinstance(upload_ids, list):
        return Response({
            'error': UPLOAD_IDS_MUST_BE_LIST_ERROR
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not status_value:
        return Response({
            'error': 'status is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    valid_statuses = ['pending', 'uploading', 'uploaded', 'processing', 'error']
    if status_value not in valid_statuses:
        return Response({
            'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    uploads = UploadFile.objects.filter(id__in=upload_ids)
    updated_count = uploads.count()
    
    updates = {'status': status_value}
    if error_message and status_value == 'error':
        updates['error_message'] = error_message
    
    uploads.update(**updates)
    
    return Response({
        'message': f'{updated_count} uploads updated to status: {status_value}',
        'updated_count': updated_count,
        'status': status_value
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_delete_uploads(request):
    """
    Bulk delete uploads
    """
    if not request.user.is_staff:
        return Response({
            'error': 'Only administrators can perform bulk deletions'
        }, status=status.HTTP_403_FORBIDDEN)
    
    upload_ids = request.data.get('upload_ids', [])
    
    if not isinstance(upload_ids, list):
        return Response({
            'error': UPLOAD_IDS_MUST_BE_LIST_ERROR
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not upload_ids:
        return Response({
            'error': 'No upload IDs provided'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    uploads = UploadFile.objects.filter(id__in=upload_ids)
    deleted_count = uploads.count()
    
    # Delete associated files
    for upload in uploads:
        if upload.file:
            try:
                upload.file.delete(save=False)
            except:
                logger.warning(f'Could not delete file for upload {upload.id}')
                raise
    
    uploads.delete()
    
    return Response({
        'message': f'{deleted_count} uploads deleted',
        'deleted_count': deleted_count
    }, status=status.HTTP_200_OK)


# ==================== STATISTICS & ANALYTICS VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def upload_statistics(request):
    """
    Get upload statistics
    """
    if not request.user.is_staff:
        return Response({
            'error': 'Only administrators can view upload statistics'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Total counts
    total_uploads = UploadFile.objects.count()
    total_size_bytes = UploadFile.objects.aggregate(
        total_size=Sum('size')
    )['total_size'] or 0
    
    # Uploads by status
    uploads_by_status = UploadFile.objects.values('status').annotate(
        count=Count('id'),
        total_size=Sum('size')
    ).order_by('-count')
    
    # Uploads by file type
    uploads_by_type = UploadFile.objects.exclude(file_type='').values('file_type').annotate(
        count=Count('id'),
        total_size=Sum('size')
    ).order_by('-count')[:10]
    
    # ADD THIS: Uploads by category
    uploads_by_category = UploadFile.objects.values('category').annotate(
        count=Count('id'),
        total_size=Sum('size')
    ).order_by('-count')
    
    # Recent uploads (last 7 days)
    week_ago = timezone.now() - timedelta(days=7)
    recent_uploads = UploadFile.objects.filter(
        created_at__gte=week_ago
    ).count()
    
    # Format the data
    formatted_by_status = []
    for item in uploads_by_status:
        formatted_by_status.append({
            'status': item['status'],
            'count': item['count'],
            'total_size_mb': round(item['total_size'] / (1024 * 1024), 2) if item['total_size'] else 0
        })
    
    formatted_by_type = []
    for item in uploads_by_type:
        formatted_by_type.append({
            'file_type': item['file_type'],
            'count': item['count'],
            'total_size_mb': round(item['total_size'] / (1024 * 1024), 2) if item['total_size'] else 0
        })
    
    # ADD THIS: Format category data
    formatted_by_category = []
    for item in uploads_by_category:
        formatted_by_category.append({
            'category': item['category'],
            'count': item['count'],
            'total_size_mb': round(item['total_size'] / (1024 * 1024), 2) if item['total_size'] else 0
        })
    
    return Response({
        'total_uploads': total_uploads,
        'total_size_gb': round(total_size_bytes / (1024 * 1024 * 1024), 2),
        'recent_uploads_7days': recent_uploads,
        'uploads_by_status': formatted_by_status,
        'uploads_by_type': formatted_by_type,
        'uploads_by_category': formatted_by_category,  # ADD THIS
        'consented_uploads': UploadFile.objects.filter(patient_consent=True).count()  # ADD THIS
    }, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def patient_upload_statistics(request, patient_id):
    """
    Get upload statistics for a specific patient
    """
    patient = get_object_or_404(Patient, id=patient_id)
    
    # Check permissions
    if not request.user.is_staff and patient.primary_doctor != request.user:
        return Response({
            'error': 'You do not have permission to view statistics for this patient'
        }, status=status.HTTP_403_FORBIDDEN)
    
    uploads = UploadFile.objects.filter(patient=patient)
    
    total_uploads = uploads.count()
    total_size_bytes = uploads.aggregate(
        total_size=Sum('size')
    )['total_size'] or 0
    
    # Uploads by status
    uploads_by_status = uploads.values('status').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Uploads by file type
    uploads_by_type = uploads.exclude(file_type='').values('file_type').annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    # Recent uploads (last 30 days)
    month_ago = timezone.now() - timedelta(days=30)
    recent_uploads = uploads.filter(
        created_at__gte=month_ago
    ).count()
    
    return Response({
        'patient_id': str(patient.id),
        'patient_name': patient.full_name,
        'total_uploads': total_uploads,
        'total_size_mb': round(total_size_bytes / (1024 * 1024), 2),
        'recent_uploads_30days': recent_uploads,
        'uploads_by_status': list(uploads_by_status),
        'uploads_by_type': list(uploads_by_type)
    }, status=status.HTTP_200_OK)


# ==================== FILE VALIDATION & UTILITIES ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_file(request):
    """
    Validate a file before upload
    """
    file_obj = request.FILES.get('file')
    
    if not file_obj:
        return Response({
            'error': 'No file provided'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Check file size (max 2GB)
    max_size = 2 * 1024 * 1024 * 1024  # 2GB
    if file_obj.size > max_size:
        return Response({
            'valid': False,
            'error': f'File size exceeds limit of {max_size / (1024*1024*1024)}GB'
        }, status=status.HTTP_200_OK)
    
    # Check file type
    allowed_types = [
        'image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/tiff',
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'text/plain', 'text/csv',
        'application/dicom',
        'application/zip',
        'video/mp4',
        'audio/mpeg'
    ]
    
    file_type = file_obj.content_type
    file_name = file_obj.name.lower()
    
    # Check by content type
    if file_type not in allowed_types:
        # Also check by extension
        allowed_extensions = [
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx',
            '.txt', '.csv', '.dcm', '.zip', '.mp4', '.mp3'
        ]
        
        if not any(file_name.endswith(ext) for ext in allowed_extensions):
            return Response({
                'valid': False,
                'error': 'File type not allowed'
            }, status=status.HTTP_200_OK)
    
    # Calculate file hash
    file_hash = hashlib.md5()
    for chunk in file_obj.chunks(8192):
        file_hash.update(chunk)
    
    return Response({
        'valid': True,
        'file_name': file_obj.name,
        'file_size': file_obj.size,
        'file_type': file_type,
        'file_hash': file_hash.hexdigest(),
        'message': 'File is valid for upload'
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def storage_usage(request):
    """
    Get storage usage information
    """
    if not request.user.is_staff:
        return Response({
            'error': 'Only administrators can view storage usage'
        }, status=status.HTTP_403_FORBIDDEN)
    
    total_size_bytes = UploadFile.objects.aggregate(
        total_size=Sum('size')
    )['total_size'] or 0
    
    total_files = UploadFile.objects.count()
    
    # Calculate storage limits (example values)
    storage_limit_gb = 100  # Example: 100GB limit
    used_gb = total_size_bytes / (1024 * 1024 * 1024)
    percentage_used = (used_gb / storage_limit_gb) * 100 if storage_limit_gb > 0 else 0
    
    return Response({
        'total_files': total_files,
        'total_size_gb': round(used_gb, 2),
        'storage_limit_gb': storage_limit_gb,
        'percentage_used': round(percentage_used, 2),
        'available_gb': round(storage_limit_gb - used_gb, 2),
        'avg_file_size_mb': round((total_size_bytes / total_files) / (1024 * 1024), 2) if total_files > 0 else 0
    }, status=status.HTTP_200_OK)


# ==================== HEALTH CHECK ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def uploads_health_check(request):
    """
    Health check for uploads app
    """
    from django.db import connection
    from django.core.files.storage import default_storage
    
    try:
        # Check database
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM uploads_uploadfile")
            upload_count = cursor.fetchone()[0]
        
        # Check storage
        storage_info = 'healthy'
        try:
            # Try to write a test file
            test_path = 'health_check_test.txt'
            default_storage.save(test_path, b'test')
            default_storage.delete(test_path)
        except Exception as e:
            storage_info = f'unhealthy: {str(e)}'
        
        return Response({
            'status': 'healthy',
            'database': 'connected',
            'storage': storage_info,
            'total_uploads': upload_count,
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        
        
        


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dicom_metadata(request, upload_id):
    """
    Get DICOM metadata for a medical imaging file
    """
    upload = get_object_or_404(UploadFile, id=upload_id)
    
    # Check permissions
    if not request.user.is_staff and upload.patient and upload.patient.primary_doctor != request.user:
        return Response({
            'error': 'You do not have permission to access this file'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Check if file is DICOM
    if upload.file_type not in DICOM_MIME_TYPES and not upload.file.name.lower().endswith(DICOM_FILE_EXTENSION):
        return Response({
            'error': 'File is not a DICOM medical image'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Try to get existing metadata
        metadata = upload.dicom_metadata
        
        return Response({
            'upload_id': str(upload.id),
            'file_name': upload.name,
            'metadata': DICOMMetadataSerializer(metadata).data
        }, status=status.HTTP_200_OK)
        
    except DICOMMetadata.DoesNotExist:
        # Try to extract metadata from file
        try:
            file_path = upload.file.path
            
            # Read DICOM file
            ds = pydicom.dcmread(file_path, stop_before_pixels=True)
            
            # Extract basic metadata
            dicom_metadata = DICOMMetadata.objects.create(
                upload=upload,
                modality=str(ds.get('Modality', '')),
                study_description=str(ds.get('StudyDescription', '')),
                series_description=str(ds.get('SeriesDescription', '')),
                rows=ds.get('Rows', None),
                columns=ds.get('Columns', None),
                patient_name=str(ds.get('PatientName', '')),
                patient_id=str(ds.get('PatientID', '')),
                patient_sex=str(ds.get('PatientSex', '')),
                study_instance_uid=str(ds.get('StudyInstanceUID', '')),
                series_instance_uid=str(ds.get('SeriesInstanceUID', ''))
            )
            
            return Response({
                'upload_id': str(upload.id),
                'file_name': upload.name,
                'message': 'DICOM metadata extracted successfully',
                'metadata': DICOMMetadataSerializer(dicom_metadata).data
            }, status=status.HTTP_200_OK)
            
        except InvalidDicomError:
            return Response({
                'error': 'File is not a valid DICOM format'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error reading DICOM file: {str(e)}")
            return Response({
                'error': f'Failed to read DICOM file: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def anonymize_dicom(request, upload_id):
    """
    Anonymize a DICOM file (remove patient identifying information)
    """
    upload = get_object_or_404(UploadFile, id=upload_id)
    
    # Check permissions
    if not request.user.is_staff and upload.patient and upload.patient.primary_doctor != request.user:
        return Response({
            'error': 'You do not have permission to anonymize this file'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Check if file is DICOM
    if upload.file_type not in DICOM_MIME_TYPES and not upload.file.name.lower().endswith(DICOM_FILE_EXTENSION):
        return Response({
            'error': 'File is not a DICOM medical image'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        file_path = upload.file.path
        
        # Read DICOM file
        ds = pydicom.dcmread(file_path)
        
        # Remove patient identifying information
        tags_to_remove = [
            'PatientName', 'PatientID', 'PatientBirthDate',
            'PatientSex', 'PatientAge', 'PatientAddress',
            'InstitutionName', 'InstitutionAddress',
            'ReferringPhysicianName', 'PhysicianOfRecord',
            'StudyDate', 'SeriesDate', 'AcquisitionDate'
        ]
        
        for tag in tags_to_remove:
            if hasattr(ds, tag):
                delattr(ds, tag)
        
        # Add anonymization note
        from datetime import datetime
        ds.AnonymizationNotes = "Anonymized for clinical use"
        ds.AnonymizationDate = datetime.now().strftime("%Y%m%d")
        
        # Save anonymized file (create new file)
        import os
        original_dir = os.path.dirname(file_path)
        original_name = os.path.basename(file_path)
        anonymized_path = os.path.join(original_dir, f"anonymized_{original_name}")
        
        ds.save_as(anonymized_path)
        
        # Update metadata
        try:
            metadata = upload.dicom_metadata
            metadata.is_anonymized = True
            metadata.anonymization_date = timezone.now()
            metadata.patient_name = ""
            metadata.patient_id = ""
            metadata.patient_birth_date = None
            metadata.institution_name = ""
            metadata.save()
        except DICOMMetadata.DoesNotExist:
            pass
        
        # Log the action
        logger.info(f"DICOM file anonymized: {upload_id} by user {request.user.id}")
        
        return Response({
            'message': 'DICOM file anonymized successfully',
            'anonymized_path': anonymized_path,
            'original_file': upload.name,
            'anonymized_at': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error anonymizing DICOM file: {str(e)}")
        return Response({
            'error': f'Failed to anonymize DICOM file: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_consent(request, upload_id):
    """
    Update patient consent for an upload (HIPAA/GDPR requirement)
    """
    upload = get_object_or_404(UploadFile, id=upload_id)
    
    # Check permissions - only staff or patient's doctor can update consent
    if not request.user.is_staff:
        if not upload.patient:
            return Response({
                'error': 'Cannot update consent for upload without patient'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if upload.patient.primary_doctor != request.user:
            return Response({
                'error': 'You do not have permission to update consent for this file'
            }, status=status.HTTP_403_FORBIDDEN)
    
    serializer = ConsentUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    consent_granted = serializer.validated_data['consent_granted']
    consent_type = serializer.validated_data['consent_type']
    
    
    # Update consent
    upload.patient_consent = consent_granted
    
    if consent_granted:
        upload.consent_date = timezone.now()
    else:
        upload.consent_date = None
    
    upload.save()
    
    # Log consent update
    logger.info(f"Consent updated for upload {upload_id}: {consent_type} = {consent_granted} by user {request.user.id}")
    
    return Response({
        'message': f'Consent for {consent_type} updated successfully',
        'upload_id': str(upload.id),
        'patient_consent': upload.patient_consent,
        'consent_date': upload.consent_date,
        'consent_type': consent_type,
        'updated_by': request.user.id,
        'updated_at': timezone.now().isoformat()
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_uploads(request):
    """
    Search uploads by name, patient, or DICOM metadata
    """
    search_term = request.query_params.get('q', '')
    category = request.query_params.get('category')
    patient_id = request.query_params.get('patient_id')
    
    if not search_term and not category and not patient_id:
        return Response({
            'error': 'Please provide a search term, category, or patient_id'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Start with all uploads user can access
    if request.user.is_staff:
        uploads = UploadFile.objects.all()
    else:
        # Get user's patients
        patient_ids = Patient.objects.filter(
            Q(primary_doctor=request.user) | Q(consulting_doctors=request.user)
        ).distinct().values_list('id', flat=True)
        
        uploads = UploadFile.objects.filter(patient_id__in=patient_ids)
    
    # Apply search filters
    if search_term:
        uploads = uploads.filter(
            Q(name__icontains=search_term) |
            Q(file_type__icontains=search_term) |
            Q(patient__full_name__icontains=search_term) |
            Q(patient__national_id__icontains=search_term)
        )
    
    if category:
        uploads = uploads.filter(category=category)
    
    if patient_id:
        uploads = uploads.filter(patient_id=patient_id)
    
    # Limit results
    uploads = uploads.order_by('-created_at')[:50]
    
    serializer = UploadFileMinimalSerializer(uploads, many=True, context={'request': request})
    
    return Response({
        'count': uploads.count(),
        'results': serializer.data,
        'search_term': search_term,
        'category': category,
        'patient_id': patient_id
    }, status=status.HTTP_200_OK)
