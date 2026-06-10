# Playwright's official image ships Chromium + all system deps preinstalled.
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

# Shared form logic lives in the parent ruc/ package.
COPY purchase_core.py purchase_core.py
COPY server/ server/

WORKDIR /app/server
EXPOSE 8000

# config.json is mounted at runtime (it holds your card) - never baked in.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
