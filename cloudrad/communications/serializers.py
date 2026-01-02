# communications/serializers.py
from rest_framework import serializers

from patients.models import Patient
from users.models import User
from .models import Message, Attachment
from users.serializers import UserMinimalSerializer
from patients.serializers import PatientMinimalSerializer
import uuid


class AttachmentSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    file_url = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    
    class Meta:
        model = Attachment
        fields = [
            'id',
            'message',
            'file',
            'file_url',
            'file_name',
            'file_type',
            'file_size',
            'file_size_mb',
            'uploaded_at'
        ]
        read_only_fields = ['id', 'uploaded_at', 'file_size', 'file_type', 'file_name']
    
    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None
    
    def get_file_size_mb(self, obj):
        if obj.file_size:
            return round(obj.file_size / (1024 * 1024), 2)
        return 0
    
    def validate_file(self, value):
        # Maximum file size: 10MB
        max_size = 10 * 1024 * 1024  # 10MB in bytes
        if value.size > max_size:
            raise serializers.ValidationError("File size cannot exceed 10MB.")
        
        # Allowed file types
        allowed_types = [
            'image/jpeg', 'image/png', 'image/gif',
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ]
        
        if value.content_type not in allowed_types:
            raise serializers.ValidationError("File type not allowed.")
        
        return value


class MessageSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    
    # Sender/Recipient details
    sender = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        write_only=True
    )
    sender_details = UserMinimalSerializer(source='sender', read_only=True)
    
    recipient = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False,
        allow_null=True
    )
    recipient_details = UserMinimalSerializer(source='recipient', read_only=True)
    
    # Patient details
    patient = serializers.PrimaryKeyRelatedField(
        queryset=Patient.objects.all(),
        required=False,
        allow_null=True
    )
    patient_details = PatientMinimalSerializer(source='patient', read_only=True)
    
    # Nested attachments
    attachments = AttachmentSerializer(many=True, read_only=True)
    
    # Computed fields
    has_attachments = serializers.SerializerMethodField()
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = Message
        fields = [
            'id',
            'sender',
            'sender_details',
            'recipient',
            'recipient_details',
            'message_type',
            'subject',
            'content',
            'timestamp',
            'is_read',
            'is_important',
            'priority',
            'status',
            'category',
            'patient',
            'patient_details',
            'announcement_type',
            'attachments_count',
            'attachments',
            'has_attachments',
            'time_ago'
        ]
        read_only_fields = [
            'id', 'timestamp', 'attachments_count', 'sender_details', 
            'recipient_details', 'patient_details', 'has_attachments',
            'time_ago'
        ]
    
    def get_has_attachments(self, obj):
        return obj.attachments_count > 0
    
    def get_time_ago(self, obj):
        from django.utils import timezone
        from django.utils.timesince import timesince
        
        now = timezone.now()
        difference = now - obj.timestamp
        
        if difference.days == 0:
            if difference.seconds < 60:
                return "Just now"
            elif difference.seconds < 3600:
                minutes = difference.seconds // 60
                return f"{minutes}m ago"
            else:
                hours = difference.seconds // 3600
                return f"{hours}h ago"
        elif difference.days == 1:
            return "Yesterday"
        elif difference.days < 7:
            return f"{difference.days}d ago"
        elif difference.days < 30:
            weeks = difference.days // 7
            return f"{weeks}w ago"
        else:
            months = difference.days // 30
            return f"{months}mo ago"
    
    def validate(self, data):
        # Validate message type requirements
        message_type = data.get('message_type')
        recipient = data.get('recipient')
        
        # For announcement type messages
        if message_type == 'announcement':
            if 'announcement_type' not in data:
                raise serializers.ValidationError({
                    'announcement_type': 'Announcement type is required for announcement messages.'
                })
            if recipient:
                raise serializers.ValidationError({
                    'recipient': 'Announcement messages should not have a specific recipient.'
                })
        
        # For regular messages (inbox/sent)
        if message_type in ['inbox', 'sent']:
            if not recipient:
                raise serializers.ValidationError({
                    'recipient': 'Recipient is required for inbox/sent messages.'
                })
            if recipient == self.context['request'].user:
                raise serializers.ValidationError({
                    'recipient': 'You cannot send a message to yourself.'
                })
        
        # For patient-related messages
        patient = data.get('patient')
        if patient and not recipient:
            raise serializers.ValidationError({
                'recipient': 'Recipient is required for patient-related messages.'
            })
        
        return data
    
    def create(self, validated_data):
        # Set sender from request if not provided
        request = self.context.get('request')
        if request and 'sender' not in validated_data:
            validated_data['sender'] = request.user
        
        # Set default status based on message type
        if validated_data.get('message_type') == 'announcement':
            validated_data['status'] = 'delivered'
        
        return super().create(validated_data)


