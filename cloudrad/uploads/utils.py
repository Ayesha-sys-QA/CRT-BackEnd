# uploads/utils.py
import hashlib
import os
from django.conf import settings
import magic

def get_upload_directory(patient_id=None):
    """Get upload directory path - UPDATED with security improvements"""
    if patient_id:
        # Create date-based directory structure
        import datetime
        today = datetime.date.today()
        year = today.year
        month = today.month
        day = today.day
        
        # Create path like: patient_uploads/patient_id/2024/01/15/
        return os.path.join(
            'patient_uploads', 
            str(patient_id),
            str(year),
            f"{month:02d}",
            f"{day:02d}"
        )
    return 'patient_uploads'

def validate_file_type(file_obj):
    """Validate file type - UPDATED with actual content checking"""
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.pdf', '.dcm', '.zip']
    
    # Check extension
    file_name = file_obj.name.lower()
    if not any(file_name.endswith(ext) for ext in allowed_extensions):
        return False, "File extension not allowed"
    
    # ADD THIS: Check file content using magic
    try:
        # Reset file pointer
        file_obj.seek(0)
        
        # Read first 2048 bytes
        header = file_obj.read(2048)
        file_obj.seek(0)
        
        # Use python-magic to check actual file type
        mime = magic.Magic(mime=True)
        actual_type = mime.from_buffer(header)
        
        # Define allowed MIME types
        allowed_mime_types = {
            '.jpg': ['image/jpeg'],
            '.jpeg': ['image/jpeg'],
            '.png': ['image/png'],
            '.pdf': ['application/pdf'],
            '.dcm': ['application/dicom', 'application/octet-stream'],  # DICOM can vary
            '.zip': ['application/zip']
        }
        
        # Get expected MIME types for this extension
        file_ext = '.' + file_name.split('.')[-1] if '.' in file_name else ''
        expected_types = allowed_mime_types.get(file_ext, [])
        
        # Check if actual type matches expected
        if expected_types and actual_type not in expected_types:
            return False, f"File content ({actual_type}) doesn't match extension"
        
        return True, actual_type
        
    except ImportError:
        # If magic not installed, just do extension check
        return True, "unknown"
    except Exception as e:
        return False, f"Validation error: {str(e)}"




def calculate_file_hash(file_obj):
    """Calculate file hash for integrity checking - UPDATED to use SHA256"""
    # Use SHA256 instead of MD5 for security
    hash_sha256 = hashlib.sha256()
    
    # Reset file pointer
    original_position = file_obj.tell()
    file_obj.seek(0)
    
    try:
        for chunk in file_obj.chunks(4096):
            hash_sha256.update(chunk)
        
        # Also calculate MD5 for backward compatibility
        file_obj.seek(0)
        hash_md5 = hashlib.md5()
        for chunk in file_obj.chunks(4096):
            hash_md5.update(chunk)
            
        return {
            'sha256': hash_sha256.hexdigest(),
            'md5': hash_md5.hexdigest()  # Keep for compatibility
        }
    finally:
        file_obj.seek(original_position)



def validate_dicom_file(file_path):
    """
    Validate DICOM file structure
    Returns: (is_valid, error_message, metadata_dict)
    """
    try:
        import pydicom
        from pydicom.errors import InvalidDicomError
        
        # Check if file exists
        if not os.path.exists(file_path):
            return False, "File not found", None
        
        # Try to read DICOM file
        ds = pydicom.dcmread(file_path, stop_before_pixels=True)
        
        # Extract basic metadata
        metadata = {
            'modality': str(ds.get('Modality', '')),
            'study_description': str(ds.get('StudyDescription', '')),
            'series_description': str(ds.get('SeriesDescription', '')),
            'patient_name': str(ds.get('PatientName', '')),
            'patient_id': str(ds.get('PatientID', '')),
            'study_date': str(ds.get('StudyDate', '')),
            'rows': ds.get('Rows', 0),
            'columns': ds.get('Columns', 0),
            'has_pixel_data': hasattr(ds, 'pixel_array'),
            'is_valid_dicom': True
        }
        
        # Check for required DICOM fields
        required_fields = ['StudyInstanceUID', 'SeriesInstanceUID', 'SOPInstanceUID']
        missing_fields = []
        for field in required_fields:
            if not hasattr(ds, field):
                missing_fields.append(field)
        
        if missing_fields:
            return True, f"Missing optional DICOM fields: {', '.join(missing_fields)}", metadata
        
        return True, "Valid DICOM file", metadata
        
    except InvalidDicomError:
        return False, "Not a valid DICOM file format", None
    except Exception as e:
        return False, f"DICOM validation error: {str(e)}", None


