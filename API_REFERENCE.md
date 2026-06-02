# Building Footprint Detection - Complete API Reference

## Workflow Flow Chart

```
┌─────────────────────────────────────────────────────────────────────┐
│                    USER UPLOADS IMAGES                              │
│                 (/upload/ - GET HTML Form)                          │
└────────────────────────┬────────────────────────────────────────────┘
                         │
        ┌────────────────┴────────────────┐
        │                                 │
    [File 1]                         [File 2]
   OLD Image                        NEW Image
        │                                 │
        └────────────────┬────────────────┘
                         │
         ┌───────────────▼──────────────┐
         │  DRAG-DROP / FILE SELECT     │
         │  (Frontend: showName())       │
         └───────────────┬──────────────┘
                         │
         ┌───────────────▼──────────────┐
         │  AUTO UPLOAD (background)    │
         │  POST /upload-chunk/         │
         │  → Returns: file_path        │
         └───────────────┬──────────────┘
                         │
        ┌────────────────┴────────────────┐
        │                                 │
   OLD_PATH                          NEW_PATH
        │                                 │
        └────────────────┬────────────────┘
                         │
         ┌───────────────▼──────────────┐
         │ START FOOTPRINT DETECTION    │
         │ POST /start-footprint-       │
         │       detection/             │
         │ Payload: {                   │
         │   file_path: ...,            │
         │   image_type: 'old'/'new',   │
         │   job_id: ...                │
         │ }                            │
         │ → Returns: job_id            │
         └───────────────┬──────────────┘
                         │
        ┌────────────────┴────────────────┐
        │                                 │
    OLD_FP_TASK                    NEW_FP_TASK
    (Celery)                       (Celery)
        │                                 │
        ▼                                 ▼
    ┌─────────────────────────────────────┐
    │   FRONTEND POLLING (every 1.5s)     │
    │   GET /footprint-status/{job_id}/   │
    │   → Returns: {                      │
    │       old_status: 'processing',     │
    │       new_status: 'processing',     │
    │       old_progress: 45,             │
    │       new_progress: 32,             │
    │       ready: false                  │
    │     }                               │
    └──────┬──────────────────────────────┘
           │
           ▼
    ┌─────────────────────────────────────┐
    │  UPDATE PROGRESS BARS (LIVE)        │
    │  Show % under each image            │
    │  Spinner + status message           │
    └──────┬──────────────────────────────┘
           │
    ┌──────┴──────┐
    │             │
   NO           YES (ready: true)
    │             │
    │    ┌────────▼──────────────┐
    │    │ BOTH COMPLETED ✓      │
    │    │ Enable "Start Upload" │
    │    │ Change button state   │
    │    └────────┬──────────────┘
    │             │
    └─────────────┤
                  │
    ┌─────────────▼──────────────┐
    │  USER CLICKS "START UPLOAD"│
    └──────────┬─────────────────┘
               │
    ┌──────────▼──────────────┐
    │  START CHANGE DETECTION │
    │  POST /start-processing/│
    │  Payload: {             │
    │    file1: old_path,     │
    │    file2: new_path,     │
    │    job_id: ...          │
    │  }                      │
    │  → Returns: task_id     │
    └──────────┬──────────────┘
               │
    ┌──────────▼──────────────┐
    │  CELERY TASK RUNS       │
    │  run_change_detection() │
    │  (Main Processing)      │
    └──────────┬──────────────┘
               │
    ┌──────────▼──────────────┐
    │  POLL TASK STATUS       │
    │  GET /task-status/{id}/ │
    │  → Returns: status,     │
    │    result.id            │
    └──────────┬──────────────┘
               │
    ┌──────────▼──────────────┐
    │  REDIRECT TO RESULT     │
    │  /result/?id={result_id}│
    └──────────┬──────────────┘
               │
    ┌──────────▼──────────────┐
    │  DISPLAY RESULTS        │
    │  • Change Map (PNG)     │
    │  • Raster Data (TIF)    │
    │  • Shapefile (SHP+ZIP)  │
    │  • Download Buttons     │
    └────────────────────────┘
```

