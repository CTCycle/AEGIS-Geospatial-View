# Background Job Management

ADSMOD uses a centralized, thread-based job management system to handle long-running operations like isotherm fitting, dataset processing, and chemical property scraping. This ensures the main FastAPI event loop remains unblocked and responsive.

## Core Concepts

The system is built around a singleton `JobManager` instance located in `server/utils/jobs.py`.

### Threading Model
- **Daemon Threads**: Each job runs in its own dedicated `threading.Thread`. The threads are set to `daemon=True`, meaning they will not prevent the application from shutting down.
- **Concurrency**: The Global Interpreter Lock (GIL) is respected, but since many of ADSMOD's heavy tasks (NumPy/SciPy fitting, PyTorch training) release the GIL or are I/O bound (network requests), threaded concurrency is effective.

### Job State
Every job is tracked via a thread-safe `JobState` object containing:
- **`job_id`**: A unique 8-character UUID string.
- **`status`**: Current state (`pending`, `running`, `completed`, `failed`, `cancelled`).
- **`progress`**: Float value from 0.0 to 100.0.
- **`result`**: The final output payload (dict) upon successful completion.
- **`error`**: Error message if the job failed.
- **`stop_requested`**: Boolean flag indicating if a user cancellation has been requested.

## Usage Guide

### 1. The Job Manager Singleton
Import the shared instance to interact with the system:
```python
from ADSMOD.server.utils.jobs import job_manager
```

### 2. Implementation Pattern
To create a new background service, define a synchronous runner function that performs the heavy lifting.

```python
def my_blocking_runner(payload: dict) -> dict:
    """
    This function runs inside the worker thread.
    """
    # 1. Periodically check for cancellation
    # Note: 'job_id' checks must be managed by passing the ID or handling it within the context
    
    # 2. Update progress (optional, if you have reference to the manager/id)
    # job_manager.update_progress(job_id, 50.0)
    
    # 3. Perform work
    result = perform_expensive_calculation(payload)
    
    return {"data": result}
```

### 3. Starting a Job in an API Endpoint
In your FastAPI route, use `start_job` to spawn the thread.

```python
@router.post("/start")
def start_processing(payload: Dict):
    # Optional: Prevent multiple jobs of the same type
    if job_manager.is_job_running("MY_JOB_TYPE"):
        raise HTTPException(400, "Job already in progress")

    job_id = job_manager.start_job(
        job_type="MY_JOB_TYPE",
        runner=my_blocking_runner,
        args=(payload,)
    )
    return {"job_id": job_id}
```

### 4. Cooperative Cancellation
Cancellation is **cooperative**, meaning the running thread must actively check if it should stop. It is not forcibly killed.

Inside your runner loop:
```python
if job_manager.should_stop(current_job_id):
    # Clean up resources if necessary
    return
```

## API Interaction

The frontend interacts with jobs via a polling mechanism:

1. **Start**: `POST /api/...` returns `{"job_id": "..."}`.
2. **Poll**: `GET /api/jobs/{job_id}` returns the full `JobState`.
   - The frontend updates progress bars based on the `progress` field.
   - If `status` is `completed`, the frontend displays the `result`.
   - If `status` is `failed`, the frontend displays the `error`.
