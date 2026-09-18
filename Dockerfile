# syntax=docker/dockerfile:1
FROM python:3.10-slim

# Ustawienia środowiska Pythona i strefy czasowej
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Warsaw

# Utworzenie dedykowanego nieuprzywilejowanego użytkownika (bezpieczeństwo kontenera)
RUN groupadd -g 1000 librus && \
    useradd -u 1000 -g librus -s /bin/bash -m librus

WORKDIR /app

# Utworzenie katalogów na dane ze stosownymi uprawnieniami
RUN mkdir -p /app/storage && chown -R librus:librus /app

# Kopiowanie plików projektu i definicji pakietu
COPY pyproject.toml requirements.txt README.md LICENSE /app/
COPY src/ /app/src/
COPY templates/ /app/templates/
COPY main.py librus_collector.py progress_report.py /app/

# Instalacja pakietu librus2mail wraz ze skryptami CLI i wsparciem strefy czasowej
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir tzdata .

# Przełączenie na użytkownika nieuprzywilejowanego
USER librus

# Punkt montowania dla trwałej bazy JSON
VOLUME ["/app/storage"]

# Domyślne uruchomienie demona monitorującego
CMD ["librus-collector", "config.yaml"]
