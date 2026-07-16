from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import user_passes_test
from django.conf import settings
from django.urls import reverse
from matplotlib import image
from requests import request
from django.contrib.auth.models import User
from django.core.files import File
from django.contrib.auth import authenticate, login, logout
from rest_framework.response import Response # type: ignore
from rest_framework import status # type: ignore
from rest_framework.views import APIView # type: ignore
from rest_framework.authentication import SessionAuthentication
from myapp.serializers import SignupSerializer, LoginSerializer, SpatialJoinResultSerializer, FeedbackSerializer, UserSerializer
from rest_framework.decorators import api_view # type: ignore
from django.db import transaction       
from django.utils import timezone
import json
from .models import *
from datetime import timedelta
from rest_framework_simplejwt.tokens import RefreshToken # type: ignore
import numpy as np
from django.views.decorators.csrf import csrf_exempt
from  rest_framework.permissions import IsAuthenticated # type: ignore
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.plot import reshape_as_image
from rasterio.features import rasterize
import cv2
from PIL import Image
from PIL import ImageDraw
import os
import geopandas as gpd
import pandas as pd
from urllib.parse import urlencode
from celery.result import EagerResult # type: ignore
from django.contrib.sessions.models import Session
from .file_handler import save_large_file
from django.http import FileResponse
import zipfile
import tempfile

HIGH_QUALITY_PREVIEW_SIZE = 4096
PNG_SAVE_OPTIONS = {"compress_level": 1}

def media_url_from_path(file_path):
    return settings.MEDIA_URL + os.path.relpath(file_path, settings.MEDIA_ROOT).replace("\\", "/")


def resolve_media_file_path(file_ref):
    if not file_ref:
        return None

    normalized_ref = str(file_ref).strip()

    if normalized_ref.startswith(settings.MEDIA_URL):
        normalized_ref = normalized_ref[len(settings.MEDIA_URL):]

    normalized_ref = normalized_ref.lstrip("/\\")

    if os.path.isabs(normalized_ref):
        candidate = os.path.abspath(normalized_ref)
    else:
        candidate = os.path.abspath(os.path.join(settings.MEDIA_ROOT, normalized_ref))

    media_root = os.path.abspath(settings.MEDIA_ROOT)

    try:
        common_path = os.path.commonpath([candidate, media_root])
    except ValueError:
        return None

    if common_path != media_root:
        return None

    return candidate if os.path.exists(candidate) else None


def build_download_url(route_name, file_name):
    return f"{reverse(route_name)}?{urlencode({'file': file_name})}"


def read_shapefile_attribute_table(file_path):
    table = {
        "name": os.path.basename(file_path) if file_path else "",
        "columns": [],
        "rows": [],
        "total_rows": 0,
        "error": "",
    }

    if not file_path or not os.path.exists(file_path):
        table["error"] = "Shapefile not found."
        return table

    try:
        if file_path.lower().endswith(".zip"):
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(file_path) as archive:
                    for member in archive.infolist():
                        target_path = os.path.abspath(os.path.join(temp_dir, member.filename))
                        if os.path.commonpath([target_path, temp_dir]) != temp_dir:
                            continue
                        archive.extract(member, temp_dir)

                shp_path = None
                for root, _, files in os.walk(temp_dir):
                    for file_name in files:
                        if file_name.lower().endswith(".shp"):
                            shp_path = os.path.join(root, file_name)
                            break
                    if shp_path:
                        break

                if not shp_path:
                    table["error"] = "No .shp file found inside ZIP."
                    return table

                table["name"] = os.path.basename(shp_path)
                gdf = gpd.read_file(shp_path)
        else:
            table["name"] = os.path.basename(file_path)
            gdf = gpd.read_file(file_path)

        if getattr(gdf, "geometry", None) is not None and gdf.geometry.name in gdf.columns:
            gdf = gdf.drop(columns=[gdf.geometry.name])

        gdf = gdf.fillna("")
        table["columns"] = [str(column) for column in gdf.columns]
        table["total_rows"] = len(gdf)
        table["rows"] = [
            [str(value) for value in row]
            for row in gdf.astype(str).values.tolist()
        ]
    except Exception as exc:
        table["error"] = f"Could not read attribute table: {exc}"

    return table


def get_readable_shapefile_path(file_path, temp_dir):
    if not file_path:
        return None

    if not file_path.lower().endswith(".zip"):
        return file_path if file_path.lower().endswith(".shp") else None

    with zipfile.ZipFile(file_path) as archive:
        for member in archive.infolist():
            target_path = os.path.abspath(os.path.join(temp_dir, member.filename))
            if os.path.commonpath([target_path, temp_dir]) != temp_dir:
                continue
            archive.extract(member, temp_dir)

    for root, _, files in os.walk(temp_dir):
        for file_name in files:
            if file_name.lower().endswith(".shp"):
                return os.path.join(root, file_name)

    return None


