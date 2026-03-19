import os
import uuid
import shutil
import redis
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, WebSocket, WebSocketDisconnect
from pathlib import Path
from celery import Celery
import asyncio


app = FastAPI()

UPLOAD_DIR = Path("/app/data")
UPLOAD_DIR.mkdir(exist_ok=True)

celery_app = Celery(
    "worker",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0"
)

r = redis.Redis(host="redis", port=6379, db=0)

@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):

    await websocket.accept()

    pubsub = r.pubsub()
    pubsub.subscribe(f"status_{task_id}")

    try:
        while True:

            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

            if message:
                data = message["data"].decode("utf-8")

                await websocket.send_text(data)

                if "complete" in data or "error" in data:
                    break

            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        print(f"User disconnected from task {task_id}")
    finally:
        pubsub.unsubscribe(f"status_{task_id}")
        pubsub.close()
        await websocket.close()

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):

    task_id = str(uuid.uuid4())

    original_path = UPLOAD_DIR / f"{task_id}.pptx"

    with original_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    celery_app.send_task("tasks.convert_to_pdf", args=[task_id])

    return {"task_id": task_id, "status":"queued"}


