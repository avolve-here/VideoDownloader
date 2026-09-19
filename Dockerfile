# ============================================================
# Stage 1: Build bgutil PO Token Provider
# ============================================================

FROM node:22-bookworm-slim AS pot-provider

WORKDIR /provider

COPY bgutil-ytdlp-pot-provider/server/package.json .
COPY bgutil-ytdlp-pot-provider/server/package-lock.json .

RUN npm ci

COPY bgutil-ytdlp-pot-provider/server/types/ ./types/
COPY bgutil-ytdlp-pot-provider/server/src/ ./src/
COPY bgutil-ytdlp-pot-provider/server/tsconfig.json .

RUN npx tsc


# ============================================================
# Stage 2: Nuvexa Video Downloader
# ============================================================

FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl unzip && \
    rm -rf /var/lib/apt/lists/*

# Install Deno for yt-dlp's YouTube JavaScript challenge solving
RUN curl -fsSL https://deno.land/install.sh | sh

ENV DENO_INSTALL=/root/.deno
ENV PATH=$DENO_INSTALL/bin:$PATH

# Copy Node.js runtime for bgutil PO Token provider
COPY --from=pot-provider /usr/local/bin/node /usr/local/bin/node

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy the built PO Token provider
COPY --from=pot-provider /provider/build /app/pot-provider/build
COPY --from=pot-provider /provider/node_modules /app/pot-provider/node_modules

COPY . .

# Start both the PO Token provider and FastAPI
CMD ["sh", "-c", "node /app/pot-provider/build/main.js --host 127.0.0.1 --port 4416 & uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]