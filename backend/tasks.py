# THIS DUDE IS A WORKER WHO DOES THE PROCESSING

import subprocess
import os
import json
import redis
from pathlib import Path
from celery import Celery
from pptx import Presentation

UPLOAD_DIR = Path("/app/data")

celery_app = Celery(
    "worker",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0",
)

r = redis.Redis(host="redis", port=6379, db=0)

def count_pages(file_path):
    try:
        prs = Presentation(file_path)
        return len(prs.slides)
    except Exception as e:
        print(f"Metadata Error: {e}")
        return 0

@celery_app.task(name="tasks.convert_to_pdf")
def convert_to_pdf(task_id: str):
    input_file = UPLOAD_DIR / f"{task_id}.pptx"
    
    pages = count_pages(input_file)
    r.publish(f"status_{task_id}", json.dumps({
        "status": "processing", 
        "progress": 10, 
        "details": f"Detected {pages} slides. Starting engine..."
    }))

    command = [
        "libreoffice", "--headless", "--convert-to", "pdf",
        "--outdir", str(UPLOAD_DIR), str(input_file)
    ]

    try:
        r.publish(f"status_{task_id}", json.dumps({
            "status": "converting", 
            "progress": 30
        }))

        result = subprocess.run(command, capture_output=True, text=True, check=True)
        
        r.publish(f"status_{task_id}", json.dumps({
            "status": "complete", 
            "progress": 100,
            "pdf_url": f"/download/{task_id}.pdf" 
        }))

    except subprocess.CalledProcessError as e:
        r.publish(f"status_{task_id}", json.dumps({
            "status": "error", 
            "message": "LibreOffice failed to convert the file."
        }))