def build_shapefile_preview_png(file_path, reference_raster_path=None, preview_image_path=None):
    if not file_path or not os.path.exists(file_path):
        return None

    base_path = os.path.splitext(file_path)[0]
    preview_path = base_path + "_join_mask_preview.png"
    reference_mtime = os.path.getmtime(reference_raster_path) if reference_raster_path and os.path.exists(reference_raster_path) else 0
    source_mtime = os.path.getmtime(file_path)

    with tempfile.TemporaryDirectory() as temp_dir:
        shp_path = get_readable_shapefile_path(file_path, temp_dir)
        if not shp_path:
            return None

        gdf = gpd.read_file(shp_path)

    if gdf.empty or getattr(gdf, "geometry", None) is None:
        return None

    gdf = gdf.reset_index(drop=True)
    gdf["_feature_row_index"] = gdf.index
    gdf = gdf[gdf.geometry.notna()].copy()
    if gdf.empty:
        return None

    os.makedirs(os.path.dirname(preview_path), exist_ok=True)

    if reference_raster_path and os.path.exists(reference_raster_path):
        with rasterio.open(reference_raster_path) as reference:
            target_width = reference.width
            target_height = reference.height
            target_transform = reference.transform
            target_crs = reference.crs

            if preview_image_path and os.path.exists(preview_image_path):
                with Image.open(preview_image_path) as preview_image:
                    target_width, target_height = preview_image.size
                x_scale = reference.width / target_width
                y_scale = reference.height / target_height
                target_transform = reference.transform * reference.transform.scale(x_scale, y_scale)

            if target_crs and gdf.crs and gdf.crs != target_crs:
                gdf = gdf.to_crs(target_crs)

            shapes = [(geometry, 255) for geometry in gdf.geometry if geometry and not geometry.is_empty]
            if not shapes:
                return None

            mask = rasterize(
                shapes,
                out_shape=(target_height, target_width),
                transform=target_transform,
                fill=0,
                dtype="uint8",
            )

            if not mask.any():
                return build_unaligned_shapefile_preview_png(gdf, preview_path)

            image = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
            fill = Image.new("RGBA", image.size, (255, 0, 0, 100))
            image.paste(fill, mask=Image.fromarray(mask))

            draw = ImageDraw.Draw(image)
            features = []

            for _, row in gdf.iterrows():
                geometry = row.geometry
                if not geometry or geometry.is_empty:
                    continue

                try:
                    pixel_parts = []
                    geometries = geometry.geoms if hasattr(geometry, "geoms") else [geometry]
                    for part in geometries:
                        exterior = getattr(part, "exterior", None)
                        if exterior is None:
                            continue
                        coords = [~target_transform * coord for coord in exterior.coords]
                        pixel_parts.append([(x, y) for x, y in coords])

                    for coords in pixel_parts:
                        if len(coords) >= 2:
                            draw.line(coords + [coords[0]], fill=(255, 0, 0, 230), width=2)

                    feature_payload = build_feature_payload(int(row["_feature_row_index"]), pixel_parts)
                    if feature_payload:
                        features.append(feature_payload)
                except Exception:
                    continue

            image.save(preview_path, **PNG_SAVE_OPTIONS)
            return preview_path, {
                "width": target_width,
                "height": target_height,
                "features": features,
            }

    return build_unaligned_shapefile_preview_png(gdf, preview_path)


def build_feature_payload(feature_index, pixel_parts):
    clean_parts = []
    all_x = []
    all_y = []

    for coords in pixel_parts:
        clean_coords = [
            [round(float(x), 2), round(float(y), 2)]
            for x, y in coords
            if np.isfinite(x) and np.isfinite(y)
        ]
        if len(clean_coords) < 3:
            continue
        clean_parts.append(clean_coords)
        all_x.extend(point[0] for point in clean_coords)
        all_y.extend(point[1] for point in clean_coords)

    if not clean_parts or not all_x or not all_y:
        return None

    return {
        "index": feature_index,
        "parts": clean_parts,
        "bounds": [
            min(all_x),
            min(all_y),
            max(all_x),
            max(all_y),
        ],
    }


def build_unaligned_shapefile_preview_png(gdf, preview_path):
    bounds = gdf.total_bounds
    min_x, min_y, max_x, max_y = bounds
    if min_x == max_x or min_y == max_y:
        return None

    width, height = 1024, 1024
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def to_pixel(x, y):
        px = ((x - min_x) / (max_x - min_x)) * (width - 40) + 20
        py = height - (((y - min_y) / (max_y - min_y)) * (height - 40) + 20)
        return px, py

    features = []

    for _, row in gdf.iterrows():
        geometry = row.geometry
        if not geometry or geometry.is_empty:
            continue

        pixel_parts = []
        geometries = geometry.geoms if hasattr(geometry, "geoms") else [geometry]
        for part in geometries:
            exterior = getattr(part, "exterior", None)
            if exterior is None:
                continue
            coords = [to_pixel(x, y) for x, y in exterior.coords]
            pixel_parts.append(coords)
            if len(coords) >= 3:
                draw.polygon(coords, fill=(255, 0, 0, 100), outline=(255, 0, 0, 230))

        feature_payload = build_feature_payload(int(row["_feature_row_index"]), pixel_parts)
        if feature_payload:
            features.append(feature_payload)

    image.save(preview_path, **PNG_SAVE_OPTIONS)
    return preview_path, {
        "width": width,
        "height": height,
        "features": features,
    }


def find_change_result_for_shapefile(file_path):
    if not file_path:
        return None

    target_name = os.path.basename(file_path)
    if not target_name:
        return None

    return ChangeResult.objects.filter(result_shp__iendswith=target_name).order_by("-created_at").first()


def find_latest_change_result_for_user(user):
    if not user:
        return None

    return (
        ChangeResult.objects
        .filter(user=user)
        .exclude(result_png="")
        .exclude(result_shp="")
        .order_by("-created_at")
        .first()
    )


def build_preview_path(source_path):
    base, _ = os.path.splitext(source_path)
    return base + ".png"


def build_aligned_preview_path(source_path):
    base, _ = os.path.splitext(source_path)
    return base + "_aligned_to_old.png"


def preview_needs_refresh(source_path, preview_path, max_preview_size=HIGH_QUALITY_PREVIEW_SIZE):
    if not source_path or not preview_path or not os.path.exists(source_path):
        return False

    if not os.path.exists(preview_path):
        return True

    if os.path.getmtime(preview_path) < os.path.getmtime(source_path):
        return True

    try:
        with rasterio.open(source_path) as source, Image.open(preview_path) as preview:
            expected_max_dimension = min(max(source.width, source.height), max_preview_size)
            return max(preview.size) < expected_max_dimension
    except Exception:
        return False


def normalize_band_to_uint8(band):
    finite_mask = np.isfinite(band)
    if not finite_mask.any():
        return np.zeros(band.shape, dtype=np.uint8)

    values = band[finite_mask].astype(np.float32)
    low, high = np.percentile(values, (2, 98))

    if high <= low:
        scaled = np.zeros(band.shape, dtype=np.uint8)
        scaled[finite_mask] = 255
        return scaled

    normalized = np.clip((band.astype(np.float32) - low) / (high - low), 0, 1)
    normalized[~finite_mask] = 0
    return (normalized * 255).astype(np.uint8)


