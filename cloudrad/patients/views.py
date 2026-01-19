from django.shortcuts import render

# Create your views here.
# patients/views.py
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Avg, Sum
from django.db.models.functions import TruncMonth
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime, timedelta, date
from django.core.cache import cache
import json

from .models import Patient, PatientStats, Insurance
from .serializers import (
    PatientSerializer, PatientCreateSerializer, PatientUpdateSerializer,
    PatientListSerializer, PatientMinimalSerializer,
    PatientStatsSerializer, InsuranceSerializer
)
from users.models import User, UserStats
from communications.models import Message
from uploads.models import UploadFile
import logging
from django.db import transaction

logger = logging.getLogger(__name__)


# ==================== PATIENT CRUD VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def patient_list(request):
    """
    List all patients with filtering and pagination
    """
    patients = Patient.objects.select_related(
        'primary_doctor', 'stats'
    ).prefetch_related('uploads').order_by('-created_at')
    
    # Apply filters
    status_filter = request.query_params.get('status')
    blood_type = request.query_params.get('blood_type')
    gender = request.query_params.get('gender')
    city = request.query_params.get('city')
    country = request.query_params.get('country')
    doctor_id = request.query_params.get('doctor_id')
    search = request.query_params.get('search')
    is_archived = request.query_params.get('is_archived', 'false')
    
    if status_filter:
        patients = patients.filter(status=status_filter)
    
    if blood_type:
        patients = patients.filter(blood_type=blood_type)
    
    if gender:
        patients = patients.filter(gender=gender)
    
    if city:
        patients = patients.filter(city__icontains=city)
    
    if country:
        patients = patients.filter(country__icontains=country)
    
    if doctor_id:
        patients = patients.filter(primary_doctor_id=doctor_id)
    
    # Archive filter - default to show only active patients
    if is_archived.lower() == 'true':
        patients = patients.filter(is_archived=True)
    elif is_archived.lower() == 'false':
        patients = patients.filter(is_archived=False)
    
    if search:
        patients = patients.filter(
            Q(full_name__icontains=search) |
            Q(national_id__icontains=search) |
            Q(phone__icontains=search) |
            Q(email__icontains=search) |
            Q(city__icontains=search) |
            Q(country__icontains=search)
        )
    
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
    
    paginator = Paginator(patients, page_size)
    try:
        paginated_patients = paginator.page(page)
    except:
        return Response({
            'error': 'Invalid page number'
        }, status=status.HTTP_400_BAD_REQUEST)
        raise
    
    serializer = PatientListSerializer(paginated_patients, many=True, context={'request': request})
    
    # Get counts for filters
    total_count = patients.count()
    active_count = patients.filter(status='Active').count()
    critical_count = patients.filter(status='Critical').count()
    
    return Response({
        'count': total_count,
        'page': page,
        'page_size': page_size,
        'total_pages': paginator.num_pages,
        'active_count': active_count,
        'critical_count': critical_count,
        'results': serializer.data
    }, status=status.HTTP_200_OK)


# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
# def create_patient(request):
#     """
#     Create a new patient
#     """
#     serializer = PatientCreateSerializer(data=request.data, context={'request': request})
    
#     if serializer.is_valid():
#         with transaction.atomic():
#             patient = serializer.save()
            
#             # Create PatientStats for the new patient
#             PatientStats.objects.create(patient=patient)
            
#             # If primary_doctor is specified, increment their patient count
#             if patient.primary_doctor:
#                 try:
#                     stats = patient.primary_doctor.stats
#                     stats.patients += 1
#                     stats.save()
#                 except UserStats.DoesNotExist:
#                     pass
        
#         return Response({
#             'message': 'Patient created successfully',
#             'patient': PatientSerializer(patient, context={'request': request}).data
#         }, status=status.HTTP_201_CREATED)
    
