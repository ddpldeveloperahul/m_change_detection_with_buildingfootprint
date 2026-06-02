from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


def default_subscription_end():
    return timezone.now() + timedelta(days=30)


class ChangeResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    uploaded_2023 = models.FileField(upload_to='uploads/')
    uploaded_2025 = models.FileField(upload_to='uploads/')

    result_png = models.FileField(upload_to='images_upload/')
    result_tif = models.FileField(upload_to='images_upload/')
    result_shp = models.FileField(upload_to='images_upload/')

    status = models.CharField(
        max_length=20,
        default='pending'
    )

    # ====================================
    # Building Footprint Detection
    # ====================================

    footprint_old_status = models.CharField(
        max_length=20,
        default='pending'
    )

    footprint_new_status = models.CharField(
        max_length=20,
        default='pending'
    )

    # NEW FIELDS
    footprint_old_progress = models.IntegerField(
        default=0
    )

    footprint_new_progress = models.IntegerField(
        default=0
    )

    footprint_old = models.FileField(
        upload_to='footprints/',
        null=True,
        blank=True
    )

    footprint_new = models.FileField(
        upload_to='footprints/',
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Change Result - {self.user.username}"

    @property
    def footprints_ready(self):
        return (
            self.footprint_old_status == "completed"
            and
            self.footprint_new_status == "completed"
        )



class SpatialJoinResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    main_shapefile = models.FileField(upload_to='shapefiles/')
    change_shapefile = models.FileField(upload_to='shapefiles/')

    result_shapefile = models.FileField(upload_to='output/')
    result_excel = models.FileField(upload_to='output/') # ✅ ADD
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Spatial Join Result - {self.user.username}"