---

## API Endpoints Reference

### 1. **Upload Image Chunk**
```
POST /upload-chunk/
Content-Type: multipart/form-data

Request:
  file: <binary file data>

Response (200):
  {
    "file_path": "/home/user/media/uploads/user_1/image.tif",
    "message": "File uploaded successfully"
  }

Response (429 - Server Busy):
  {
    "error": "Server busy. username's change detection is already processing..."
  }
```

### 2. **Start Footprint Detection**
```
POST /start-footprint-detection/
Content-Type: application/json
X-CSRFToken: <token>

Request:
  {
    "file_path": "/home/user/media/uploads/user_1/old_image.tif",
    "image_type": "old",  // or "new"
    "job_id": 42          // optional: create new if not provided
  }

Response (200):
  {
    "status": "started",
    "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "job_id": 42
  }

Response (400):
  {
    "error": "file_path and image_type are required"
  }
```

### 3. **Get Footprint Status** (POLLING ENDPOINT)
```
GET /footprint-status/{job_id}/

Response (200):
  {
    "job_id": 42,
    "old_status": "processing",      // pending|processing|completed|failed
    "new_status": "processing",
    "old_progress": 45,              // 0-100
    "new_progress": 32,              // 0-100
    "ready": false,                  // true when both completed
    "old_footprint_url": "/media/footprints/old_fp_42.png",  // if completed
    "new_footprint_url": "/media/footprints/new_fp_42.png"   // if completed
  }
```

### 4. **Start Change Detection**
```
POST /start-processing/
Content-Type: application/json
X-CSRFToken: <token>

Request:
  {
    "file1": "/home/user/media/uploads/user_1/old_image.tif",
    "file2": "/home/user/media/uploads/user_1/new_image.tif",
    "job_id": 42
  }

Response (200):
  {
    "task_id": "x1y2z3a4-b5c6-7890-defg-hi1234567890",
    "job_id": 42
  }

Response (429 - Server Busy):
  {
    "error": "Server busy. Another user is processing..."
  }
```

### 5. **Get Task Status** (POLLING ENDPOINT)
```
GET /task-status/{task_id}/

Response (200 - Processing):
  {
    "task_id": "x1y2z3a4-...",
    "status": "PENDING"  // or STARTED, SUCCESS, FAILURE
  }

Response (200 - Completed):
  {
    "task_id": "x1y2z3a4-...",
    "status": "SUCCESS",
    "result": {
      "id": 42,
      "status": "done"
    }
  }

Response (200 - Failed):
  {
    "task_id": "x1y2z3a4-...",
    "status": "FAILURE",
    "error": "Error message"
  }
```

### 6. **Get Result**
```
GET /result/?id={result_id}

Returns: HTML page with:
  • Change detection map (PNG)
  • Aligned preview (PNG)
  • Raster data (TIF)
  • Shapefile ZIP download
  • Download buttons
```

---

## Celery Task Details

### Task: `process_single_footprint`
```python
@shared_task(bind=True)
def process_single_footprint(self, file_path, job_id, image_type):
    """
    Run building footprint detection on single image.
    
    Args:
        file_path: str - Full path to image (TIFF/JPG/PNG)
        job_id: int - ChangeResult.id
        image_type: str - 'old' or 'new'
    
    Flow:
    1. Set status to 'processing'
    2. Load Mask R-CNN model (cached after first use)
    3. Process image (with progress callbacks)
    4. Save footprint to media/footprints/
    5. Update status to 'completed' or 'failed'
    
    Progress Callback:
    - Called with 0-100 value during processing
    - Updates ChangeResult.footprint_old_progress or footprint_new_progress
    - Frontend polls every 1.5s and displays live progress bar
    """
```