#     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_patient(request):
    """
    Create a new patient
    """
    # Add current user as primary_doctor if not specified
    data = request.data.copy()
    
    # Auto-assign current doctor if not specified
    if 'primary_doctor' not in data and request.user.role == 'doctor':
        data['primary_doctor'] = str(request.user.id)
    
    serializer = PatientCreateSerializer(data=data, context={'request': request})
    
    if serializer.is_valid():
        with transaction.atomic():
            patient = serializer.save()
            
            # Create PatientStats for the new patient
            PatientStats.objects.create(patient=patient)
            
            # If primary_doctor is specified, increment their patient count
            if patient.primary_doctor:
                try:
                    stats = patient.primary_doctor.stats
                    stats.patients += 1
                    stats.save()
                except UserStats.DoesNotExist:
                    pass
        
        return Response({
            'message': 'Patient created successfully',
            'patient': PatientSerializer(patient, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def patient_detail(request, patient_id):
    """
    Get patient details
    """
    patient = get_object_or_404(Patient.objects.select_related(
        'primary_doctor', 'stats'
    ).prefetch_related('uploads'), id=patient_id)
    
    # Check permissions - doctors can see their own patients or if admin
    if patient.primary_doctor != request.user and not request.user.is_staff:
        return Response({
            'error': 'You do not have permission to view this patient'
        }, status=status.HTTP_403_FORBIDDEN)
    
    serializer = PatientSerializer(patient, context={'request': request})
    
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_patient(request, patient_id):
    """
    Update patient information
    """
    patient = get_object_or_404(Patient, id=patient_id)

    # Check permissions
    if not _has_permission_to_update(request.user, patient):
        return Response({
            'error': 'You can only update your own patients'
        }, status=status.HTTP_403_FORBIDDEN)

    partial = request.method == 'PATCH'
    serializer = PatientUpdateSerializer(patient, data=request.data, partial=partial)

    if serializer.is_valid():
        old_doctor = patient.primary_doctor
        patient = serializer.save()

        _handle_doctor_change(old_doctor, patient.primary_doctor)

        return Response({
            'message': 'Patient updated successfully',
            'patient': PatientSerializer(patient, context={'request': request}).data
        }, status=status.HTTP_200_OK)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

def _has_permission_to_update(user, patient):
    return patient.primary_doctor == user or user.is_staff

def _handle_doctor_change(old_doctor, new_doctor):
    if old_doctor != new_doctor:
        _update_doctor_patient_count(old_doctor, decrement=True)
        _update_doctor_patient_count(new_doctor, decrement=False)

def _update_doctor_patient_count(doctor, decrement):
    if doctor:
        try:
            stats = doctor.stats
            stats.patients = max(0, stats.patients - 1) if decrement else stats.patients + 1
            stats.save()
        except UserStats.DoesNotExist:
            pass

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_patient(request, patient_id):
    """
    Delete a patient (soft delete - archive)
    """
    patient = get_object_or_404(Patient, id=patient_id)
    
    # Check permissions
    if patient.primary_doctor != request.user and not request.user.is_staff:
        return Response({
            'error': 'You can only delete your own patients'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Soft delete - archive the patient
    patient.is_archived = True
    patient.is_active = False
    patient.status = 'Inactive'
    patient.save()
    
    # Decrement doctor's patient count
    if patient.primary_doctor:
        try:
            stats = patient.primary_doctor.stats
            stats.patients = max(0, stats.patients - 1)
            stats.save()
        except UserStats.DoesNotExist:
            pass
    
    return Response({
        'message': 'Patient archived successfully'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def restore_patient(request, patient_id):
    """
    Restore an archived patient
    """
    patient = get_object_or_404(Patient, id=patient_id)
    
    # Check permissions
    if patient.primary_doctor != request.user and not request.user.is_staff:
        return Response({
            'error': 'You can only restore your own patients'
        }, status=status.HTTP_403_FORBIDDEN)
    
    if not patient.is_archived:
        return Response({
            'error': 'Patient is not archived'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    patient.is_archived = False
    patient.is_active = True
    patient.status = 'Active'
    patient.save()
    
    # Increment doctor's patient count
    if patient.primary_doctor:
        try:
            stats = patient.primary_doctor.stats
            stats.patients += 1
            stats.save()
        except UserStats.DoesNotExist:
            pass
    
    return Response({
        'message': 'Patient restored successfully',
        'patient': PatientSerializer(patient, context={'request': request}).data
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def permanent_delete_patient(request, patient_id):
    """
    Permanently delete a patient (admin only)
    """
    if not request.user.is_staff:
        return Response({
            'error': 'Only administrators can permanently delete patients'
        }, status=status.HTTP_403_FORBIDDEN)
    
    patient = get_object_or_404(Patient, id=patient_id)
    
    # Check if patient is archived first
    if not patient.is_archived:
        return Response({
            'error': 'Patient must be archived before permanent deletion'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Decrement doctor's patient count
    if patient.primary_doctor:
        try:
            stats = patient.primary_doctor.stats
            stats.patients = max(0, stats.patients - 1)
            stats.save()
        except UserStats.DoesNotExist:
            pass
    
    patient.delete()
    
    return Response({
        'message': 'Patient permanently deleted'
    }, status=status.HTTP_200_OK)


# ==================== BULK OPERATIONS ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_update_patients(request):
    """
    Bulk update patients (status, doctor, etc.)
    """
    if not request.user.is_staff:
        return Response({
            'error': 'Only administrators can perform bulk updates'
        }, status=status.HTTP_403_FORBIDDEN)

    patient_ids = request.data.get('patient_ids', [])
    updates = request.data.get('updates', {})

    error_response = _validate_bulk_update_inputs(patient_ids, updates)
    if error_response:
        return error_response

    patients = Patient.objects.filter(id__in=patient_ids)
    updated_count = patients.count()

    if 'primary_doctor' in updates:
        error_response = _handle_bulk_doctor_update(patients, updates['primary_doctor'])
        if error_response:
            return error_response

    patients.update(**updates)

    return Response({
        'message': f'{updated_count} patients updated successfully',
        'updated_count': updated_count
    }, status=status.HTTP_200_OK)

def _validate_bulk_update_inputs(patient_ids, updates):
    if not isinstance(patient_ids, list):
        return Response({
            'error': 'patient_ids must be a list'
        }, status=status.HTTP_400_BAD_REQUEST)

    if not patient_ids:
        return Response({
            'error': 'No patient IDs provided'
        }, status=status.HTTP_400_BAD_REQUEST)

    if not updates:
        return Response({
            'error': 'No updates provided'
        }, status=status.HTTP_400_BAD_REQUEST)

    allowed_fields = ['status', 'primary_doctor', 'is_active', 'city', 'country']
    for field in updates.keys():
        if field not in allowed_fields:
            return Response({
                'error': f'Field "{field}" is not allowed for bulk update'
            }, status=status.HTTP_400_BAD_REQUEST)

    return None

def _handle_bulk_doctor_update(patients, new_doctor_id):
    try:
        new_doctor = User.objects.get(id=new_doctor_id)
    except User.DoesNotExist:
        return Response({
            'error': 'Doctor not found'
        }, status=status.HTTP_400_BAD_REQUEST)

    for patient in patients:
        old_doctor = patient.primary_doctor
        if old_doctor != new_doctor:
            _update_doctor_patient_count(old_doctor, decrement=True)
            _update_doctor_patient_count(new_doctor, decrement=False)

    return None

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_archive_patients(request):
    """
    Bulk archive patients
    """
    if not request.user.is_staff:
        return Response({
            'error': 'Only administrators can perform bulk archiving'
        }, status=status.HTTP_403_FORBIDDEN)
    
    patient_ids = request.data.get('patient_ids', [])
    
    if not isinstance(patient_ids, list):
        return Response({
            'error': 'patient_ids must be a list'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not patient_ids:
        return Response({
            'error': 'No patient IDs provided'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    patients = Patient.objects.filter(id__in=patient_ids, is_archived=False)
    archived_count = patients.count()
    
    # Update patient counts for doctors
    for patient in patients:
        if patient.primary_doctor:
            try:
                stats = patient.primary_doctor.stats
                stats.patients = max(0, stats.patients - 1)
                stats.save()
            except UserStats.DoesNotExist:
                pass
    
    patients.update(is_archived=True, is_active=False, status='Inactive')
    
    return Response({
        'message': f'{archived_count} patients archived',
        'archived_count': archived_count
    }, status=status.HTTP_200_OK)


# ==================== SEARCH & FILTER ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_patients(request):
    """
    Search patients by various criteria
    """
    query = request.query_params.get('q', '').strip()
    
    if not query or len(query) < 2:
        return Response({
            'error': 'Search query must be at least 2 characters long'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    patients = Patient.objects.filter(
        Q(full_name__icontains=query) |
        Q(national_id__icontains=query) |
        Q(phone__icontains=query) |
        Q(email__icontains=query) |
        Q(city__icontains=query) |
        Q(country__icontains=query) |
        Q(emergency_contact_name__icontains=query) |
        Q(emergency_contact_phone__icontains=query)
    ).filter(is_archived=False).select_related('primary_doctor').order_by('-created_at')[:50]
    
    serializer = PatientListSerializer(patients, many=True, context={'request': request})
    
    return Response({
        'count': patients.count(),
        'query': query,
        'results': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def doctor_patients(request, doctor_id=None):
    """
    Get patients for a specific doctor
    """
    if doctor_id:
        doctor = get_object_or_404(User, id=doctor_id)
    else:
        doctor = request.user
    
    # Check permissions
    if doctor != request.user and not request.user.is_staff:
        return Response({
            'error': 'You can only view your own patients'
        }, status=status.HTTP_403_FORBIDDEN)
    
    patients = Patient.objects.filter(
        primary_doctor=doctor,
        is_archived=False
    ).select_related('stats').order_by('-created_at')
    
    # Apply status filter if provided
    status_filter = request.query_params.get('status')
    if status_filter:
        patients = patients.filter(status=status_filter)
    
    serializer = PatientListSerializer(patients, many=True, context={'request': request})
    
    # Get statistics for this doctor's patients
    total_patients = patients.count()
    active_patients = patients.filter(status='Active').count()
    critical_patients = patients.filter(status='Critical').count()
    
    return Response({
        'doctor_id': str(doctor.id),
        'doctor_name': doctor.get_full_name(),
        'total_patients': total_patients,
        'active_patients': active_patients,
        'critical_patients': critical_patients,
        'patients': serializer.data
    }, status=status.HTTP_200_OK)


# ==================== PATIENT STATS VIEWS ====================
@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def patient_stats(request, patient_id):
    """
    Get or update patient statistics
    """
    patient = get_object_or_404(Patient, id=patient_id)
    
    # Check permissions
    if patient.primary_doctor != request.user and not request.user.is_staff:
        return Response({
            'error': 'You can only view stats for your own patients'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        stats = patient.stats
    except PatientStats.DoesNotExist:
        stats = PatientStats.objects.create(patient=patient)
    
    if request.method == 'GET':
        serializer = PatientStatsSerializer(stats)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        serializer = PatientStatsSerializer(stats, data=request.data, partial=partial)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Patient stats updated',
                'stats': serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_appointment_rate(request, patient_id):
    """
    Update patient's appointment rate
    """
    patient = get_object_or_404(Patient, id=patient_id)
    
    # Check permissions
    if patient.primary_doctor != request.user and not request.user.is_staff:
        return Response({
            'error': 'You can only update stats for your own patients'
        }, status=status.HTTP_403_FORBIDDEN)
    
    rate = request.data.get('rate')
    
    if rate is None:
        return Response({
            'error': 'Rate is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        rate = float(rate)
        if not 0 <= rate <= 100:
            raise ValueError
    except (ValueError, TypeError):
        return Response({
            'error': 'Rate must be a number between 0 and 100'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        stats = patient.stats
    except PatientStats.DoesNotExist:
        stats = PatientStats.objects.create(patient=patient)
    
    stats.appointment_rate = rate
    stats.save()
    
    return Response({
        'message': 'Appointment rate updated',
        'appointment_rate': rate
    }, status=status.HTTP_200_OK)


# ==================== INSURANCE VIEWS ====================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def patient_insurances(request, patient_id):
    """
    Get or create insurance records for a patient
    """
    patient = get_object_or_404(Patient, id=patient_id)
    
    # Check permissions
    if patient.primary_doctor != request.user and not request.user.is_staff:
        return Response({
            'error': 'You can only manage insurance for your own patients'
        }, status=status.HTTP_403_FORBIDDEN)
    
    if request.method == 'GET':
        # Return patient's insurance info from patient model
        return Response({
            'provider': patient.insurance_provider,
            'policy_number': patient.insurance_policy_number,
            'expiry_date': patient.insurance_expiry_date,
            'is_valid': patient.insurance_expiry_date and patient.insurance_expiry_date >= date.today()
        }, status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        # Update patient's insurance info
        provider = request.data.get('provider', '')
        policy_number = request.data.get('policy_number', '')
        expiry_date = request.data.get('expiry_date')
        
        if not all([provider, policy_number, expiry_date]):
            return Response({
                'error': 'Provider, policy number, and expiry date are all required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({
                'error': 'Invalid date format. Use YYYY-MM-DD'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        patient.insurance_provider = provider
        patient.insurance_policy_number = policy_number
        patient.insurance_expiry_date = expiry_date
        patient.save()
        
        return Response({
            'message': 'Insurance information updated',
            'insurance': {
                'provider': provider,
                'policy_number': policy_number,
                'expiry_date': expiry_date,
                'is_valid': expiry_date >= date.today()
            }
        }, status=status.HTTP_200_OK)


# ==================== MEDICAL INFO VIEWS ====================
@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def patient_allergies(request, patient_id):
    """
    Get or update patient allergies
    """
    patient = get_object_or_404(Patient, id=patient_id)
    
    # Check permissions
    if patient.primary_doctor != request.user and not request.user.is_staff:
        return Response({
            'error': 'You can only manage allergies for your own patients'
        }, status=status.HTTP_403_FORBIDDEN)
    
    if request.method == 'GET':
        return Response({
            'allergies': patient.allergies
        }, status=status.HTTP_200_OK)
    
    elif request.method in ['PUT', 'PATCH']:
        allergies = request.data.get('allergies')
        
        if allergies is None:
            return Response({
                'error': 'Allergies data is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not isinstance(allergies, list):
            return Response({
                'error': 'Allergies must be a list'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        patient.allergies = allergies
        patient.save()
        
        return Response({
            'message': 'Allergies updated',
            'allergies': patient.allergies
        }, status=status.HTTP_200_OK)


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def patient_medical_history(request, patient_id):
    """
    Get or update patient medical history
    """
    patient = get_object_or_404(Patient, id=patient_id)
    
    # Check permissions
    if patient.primary_doctor != request.user and not request.user.is_staff:
        return Response({
            'error': 'You can only manage medical history for your own patients'
        }, status=status.HTTP_403_FORBIDDEN)
    
    if request.method == 'GET':
        return Response({
            'medical_history': patient.medical_history,
            'medications': patient.medications
        }, status=status.HTTP_200_OK)
    
    elif request.method in ['PUT', 'PATCH']:
        medical_history = request.data.get('medical_history', '')
        medications = request.data.get('medications', '')
        
        patient.medical_history = medical_history
        patient.medications = medications
        patient.save()
        
        return Response({
            'message': 'Medical information updated',
            'medical_history': patient.medical_history,
            'medications': patient.medications
        }, status=status.HTTP_200_OK)


# ==================== EMERGENCY CONTACT VIEWS ====================
@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def patient_emergency_contact(request, patient_id):
    """
    Get or update patient emergency contact
    """
    patient = get_object_or_404(Patient, id=patient_id)
    
    # Check permissions
    if patient.primary_doctor != request.user and not request.user.is_staff:
        return Response({
            'error': 'You can only manage emergency contact for your own patients'
        }, status=status.HTTP_403_FORBIDDEN)
    
    if request.method == 'GET':
        return Response({
            'name': patient.emergency_contact_name,
            'phone': patient.emergency_contact_phone,
            'relationship': patient.emergency_contact_relationship
        }, status=status.HTTP_200_OK)
    
    elif request.method in ['PUT', 'PATCH']:
        name = request.data.get('name')
        phone = request.data.get('phone')
        relationship = request.data.get('relationship')
        
        if not all([name, phone, relationship]):
            return Response({
                'error': 'Name, phone, and relationship are all required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        patient.emergency_contact_name = name
        patient.emergency_contact_phone = phone
        patient.emergency_contact_relationship = relationship
        patient.save()
        
        return Response({
            'message': 'Emergency contact updated',
            'emergency_contact': {
                'name': name,
                'phone': phone,
                'relationship': relationship
            }
        }, status=status.HTTP_200_OK)


# ==================== STATISTICS & ANALYTICS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def patient_statistics(request):
    """
    Get patient statistics for the system
    """
    if not request.user.is_staff:
        return Response({
            'error': 'Only administrators can view system statistics'
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Use cache for expensive queries
    cache_key = 'patient_statistics'
    cached_data = cache.get(cache_key)
    
    if cached_data:
        return Response(cached_data, status=status.HTTP_200_OK)
    
    # Total counts
    total_patients = Patient.objects.count()
    active_patients = Patient.objects.filter(is_active=True).count()
    archived_patients = Patient.objects.filter(is_archived=True).count()
    
    # Patients by status
    patients_by_status = Patient.objects.values('status').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Patients by gender
    patients_by_gender = Patient.objects.values('gender').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Patients by blood type
    patients_by_blood_type = Patient.objects.values('blood_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Patients by city
    patients_by_city = Patient.objects.values('city').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # Recent registrations
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    patients_today = Patient.objects.filter(created_at__date=today).count()
    patients_this_week = Patient.objects.filter(created_at__date__gte=week_ago).count()
    patients_this_month = Patient.objects.filter(created_at__date__gte=month_ago).count()
    
    # Age distribution
    age_distribution = {
        '0-18': Patient.objects.filter(dob__gte=date(today.year-18, today.month, today.day)).count(),
        '19-30': Patient.objects.filter(
            dob__lt=date(today.year-18, today.month, today.day),
            dob__gte=date(today.year-30, today.month, today.day)
        ).count(),
        '31-50': Patient.objects.filter(
            dob__lt=date(today.year-30, today.month, today.day),
            dob__gte=date(today.year-50, today.month, today.day)
        ).count(),
        '51-70': Patient.objects.filter(
            dob__lt=date(today.year-50, today.month, today.day),
            dob__gte=date(today.year-70, today.month, today.day)
        ).count(),
        '71+': Patient.objects.filter(dob__lt=date(today.year-70, today.month, today.day)).count()
    }
    
    data = {
        'total_patients': total_patients,
        'active_patients': active_patients,
        'archived_patients': archived_patients,
        'patients_today': patients_today,
        'patients_this_week': patients_this_week,
        'patients_this_month': patients_this_month,
        'patients_by_status': list(patients_by_status),
        'patients_by_gender': list(patients_by_gender),
        'patients_by_blood_type': list(patients_by_blood_type),
        'patients_by_city': list(patients_by_city),
        'age_distribution': age_distribution
    }
    
    # Cache for 5 minutes
    cache.set(cache_key, data, 300)
    
    return Response(data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def doctor_patient_statistics(request, doctor_id=None):
    """
    Get patient statistics for a specific doctor
    """
    if doctor_id:
        doctor = get_object_or_404(User, id=doctor_id)
    else:
        doctor = request.user
    
    # Check permissions
    if doctor != request.user and not request.user.is_staff:
        return Response({
            'error': 'You can only view your own statistics'
        }, status=status.HTTP_403_FORBIDDEN)
    
    cache_key = f'doctor_patient_stats_{doctor.id}'
    cached_data = cache.get(cache_key)
    
    if cached_data:
        return Response(cached_data, status=status.HTTP_200_OK)
    
    patients = Patient.objects.filter(primary_doctor=doctor, is_archived=False)
    
    total_patients = patients.count()
    active_patients = patients.filter(status='Active').count()
    critical_patients = patients.filter(status='Critical').count()
    
    # Patients by status
    patients_by_status = patients.values('status').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Recent patients
    month_ago = timezone.now() - timedelta(days=30)
    recent_patients = patients.filter(created_at__gte=month_ago).count()
    
    # Average patient stats
    avg_appointment_rate = patients.aggregate(
        avg=Avg('stats__appointment_rate')
    )['avg'] or 0
    
    avg_follow_up_rate = patients.aggregate(
        avg=Avg('stats__follow_up_rate')
    )['avg'] or 0
    
    data = {
        'doctor_id': str(doctor.id),
        'doctor_name': doctor.get_full_name(),
        'total_patients': total_patients,
        'active_patients': active_patients,
        'critical_patients': critical_patients,
        'recent_patients': recent_patients,
        'avg_appointment_rate': round(avg_appointment_rate, 2),
        'avg_follow_up_rate': round(avg_follow_up_rate, 2),
        'patients_by_status': list(patients_by_status)
    }
    
    cache.set(cache_key, data, 300)
    
    return Response(data, status=status.HTTP_200_OK)


# ==================== EXPORT & IMPORT ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_patients(request):
    """
    Export patients data (CSV/JSON format)
    """
    if not request.user.is_staff:
        return Response({
            'error': 'Only administrators can export patient data'
        }, status=status.HTTP_403_FORBIDDEN)
    
    format_type = request.query_params.get('format', 'json').lower()
    
    if format_type not in ['json', 'csv']:
        return Response({
            'error': 'Format must be either "json" or "csv"'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    patients = Patient.objects.filter(is_archived=False).select_related('primary_doctor')
    
    if format_type == 'json':
        data = list(patients.values(
            'national_id', 'full_name', 'date_of_birth', 'gender',
            'phone', 'email', 'blood_type', 'city', 'country',
            'status', 'created_at'
        ))
        
        return Response({
            'format': 'json',
            'count': len(data),
            'data': data
        }, status=status.HTTP_200_OK)
    
    elif format_type == 'csv':
        # In a real implementation, you would generate a CSV file
        # For now, return a placeholder response
        return Response({
            'message': 'CSV export endpoint',
            'note': 'Implement CSV generation logic here'
        }, status=status.HTTP_200_OK)


# ==================== HEALTH CHECK ====================
@api_view(['GET'])
@permission_classes([AllowAny])
def patients_health_check(request):
    """
    Health check for patients app
    """
    from django.db import connection
    
    try:
        # Check database
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM patients")
            patient_count = cursor.fetchone()[0]
        
        return Response({
            'status': 'healthy',
            'database': 'connected',
            'total_patients': patient_count,
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# ==================== DASHBOARD VIEWS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    """
    Get dashboard summary for the current user
    """
    user = request.user
    
    if user.is_staff:
        # Admin dashboard
        total_patients = Patient.objects.count()
        active_patients = Patient.objects.filter(is_active=True).count()
        critical_patients = Patient.objects.filter(status='Critical').count()
        
        # Recent activity
        today = timezone.now().date()
        new_patients_today = Patient.objects.filter(created_at__date=today).count()
        
        return Response({
            'role': 'admin',
            'total_patients': total_patients,
            'active_patients': active_patients,
            'critical_patients': critical_patients,
            'new_patients_today': new_patients_today
        }, status=status.HTTP_200_OK)
    
    else:
        # Doctor dashboard
        patients = Patient.objects.filter(primary_doctor=user, is_archived=False)
        total_patients = patients.count()
        active_patients = patients.filter(status='Active').count()
        critical_patients = patients.filter(status='Critical').count()
        
        # Recent patients
        week_ago = timezone.now() - timedelta(days=7)
        recent_patients = patients.filter(created_at__gte=week_ago).count()
        
        # Pending tasks
        pending_tests = patients.aggregate(
            total=Sum('stats__test_results_pending')
        )['total'] or 0
        
        return Response({
            'role': 'doctor',
            'total_patients': total_patients,
            'active_patients': active_patients,
            'critical_patients': critical_patients,
            'recent_patients': recent_patients,
            'pending_tests': pending_tests
        }, status=status.HTTP_200_OK)