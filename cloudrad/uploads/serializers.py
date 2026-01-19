# uploads/serializers.py
from rest_framework import serializers

from patients.models import Patient
from .models import DICOMMetadata, UploadFile, ProcessingOptions
from patients.serializers import PatientMinimalSerializer
import uuid
import os
from django.core.files.storage import default_storage



class DICOMMetadataSerializer(serializers.ModelSerializer):
    """Serializer for DICOM metadata"""
    class Meta:
        model = DICOMMetadata
        fields = [
            'id',
            'modality',
            'study_description',
            'series_description',
            'rows',
            'columns',
            'patient_name',
            'patient_id',
            'patient_birth_date',
            'patient_sex',
            'study_instance_uid',
            'study_date',
            'accession_number',
            'series_instance_uid',
            'series_number',
            'bits_allocated',
            'pixel_spacing',
            'slice_thickness',
            'manufacturer',
            'institution_name',
            'is_anonymized',
            'anonymization_date',
            'created_at',
            'updated_at'
        ]
        read_only_fields = fields  # All fields are read-only


class UploadFileMinimalSerializer(serializers.ModelSerializer):
    """Minimal serializer for lists and dropdowns"""
    file_url = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    
    class Meta:
        model = UploadFile
        fields = [
            'id',
            'name',
            'file_url',
            'file_size_mb',
            'file_type',
            'status',
            'progress',
            'category',  # ADD THIS
            'created_at'
        ]
        read_only_fields = fields
    
    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request and obj.status == 'uploaded':
            return request.build_absolute_uri(obj.file.url)
        return None
    
    def get_file_size_mb(self, obj):
        if obj.size:
            return round(obj.size / (1024 * 1024), 2)
        return 0


class UploadFileSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    
    # Patient details
    patient = serializers.PrimaryKeyRelatedField(
        queryset=Patient.objects.all(),
        required=False,
        allow_null=True
    )
    patient_details = PatientMinimalSerializer(source='patient', read_only=True)
    
    # File information
    file_url = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    file_extension = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    file_size_kb = serializers.SerializerMethodField()
    
    # Read-only status fields
    status = serializers.CharField(read_only=True)
    progress = serializers.IntegerField(read_only=True)
    error_message = serializers.CharField(read_only=True)
    
    # Timestamps
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    
    # Processing options
    processing_options = serializers.SerializerMethodField()
    
    dicom_metadata = serializers.SerializerMethodField()
    
    uploaded_by_details = serializers.SerializerMethodField()
    
    class Meta:
        model = UploadFile
        fields = [
            'id',
            'name',
            'file',
            'file_url',
            'file_name',
            'file_extension',
            'size',
            'file_size_mb',
            'file_size_kb',
            'file_type',
            'last_modified',
            'status',
            'progress',
            'error_message',
            'patient',
            'patient_details',
            'processing_options',
            'dicom_metadata',  
            'category',  
            'uploaded_by',  
            'uploaded_by_details',  
            'patient_consent',  
            'consent_date',  
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id', 'size', 'file_type', 'status', 'progress', 
            'error_message', 'created_at', 'updated_at', 'file_url',
            'file_name', 'file_extension', 'file_size_mb', 'file_size_kb',
            'processing_options', 'dicom_metadata', 'uploaded_by_details'
        ]
    
    
    def get_uploaded_by_details(self, obj):
        if obj.uploaded_by:
            return {
                'id': obj.uploaded_by.id,
                'username': obj.uploaded_by.username,
                'email': obj.uploaded_by.email,
                'full_name': getattr(obj.uploaded_by, 'full_name', '')
            }
        return None
    
    
    def get_processing_options(self, obj):
        try:
            options = obj.processing_options
            return ProcessingOptionsSerializer(options).data
        except ProcessingOptions.DoesNotExist:
            return None
    
    
    def get_dicom_metadata(self, obj):
        try:
            metadata = obj.dicom_metadata
            return DICOMMetadataSerializer(metadata).data
        except DICOMMetadata.DoesNotExist:
            return None
    
    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None
    
    def get_file_name(self, obj):
        if obj.file:
            return os.path.basename(obj.file.name)
        return obj.name
    
    def get_file_extension(self, obj):
        if obj.file:
            return os.path.splitext(obj.file.name)[1].lower()
        return ''
    
    def get_file_size_mb(self, obj):
        if obj.size:
            return round(obj.size / (1024 * 1024), 2)
        return 0
    
    def get_file_size_kb(self, obj):
        if obj.size:
            return round(obj.size / 1024, 2)
        return 0
    
    
    
    def validate(self, data):
        # Set name from file if not provided
        if 'file' in data and 'name' not in data:
            file_name = os.path.splitext(data['file'].name)[0]
            data['name'] = file_name
        
        # Set category based on file type
        if 'file' in data and 'category' not in data:
            file_type = data['file'].content_type
            if 'dicom' in file_type or data['file'].name.lower().endswith('.dcm'):
                data['category'] = 'other'  # Will be updated based on DICOM metadata
            elif 'image' in file_type:
                data['category'] = 'photo'
            elif 'pdf' in file_type:
                data['category'] = 'document'
            else:
                data['category'] = 'other'
        
        # Validate file size (max 2GB)
        if 'file' in data:
            max_size = 2 * 1024 * 1024 * 1024  # 2GB in bytes
            if data['file'].size > max_size:
                raise serializers.ValidationError({
                    'file': 'File size cannot exceed 2GB.'
                })
            
            # Extract file type from content type
            content_type = data['file'].content_type
            if content_type:
                data['file_type'] = content_type
            
            # Set size
            data['size'] = data['file'].size
        
        return data
    
    def create(self, validated_data):
        # Get request user
        request = self.context.get('request')
        
        # Set initial status
        validated_data['status'] = 'pending'
        validated_data['progress'] = 0
        
        # Set uploaded_by if not set
        if 'uploaded_by' not in validated_data and request and request.user.is_authenticated:
            validated_data['uploaded_by'] = request.user
        
        # Save the upload
        upload = super().create(validated_data)
        
        # Create default processing options
        ProcessingOptions.objects.create(upload=upload)
        
        return upload


class UploadCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating uploads (with file handling)"""
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    
    # For chunked uploads support
    upload_id = serializers.CharField(required=False, write_only=True)
    chunk_index = serializers.IntegerField(required=False, write_only=True)
    total_chunks = serializers.IntegerField(required=False, write_only=True)
    
    category = serializers.ChoiceField(
        choices=UploadFile.CATEGORY_CHOICES,  # ADD THIS
        required=False,
        default='other'
    )
    
    class Meta:
        model = UploadFile
        fields = [
            'id',
            'name',
            'file',
            'patient',
            'category',
            'upload_id',
            'chunk_index',
            'total_chunks'
        ]
        read_only_fields = ['id']
    
    def validate(self, data):
        file_obj = data.get('file')
        
        if not file_obj:
            raise serializers.ValidationError({
                'file': 'File is required.'
            })
        
        # Validate file type
        allowed_types = [
            # Images
            'image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/tiff',
            'image/svg+xml', 'image/webp',
            
            # Documents
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-powerpoint',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'text/plain', 'text/csv',
            
            # Medical formats
            'application/dicom',
            'application/vnd.hzn-3d-crossword',
            
            # Archives
            'application/zip', 'application/x-rar-compressed',
            'application/x-tar', 'application/gzip',
            
            # Video
            'video/mp4', 'video/mpeg', 'video/quicktime', 'video/x-msvideo',
            
            # Audio
            'audio/mpeg', 'audio/wav', 'audio/ogg'
        ]
        
        content_type = file_obj.content_type
        if content_type not in allowed_types:
            # Also check by extension as fallback
            file_name = file_obj.name.lower()
            allowed_extensions = [
                '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.svg', '.webp',
                '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv',
                '.dcm', '.zip', '.rar', '.tar', '.gz',
                '.mp4', '.mpeg', '.mov', '.avi',
                '.mp3', '.wav', '.ogg'
            ]
            
            if not any(file_name.endswith(ext) for ext in allowed_extensions):
                raise serializers.ValidationError({
                    'file': 'File type not allowed. Please upload a supported file type.'
                })
        
        return data


class UploadUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating upload status and metadata"""
    patient_consent = serializers.BooleanField(required=False)
    class Meta:
        model = UploadFile
        fields = [
            'name',
            'status',
            'progress',
            'error_message',
            'patient',
            'patient_consent',  
            'category'
        ]
        read_only_fields = ['status', 'progress', 'error_message']
    
    def update(self, instance, validated_data):
        # Don't allow updating file itself
        if 'file' in validated_data:
            del validated_data['file']
        
        return super().update(instance, validated_data)


class UploadStatusSerializer(serializers.ModelSerializer):
    """Serializer for upload status/progress updates"""
    file_url = serializers.SerializerMethodField()
    category = serializers.CharField(read_only=True)
    class Meta:
        model = UploadFile
        fields = [
            'id',
            'name',
            'status',
            'progress',
            'error_message',
            'file_url',
            'category',
            'created_at',
            'updated_at'
        ]
        read_only_fields = fields
    
    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request and obj.status == 'uploaded':
            return request.build_absolute_uri(obj.file.url)
        return None


class ProcessingOptionsSerializer(serializers.ModelSerializer):
    upload_id = serializers.UUIDField(source='upload.id', read_only=True)
    upload_name = serializers.CharField(source='upload.name', read_only=True)
    
    
    upload_status = serializers.CharField(source='upload.status', read_only=True)
    upload_category = serializers.CharField(source='upload.category', read_only=True)
    class Meta:
        model = ProcessingOptions
        fields = [
            'id',
            'upload_id',
            'upload_name',
            'upload_status',  
            'upload_category',
            'auto_anonymize',
            'ai_analysis',
            'auto_3d',
            'send_notifications',
            'archive'
        ]
        read_only_fields = ['id', 'upload_id', 'upload_name']
    
    def create(self, validated_data):
        # Processing options should be created automatically with upload
        raise serializers.ValidationError(
            "Processing options are created automatically with uploads."
        )


class ProcessingOptionsUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating processing options"""
    compression_level = serializers.ChoiceField(
        choices=[('none', 'None'), ('lossless', 'Lossless'), ('lossy', 'Lossy')],
        required=False
    )
    output_format = serializers.ChoiceField(
        choices=[
            ('original', 'Original'),
            ('jpeg', 'JPEG'),
            ('png', 'PNG'),
            ('dicom', 'DICOM'),
            ('pdf', 'PDF')
        ],
        required=False
    )
    priority = serializers.ChoiceField(
        choices=[('low', 'Low'), ('normal', 'Normal'), ('high', 'High'), ('emergency', 'Emergency')],
        required=False
    )
    class Meta:
        model = ProcessingOptions
        fields = [
            'auto_anonymize',
            'ai_analysis',
            'auto_3d',
            'send_notifications',
            'archive',
            'compression_level',  
            'output_format',  
            'priority'
        ]


class PatientUploadsSerializer(serializers.ModelSerializer):
    """Serializer for listing patient's uploads"""
    file_url = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    file_extension = serializers.SerializerMethodField()
    
    category = serializers.CharField(read_only=True)
    class Meta:
        model = UploadFile
        fields = [
            'id',
            'name',
            'file_url',
            'file_size_mb',
            'file_extension',
            'file_type',
            'status',
            'progress',
            'category',
            'created_at'
        ]
        read_only_fields = fields
    
    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request and obj.status == 'uploaded':
            return request.build_absolute_uri(obj.file.url)
        return None
    
    def get_file_size_mb(self, obj):
        if obj.size:
            return round(obj.size / (1024 * 1024), 2)
        return 0
    
    def get_file_extension(self, obj):
        if obj.file:
            return os.path.splitext(obj.file.name)[1].lower()
        return ''


class ChunkedUploadSerializer(serializers.Serializer):
    """Serializer for handling chunked uploads"""
    upload_id = serializers.CharField(required=True)
    chunk_index = serializers.IntegerField(required=True, min_value=0)
    total_chunks = serializers.IntegerField(required=True, min_value=1)
    file = serializers.FileField(required=True)
    name = serializers.CharField(required=True)
    patient = serializers.PrimaryKeyRelatedField(
        queryset=Patient.objects.all(),
        required=False,
        allow_null=True
    )
    
    def validate(self, data):
        chunk_index = data.get('chunk_index')
        total_chunks = data.get('total_chunks')
        
        if chunk_index >= total_chunks:
            raise serializers.ValidationError({
                'chunk_index': f'Chunk index must be less than total chunks ({total_chunks}).'
            })
        
        return data


class UploadStatsSerializer(serializers.Serializer):
    """Serializer for upload statistics"""
    total_uploads = serializers.IntegerField()
    total_size_gb = serializers.FloatField()
    uploads_by_type = serializers.DictField()
    uploads_by_status = serializers.DictField()
    uploads_by_category = serializers.DictField()
    recent_uploads = serializers.ListField()
    
    class Meta:
        fields = [
            'total_uploads',
            'total_size_gb',
            'uploads_by_type',
            'uploads_by_status',
            'uploads_by_category',
            'recent_uploads'
        ]
        
        
        
class DICOMUploadSerializer(serializers.Serializer):
    """Special serializer for DICOM uploads with metadata extraction"""
    file = serializers.FileField(required=True)
    patient_id = serializers.PrimaryKeyRelatedField(
        queryset=Patient.objects.all(),
        required=True
    )
    extract_metadata = serializers.BooleanField(default=True)
    auto_anonymize = serializers.BooleanField(default=True)
    
    def validate_file(self, value):
        # Check if it's a DICOM file
        filename = value.name.lower()
        if not filename.endswith('.dcm'):
            raise serializers.ValidationError("Only DICOM files (.dcm) are allowed.")
        
        # Check file size
        max_size = 1 * 1024 * 1024 * 1024  # 1GB for DICOM
        if value.size > max_size:
            raise serializers.ValidationError("DICOM file size cannot exceed 1GB.")
        
        return value


class ConsentUpdateSerializer(serializers.Serializer):
    """Serializer for updating patient consent"""
    consent_granted = serializers.BooleanField(required=True)
    consent_type = serializers.ChoiceField(
        choices=[('storage', 'Storage'), ('processing', 'Processing'), ('sharing', 'Sharing')],
        default='processing'
    )
    expires_in_days = serializers.IntegerField(min_value=1, max_value=365, default=30)


class FileValidationSerializer(serializers.Serializer):
    """Serializer for file validation results"""
    valid = serializers.BooleanField()
    errors = serializers.ListField(child=serializers.CharField())
    warnings = serializers.ListField(child=serializers.CharField())
    metadata = serializers.DictField()
    recommendations = serializers.DictField()