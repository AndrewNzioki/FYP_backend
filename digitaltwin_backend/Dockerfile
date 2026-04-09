# Use a lightweight Python image
FROM python:3.10-slim

# Force Python to print logs immediately (crucial for debugging on Render)
ENV PYTHONUNBUFFERED=1

# Set the working directory
WORKDIR /app

# Install system dependencies (sometimes needed for building packages)
RUN apt-get update && apt-get install -y gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy your requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your entire project into the container
COPY . .

# Make the start script executable
RUN chmod +x start.sh

# The container entrypoint
CMD ["./start.sh"]