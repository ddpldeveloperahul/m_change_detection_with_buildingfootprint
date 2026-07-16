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

    main_shapefile = models.FileField(upload_to='shapefiles/', null=True, blank=True)
    change_shapefile = models.FileField(upload_to='shapefiles/', null=True, blank=True)

    result_shapefile = models.FileField(upload_to='output/', null=True, blank=True)
    result_excel = models.FileField(upload_to='output/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Spatial Join Result - {self.user.id}"


class Feedback(models.Model):
    result_excel = models.ForeignKey(
        SpatialJoinResult,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedbacks"
    )
    plot_id = models.CharField(max_length=100, blank=True, null=True)
    feedback_message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.plot_id} - {self.result_excel.id if self.result_excel else 'No Excel'}"