### Task: `run_change_detection`
```python
@shared_task(bind=True)
def run_change_detection(self, img23_path, img25_path, user_id, job_id):
    """
    Run main change detection analysis.
    
    Flow:
    1. Create preview PNG from TIFF files
    2. Run change detection model
    3. Align new image to old image
    4. Generate change map (PNG)
    5. Export raster results (TIF)
    6. Export shapefile results (SHP)
    7. Save to ChangeResult.result_* fields
    8. Update status to 'done' or 'failed'
    """
```

---

## Frontend JavaScript Functions

### Auto-Trigger Footprint Detection
```javascript
handleBackgroundFootprint(file, imageType, index)
// When user selects a file:
// 1. Upload file to /upload-chunk/
// 2. Start footprint detection via /start-footprint-detection/
// 3. Show progress tracker
// 4. Call startFootprintPolling()
```

### Real-Time Progress Polling
```javascript
startFootprintPolling()
// Polls /footprint-status/{job_id}/ every 1.5 seconds
// Updates progress bars and status messages
// Stops when both footprints ready or one fails
```

### Update Button State
```javascript
updateSubmitButtonState()
// Checks: oldReady && newReady
// If true:
//   - Enable "Start Upload" button
//   - Set opacity to 1
//   - Remove cursor: not-allowed
// If false:
//   - Disable button
//   - Set opacity to 0.6
//   - Show appropriate message
```

---

## Database Schema

### ChangeResult Model
```python
class ChangeResult(models.Model):
    user = ForeignKey(User)
    
    # Original uploads
    uploaded_2023 = FileField('uploads/')
    uploaded_2025 = FileField('uploads/')
    
    # Footprint detection status
    footprint_old_status = CharField('pending'|'processing'|'completed'|'failed')
    footprint_new_status = CharField('pending'|'processing'|'completed'|'failed')
    footprint_old_progress = IntegerField(0-100)
    footprint_new_progress = IntegerField(0-100)
    footprint_old = FileField('footprints/', null=True)
    footprint_new = FileField('footprints/', null=True)
    
    # Main analysis results
    result_png = FileField('images_upload/')
    result_tif = FileField('images_upload/')
    result_shp = FileField('images_upload/')
    status = CharField('pending'|'processing'|'done'|'failed')
    
    @property
    def footprints_ready(self):
        return (self.footprint_old_status == "completed" 
                and self.footprint_new_status == "completed")
```

---

## Configuration

### Production (with Redis)
```python
# my_gis_project/settings.py
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_TASK_ALWAYS_EAGER = False  # Async execution
```

### Development (Memory Broker)
```python
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'
CELERY_TASK_ALWAYS_EAGER = True  # Sync execution
```

---

## Key Features

✅ **Real-Time Progress Tracking**
- Progress updates every 1.5 seconds
- Live percentage display under each image
- Spinner animations for user feedback

✅ **Background Processing**
- Celery tasks run asynchronously
- Main thread doesn't block
- User can upload while model processes

✅ **Smart Button Management**
- Disabled until both footprints ready
- Shows helpful status messages
- Prevents accidental re-submissions

✅ **Fault Tolerance**
- Failed tasks marked as 'failed'
- User can re-upload images
- Database tracks all states

✅ **Large File Support**
- Chunked uploads (resumable.js)
- Tile-based TIFF processing (2048x2048)
- Automatic normalization

---

## Testing Checklist

- [ ] Redis server running (if not using memory broker)
- [ ] Celery worker running
- [ ] Django server running
- [ ] Navigate to http://localhost:8000/upload/
- [ ] Upload OLD image
- [ ] Watch OLD footprint progress tracker
- [ ] Upload NEW image
- [ ] Watch NEW footprint progress tracker
- [ ] Both complete → button enables
- [ ] Click "Start Upload"
- [ ] Watch main progress bar
- [ ] See result page with outputs

---

## Emergency Troubleshooting

```bash
# Kill all hung processes
taskkill /F /IM python.exe
taskkill /F /IM redis-server.exe

# Clear celery tasks
celery -A my_gis_project purge

# Check celery worker logs
celery -A my_gis_project worker --loglevel=debug

# Clear Django cache
python manage.py clear_cache

# Reset database
python manage.py migrate --fake-initial
```
