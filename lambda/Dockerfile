# ---- builder ----
FROM public.ecr.aws/lambda/python:3.12 AS builder
WORKDIR /build

COPY requirements.txt .

# Build deps + runtime libs needed by PDF conversion (libGL + X libs)
RUN microdnf install -y \
      gcc gcc-c++ make \
      mesa-libGL mesa-libEGL \
      libXext libXrender libSM \
    && pip install --no-cache-dir -r requirements.txt -t /opt/python \
    && microdnf clean all \
    && rm -rf /root/.cache

# ✅ CRITICAL FIX:
# RapidOCR tries to download/write model files under /opt/python/rapidocr/models (read-only in Lambda).
# We remove that folder in the image and replace with a symlink to /tmp/cache/rapidocr/models.
RUN if [ -d "/opt/python/rapidocr/models" ]; then rm -rf /opt/python/rapidocr/models; fi \
    && mkdir -p /tmp/cache/rapidocr/models \
    && ln -s /tmp/cache/rapidocr/models /opt/python/rapidocr/models


# ---- runtime ----
FROM public.ecr.aws/lambda/python:3.12

# Runtime libs needed by PDF conversion inside Lambda container
RUN microdnf install -y \
      mesa-libGL mesa-libEGL mesa-dri-drivers \
      libglvnd-glx libglvnd-opengl \
      libXext libXrender libSM \
    && microdnf clean all

# Put caches in /tmp (writable in Lambda)
ENV HF_HOME=/tmp/cache/hf \
    HUGGINGFACE_HUB_CACHE=/tmp/cache/hf/hub \
    TRANSFORMERS_CACHE=/tmp/cache/hf/transformers \
    TORCH_HOME=/tmp/cache/torch \
    XDG_CACHE_HOME=/tmp/cache/.cache \
    RAPIDOCR_HOME=/tmp/cache/rapidocr \
    RAPIDOCR_MODEL_PATH=/tmp/cache/rapidocr/models

COPY --from=builder /opt/python /opt/python
COPY handler.py ${LAMBDA_TASK_ROOT}/handler.py

CMD ["handler.lambda_handler"]