class MessageCreateSerializer(serializers.ModelSerializer):
    """Serializer specifically for creating messages"""
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    
    class Meta:
        model = Message
        fields = [
            'id',
            'recipient',
            'message_type',
            'subject',
            'content',
            'is_important',
            'priority',
            'category',
            'patient',
            'announcement_type'
        ]
        read_only_fields = ['id']
    
    def validate(self, data):
        # Add sender to validated data
        request = self.context.get('request')
        if request:
            data['sender'] = request.user
        
        return data


class MessageUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating messages (mainly status and read flags)"""
    class Meta:
        model = Message
        fields = [
            'is_read',
            'is_important',
            'priority',
            'status'
        ]


class InboxMessageSerializer(serializers.ModelSerializer):
    """Serializer for inbox message list"""
    sender_details = UserMinimalSerializer(source='sender', read_only=True)
    patient_details = PatientMinimalSerializer(source='patient', read_only=True)
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = Message
        fields = [
            'id',
            'sender_details',
            'subject',
            'content_preview',
            'timestamp',
            'is_read',
            'is_important',
            'priority',
            'patient_details',
            'has_attachments',
            'time_ago'
        ]
    
    def get_content_preview(self, obj):
        if len(obj.content) > 100:
            return obj.content[:100] + '...'
        return obj.content
    
    def get_time_ago(self, obj):
        return MessageSerializer().get_time_ago(obj)
    
    def get_has_attachments(self, obj):
        return obj.attachments_count > 0


class SentMessageSerializer(serializers.ModelSerializer):
    """Serializer for sent message list"""
    recipient_details = UserMinimalSerializer(source='recipient', read_only=True)
    patient_details = PatientMinimalSerializer(source='patient', read_only=True)
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = Message
        fields = [
            'id',
            'recipient_details',
            'subject',
            'content_preview',
            'timestamp',
            'status',
            'patient_details',
            'has_attachments',
            'time_ago'
        ]
    
    def get_content_preview(self, obj):
        if len(obj.content) > 100:
            return obj.content[:100] + '...'
        return obj.content
    
    def get_time_ago(self, obj):
        return MessageSerializer().get_time_ago(obj)
    
    def get_has_attachments(self, obj):
        return obj.attachments_count > 0


class AnnouncementSerializer(serializers.ModelSerializer):
    """Serializer for announcements"""
    sender_details = UserMinimalSerializer(source='sender', read_only=True)
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = Message
        fields = [
            'id',
            'sender_details',
            'subject',
            'content',
            'announcement_type',
            'timestamp',
            'priority',
            'time_ago'
        ]
    
    def get_time_ago(self, obj):
        return MessageSerializer().get_time_ago(obj)


class AttachmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating attachments"""
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    
    class Meta:
        model = Attachment
        fields = [
            'id',
            'message',
            'file'
        ]
        read_only_fields = ['id']
    
    def create(self, validated_data):
        # Set file metadata
        file = validated_data['file']
        validated_data['file_name'] = file.name
        validated_data['file_type'] = file.content_type
        validated_data['file_size'] = file.size
        
        # Update message attachments count
        message = validated_data['message']
        message.attachments_count += 1
        message.save()
        
        return super().create(validated_data)