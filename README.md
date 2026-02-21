# Kitagawa Monorepo

Maritime surveillance system using YOLO vessel detection on SAR/EO satellite imagery, AIS track correlation, and a Leaflet-based frontend.

## Project Structure

- `backend_server/`: FastAPI server for data ingestion, correlation, and frontend API.
- `inference_server/`: GPU-enabled FastAPI server for running YOLO inference.
- `client/`: React + Vite frontend for map visualization.
- `shared/`: Shared Python schemas and configuration.
- `data/`: Local directory for satellite imagery and database storage.

## Prerequisites

- **Docker & Docker Compose**: Recommended for running the full stack.
- **NVIDIA Container Toolkit**: Required for `inference-server` GPU acceleration.
- **Node.js 20+**: If running the client locally.
- **Python 3.10+**: If running servers locally.

## Getting Started (Docker)

The easiest way to run the entire stack is using Docker Compose:

```bash
# Clone the repository
git clone <repository-url>
cd kitagawa-backend

# (Optional) Set your Copernicus credentials in .env
# COPERNICUS_USERNAME=your_username
# COPERNICUS_PASSWORD=your_password

# Build and start the stack
docker-compose up --build
```

The services will be available at:
- **Frontend**: [http://localhost:3000](http://localhost:3000)
- **Backend API**: [http://localhost:8000](http://localhost:8000)
- **Inference API**: [http://localhost:8001](http://localhost:8001)
- **MinIO Console**: [http://localhost:9001](http://localhost:9001)

## Local Development (Non-Docker)

### 1. Database & Object Storage
You still need PostgreSQL/PostGIS and MinIO. You can start just these using:
```bash
docker-compose up -d postgres minio
```

### 2. Backend Server
```bash
cd backend_server
pip install -r requirements.txt
python main.py
```

### 3. Inference Server
```bash
cd inference_server
# Ensure you have models in inference_server/models/
pip install -r requirements.txt
python main.py
```

### 4. Client
```bash
cd client
npm install
npm run dev
```

## Running the Pipeline

To trigger a data processing pipeline for a specific set of S1/S2 image names:

```bash
curl -X POST http://localhost:8000/api/v1/pipeline/run \
     -H "Content-Type: application/json" \
     -d '["S1A_IW_GRDH_1SDV_20230501T..."]'
```