def to_preview_rgb(data):
    if data.ndim == 2:
        data = data[np.newaxis, ...]

    if data.shape[0] >= 3:
        channels = data[:3]
    else:
        channels = np.repeat(data[:1], 3, axis=0)

    rgb = np.stack([normalize_band_to_uint8(channel) for channel in channels], axis=-1)
    return rgb

def save_tiff_preview_png(source_path, preview_path):
    import rasterio
    import numpy as np
    from PIL import Image
    from rasterio.enums import Resampling

    MAX_PREVIEW_SIZE = HIGH_QUALITY_PREVIEW_SIZE
    
    with rasterio.open(source_path) as src:
        print(f"Image info: bands={src.count}, shape=({src.height}x{src.width}), dtype={src.dtypes[0]}")
        
        # Calculate scaling
        scale = max(src.width / MAX_PREVIEW_SIZE, src.height / MAX_PREVIEW_SIZE, 1)
        out_height = int(src.height / scale)
        out_width = int(src.width / scale)

        # Read first 3 bands or less
        band_count = min(3, src.count)
        data = src.read(list(range(1, band_count + 1)), out_shape=(band_count, out_height, out_width), resampling=Resampling.bilinear)
        
        print(f"Read {band_count} bands, shape: {data.shape}")

        # Convert to uint8 with proper normalization for satellite imagery
        if band_count == 1:
            # Single band → grayscale → RGB
            band = data[0].astype(np.float32)
            p2, p98 = np.percentile(band[np.isfinite(band)], (2, 98))
            normalized = np.clip((band - p2) / (p98 - p2 + 1e-6), 0, 1)
            normalized = (normalized * 255).astype(np.uint8)
            img = np.stack([normalized, normalized, normalized], axis=-1)
        else:
            # Multi-band → RGB
            img_data = data[:3].astype(np.float32)
            
            # Normalize each band independently for better color
            normalized_bands = []
            for i in range(img_data.shape[0]):
                band = img_data[i]
                p2, p98 = np.percentile(band[np.isfinite(band)], (2, 98))
                normalized = np.clip((band - p2) / (p98 - p2 + 1e-6), 0, 1)
                normalized_bands.append((normalized * 255).astype(np.uint8))
            
            # Stack as RGB (in correct order)
            img = np.stack(normalized_bands, axis=-1)
        
        print(f"Preview shape: {img.shape}, dtype: {img.dtype}")
        Image.fromarray(img, mode='RGB').save(preview_path, **PNG_SAVE_OPTIONS)
        print(f"Preview saved: {preview_path}")


def save_aligned_tiff_preview_png(reference_path, source_path, preview_path):
    from PIL import Image
    from rasterio.enums import Resampling
    from .utils import open_aligned_new_source

    MAX_PREVIEW_SIZE = HIGH_QUALITY_PREVIEW_SIZE

    with rasterio.open(reference_path) as reference_src, rasterio.open(source_path) as source_src:
        with open_aligned_new_source(reference_src, source_src) as aligned_src:
            scale = max(aligned_src.width / MAX_PREVIEW_SIZE, aligned_src.height / MAX_PREVIEW_SIZE, 1)
            out_height = max(1, int(aligned_src.height / scale))
            out_width = max(1, int(aligned_src.width / scale))
            band_count = min(3, aligned_src.count)
            data = aligned_src.read(
                list(range(1, band_count + 1)),
                out_shape=(band_count, out_height, out_width),
                resampling=Resampling.bilinear,
            )

        img = to_preview_rgb(data)
        Image.fromarray(img, mode='RGB').save(preview_path, **PNG_SAVE_OPTIONS)
        print(f"Aligned preview saved: {preview_path}")

def build_result_context(result_png_path, result_tif_path, result_shp_path, img23_preview_path, img25_preview_path, img23_name, img25_name):
    return {
        'result_png': media_url_from_path(result_png_path),
        'result_tif': media_url_from_path(result_tif_path),
        'result_shp': media_url_from_path(result_shp_path),
        'img23': media_url_from_path(img23_preview_path),
        'img25': media_url_from_path(img25_preview_path),
        'img23_source': media_url_from_path(os.path.join(settings.MEDIA_ROOT, 'uploads', img23_name)),
        'img25_source': media_url_from_path(os.path.join(settings.MEDIA_ROOT, 'uploads', img25_name)),
        'result_shp_source': media_url_from_path(result_shp_path),
        'img23_name': img23_name,
        'img25_name': img25_name,
        'result_shp_name': os.path.basename(result_shp_path),
        'result_tif_name': os.path.basename(result_tif_path),
    }


def home(request):
    return render(request, 'base.html')


@csrf_exempt
def processing_availability(request):
    running_job = get_active_change_job()

    if running_job:
        username = running_job.user.username if running_job.user else "another user"
        return JsonResponse({
            "available": False,
            "error": f"Server busy. {username}'s change detection is already processing. Please wait until it finishes."
        }, status=429)

    return JsonResponse({"available": True})


@csrf_exempt
def upload_chunk(request):
    """Handle chunked file uploads from Resumable.js"""
    try:
        print(f"Upload chunk called - Method: {request.method}")

        user = request.user if request.user.is_authenticated else User.objects.first()
        clear_inactive_processing_jobs()
        
        if request.method == 'POST':
            # NOTE: We allow uploads even during change detection!
            # Only the main processing endpoint checks for conflicts
            
            # Resumable.js sends the file with name 'file'
            chunk_file = request.FILES.get('file')
            
            if not chunk_file:
                print("No 'file' in request.FILES")
                # Try alternative field names
                for key in request.FILES:
                    print(f"Available file key: {key}")
                    chunk_file = request.FILES.get(key)
                    if chunk_file:
                        break
            
            if not chunk_file:
                print("Error: No file provided")
                return JsonResponse({'error': 'No file provided'}, status=400)
            
            print(f"Saving file: {chunk_file.name}")
            # Save the uploaded file
            file_path = save_large_file(chunk_file, "uploads", user=user)
            print(f"File saved at: {file_path}")
            
            return JsonResponse({
                'file_path': file_path,
                'message': 'File uploaded successfully'
            })
        
        # GET request for checking if chunk exists (optional)
        return JsonResponse({'status': 'ready'})
    except Exception as e:
        print(f"Upload chunk error: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return JsonResponse({
            'error': f"Upload error: {str(e)}"
        }, status=500)

