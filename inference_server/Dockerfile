# Build stage
FROM pytorch/pytorch:2.9.0-cuda12.8-cudnn9-runtime AS builder

WORKDIR /app

# Install build dependencies
RUN rm -f /etc/apt/apt.conf.d/docker-clean; echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update -y && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libgdal-dev

# Environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install Heavy Python packages in builder
# Using --user to easily copy them later
COPY inference_server/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --user --no-cache-dir GDAL==3.4.1 && \
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
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update -y && \
    apt-get install -y --no-install-recommends \
    gdal-bin \
    libglib2.0-0 \
    curl \
    unzip

# Pre-download Landmask (Internal to Image)
WORKDIR /app/landmask
RUN curl -L http://www.soest.hawaii.edu/pwessel/gshhg/gshhg-shp-2.3.7.zip -o gshhg.zip && \
    unzip gshhg.zip && \
    rm gshhg.zip
WORKDIR /app

# Copy installed python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy applications
COPY shared/ ./shared/
COPY inference_server/ ./inference_server/

VOLUME ["/data"]

EXPOSE 8001

CMD ["uvicorn", "inference_server.main:app", "--host", "0.0.0.0", "--port", "8001"]
