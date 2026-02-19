# Use PyTorch’s official CUDA 12.8 + cuDNN 9 runtime (Ubuntu 22.04)
FROM pytorch/pytorch:2.9.0-cuda12.8-cudnn9-runtime

WORKDIR /app

# Install build and system dependencies (includes GDAL)
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        build-essential \
        python3-venv \
        python3-dev \
        gdal-bin \
        libgdal-dev \
        libgl1 \
        libglib2.0-0 \
        curl && \
    rm -rf /var/lib/apt/lists/*

# Install GDAL Python bindings matching system GDAL
RUN pip install --no-cache-dir GDAL==3.4.1

RUN pip install --no-cache-dir numpy matplotlib opencv-python pillow polars psutil pyyaml requests scipy \
    && pip install --no-deps ultralytics-thop \
    && pip install --no-deps ultralytics==8.3.213

# Copy and install other requirements
COPY requirements_inference.txt .
RUN pip install --no-cache-dir -r requirements_inference.txt
RUN find /usr/local/lib/python3.*/ -type d -name "__pycache__" -exec rm -rf {} + \
    && find /usr/local/lib/python3.*/ -type f -name "*.pyc" -delete

# Copy the application
COPY inference ./inference
COPY inference_pipeline.py .

# Copy the models
COPY docker_entrypoint.sh .
RUN chmod +x docker_entrypoint.sh

# Stores input, datasets, results 
VOLUME ["/app/mnt"]

ENTRYPOINT ["./docker_entrypoint.sh"]