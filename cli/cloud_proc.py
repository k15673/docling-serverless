#!/usr/bin/env python3
import os
import sys
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from botocore.exceptions import ClientError

SUPPORTED = (".pdf", ".docx")


def to_output_keys(filename: str):
    base = os.path.basename(filename)
    root, _ = os.path.splitext(base)
    return f"output/{root}.md", f"output/{root}.error.txt"


def upload_and_wait(s3, bucket: str, filepath: str, poll_sec: float, timeout_sec: int):
    base = os.path.basename(filepath)
    in_key = f"input/{base}"
    out_key, err_key = to_output_keys(filepath)

    print(f"[+] Uploading {filepath} -> s3://{bucket}/{in_key}")
    s3.upload_file(filepath, bucket, in_key)

    print(f"[~] Waiting for output: s3://{bucket}/{out_key}")
    start = time.time()
    spinner = ["|", "/", "-", "\\"]
    idx = 0

    while True:
        if time.time() - start > timeout_sec:
            raise TimeoutError(f"Timed out waiting for {out_key} (or {err_key})")

        # success?
        try:
            s3.head_object(Bucket=bucket, Key=out_key)
            break
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code not in ("404", "NoSuchKey", "NotFound"):
                raise

        # error?
        try:
            s3.head_object(Bucket=bucket, Key=err_key)
            local_err = os.path.join(os.getcwd(), os.path.basename(err_key))
            s3.download_file(bucket, err_key, local_err)
            with open(local_err, "r", encoding="utf-8", errors="ignore") as f:
                msg = f.read().strip()
            raise RuntimeError(f"Conversion failed. Error file downloaded: {local_err}\n{msg}")
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code not in ("404", "NoSuchKey", "NotFound"):
                raise

        print(f"\r    {spinner[idx % len(spinner)]} still converting...", end="", flush=True)
        idx += 1
        time.sleep(poll_sec)

    print("\r    ✓ conversion complete            ")

    local_out = os.path.join(os.getcwd(), os.path.basename(out_key))
    print(f"[↓] Downloading -> {local_out}")
    s3.download_file(bucket, out_key, local_out)

    return local_out


def main():
    p = argparse.ArgumentParser(
        description="Upload PDF/DOCX to S3 input/ and download converted Markdown from output/."
    )
    p.add_argument("files", nargs="+", help="PDF/DOCX files to convert")
    p.add_argument("--bucket", required=True, help="S3 bucket name created by CloudFormation")
    p.add_argument("--region", default="us-east-2", help="AWS region (default: us-east-2)")
    p.add_argument("--poll", type=float, default=2.5, help="Polling interval seconds (default: 2.5)")
    p.add_argument("--timeout", type=int, default=900, help="Timeout seconds (default: 900)")
    p.add_argument("--parallel", type=int, default=1, help="Convert N files in parallel (bonus feature)")
    args = p.parse_args()

    valid = []
    for f in args.files:
        if not os.path.isfile(f):
            print(f"[!] Not found: {f}", file=sys.stderr)
            sys.exit(2)
        if not f.lower().endswith(SUPPORTED):
            print(f"[!] Unsupported (must be PDF/DOCX): {f}", file=sys.stderr)
            sys.exit(2)
        valid.append(f)

    s3 = boto3.client("s3", region_name=args.region)

    if args.parallel <= 1 or len(valid) == 1:
        for f in valid:
            try:
                out = upload_and_wait(s3, args.bucket, f, args.poll, args.timeout)
                print(f"[✓] Done: {out}\n")
            except Exception as e:
                print(f"[x] Failed for {f}: {e}", file=sys.stderr)
        return

    print(f"[*] Running in parallel with {args.parallel} workers")
    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futures = {ex.submit(upload_and_wait, s3, args.bucket, f, args.poll, args.timeout): f for f in valid}
        for fut in as_completed(futures):
            f = futures[fut]
            try:
                out = fut.result()
                print(f"[✓] Done: {f} -> {out}")
            except Exception as e:
                print(f"[x] Failed: {f}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
