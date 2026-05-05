import os
from django.conf import settings
from cloudinary_storage.storage import MediaCloudinaryStorage

class HybridMediaStorage(MediaCloudinaryStorage):
    """
    Custom storage backend that serves existing local files from /media/ 
    and handles new uploads via Cloudinary.
    """
    def url(self, name):
        if not name:
            return ''
            
        name_str = str(name)
            
        # If it's already an absolute URL, return it directly
        if name_str.startswith('http://') or name_str.startswith('https://'):
            return name_str
            
        # Check if the file exists locally
        local_path = os.path.join(settings.MEDIA_ROOT, name_str)
        if os.path.exists(local_path):
            # Return the local URL
            url_path = name_str.replace('\\', '/')
            if url_path.startswith('/'):
                url_path = url_path[1:]
            return f"{settings.MEDIA_URL}{url_path}"
            
        # If the file does not exist locally, fall back to Cloudinary
        return super().url(name)
