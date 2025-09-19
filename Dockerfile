# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY BACKEND/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY BACKEND/ .

# List files to debug what was copied
RUN ls -la

# Create a simple .env file with placeholder values (will be overridden by Render env vars)
RUN echo "MONGO_URL=mongodb+srv://avacarrel:PWih03O7JCO3fPze@grocery-scheduler-clust.6fxjap1.mongodb.net/?retryWrites=true&w=majority&appName=grocery-scheduler-cluster" > .env && \
    echo "DB_NAME=grocery-scheduler" >> .env && \
    echo "CORS_ORIGINS=placeholder" >> .env

# Expose port
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
