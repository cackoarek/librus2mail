# syntax=docker/dockerfile:1
FROM python:3.10-slim

# Ustawienia środowiska Pythona i strefy czasowej
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Warsaw

# Instalacja strefy czasowej tzdata oraz narzędzi bazowych
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Utworzenie dedykowanego nieuprzywilejowanego użytkownika (bezpieczeństwo kontenera)
RUN groupadd -g 1000 librus && \
    useradd -u 1000 -g librus -s /bin/bash -m librus

WORKDIR /app

# Utworzenie katalogów na dane ze stosownymi uprawnieniami
RUN mkdir -p /app/storage && chown -R librus:librus /app

# Kopiowanie plików definicji pakietu i instalacja zależności
COPY pyproject.toml requirements.txt README.md /app/
COPY src/ /app/src/
COPY templates/ /app/templates/
COPY main.py librus_collector.py progress_report.py /app/

# Instalacja pakietu librus2mail wraz ze skryptami CLI
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Przełączenie na użytkownika nieuprzywilejowanego
USER librus

# Punkt montowania dla trwałej bazy JSON
VOLUME ["/app/storage"]

# Domyślne uruchomienie demona monitorującego
CMD ["librus-collector", "config.yaml"]
