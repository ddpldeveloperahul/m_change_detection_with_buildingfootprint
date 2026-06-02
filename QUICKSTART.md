# 🚀 Quick Start Guide - Building Footprint Detection

## ✅ What's Already Set Up

Your system has **all components ready**. This guide will start them:

### ✓ Backend Infrastructure
- ✓ Django application with all endpoints configured
- ✓ Celery task system (`process_single_footprint` task)
- ✓ Database model with footprint tracking (`ChangeResult`)
- ✓ Real-time progress callbacks

### ✓ Frontend Infrastructure  
- ✓ Upload page with drag-and-drop zones
- ✓ Real-time progress trackers (with progress bars)
- ✓ Auto-disable/enable button based on status
- ✓ AJAX polling for live updates

### ✓ AI Model
- ✓ Mask R-CNN model loaded (`building_maskrcnn_trained.pth`)
- ✓ TIFF and JPG/PNG support
- ✓ GPU acceleration (auto-detected)

---

## 🎯 The Exact Workflow (Step-by-Step)

```
1. USER UPLOADS OLD IMAGE
   ↓
2. AUTO: Footprint Detection Starts (Background)
   ↓
3. SHOW: Progress % under OLD image
   ↓
4. USER UPLOADS NEW IMAGE  
   ↓
5. AUTO: Footprint Detection Starts (Background)
   ↓
6. SHOW: Progress % under NEW image
   ↓
7. WAIT: Both complete ✓
   ↓
8. ENABLE: "Start Upload" button becomes clickable
   ↓
9. USER CLICKS "Start Upload"
   ↓
10. AUTO: Change Detection runs (Background)
   ↓
11. SHOW: Main progress bar (25% → 60% → 100%)
   ↓
12. REDIRECT: Result page with outputs
   ↓
13. DOWNLOAD: PNG, TIF, Shapefile
```

---

## 🔧 HOW TO START (3 Options)

### OPTION A: Automatic (EASIEST - Windows)

1. **Open File Explorer**
   - Navigate to: `d:\AI_Portal\change_detection_main_with_footprint\change_detection_main\gis_django\my_gis_project\`

2. **Double-Click:**
   ```
   START_SERVICES.bat
   ```

3. **Choose When Prompted:**
   - If Redis is installed: Press `n`
   - If Redis is NOT installed: Press `y` (uses memory broker)

4. **Wait for:** 4 terminal windows to open
   - Terminal 1: Redis (if available)
   - Terminal 2: Celery Worker
   - Terminal 3: Django Server  
   - Terminal 4: Flower Dashboard (monitoring)

5. **Done!** Navigate to: http://localhost:8000/upload/

---

### OPTION B: Manual (With Redis - PRODUCTION)

**Terminal 1 - Redis Server:**
```powershell
redis-server
```
Expected: `* Ready to accept connections`

**Terminal 2 - Celery Worker:**
```powershell
cd d:\AI_Portal\change_detection_main_with_footprint\change_detection_main\gis_django\my_gis_project
.\venv\Scripts\activate
celery -A my_gis_project worker --loglevel=info --reload
```
Expected: `[*] mingle: there are no known tasks`

**Terminal 3 - Django Server:**
```powershell
cd d:\AI_Portal\change_detection_main_with_footprint\change_detection_main\gis_django\my_gis_project
.\venv\Scripts\activate
python manage.py runserver
```
Expected: `Starting development server at http://127.0.0.1:8000/`

**Terminal 4 - Flower (Optional):**
```powershell
cd d:\AI_Portal\change_detection_main_with_footprint\change_detection_main\gis_django\my_gis_project
.\venv\Scripts\activate
pip install flower
celery -A my_gis_project flower
```
Navigate to: http://localhost:5555/

---

### OPTION C: Quick (Without Redis - DEVELOPMENT)

