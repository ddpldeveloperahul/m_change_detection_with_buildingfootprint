# Building Footprint Detection - Complete Setup Guide

## Overview
This guide explains how to set up the building footprint detection system that runs in the background using Celery and shows progress to users.

---

## Architecture

### Workflow
1. **User uploads old & new images** → Images uploaded to server
2. **Footprint detection starts** → Background Celery tasks begin
3. **Progress shown in real-time** → Frontend polls `/footprint-status/` endpoint
4. **Start Upload button enabled** → When both footprints are ready
5. **Change detection runs** → Main processing begins

### Key Components
- **Model**: `ChangeResult` (stores footprint progress & status)
- **Celery Task**: `process_single_footprint` (runs AI detection in background)
- **Frontend**: AJAX polling + real-time progress trackers
- **Message Broker**: Redis/RabbitMQ (or memory for simple dev testing)

---

## OPTION 1: Production Setup with Redis (RECOMMENDED)

### Step 1: Install Redis
**Windows:**
```powershell
# Using Chocolatey
choco install redis-64

# Or download from: https://github.com/tporadowski/redis/releases
```

**macOS/Linux:**
```bash
brew install redis
# or
sudo apt-get install redis-server
```

### Step 2: Update Celery Configuration
Modify `my_gis_project/settings.py`:

```python
# ============================================
# CELERY CONFIGURATION (Production with Redis)
# ============================================
import os

CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Kolkata'

# Async task execution (production)
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_TASK_STORE_EAGER_RESULT = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Optional: Task timeout (30 minutes for large images)
CELERY_TASK_TIME_LIMIT = 1800
CELERY_TASK_SOFT_TIME_LIMIT = 1700
```

### Step 3: Install Required Packages
```bash
pip install redis celery
```

### Step 4: Run Redis Server
**Windows (in separate PowerShell window):**
```powershell
redis-server
```

**macOS/Linux:**
```bash
redis-server
```

Expected output: `* Ready to accept connections`

### Step 5: Run Celery Worker
**Windows (in separate PowerShell window, in project directory):**
```powershell
cd d:\AI_Portal\change_detection_main_with_footprint\change_detection_main\gis_django\my_gis_project

# Activate virtual environment
.\venv\Scripts\activate

# Run Celery worker
celery -A my_gis_project worker --loglevel=info
```

**Expected output:**
```
[*] Connected to redis://localhost:6379/0
[*] mingle: there are no known tasks
[*] Concurrency: 4 (prefork)
[*] Tasks:
  - myapp.tasks.process_single_footprint
  - myapp.tasks.run_change_detection
  - myapp.tasks.run_spatial_join
  - myapp.tasks.run_new_footprint_detection
```

### Step 6: Run Django Server (different terminal)
```powershell
# Activate virtual environment
.\venv\Scripts\activate

# Run server
python manage.py runserver
```

**Now the system is fully operational!**

---

## OPTION 2: Simple Development Setup (No Redis)

If you don't want to install Redis, you can test with the memory broker:

### Update `my_gis_project/settings.py`:
```python
# ============================================
# CELERY CONFIGURATION (Simple Development)
# ============================================

CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Kolkata'

# Synchronous execution (development - progress updates may be delayed)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_STORE_EAGER_RESULT = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = False
```

**Note**: With this setup:
- Tasks execute synchronously
- Progress updates will show only after task completion
- Good for testing, not for production

---

## Complete Multi-Terminal Setup (Production)

Run these 4 terminals simultaneously:

**Terminal 1: Redis Server**
```powershell
redis-server
```

**Terminal 2: Celery Worker**
```powershell
cd d:\AI_Portal\change_detection_main_with_footprint\change_detection_main\gis_django\my_gis_project
.\venv\Scripts\activate
celery -A my_gis_project worker --loglevel=info
```

**Terminal 3: Django Server**
```powershell
cd d:\AI_Portal\change_detection_main_with_footprint\change_detection_main\gis_django\my_gis_project
.\venv\Scripts\activate
python manage.py runserver
```

**Terminal 4: (Optional) Celery Flower Dashboard**
```powershell
cd d:\AI_Portal\change_detection_main_with_footprint\change_detection_main\gis_django\my_gis_project
.\venv\Scripts\activate
pip install flower
celery -A my_gis_project flower
# Access at http://localhost:5555/
```

---

## Testing the System

### 1. Navigate to Upload Page
```
http://localhost:8000/upload/
```

### 2. Upload Two Images
- Select OLD image (TIFF, JPG, PNG)
- Select NEW image (TIFF, JPG, PNG)

### 3. Observe Footprint Trackers
- Building Footprint Generation progress shows under each image
- Progress bar fills as AI model processes
- Status updates every 1.5 seconds

### 4. Start Upload
- "Start Upload" button enables when both footprints are ready
- Click to begin change detection process

---

## Model Architecture

The **Mask R-CNN** model detects building footprints with:
- **Confidence threshold**: 30% (adjustable in `footprint_detection.py`)
- **Tile processing**: 2048x2048 pixels for large TIFF files
- **Progress tracking**: Real-time updates to database
- **Output format**: PNG with building outlines highlighted

---

## File Locations

| File | Purpose |
|------|---------|
| `tasks.py` | Celery task: `process_single_footprint` |
| `footprint_detection.py` | AI inference & footprint generation |
| `views.py` | REST endpoints for upload & status |
| `templates/upload.html` | Frontend UI with progress trackers |
| `models.py` | Database schema (footprint fields) |
| `ai_models/building_maskrcnn_trained.pth` | Pre-trained model weights |

---

## Troubleshooting

### Issue: Tasks running synchronously (no background execution)
**Cause**: `CELERY_TASK_ALWAYS_EAGER = True`
**Solution**: Set to `False` and ensure Redis is running with Celery worker

### Issue: Progress not updating on frontend
**Cause**: Database not being updated in real-time
**Solution**: Ensure `process_single_footprint` progress_callback is saving correctly

### Issue: Celery worker not picking up tasks
**Cause**: Worker not running or not autodiscovering tasks
**Solution**: 
```powershell
celery -A my_gis_project worker --loglevel=info --reload
```

### Issue: Redis connection refused
**Cause**: Redis server not running
**Solution**: Start Redis: `redis-server`

### Issue: Model taking too long to load
**Cause**: First run loads model (~2GB)
**Solution**: Model is cached after first use

---

## Performance Optimization

### For Large TIFF Files (>500MB)
- Increase `CELERY_TASK_TIME_LIMIT` to 3600 (1 hour)
- Use GPU if available (model uses CUDA automatically)
- Process in separate worker pool

### Enable GPU Support
The model automatically uses GPU if PyTorch detects CUDA. No additional configuration needed.

---

## Next Steps

1. ✅ Fixed progress callback bug in `tasks.py`
2. ⏭️ Choose Redis or Simple setup above
3. ⏭️ Run the 3-4 terminals as shown
4. ⏭️ Test uploading images
5. ⏭️ Monitor Celery worker output for errors

**Questions?** Check Celery logs in worker terminal for detailed error messages.