def get_logged_in_user_ids():
    user_ids = set()
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        user_id = session.get_decoded().get("_auth_user_id")
        if user_id:
            user_ids.add(int(user_id))
    return user_ids


def clear_inactive_processing_jobs():
    stale_before = timezone.now() - timedelta(minutes=30)
    ChangeResult.objects.filter(status="processing", created_at__lt=stale_before).update(status="failed")
    active_user_ids = get_logged_in_user_ids()
    if active_user_ids:
        ChangeResult.objects.filter(status="processing").exclude(user_id__in=active_user_ids).update(status="failed")
    else:
        ChangeResult.objects.filter(status="processing").update(status="failed")


def get_active_change_job():
    clear_inactive_processing_jobs()
    return ChangeResult.objects.filter(status="processing").select_related("user").first()


def upload_images(request):

    if request.method == 'POST':
        from .tasks import run_change_detection

        user = request.user if request.user.is_authenticated else User.objects.first()

        # 🔒 LOCK FIRST (before anything)
        with transaction.atomic():

            running_job = ChangeResult.objects.select_for_update().filter(status="processing").select_related("user").first()

            if running_job:
                username = running_job.user.username if running_job.user else "another user"
                return JsonResponse({
                    'error': '⚠️ Server busy. Please wait.'
                }, status=429)

            # ✅ job create immediately (lock acquired)
            job = ChangeResult.objects.create(
                user=user,
                status="processing"
            )

        # ⬇️ now file handling
        file1 = request.FILES.get('uploaded_2023')
        file2 = request.FILES.get('uploaded_2025')

        if not file1 or not file2:
            job.status = "failed"
            job.save()
            return JsonResponse({'error': 'Files missing'}, status=400)

        path1 = save_large_file(file1, "uploads", user=user)
        path2 = save_large_file(file2, "uploads", user=user)

        # 🚀 celery
        run_change_detection.delay(path1, path2, user.id, job.id)

        return JsonResponse({
            "message": "Processing started",
            "job_id": job.id
        })

    return render(request, 'upload.html')



def result_view(request):
    result_id = request.GET.get('id')
    attribute_file = request.GET.get('attribute_file')

    if not result_id:
        return HttpResponse("Result id is required", status=400)

    try:
        result = ChangeResult.objects.get(id=result_id)
    except ChangeResult.DoesNotExist:
        return HttpResponse("Result not found", status=404)

    def field_path(field):
        try:
            return field.path if field else None
        except ValueError:
            return None

    result_png_path = field_path(result.result_png)
    result_tif_path = field_path(result.result_tif)
    result_shp_path = field_path(result.result_shp)
    img23_path = field_path(result.uploaded_2023)
    img25_path = field_path(result.uploaded_2025)
    img23_preview_path = build_preview_path(img23_path) if img23_path else None
    img25_preview_path = build_aligned_preview_path(img25_path) if img23_path and img25_path else (
        build_preview_path(img25_path) if img25_path else None
    )

    if img23_path and img23_preview_path and preview_needs_refresh(img23_path, img23_preview_path):
        save_tiff_preview_png(img23_path, img23_preview_path)

    if img23_path and img25_path and img25_preview_path and preview_needs_refresh(img25_path, img25_preview_path):
        save_aligned_tiff_preview_png(img23_path, img25_path, img25_preview_path)
    elif img25_path and img25_preview_path and preview_needs_refresh(img25_path, img25_preview_path):
        save_tiff_preview_png(img25_path, img25_preview_path)

    context = {
        'result_png': media_url_from_path(result_png_path) if result_png_path else '',
        'result_tif': media_url_from_path(result_tif_path) if result_tif_path else '',
        'result_shp': media_url_from_path(result_shp_path) if result_shp_path else '',
        'img23': media_url_from_path(img23_preview_path) if img23_preview_path and os.path.exists(img23_preview_path) else '',
        'img25': media_url_from_path(img25_preview_path) if img25_preview_path and os.path.exists(img25_preview_path) else '',
        'img23_source': media_url_from_path(img23_path) if img23_path else '',
        'img25_source': media_url_from_path(img25_path) if img25_path else '',
        'result_shp_source': media_url_from_path(result_shp_path) if result_shp_path else '',
        'img23_name': os.path.basename(result.uploaded_2023.name) if result.uploaded_2023 else '',
        'img25_name': os.path.basename(result.uploaded_2025.name) if result.uploaded_2025 else '',
        'result_shp_name': os.path.basename(result.result_shp.name) if result.result_shp else '',
        'result_tif_name': os.path.basename(result.result_tif.name) if result.result_tif else '',
        'join_output_features': {},
    }

    attribute_path = resolve_media_file_path(attribute_file)
    if attribute_file and attribute_path:
        context['attribute_table'] = read_shapefile_attribute_table(attribute_path)
        context['attribute_file_url'] = media_url_from_path(attribute_path)
        join_preview_result = build_shapefile_preview_png(attribute_path, img23_path, img23_preview_path)
        if join_preview_result:
            join_preview_path, join_output_features = join_preview_result
            context['join_output_png'] = media_url_from_path(join_preview_path)
            context['join_output_name'] = os.path.basename(attribute_path)
            context['join_output_features'] = join_output_features or {}

    return render(request, 'result.html', context)




