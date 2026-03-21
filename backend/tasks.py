"""
Celery tasks for PPTX to PDF conversion.

Each file gets its own independent task for true parallel conversion.
"""
import logging
import tempfile
from pathlib import Path

from celery_app import celery
from converter import convert_pptx_to_pdf

logger = logging.getLogger(__name__)

# All output goes under the shared volume
OUTPUT_BASE = Path("/tmp/mubadal_uploads")
OUTPUT_BASE.mkdir(parents=True, exist_ok=True)


@celery.task(bind=True, name="convert_single_file")
def convert_single_file(self, input_path: str, original_filename: str) -> dict:
    """
    Convert a single PPTX file to PDF.
    Each file = one task = one worker. True concurrency.
    """
    try:
        self.update_state(state="CONVERTING", meta={"filename": original_filename})

        output_dir = tempfile.mkdtemp(prefix="out_", dir=str(OUTPUT_BASE))
        pdf_path = convert_pptx_to_pdf(input_path, output_dir)

        return {
            "status": "success",
            "pdf_path": str(pdf_path),
            "filename": pdf_path.name,
            "size": pdf_path.stat().st_size,
        }
    except Exception as e:
        logger.exception("Task failed for '%s'", original_filename)
        return {
            "status": "failed",
            "filename": original_filename,
            "error": str(e),
        }
