# 1. Use official Python image
FROM python:3.12-slim

# 2. Set working directory inside container
WORKDIR /app

# 3. Copy requirements first (for Docker caching)
COPY requirements.txt .

# 4. Install Python dependencies in container
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy entire project
COPY . .

# 6. Expose port 8000 for Django
EXPOSE 8000

# 7. Default command to run Django server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