**Terminal 1 - Django + Celery (Memory Broker):**
```powershell
cd d:\AI_Portal\change_detection_main_with_footprint\change_detection_main\gis_django\my_gis_project
.\venv\Scripts\activate
python manage.py runserver
```

Note: Celery tasks will execute synchronously (no separate worker needed)

---

## 🧪 TESTING THE WORKFLOW

### Test Case 1: Both Images Upload Successfully

**Step 1:** Go to http://localhost:8000/upload/

**Step 2:** Select OLD Image
- Click or drag OLD image onto first zone
- Watch: File name appears
- Watch: "Building Footprint Generation" tracker shows
- Watch: Progress bar fills (0% → 100%)
- Watch: Status changes to "✓ Footprint generated successfully!"

**Step 3:** Select NEW Image  
- Click or drag NEW image onto second zone
- Same progress tracking as OLD image

**Step 4:** Wait for Both Footprints
- When both show "✓", "Start Upload" button enables
- Button changes from gray (disabled) to blue (enabled)

**Step 5:** Click "Start Upload"
- Main progress bar appears at bottom
- Status: "Initializing change detection..."
- Progress bar fills (25% → 60% → 100%)
- Redirects to result page

**Step 6:** View Results
- Download change map (PNG)
- Download raster data (TIF)
- Download shapefile (ZIP)

---

### Test Case 2: Monitor Progress in Real-Time

**While processing:**

1. **Check Terminal 2 (Celery Worker):**
   ```
   [2026-05-29 15:30:45] Starting footprint detection for job 42 (old image)
   [2026-05-29 15:30:50] Progress: 25%
   [2026-05-29 15:30:55] Progress: 50%
   [2026-05-29 15:31:00] Progress: 75%
   [2026-05-29 15:31:05] Footprint saved: /media/footprints/old_fp_42.png
   ```

2. **Check Flower Dashboard:** http://localhost:5555/
   - See active tasks
   - See task execution time
   - See results

3. **Check Frontend:**
   - Progress bars update live
   - Percentage changes every 1-2 seconds

---

### Test Case 3: Error Handling

**If model fails to load:**
```
Check: d:\AI_Portal\change_detection_main_with_footprint\change_detection_main\
       gis_django\my_gis_project\ai_models\building_maskrcnn_trained.pth

File should exist and be ~170MB
```

**If upload fails:**
```
Check Terminal 3 (Django Server) for error message
Common issues:
- File too large (increase FILE_UPLOAD_MAX_MEMORY_SIZE)
- Permission denied (check media/ folder permissions)
- Disk space full (check d: drive space)
```

**If footprint status stuck at "processing":**
```
Check Terminal 2 (Celery Worker) for errors
Refresh page - frontend will poll updated status
```

---

## 📊 EXPECTED TIMES

| Step | Time | Device |
|------|------|--------|
| Model Load (first time) | 5-10 sec | Any |
| JPG/PNG Footprint | 10-30 sec | GPU/CPU |
| Small TIFF Footprint | 30-60 sec | GPU/CPU |
| Large TIFF Footprint (500MB+) | 2-5 min | GPU/CPU |
| Change Detection | 2-5 min | GPU/CPU |
| **Total Workflow** | **5-15 min** | **Typical** |

---

## 🔍 DEBUGGING

### Check Database Status
```powershell
cd d:\AI_Portal\change_detection_main_with_footprint\change_detection_main\gis_django\my_gis_project

# Open Django shell
python manage.py shell

# Check latest job
from myapp.models import ChangeResult
job = ChangeResult.objects.latest('id')
print(f"Job {job.id}:")
print(f"  Old Status: {job.footprint_old_status} ({job.footprint_old_progress}%)")
print(f"  New Status: {job.footprint_new_status} ({job.footprint_new_progress}%)")
print(f"  Ready: {job.footprints_ready}")
```

### Check Celery Tasks
```powershell
# List active tasks
celery -A my_gis_project inspect active

# Check worker stats
celery -A my_gis_project inspect stats

# Purge all tasks
celery -A my_gis_project purge
```

