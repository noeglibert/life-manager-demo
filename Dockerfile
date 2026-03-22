FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Seed demo database at build time (baked into image)
ENV DEMO_MODE=true
ENV SECRET_KEY=demo-secret-key
RUN python seed_demo.py

# Expose port
EXPOSE 10000

# Run with gunicorn
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000", "--workers", "2", "--timeout", "120"]
