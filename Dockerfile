FROM python:3.9-slim

WORKDIR /app

# Install dependencies required by Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements and install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser binaries and system dependencies
RUN playwright install --with-deps chromium

# Copy the rest of the application
COPY . .

# Default port for Render/Railway
ENV PORT=8000
EXPOSE 8000

# Start the FastAPI server
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
