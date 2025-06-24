# Dockerfile

# 1) Base image
FROM python:3.10-slim

# 2) Prevent Python buffering (so logs show up immediately)
ENV PYTHONUNBUFFERED=1

# 3) Set working directory
WORKDIR /app

# 4) Install system deps (if any needed) and Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5) Copy source code
COPY . .

# 6) Define the startup command
#    TELEGRAM_TOKEN and ANIWATCH_API_BASE should be provided via
#    Docker -e flags, or a secrets mechanism
CMD ["python", "bot.py"]