### Check Server Logs
```powershell
# Terminal 3 (Django) - Look for:
# - GET /upload/
# - POST /upload-chunk/
# - POST /start-footprint-detection/
# - GET /footprint-status/42/

# Terminal 2 (Celery) - Look for:
# - Received task process_single_footprint
# - Progress callbacks (25%, 50%, 75%, 100%)
# - Task succeeded
```

---

## ⚙️ CONFIGURATION (if needed)

### Increase Model Confidence Threshold
Edit: `myapp/footprint_detection.py` (line 20)
```python
CONFIDENCE = 0.30  # Change to 0.50 for stricter detection
```

### Adjust Polling Interval
Edit: `myapp/templates/upload.html` (line 660)
```javascript
}, 1500);  // Change 1500 to 2000 for slower polling
```

### Change Progress Update Frequency
Edit: `myapp/footprint_detection.py` (TIFF section)
```python
# Progress callbacks happen at: 5%, 40%, 80%, 100% for PNG/JPG
# For TIFF: updates every tile (per 2048x2048 block)
```

### Redis Connection String
Edit: `my_gis_project/settings.py` (line 119)
```python
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
```

---

## 🛑 STOPPING SERVICES

**Graceful Shutdown:**
```powershell
# Terminal 3: Press Ctrl+C
# Terminal 2: Press Ctrl+C
# Terminal 1: Press Ctrl+C
```

**Force Kill (if stuck):**
```powershell
taskkill /F /IM python.exe
taskkill /F /IM redis-server.exe
```

---

## 📋 PRE-FLIGHT CHECKLIST

Before starting, verify:

- [ ] Virtual environment exists: `d:\...\venv\`
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Model file exists: `ai_models/building_maskrcnn_trained.pth` (~170MB)
- [ ] Media folder writable: `media/` 
- [ ] Database initialized: `db.sqlite3`
- [ ] Django migrations applied: `python manage.py migrate`
- [ ] Sufficient disk space: >2GB free
- [ ] Port 8000 available (or change in `runserver`)
- [ ] Port 6379 available (Redis, if using)
- [ ] Port 5555 available (Flower, if using)

---

## ✅ FINAL CHECKLIST BEFORE RUNNING

```
System Requirements:
  ✓ Python 3.8+
  ✓ 4GB RAM (8GB+ recommended)
  ✓ GPU optional (but 10x faster)
  ✓ 2GB disk space free
  
Dependencies:
  ✓ Django 5.2+
  ✓ Celery 5.6+
  ✓ PyTorch
  ✓ OpenCV
  ✓ Rasterio
  ✓ GeoPandas
  
Files in Place:
  ✓ ai_models/building_maskrcnn_trained.pth
  ✓ myapp/footprint_detection.py
  ✓ myapp/tasks.py (with process_single_footprint)
  ✓ myapp/views.py (with all endpoints)
  ✓ myapp/templates/upload.html (with frontend logic)
  ✓ myapp/models.py (with ChangeResult footprint fields)
  
Configuration:
  ✓ settings.py has Celery config
  ✓ celery.py configured
  ✓ urls.py has all endpoints
  ✓ MEDIA_ROOT is writable
  ✓ FILE_UPLOAD_MAX_MEMORY_SIZE is large enough
  
Ready to Start?
  → Run: START_SERVICES.bat (or choose Option B/C above)
  → Navigate to: http://localhost:8000/upload/
  → Upload images and test!
```

---

## 🎉 YOU'RE ALL SET!

Everything is configured. Just start the services using Option A, B, or C above, and test the workflow!

**Questions or Issues?** 
- Check `API_REFERENCE.md` for endpoint details
- Check `FOOTPRINT_SETUP.md` for configuration options
- Check Celery worker logs for task errors
- Check Django server logs for HTTP errors

**Happy processing! 🚀**
