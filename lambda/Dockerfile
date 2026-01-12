
# ---- builder ----
FROM public.ecr.aws/lambda/python:3.12 AS builder
WORKDIR /build

COPY requirements.txt .

# Build deps + runtime libs needed by PDF conversion (libGL.so.1, X libs)
RUN microdnf install -y \
      gcc gcc-c++ make \
      mesa-libGL mesa-libEGL \
      libXext libXrender libSM \
    && pip install --no-cache-dir -r requirements.txt -t /opt/python \
    && microdnf clean all \
    && rm -rf /root/.cache

# ---- runtime ----
FROM public.ecr.aws/lambda/python:3.12

# Runtime libs needed by PDF conversion inside Lambda container
RUN microdnf install -y \
      mesa-libGL mesa-libEGL \
      libXext libXrender libSM \
    && microdnf clean all

# Put HF caches in /tmp (writable in Lambda)
ENV HF_HOME=/tmp/hf \
    HUGGINGFACE_HUB_CACHE=/tmp/hf/hub \
    TRANSFORMERS_CACHE=/tmp/hf/transformers \
    TORCH_HOME=/tmp/torch \
    XDG_CACHE_HOME=/tmp/.cache

COPY --from=builder /opt/python /opt/python
COPY handler.py ${LAMBDA_TASK_ROOT}/handler.py

CMD ["handler.lambda_handler"]