def render_spatial_join_result(request, result_id):
    try:
        obj = SpatialJoinResult.objects.get(id=result_id)
    except SpatialJoinResult.DoesNotExist:
        return HttpResponse("Spatial join result not found", status=404)

    def get_stats_from_excel(excel_path):
        stats = {
            'total': 0,
            'changed': 0,
            'unchanged': 0,
        }

        if not excel_path or not os.path.exists(excel_path):
            return stats

        try:
            excel_df = pd.read_excel(excel_path, sheet_name='All Data')
        except Exception:
            return stats

        stats['total'] = len(excel_df)

        if 'changed' in excel_df.columns:
            changed_values = excel_df['changed'].astype(str).str.strip().str.upper()
            stats['changed'] = int(((changed_values == 'YES') | (changed_values == 'NEW CONSTRUCTION')).sum())
            stats['unchanged'] = int((changed_values == 'NO').sum())
        elif 'is_new_building' in excel_df.columns:
            changed_values = excel_df['is_new_building'].astype(str).str.strip().str.upper()
            stats['changed'] = int((changed_values == 'YES').sum())
            stats['unchanged'] = int((changed_values == 'NO').sum())
        elif 'changed_flag' in excel_df.columns:
            changed_values = excel_df['changed_flag'].astype(bool)
            stats['changed'] = int(changed_values.sum())
            stats['unchanged'] = int(stats['total'] - stats['changed'])
        else:
            stats['unchanged'] = stats['total']

        return stats

    stats = get_stats_from_excel(obj.result_excel.path)

    result_mode = "footprint" if obj.result_shapefile and "new_building_footprints" in os.path.basename(obj.result_shapefile.name) else "spatial_join"

    result = {
        **stats,
        'shapefile': obj.result_shapefile.path,
        'excel': obj.result_excel.path,
    }

    source_change_result = find_change_result_for_shapefile(obj.change_shapefile.path if obj.change_shapefile else None)
    if not source_change_result:
        source_change_result = find_latest_change_result_for_user(obj.user)
    attribute_table_url = ""
    if source_change_result:
        attribute_table_url = (
            f"{reverse('change_result')}?"
            f"{urlencode({'id': source_change_result.id, 'attribute_file': obj.result_shapefile.name})}"
        )

    return render(request, 'result1.html', {
        'result': result,
        'result_mode': result_mode,
        'result_title': "New Building Footprint Result" if result_mode == "footprint" else "Spatial Join Result",
        'changed_label': "New Buildings" if result_mode == "footprint" else "Changed",
        'unchanged_label': "Existing Buildings" if result_mode == "footprint" else "Unchanged",
        'excel_url': obj.result_excel.url,
        'shp_url': obj.result_shapefile.url,
        'excel_download_url': build_download_url('download_excel', obj.result_excel.name),
        'shp_download_url': build_download_url('download_shapefile', obj.result_shapefile.name),
        'attribute_table_url': attribute_table_url,
    })

def download_excel(request):
    file_path = resolve_media_file_path(request.GET.get('file'))

    if not file_path:
        return HttpResponse("File not found", status=404)

    return FileResponse(
        open(file_path, 'rb'),
        as_attachment=True,
        filename=os.path.basename(file_path)
    )

def download_shapefile(request):
    shp_path = resolve_media_file_path(request.GET.get('file'))

    if not shp_path:
        return HttpResponse("File not found", status=404)

    if shp_path.lower().endswith(".zip"):
        return FileResponse(
            open(shp_path, 'rb'),
            as_attachment=True,
            filename=os.path.basename(shp_path)
        )

    base = os.path.splitext(shp_path)[0]
    zip_path = base + ".zip"

    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for ext in ['.shp', '.shx', '.dbf', '.prj', '.cpg']:
            f = base + ext
            if os.path.exists(f):
                zipf.write(f, os.path.basename(f))

    return FileResponse(open(zip_path, 'rb'), as_attachment=True)






def spatial_join_view(request):
    from .tasks import run_spatial_join, run_new_footprint_detection
    
    prefilled_file = request.GET.get('file') or request.POST.get('prefilled_file')
    prefilled_path = resolve_media_file_path(prefilled_file)
    file_name = os.path.basename(prefilled_path) if prefilled_path else None

    if request.method == 'POST':

        main_zip = request.FILES.get('main_zip')
        change_zip = request.FILES.get('change_zip')

        if not main_zip:
            return HttpResponse("Upload old shapefile ZIP file", status=400)

        if not change_zip and not prefilled_path:
            return HttpResponse("Change shapefile file not found. Please select it again.", status=400)

        main_path = save_large_file(main_zip, "main")
        change_path = save_large_file(change_zip, "change") if change_zip else prefilled_path

        user = request.user if request.user.is_authenticated else User.objects.first()
        if user is None:
            return HttpResponse("No user found. Please create or log in as a user first.", status=400)

        if prefilled_path:
            task = run_spatial_join.delay(main_path, change_path, user.id)
        else:
            task = run_new_footprint_detection.delay(main_path, change_path, user.id)

        if isinstance(task, EagerResult) and task.successful():
            result_id = task.result.get("id") if isinstance(task.result, dict) else None
            if result_id:
                return render_spatial_join_result(request, result_id)
            if isinstance(task.result, dict) and task.result.get("error"):
                return HttpResponse(task.result["error"], status=400)

        if isinstance(task, EagerResult) and task.failed():
            return HttpResponse(str(task.result), status=500)

        return render(request, "processing.html", {
            "task_id": task.id
        })

    return render(request, 'change.html', {
        'prefilled_file': prefilled_file if prefilled_path else None,
        'file_name': file_name,
        'prefilled_error': "Selected change file was not found. Please run change detection again." if prefilled_file and not prefilled_path else None,
    })
# ✅ SIGNUP
@api_view(['POST'])
def signup_api(request):
    data = request.data.copy()
    data = {k: v for k, v in data.items()}  # force normal dict

    if not data.get('username'):
        data['username'] = data.get('name') or data.get('usenama')

    if not data.get('password'):
        data['password'] = data.get('passwod')

    if not data.get('confirm_password'):
        data['confirm_password'] = (
            data.get('confirm-passowd') or
            data.get('confirm_passowd')
        )

    print("FINAL DATA:", data)  # debug

    serializer = SignupSerializer(data=data)

    if serializer.is_valid():
        user = serializer.save()
        return Response({
            "message": "User created successfully",
            "user_id": user.id
        })

    return Response(serializer.errors, status=400)


@api_view(['POST'])
def login_api(request):

    username = request.data.get('username')
    password = request.data.get('password')

    user = authenticate(username=username, password=password)

    if user is None:
        return Response({"error": "Invalid credentials"}, status=401)

    refresh = RefreshToken.for_user(user)

    return Response({
        "message": "Login successful",
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh)
    })

# ✅ LOGOUT
@api_view(['POST'])
def logout_api(request):
    return Response({"message": "Logout successful (client should delete token)"})



