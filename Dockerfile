# Gebruik de 'slim' variant voor een kleinere image, maar 'bookworm' voor compatibiliteit met OR-Tools
FROM python:3.11-slim-bookworm

# Voorkom .pyc bestanden en forceer stdout/stderr logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Installeer systeem-dependencies voor Postgres en OR-Tools
# libstdc++6 en libgomp1 zijn essentieel voor de C++ solver van OR-Tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libstdc++6 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Kopieer requirements en installeer
# Voor ARM zal pip automatisch de manylinux_2_17_aarch64 wheel van ortools ophalen (v9.7+)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopieer de rest van de applicatie
COPY . .

# Start de FastAPI app met Uvicorn
# We gebruiken 0.0.0.0 om bereikbaar te zijn binnen het Docker netwerk
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]