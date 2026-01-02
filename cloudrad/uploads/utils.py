# uploads/utils.py
import os
from django.conf import settings

def get_upload_directory(patient_id=None):
    """Get upload directory path"""
    if patient_id:
        return os.path.join('patient_uploads', str(patient_id))
    return 'patient_uploads'


def validate_file_type(file_obj):
    """Validate file type"""
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.pdf', '.dcm', '.zip']
    file_name = file_obj.name.lower()
    
    if not any(file_name.endswith(ext) for ext in allowed_extensions):
        return False
    return True


def calculate_file_hash(file_obj):
    """Calculate file hash for integrity checking"""
    import hashlib
    
    hash_md5 = hashlib.md5()
    for chunk in file_obj.chunks(4096):
        hash_md5.update(chunk)
    return hash_md5.hexdigest()