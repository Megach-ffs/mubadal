import os
import uuid
import shutil
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from pathlib import Path
from celery import Celery

app FastAPI()

UPLOAD_DIR = Path("app/data")
UPLOAD_DIR.mkdir(exist_ok=True)

celery_app = Celery(
    "worker",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0"
)

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):

    task_id = str(uuid.uuid4())

    original_path = UPLOAD_DIR / f"{task_id}.pptx"

    with original_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    celery_app.send_task("tasks.convert_to_pdf", args=[task_id])

    return {"task_id": task_id, "status":"queued"}


