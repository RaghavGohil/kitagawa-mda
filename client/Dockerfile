# Build stage
FROM node:20-slim AS build

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* pnpm-lock.yaml* bun.lockb* ./

# Install dependencies
# Using npm for simplicity in Docker
RUN npm install

# Copy source
COPY . .

# Set API URL at build time (Vite bakes import.meta.env at build time)
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL

# Build the app
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy build artifacts from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Replace default nginx config if needed
# COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
