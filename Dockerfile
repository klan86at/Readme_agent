# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Ensure pip doesn't cache packages (keeps image smaller)
    PIP_NO_CACHE_DIR=1 \
    # Hugging Face Spaces port requirement
    PORT=7860 \
    # App-specific environment configurations
    OUTPUT_DIR=/app/outputs

# Set working directory
WORKDIR /app

# Install git (required by GitService to clone repos)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker build cache
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Create outputs directory (ensure it's writable by non-root users if needed)
RUN mkdir -p /app/outputs && chmod 777 /app/outputs

# Copy the rest of the application
COPY . .

# Expose the standard Hugging Face Spaces port
EXPOSE 7860

# Run the FastAPI server using uvicorn
CMD ["uvicorn", "agentic_codebase_reader.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "7860", "--workers", "2"]
