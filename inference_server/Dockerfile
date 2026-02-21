# Build stage
FROM pytorch/pytorch:2.9.0-cuda12.8-cudnn9-runtime AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install Heavy Python packages in builder
# Using --user to easily copy them later
COPY inference_server/requirements.txt .
RUN pip install --user --no-cache-dir GDAL==3.4.1 && \
    pip install --user --no-cache-dir -r requirements.txt && \
    pip install --user --no-deps ultralytics-thop && \
    pip install --user --no-deps ultralytics==8.3.213 && \
    # Force headless opencv to save space (no X11 dependencies)
    pip uninstall -y opencv-python && \
    pip install --user --no-cache-dir opencv-python-headless

# Final stage
FROM pytorch/pytorch:2.9.0-cuda12.8-cudnn9-runtime

WORKDIR /app

# Install ONLY necessary runtime libraries
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    gdal-bin \
    libglib2.0-0 \
    curl && \
    rm -rf /var/lib/apt/lists/*

# Copy installed python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy applications
COPY shared/ ./shared/
COPY inference_server/ ./inference_server/

VOLUME ["/data"]

EXPOSE 8001

CMD ["uvicorn", "inference_server.main:app", "--host", "0.0.0.0", "--port", "8001"]
