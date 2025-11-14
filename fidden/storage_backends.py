# fidden/storage_backends.py
import os
from storages.backends.s3boto3 import S3Boto3Storage

class MediaStorage(S3Boto3Storage):
    location = "media"      # files live at media/profile_images/...
    default_acl = None
    file_overwrite = False
    custom_domain = os.getenv("S3_PUBLIC_DOMAIN")  # optional
