# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    python3-dev && \
    rm -rf /var/lib/apt/lists/*

COPY backend_server/requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies ONLY
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    gdal-bin \
    libgeos-c1v5 \
    curl \
    unzip && \
    rm -rf /var/lib/apt/lists/*

# Pre-download Landmask & Boundaries (Internal to Image)
WORKDIR /app/landmask
RUN curl -L http://www.soest.hawaii.edu/pwessel/gshhg/gshhg-shp-2.3.7.zip -o gshhg.zip && \
    unzip gshhg.zip && \
    rm gshhg.zip && \
    curl -L https://github.com/lmirosevic/ReverseGeo/raw/master/lib/reverse_geo/World-EEZ.geojson -o world_eez.geojson && \
    curl -L https://raw.githubusercontent.com/newzealandpaul/Shipping-Lanes/main/data/Shipping_Lanes_v1.geojson -o shipping_lanes.geojson
WORKDIR /app

# Copy installed python packages
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy shared package
COPY shared/ ./shared/

# Copy backend server
COPY backend_server/ ./backend_server/

VOLUME ["/data"]

EXPOSE 8000

CMD ["uvicorn", "backend_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
