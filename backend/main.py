"""
Mubadal — PPTX to PDF Converter API.

FastAPI backend with Celery task queue for concurrent PPTX → PDF conversion.
"""
import io
import logging
import tempfile
import zipfile
from pathlib import Path

from celery.result import AsyncResult
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from celery_app import celery
from tasks import convert_single_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB per file
MAX_BATCH_FILES = 20
ALLOWED_EXTENSIONS = {".pptx"}

UPLOAD_BASE = Path("/tmp/mubadal_uploads")
UPLOAD_BASE.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Mubadal API",
    description="Convert PowerPoint (.pptx) files to PDF",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _validate_file(file: UploadFile) -> None:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{ext}'. Only .pptx files are accepted.",
        )


async def _save_upload(file: UploadFile, dest: Path) -> Path:
    saved_path = dest / file.filename
    total = 0
    with open(saved_path, "wb") as f:
        while chunk := await file.read(8192):
            total += len(chunk)
            if total > MAX_FILE_SIZE:
                saved_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File '{file.filename}' exceeds {MAX_FILE_SIZE // (1024*1024)} MB.",
                )
            f.write(chunk)
    return saved_path


# ── Health ──

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "mubadal"}


# ── Single Conversion ──

@app.post("/api/convert")
async def convert_single(file: UploadFile = File(...)):
    """Submit a single .pptx file. Returns task_id."""
    _validate_file(file)
    task_dir = Path(tempfile.mkdtemp(prefix="mubadal_", dir=str(UPLOAD_BASE)))
    saved = await _save_upload(file, task_dir)
    task = convert_single_file.delay(str(saved), file.filename)
    return {"task_id": task.id, "filename": file.filename}


# ── Batch Conversion ──

@app.post("/api/convert-batch")
async def convert_batch(files: list[UploadFile] = File(...)):
    """
    Submit multiple .pptx files. Each file becomes its own Celery task
    for true parallel conversion. Returns all task_ids.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum is {MAX_BATCH_FILES}.",
        )
    for f in files:
        _validate_file(f)

    task_dir = Path(tempfile.mkdtemp(prefix="mubadal_batch_", dir=str(UPLOAD_BASE)))
    task_ids = []
    for f in files:
        saved = await _save_upload(f, task_dir)
        task = convert_single_file.delay(str(saved), f.filename)
        task_ids.append({"task_id": task.id, "filename": f.filename})

    return {"tasks": task_ids, "file_count": len(files)}


# ── Task Status ──

@app.get("/api/task/{task_id}")
async def get_task_status(task_id: str):
    """Poll a single task's status."""
    result = AsyncResult(task_id, app=celery)

    if result.state == "PENDING":
        return {"state": "PENDING", "task_id": task_id}
    if result.state == "CONVERTING":
        return {"state": "CONVERTING", "task_id": task_id, "progress": result.info}
    if result.state == "SUCCESS":
        return {"state": "SUCCESS", "task_id": task_id, "result": result.result}
    if result.state == "FAILURE":
        return {"state": "FAILURE", "task_id": task_id, "error": str(result.info)}
    return {"state": result.state, "task_id": task_id}


@app.post("/api/tasks/status")
async def get_bulk_status(task_ids: list[str]):
    """Poll multiple tasks at once. Used by the frontend for batch tracking."""
    statuses = []
    for tid in task_ids:
        result = AsyncResult(tid, app=celery)
        entry = {"task_id": tid, "state": result.state}
        if result.state == "SUCCESS":
            entry["result"] = result.result
        elif result.state == "CONVERTING":
            entry["progress"] = result.info
        elif result.state == "FAILURE":
            entry["error"] = str(result.info)
        statuses.append(entry)
    return {"tasks": statuses}


# ── Download ──

@app.get("/api/download/{task_id}")
async def download_result(task_id: str):
    """Download the PDF for a completed single-file task."""
    result = AsyncResult(task_id, app=celery)
    if result.state != "SUCCESS":
        raise HTTPException(status_code=400, detail=f"Task not complete: {result.state}")

    data = result.result
    if data.get("status") != "success":
        raise HTTPException(status_code=500, detail="Conversion failed")

    pdf_path = Path(data["pdf_path"])
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="File no longer available")
    return FileResponse(path=str(pdf_path), media_type="application/pdf", filename=data["filename"])


@app.post("/api/download-batch")
async def download_batch(task_ids: list[str]):
    """
    Collect all completed PDFs from multiple tasks into a ZIP and return it.
    Called by the frontend after all individual tasks finish.
    """
    pdf_paths = []
    errors = []

    for tid in task_ids:
        result = AsyncResult(tid, app=celery)
        if result.state != "SUCCESS":
            errors.append({"task_id": tid, "error": f"Not complete: {result.state}"})
            continue
        data = result.result
        if data.get("status") != "success":
            errors.append({"task_id": tid, "error": data.get("error", "failed")})
            continue
        pdf = Path(data["pdf_path"])
        if pdf.exists():
            pdf_paths.append(pdf)
        else:
            errors.append({"task_id": tid, "error": "File not found"})

    if not pdf_paths:
        raise HTTPException(status_code=500, detail="No files available for download")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for pdf in pdf_paths:
            zf.write(pdf, pdf.name)
    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=converted_pdfs.zip",
            "X-Conversion-Success": str(len(pdf_paths)),
            "X-Conversion-Errors": str(len(errors)),
        },
    )
