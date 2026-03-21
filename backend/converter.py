"""
PPTX to PDF converter module using LibreOffice headless.

Each conversion uses an isolated user profile so multiple instances
can run concurrently without locking.
"""
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

LIBRE_OFFICE_BINARY = "soffice"
CONVERSION_TIMEOUT = 120  # seconds


def convert_pptx_to_pdf(input_path: str, output_dir: str) -> Path:
    """
    Convert a .pptx file to PDF using LibreOffice headless mode.

    Uses a unique user profile directory per invocation to allow
    concurrent conversions without LibreOffice profile locking.
    """
    input_file = Path(input_path)
    output_directory = Path(output_dir)
    output_directory.mkdir(parents=True, exist_ok=True)

    expected_pdf = output_directory / f"{input_file.stem}.pdf"

    # Create a unique, temporary user profile so multiple soffice
    # processes don't fight over a single lock file.
    profile_dir = tempfile.mkdtemp(prefix="lo_profile_")

    cmd = [
        LIBRE_OFFICE_BINARY,
        "--headless",
        "--norestore",
        "--nolockcheck",
        f"-env:UserInstallation=file://{profile_dir}",
        "--convert-to", "pdf",
        "--outdir", str(output_directory),
        str(input_file),
    ]

    logger.info("Converting '%s' -> '%s'", input_file.name, expected_pdf.name)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CONVERSION_TIMEOUT,
        )

        if result.returncode != 0:
            logger.error("LibreOffice stderr: %s", result.stderr)
            raise RuntimeError(
                f"LibreOffice conversion failed (exit code {result.returncode}): "
                f"{result.stderr.strip()}"
            )

        if not expected_pdf.exists():
            raise RuntimeError(
                f"Conversion completed but output file not found: {expected_pdf}"
            )

        logger.info("Successfully converted '%s' (%.1f KB)",
                     expected_pdf.name, expected_pdf.stat().st_size / 1024)
        return expected_pdf

    except subprocess.TimeoutExpired:
        logger.error("Conversion timed out after %ds for '%s'",
                      CONVERSION_TIMEOUT, input_file.name)
        raise RuntimeError(
            f"Conversion timed out after {CONVERSION_TIMEOUT} seconds"
        )
    finally:
        # Clean up the temp profile
        shutil.rmtree(profile_dir, ignore_errors=True)