# ✅ FEEDBACK CRUD VIEWS
class FeedbackAPIView(APIView):

    # List all feedback of a specific Excel
    def get(self, request, pk):
        try:
            excel = SpatialJoinResult.objects.get(pk=pk)
        except SpatialJoinResult.DoesNotExist:
            return Response(
                {"error": "Excel not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = FeedbackSerializer(excel.feedbacks.all(), many=True)
        return Response(serializer.data)

    # Create feedback for a specific Excel
    def post(self, request, pk):
        try:
            excel = SpatialJoinResult.objects.get(pk=pk)
        except SpatialJoinResult.DoesNotExist:
            return Response(
                {"error": "Excel not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = FeedbackSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(result_excel=excel)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class FeedbackDetailAPIView(APIView):
    authentication_classes = [SessionAuthentication]

    def get_object(self, pk):
        try:
            return Feedback.objects.get(pk=pk)
        except Feedback.DoesNotExist:
            return None

    # Retrieve
    def get(self, request, pk):
        feedback = self.get_object(pk)

        if not feedback:
            return Response(
                {"error": "Feedback not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = FeedbackSerializer(feedback)
        return Response(serializer.data)

    # Update
    def put(self, request, pk):
        feedback = self.get_object(pk)

        if not feedback:
            return Response(
                {"error": "Feedback not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = FeedbackSerializer(feedback, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save(result_excel=feedback.result_excel)
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # # Partial Update
    # def patch(self, request, pk):
    #     feedback = self.get_object(pk)

    #     if not feedback:
    #         return Response(
    #             {"error": "Feedback not found"},
    #             status=status.HTTP_404_NOT_FOUND
    #         )

    #     serializer = FeedbackSerializer(
    #         feedback,
    #         data=request.data,
    #         partial=True
    #     )

    #     if serializer.is_valid():
    #         serializer.save()
    #         return Response(serializer.data)

    #     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Delete
    def delete(self, request, pk):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        feedback = self.get_object(pk)

        if not feedback:
            return Response(
                {"error": "Feedback not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        feedback.delete()

        return Response(
            {"message": "Feedback deleted successfully"},
            status=status.HTTP_204_NO_CONTENT
        )
class AllFeedbackAPIView(APIView):

    def get(self, request):
        feedbacks = Feedback.objects.select_related("result_excel").order_by("-created_at")

        serializer = FeedbackSerializer(feedbacks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

def logout_view(request):
    """Handle HTML form logout and redirect to login page"""
    if request.user.is_authenticated:
        ChangeResult.objects.filter(user=request.user, status="processing").update(status="failed")
    logout(request)
    return redirect('login')


@csrf_exempt
@api_view(['GET'])
def list_excel_files(request):
    results = SpatialJoinResult.objects.all().order_by('-created_at')
    print("Total records:", results.count())
    serializer = SpatialJoinResultSerializer(results, many=True, context={'request': request})
    return Response(serializer.data)

@csrf_exempt
def login_page(request):
    if request.user.is_authenticated:
        return redirect('upload') 
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('upload')
        else:
            return render(request, 'login.html', {'error': 'Invalid credentials'})
    
    return render(request, 'login.html')

def signup_page(request):
    return render(request, 'signup.html')

@csrf_exempt
def start_processing(request):
    from .tasks import run_change_detection
    
    try:
        if not request.body:
            return JsonResponse({"error": "Request body is empty"}, status=400)

        data = json.loads(request.body)

        file1 = data.get('file1')
        file2 = data.get('file2')

        if not file1 or not file2:
            return JsonResponse({"error": "file1 and file2 are required"}, status=400)

        user = request.user if request.user.is_authenticated else User.objects.first()

        clear_inactive_processing_jobs()

        if user is None:
            return JsonResponse({"error": "No user found"}, status=400)

        # 🔒 ATOMIC LOCK (IMPORTANT)
        with transaction.atomic():

            running_job = ChangeResult.objects.select_for_update().filter(status="processing").select_related("user").first()

            if running_job:
                username = running_job.user.username if running_job.user else "another user"
                return JsonResponse({
                    "error": f"Server busy. {username}'s change detection is already processing. Please wait until it finishes."
                }, status=429)

            # Try to reuse existing job if job_id is passed
            job_id = data.get('job_id')
            if job_id:
                try:
                    job = ChangeResult.objects.select_for_update().get(id=job_id)
                    job.status = "processing"
                    job.save()
                except ChangeResult.DoesNotExist:
                    job = ChangeResult.objects.create(
                        user=user,
                        status="processing"
                    )
            else:
                # ✅ create job
                job = ChangeResult.objects.create(
                    user=user,
                    status="processing"
                )

        # 🚀 Celery call (outside transaction)
        task = run_change_detection.delay(file1, file2, user.id, job.id)

        return JsonResponse({
            "task_id": task.id,
            "job_id": job.id
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def task_status(request, task_id):
    """Get the status of a Celery task"""
    from celery.result import AsyncResult
    
    print(f"Task status request for task_id: {task_id}")
    
    if not task_id or task_id == 'undefined':
        return JsonResponse({
            "error": "Invalid task_id"
        }, status=400)
    
    try:
        result = AsyncResult(task_id)
        response = {
            "task_id": task_id,
            "status": result.status,
        }
        
        if result.status == 'SUCCESS':
            response['result'] = result.result
        elif result.status == 'FAILURE':
            response['error'] = str(result.info)
        
        return JsonResponse(response)
    except Exception as e:
        import traceback
        print(f"Exception in task_status: {traceback.format_exc()}")
        return JsonResponse({
            "error": f"Error fetching task status: {str(e)}"
        }, status=500)


# =========================
# 🏢 BUILDING FOOTPRINT DETECTION VIEWS
# =========================
@csrf_exempt
def start_footprint_detection(request):
    """
    Start building footprint detection for a single uploaded image in the background.
    Called immediately after an image is uploaded in the background.
    """
    try:
        if request.method != 'POST':
            return JsonResponse({"error": "POST method required"}, status=400)
        
        data = json.loads(request.body)
        file_path = data.get('file_path')
        image_type = data.get('image_type')  # 'old' or 'new'
        job_id = data.get('job_id')
        
        if not file_path or not image_type:
            return JsonResponse({"error": "file_path and image_type are required"}, status=400)
        
        user = request.user if request.user.is_authenticated else User.objects.first()
        if user is None:
            return JsonResponse({"error": "No user found"}, status=400)
            
        if job_id:
            try:
                job = ChangeResult.objects.get(id=job_id)
            except ChangeResult.DoesNotExist:
                return JsonResponse({"error": "Job not found"}, status=404)
        else:
            job = ChangeResult.objects.create(
                user=user,
                status="pending"
            )
            
        # Register the uploaded file reference to the ChangeResult job
        abs_path = os.path.abspath(file_path)
        media_root = os.path.abspath(settings.MEDIA_ROOT)
        
        if os.path.commonpath([media_root, abs_path]) == media_root:
            rel_path = os.path.relpath(abs_path, media_root).replace("\\", "/")
            if image_type == 'old':
                job.uploaded_2023.name = rel_path
                job.footprint_old_status = 'pending'
                job.footprint_old_progress = 0
            else:
                job.uploaded_2025.name = rel_path
                job.footprint_new_status = 'pending'
                job.footprint_new_progress = 0
            job.save()

        # Import and trigger the single footprint Celery task
        from .tasks import process_single_footprint
        task = process_single_footprint.delay(abs_path, job.id, image_type)
        
        print(f"Started building footprint detection task {task.id} for job {job.id} ({image_type} image)")
        
        return JsonResponse({
            "status": "started",
            "task_id": task.id,
            "job_id": job.id
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def footprint_status(request, job_id=None, pk=None):
    """
    Check the status and progress of building footprint detection for a job (supports job_id or pk routes).
    """
    target_id = job_id or pk
    if not target_id:
        return JsonResponse({"error": "Job ID or PK is required"}, status=400)
        
    try:
        job = ChangeResult.objects.get(id=target_id)
    except ChangeResult.DoesNotExist:
        return JsonResponse({"error": "Job not found"}, status=404)
    
    response = {
        "job_id": job.id,
        "old_status": job.footprint_old_status,
        "new_status": job.footprint_new_status,
        "old_progress": job.footprint_old_progress,
        "new_progress": job.footprint_new_progress,
        "ready": job.footprints_ready,
    }
    
    # Add URLs to footprint images if completed
    if job.footprint_old_status == 'completed' and job.footprint_old:
        response['old_footprint_url'] = media_url_from_path(job.footprint_old.path)
    
    if job.footprint_new_status == 'completed' and job.footprint_new:
        response['new_footprint_url'] = media_url_from_path(job.footprint_new.path)
    
    return JsonResponse(response)


@csrf_exempt
def get_footprint_image(request):
    """
    Get footprint image URL for display
    """
    try:
        job_id = request.GET.get('job_id')
        image_type = request.GET.get('type')  # 'old' or 'new'
        
        if not job_id or not image_type:
            return JsonResponse({"error": "job_id and type are required"}, status=400)
        
        job = ChangeResult.objects.get(id=job_id)
        
        if image_type == 'old':
            if job.footprint_old_status == 'completed' and job.footprint_old:
                return JsonResponse({
                    "url": media_url_from_path(job.footprint_old.path),
                    "status": "completed"
                })
            else:
                return JsonResponse({
                    "status": job.footprint_old_status
                })
        
        elif image_type == 'new':
            if job.footprint_new_status == 'completed' and job.footprint_new:
                return JsonResponse({
                    "url": media_url_from_path(job.footprint_new.path),
                    "status": "completed"
                })
            else:
                return JsonResponse({
                    "status": job.footprint_new_status
                })
        
        else:
            return JsonResponse({"error": "Invalid image type"}, status=400)
            
    except ChangeResult.DoesNotExist:
        return JsonResponse({"error": "Job not found"}, status=404)
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({"error": str(e)}, status=500)


@user_passes_test(lambda u: u.is_superuser, login_url='/login/')
def feedback_dashboard_view(request):
    """
    Renders the feedback dashboard for superusers.
    """
    feedbacks = Feedback.objects.all().select_related('result_excel').order_by('-created_at')
    
    total_feedbacks = feedbacks.count()
    unique_excels = feedbacks.exclude(result_excel=None).values('result_excel').distinct().count()
    
    latest_feedback = feedbacks.first()
    latest_time = latest_feedback.created_at if latest_feedback else None

    context = {
        'feedbacks': feedbacks,
        'total_feedbacks': total_feedbacks,
        'unique_excels': unique_excels,
        'latest_time': latest_time,
    }
    return render(request, 'feedback_dashboard.html', context)


class UserListCreateAPIView(APIView):
    """
    API endpoint to list and create users.
    """
    def get(self, request):
        users = User.objects.all().order_by('-date_joined')
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            password = request.data.get('password')
            if not password:
                return Response({"password": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)
            user = User.objects.create_user(
                username=serializer.validated_data['username'],
                email=serializer.validated_data.get('email', ''),
                password=password,
                is_superuser=serializer.validated_data.get('is_superuser', False),
                is_staff=serializer.validated_data.get('is_staff', False)
            )
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserDetailAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    """
    API endpoint to retrieve, update, and delete users.
    """
    def get_object(self, pk):
        try:
            return User.objects.get(pk=pk)
        except User.DoesNotExist:
            return None

    def get(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = UserSerializer(user)
        return Response(serializer.data)

    def put(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = UserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            password = request.data.get('password')
            if password:
                user.set_password(password)
            
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        user = self.get_object(pk)
        if not user:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Prevent self deletion
        if request.user.is_authenticated and request.user.id == user.id:
            return Response({"error": "You cannot delete your own logged-in user account."}, status=status.HTTP_400_BAD_REQUEST)
            
        user.delete()
        return Response({"message": "User deleted successfully"}, status=status.HTTP_200_OK)


@user_passes_test(lambda u: u.is_superuser, login_url='/login/')
def user_dashboard_view(request):
    """
    Renders the User Management Dashboard for superusers.
    """
    users = User.objects.all().order_by('-date_joined')
    total_users = users.count()
    total_superusers = users.filter(is_superuser=True).count()
    total_regular_users = users.filter(is_superuser=False, is_staff=False).count()

    context = {
        'users': users,
        'total_users': total_users,
        'total_superusers': total_superusers,
        'total_regular_users': total_regular_users,
    }
    return render(request, 'user_dashboard.html', context)


@user_passes_test(lambda u: u.is_superuser, login_url='/login/')
def admin_dashboard_view(request):
    """
    Renders the Admin Dashboard for superusers, showing ChangeResult, SpatialJoinResult, and Feedback.
    """
    change_results = ChangeResult.objects.all().select_related('user').order_by('-created_at')
    spatial_joins = SpatialJoinResult.objects.all().select_related('user').order_by('-created_at')
    feedbacks = Feedback.objects.all().select_related('result_excel', 'result_excel__user').order_by('-created_at')
    
    total_change = change_results.count()
    total_spatial = spatial_joins.count()
    total_feedbacks = feedbacks.count()
    
    context = {
        'change_results': change_results,
        'spatial_joins': spatial_joins,
        'feedbacks': feedbacks,
        'total_change': total_change,
        'total_spatial': total_spatial,
        'total_feedbacks': total_feedbacks,
    }
    return render(request, 'admin_dashboard.html', context)


class ChangeResultDetailAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    def delete(self, request, pk):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        try:
            obj = ChangeResult.objects.get(pk=pk)
            obj.delete()
            return Response({"message": "Change detection job deleted successfully"}, status=status.HTTP_200_OK)
        except ChangeResult.DoesNotExist:
            return Response({"error": "Job not found"}, status=status.HTTP_404_NOT_FOUND)


class SpatialJoinResultDetailAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    def delete(self, request, pk):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        try:
            obj = SpatialJoinResult.objects.get(pk=pk)
            obj.delete()
            return Response({"message": "Spatial join result deleted successfully"}, status=status.HTTP_200_OK)
        except SpatialJoinResult.DoesNotExist:
            return Response({"error": "Result not found"}, status=status.HTTP_404_NOT_FOUND)


@user_passes_test(lambda u: u.is_superuser, login_url='/login/')
def feedback_detail_view(request, feedback_id):
    """
    Renders a detailed view of a single feedback message.
    """
    try:
        feedback = Feedback.objects.select_related('result_excel', 'result_excel__user').get(id=feedback_id)
    except Feedback.DoesNotExist:
        return HttpResponse("Feedback not found", status=404)
    
    return render(request, 'feedback_detail.html', {'feedback': feedback})


@user_passes_test(lambda u: u.is_superuser, login_url='/login/')
def view_excel_sheet(request):
    """
    Renders the Excel sheet contents as a table, highlighting the specified plot_id in red.
    """
    excel_file = request.GET.get('file')
    highlight_plot_id = request.GET.get('highlight_plot_id')
    
    file_path = resolve_media_file_path(excel_file)
    if not file_path or not os.path.exists(file_path):
        return HttpResponse("Excel file not found", status=404)
        
    try:
        xl = pd.ExcelFile(file_path)
        sheet_name = 'All Data' if 'All Data' in xl.sheet_names else xl.sheet_names[0]
        df = xl.parse(sheet_name)
        
        df = df.fillna('')
        columns = [str(col) for col in df.columns]
        
        # Identify case-insensitive column representing Plot ID
        plot_col_idx = -1
        for idx, col in enumerate(columns):
            if col.strip().lower() in ['plot id', 'plot_id', 'plotid', 'id']:
                plot_col_idx = idx
                break
        formatted_rows = []
        for index, row in df.iterrows():
            row_vals = [str(val) for val in row.values]
            highlight = False
            if highlight_plot_id and plot_col_idx != -1:
                val = str(row.values[plot_col_idx]).strip()
                if val.endswith('.0'):
                    val = val[:-2]
                target_id = str(highlight_plot_id).strip()
                if target_id.endswith('.0'):
                    target_id = target_id[:-2]
                if val == target_id:
                    highlight = True
            formatted_rows.append({
                'values': row_vals,
                'highlight': highlight
            })
        context = {
            'file_name': os.path.basename(file_path),
            'excel_file': excel_file,
            'columns': columns,
            'rows': formatted_rows,
            'highlight_plot_id': highlight_plot_id,
        }
        return render(request, 'excel_viewer.html', context)
    except Exception as e:
        import traceback
        print(f"Excel viewer error: {traceback.format_exc()}")
        return HttpResponse(f"Error loading Excel sheet: {str(e)}", status=500)


@csrf_exempt
@api_view(['POST'])
def upload_desktop_results(request):
    """
    API endpoint for the desktop application to upload the generated Excel sheet 
    and shapefile ZIP, saving them into the Django database (SpatialJoinResult).
    """
    try:
        user_id = request.data.get('user_id') or request.POST.get('user_id')
        username = request.data.get('username') or request.POST.get('username')
        user = None
        
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                pass
        
        if not user and username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                pass
                
        if not user and request.user.is_authenticated:
            user = request.user
            
        if not user:
            # Fallback to first user in the database
            user = User.objects.first()
            if not user:
                # If no users exist, create a default desktop user
                user = User.objects.create_user(username='desktop_user', password='password123')

        # Get the uploaded files from request
        result_excel = request.FILES.get('result_excel')
        result_shapefile = request.FILES.get('result_shapefile')
        main_shapefile = request.FILES.get('main_shapefile')
        change_shapefile = request.FILES.get('change_shapefile')

        if not result_excel:
            return Response(
                {"error": "result_excel file is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create SpatialJoinResult object
        obj = SpatialJoinResult(user=user)
        
        if result_excel:
            obj.result_excel = result_excel
        if result_shapefile:
            obj.result_shapefile = result_shapefile
        if main_shapefile:
            obj.main_shapefile = main_shapefile
        if change_shapefile:
            obj.change_shapefile = change_shapefile

        obj.save()

        # Serialize and return the response
        serializer = SpatialJoinResultSerializer(obj, context={'request': request})
        return Response({
            "message": "Desktop results uploaded successfully",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        import traceback
        print(f"Error in upload_desktop_results: {traceback.format_exc()}")
        return Response(
            {"error": f"Failed to upload results: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )







    
