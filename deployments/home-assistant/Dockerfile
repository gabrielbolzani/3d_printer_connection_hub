ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.12-alpine3.19
FROM ${BUILD_FROM}

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install system dependencies
RUN apk add --no-cache \
    curl \
    git \
    gcc \
    musl-dev \
    linux-headers \
    libffi-dev \
    openssl-dev

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Environment variables
ENV PYTHONUNBUFFERED=1

# Expose port (Internal for HA Ingress)
EXPOSE 5000

# Fix permissions
RUN chmod a+x /app/deployments/home-assistant/run.sh

CMD ["/app/deployments/home-assistant/run.sh"]
