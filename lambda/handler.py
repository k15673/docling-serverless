import os
import json
import logging
import tempfile
from pathlib import Path

# IMPORTANT: set writable cache dirs BEFORE importing docling/rapidocr/transformers
CACHE_ROOT = Path("/tmp/cache")
CACHE_ROOT.mkdir(parents=True, exist_ok=True)

HF_HOME = CACHE_ROOT / "hf"
os.environ.setdefault("HF_HOME", str(HF_HOME))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(HF_HOME / "hub"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(HF_HOME / "transformers"))
os.environ.setdefault("TORCH_HOME", str(CACHE_ROOT / "torch"))
os.environ.setdefault("XDG_CACHE_HOME", str(CACHE_ROOT / ".cache"))

RO_HOME = CACHE_ROOT / "rapidocr"
RO_MODELS = RO_HOME / "models"
RO_MODELS.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("RAPIDOCR_HOME", str(RO_HOME))
os.environ.setdefault("RAPIDOCR_MODEL_PATH", str(RO_MODELS))

import boto3
from botocore.exceptions import ClientError
from docling.document_converter import DocumentConverter

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

s3 = boto3.client("s3")

INPUT_PREFIX = os.getenv("INPUT_PREFIX", "input/")
OUTPUT_PREFIX = os.getenv("OUTPUT_PREFIX", "output/")
SUPPORTED_EXT = {".pdf", ".docx"}


def _safe_basename(key: str) -> str:
    name = key.split("/")[-1]
    return name.replace("\\", "_").replace("/", "_")


def _output_key_for(input_key: str) -> str:
    base = _safe_basename(input_key)
    root, _ = os.path.splitext(base)
    return f"{OUTPUT_PREFIX}{root}.md"


def _write_error(bucket: str, err_key: str, message: str) -> None:
    try:
        s3.put_object(
            Bucket=bucket,
            Key=err_key,
            Body=message.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
    except Exception:
        logger.exception("Failed to upload error marker file: %s", err_key)


def lambda_handler(event, context):
    if not event or "Records" not in event:
        return {
            "ok": True,
            "message": "Lambda is deployed. Upload a .pdf/.docx into input/ in your bucket.",
            "expected": {
                "input_prefix": INPUT_PREFIX,
                "output_prefix": OUTPUT_PREFIX,
                "extensions": sorted(list(SUPPORTED_EXT)),
            },
        }

    logger.info("event=%s", json.dumps(event))

    try:
        record = event["Records"][0]
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
    except (KeyError, IndexError, TypeError):
        logger.exception("Invalid S3 event format")
        return {"ok": False, "error": "Invalid S3 event format"}

    if not key.startswith(INPUT_PREFIX):
        logger.info("Skipping object not under input prefix: %s", key)
        return {"ok": True, "skipped": True, "reason": f"Not under {INPUT_PREFIX}", "key": key}

    _, ext = os.path.splitext(key.lower())
    if ext not in SUPPORTED_EXT:
        logger.info("Skipping unsupported file type: %s", key)
        return {"ok": True, "skipped": True, "reason": "Unsupported extension", "key": key}

    out_key = _output_key_for(key)
    err_key = out_key.replace(".md", ".error.txt")

    with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
        local_in = os.path.join(tmpdir, _safe_basename(key))
        local_out = os.path.join(tmpdir, "converted.md")

        try:
            logger.info("Downloading s3://%s/%s -> %s", bucket, key, local_in)
            s3.download_file(bucket, key, local_in)
        except ClientError as e:
            logger.exception("Failed to download input")
            _write_error(bucket, err_key, f"Download failed: {e}")
            return {"ok": False, "error": "Download failed", "bucket": bucket, "key": key}

        try:
            logger.info("Converting with Docling: %s", local_in)
            converter = DocumentConverter()
            result = converter.convert(local_in)

            md_text = None
            if hasattr(result, "document") and hasattr(result.document, "export_to_markdown"):
                md_text = result.document.export_to_markdown()
            elif hasattr(result, "export_to_markdown"):
                md_text = result.export_to_markdown()

            if not md_text:
                raise RuntimeError("Docling returned no Markdown output")

            with open(local_out, "w", encoding="utf-8") as f:
                f.write(md_text)

        except Exception as e:
            logger.exception("Conversion failed")
            _write_error(bucket, err_key, str(e))
            return {"ok": False, "error": "Conversion failed", "detail": str(e)}

        try:
            logger.info("Uploading markdown -> s3://%s/%s", bucket, out_key)
            with open(local_out, "rb") as f:
                s3.put_object(
                    Bucket=bucket,
                    Key=out_key,
                    Body=f.read(),
                    ContentType="text/markdown; charset=utf-8",
                )
        except ClientError as e:
            logger.exception("Failed to upload output")
            _write_error(bucket, err_key, f"Upload failed: {e}")
            return {"ok": False, "error": "Upload failed", "out_key": out_key}

    logger.info("Success: %s -> %s", key, out_key)
    return {"ok": True, "bucket": bucket, "input_key": key, "output_key": out_key}