def anonymize_dicom_file(input_path, output_path):
    """
    Anonymize DICOM file by removing patient identifying information (PHI)
    Returns: (success, error_message)
    """
    try:
        import pydicom
        from datetime import datetime
        
        # Read DICOM file
        ds = pydicom.dcmread(input_path)
        
        # Remove patient identifying information (PHI)
        phi_tags_to_remove = [
            'PatientName', 'PatientID', 'PatientBirthDate',
            'PatientSex', 'PatientAge', 'PatientAddress',
            'InstitutionName', 'InstitutionAddress',
            'ReferringPhysicianName', 'PhysicianOfRecord',
            'StudyDate', 'SeriesDate', 'AcquisitionDate',
            'StationName', 'InstitutionalDepartmentName'
        ]
        
        for tag in phi_tags_to_remove:
            if hasattr(ds, tag):
                delattr(ds, tag)
        
        # Add anonymization metadata
        ds.AnonymizationDate = datetime.now().strftime("%Y%m%d")
        ds.AnonymizationMethod = "CloudRad Medical System"
        ds.AnonymizationNotes = "De-identified for clinical use"
        
        # Save anonymized file
        ds.save_as(output_path)
        
        return True, "File anonymized successfully"
        
    except Exception as e:
        return False, f"Anonymization failed: {str(e)}"


def check_file_safety(file_obj):
    """
    Basic safety check for uploaded files
    Returns: (is_safe, warning_message)
    """
    # Check file size (max 2GB)
    max_size = 2 * 1024 * 1024 * 1024  # 2GB
    if file_obj.size > max_size:
        return False, f"File size exceeds {max_size/(1024*1024*1024)}GB limit"
    
    # Check for dangerous extensions
    dangerous_extensions = ['.exe', '.bat', '.cmd', '.ps1', '.sh', '.js', '.vbs']
    file_name = file_obj.name.lower()
    
    for ext in dangerous_extensions:
        if file_name.endswith(ext):
            return False, f"Dangerous file extension: {ext}"
    
    # Check for double extensions (e.g., .jpg.exe)
    parts = file_name.split('.')
    if len(parts) > 2:
        # Check if any part except last looks like a dangerous extension
        for part in parts[:-1]:
            if f".{part}" in dangerous_extensions:
                return False, f"Hidden dangerous extension: .{part}"
    
    # Check file content for executable signatures
    try:
        file_obj.seek(0)
        header = file_obj.read(1024)
        file_obj.seek(0)
        
        executable_signatures = [
            b'MZ',  # Windows executable
            b'\x7fELF',  # Linux executable
            b'#!',  # Shell script
        ]
        
        for sig in executable_signatures:
            if header.startswith(sig):
                return False, f"File appears to be executable (signature: {sig.hex()})"
                
    except (IOError, OSError, ValueError, AttributeError):
       
        pass
    
    return True, "File appears safe"


def generate_secure_filename(original_filename, user_id=None):
    """
    Generate a secure filename to prevent path traversal and collisions
    """
    import uuid
    import datetime
    
    # Get file extension
    _, ext = os.path.splitext(original_filename)
    ext = ext.lower()
    
    # Generate unique filename
    unique_id = uuid.uuid4().hex[:16]  # First 16 chars of UUID
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if user_id:
        secure_name = f"{timestamp}_{user_id}_{unique_id}{ext}"
    else:
        secure_name = f"{timestamp}_{unique_id}{ext}"
    
    return secure_name


def get_file_metadata(file_obj):
    """
    Extract basic metadata from file
    """
    import imghdr
    from PIL import Image
    
    metadata = {
        'filename': file_obj.name,
        'size': file_obj.size,
        'extension': os.path.splitext(file_obj.name)[1].lower(),
    }
    
    try:
        # Try to get image dimensions if it's an image
        file_obj.seek(0)
        
        # Check if it's an image
        if imghdr.what(None, file_obj.read(2048)):
            file_obj.seek(0)
            
            try:
                img = Image.open(file_obj)
                metadata.update({
                    'width': img.width,
                    'height': img.height,
                    'format': img.format,
                    'mode': img.mode,
                    'is_image': True
                })
            except (IOError, OSError, Image.UnidentifiedImageError, ValueError):
                metadata['is_image'] = False
        else:
            metadata['is_image'] = False
            
    except ImportError:
        # PIL not available
        metadata['is_image'] = False
    except Exception:
        metadata['is_image'] = False
    finally:
        file_obj.seek(0)
    
    return metadata
