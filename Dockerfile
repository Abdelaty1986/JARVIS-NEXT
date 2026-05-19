FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    git \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt gunicorn

RUN npm install -g opencode-ai || npm install -g @opencode-ai/cli || true
RUN which opencode || true
RUN opencode --version || true

COPY . .

ENV PATH="/usr/local/bin:/usr/bin:$PATH"

CMD gunicorn app:app --bind 0.0.0.0:${PORT:-8080}
