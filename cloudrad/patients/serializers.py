# patients/serializers.py
from rest_framework import serializers

from users.models import User
from .models import Insurance, Patient, PatientStats
from users.serializers import UserSerializer  # Assuming you have this
from datetime import date
import uuid


class InsuranceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Insurance
        fields = '__all__'
        read_only_fields = ('id',)


class PatientStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientStats
        fields = [
            'id',
            'appointment_rate',
            'follow_up_rate',
            'medication_adherence',
            'test_results_pending'
        ]
        read_only_fields = ('id', 'patient')


class PatientSerializer(serializers.ModelSerializer):
    # Read-only fields
    age = serializers.ReadOnlyField()
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    
    # Related fields - using primary key for write, full object for read
    primary_doctor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='doctor'),  # Assuming you have a role field
        required=False,
        allow_null=True
    )
    primary_doctor_details = UserSerializer(source='primary_doctor', read_only=True)
    
    # Nested stats
    stats = PatientStatsSerializer(read_only=True)
    
    # Custom validations
    def validate_date_of_birth(self, value):
        if value > date.today():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value
    
    def validate_emergency_contact_phone(self, value):
        if not value.replace('+', '').replace(' ', '').replace('-', '').isdigit():
            raise serializers.ValidationError("Emergency contact phone must contain only numbers.")
        return value
    
    def validate_phone(self, value):
        if not value.replace('+', '').replace(' ', '').replace('-', '').isdigit():
            raise serializers.ValidationError("Phone number must contain only numbers.")
        return value
    
    def validate(self, data):
        # Validate insurance data consistency
        insurance_fields = ['insurance_provider', 'insurance_policy_number', 'insurance_expiry_date']
        filled_fields = sum(1 for field in insurance_fields if data.get(field))
        
        if filled_fields > 0 and filled_fields < 3:
            raise serializers.ValidationError(
                "If providing insurance information, all insurance fields must be filled."
            )
        
        # Validate emergency contact
        if 'emergency_contact_phone' in data and 'emergency_contact_name' in data:
            if data.get('emergency_contact_phone') == data.get('phone'):
                raise serializers.ValidationError(
                    "Emergency contact phone cannot be the same as patient's phone."
                )
        
        return data
    
    class Meta:
        model = Patient
        fields = [
            'id',
            'primary_doctor',
            'primary_doctor_details',
            'national_id',
            'full_name',
            'date_of_birth',
            'age',
            'gender',
            'phone',
            'country_code',
            'email',
            'blood_type',
            'allergies',
            'medications',
            'medical_history',
            'address',
            'city',
            'postal_code',
            'country',
            'emergency_contact_name',
            'emergency_contact_phone',
            'emergency_contact_relationship',
            'insurance_provider',
            'insurance_policy_number',
            'insurance_expiry_date',
            'status',
            'is_active',
            'is_archived',
            'last_visit',
            'created_at',
            'updated_at',
            'stats'
        ]
        read_only_fields = [
            'id', 'age', 'created_at', 'updated_at', 'stats'
        ]
        extra_kwargs = {
            'national_id': {'validators': []},  # We'll handle uniqueness in view
            'email': {'required': False, 'allow_blank': True},
            'allergies': {'default': list},
            'medications': {'required': False, 'allow_blank': True},
            'medical_history': {'required': False, 'allow_blank': True},
        }


class PatientCreateSerializer(serializers.ModelSerializer):
    """Serializer specifically for creating patients"""
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)
    primary_doctor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='doctor'),
        required=False,
        allow_null=True
    )
    
    class Meta:
        model = Patient
        fields = [
            'id',
            'primary_doctor',
            'national_id',
            'full_name',
            'date_of_birth',
            'gender',
            'phone',
            'country_code',
            'email',
            'blood_type',
            'allergies',
            'medications',
            'medical_history',
            'address',
            'city',
            'postal_code',
            'country',
            'emergency_contact_name',
            'emergency_contact_phone',
            'emergency_contact_relationship',
            'insurance_provider',
            'insurance_policy_number',
            'insurance_expiry_date',
            'status',
        ]
        extra_kwargs = {
            'email': {'required': False, 'allow_blank': True},
            'allergies': {'default': list},
        }


class PatientUpdateSerializer(serializers.ModelSerializer):
    """Serializer specifically for updating patients"""
    class Meta:
        model = Patient
        fields = [
            'primary_doctor',
            'full_name',
            'date_of_birth',
            'gender',
            'phone',
            'country_code',
            'email',
            'blood_type',
            'allergies',
            'medications',
            'medical_history',
            'address',
            'city',
            'postal_code',
            'country',
            'emergency_contact_name',
            'emergency_contact_phone',
            'emergency_contact_relationship',
            'insurance_provider',
            'insurance_policy_number',
            'insurance_expiry_date',
            'status',
            'is_active',
            'is_archived',
            'last_visit',
        ]
        read_only_fields = ['national_id']  # National ID shouldn't be changed
        extra_kwargs = {
            'email': {'required': False, 'allow_blank': True},
        }


class PatientListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing patients"""
    age = serializers.ReadOnlyField()
    primary_doctor_name = serializers.CharField(source='primary_doctor.full_name', read_only=True)
    
    class Meta:
        model = Patient
        fields = [
            'id',
            'national_id',
            'full_name',
            'age',
            'gender',
            'phone',
            'email',
            'blood_type',
            'status',
            'city',
            'country',
            'primary_doctor_name',
            'last_visit',
            'created_at',
        ]


class PatientMinimalSerializer(serializers.ModelSerializer):
    """Minimal serializer for dropdowns or references"""
    class Meta:
        model = Patient
        fields = ['id', 'national_id', 'full_name', 'phone']