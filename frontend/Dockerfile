# Python 이미지 사용
FROM python:3.9-slim

# Set environment variables to prevent Python from writing .pyc files and buffering output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies for Python and Streamlit
RUN apt-get update && apt-get install -y \
  build-essential \
  && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install required Python packages
RUN pip install --upgrade pip \
  && pip install streamlit boto3 requests

# Copy the application code to the container
COPY app.py /app/app.py
WORKDIR /app

# Streamlit 기본 포트 노출
EXPOSE 8501

# Streamlit 실행 (환경 변수 사용)
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.enableCORS=false"]
