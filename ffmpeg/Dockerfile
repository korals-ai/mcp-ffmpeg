# Toolspace sidecar (ffmpeg): a per-chat co-located helper container that owns
# ffmpeg/ffprobe and exposes structured media operations as MCP tools over
# Streamable HTTP (http://localhost:8094/mcp). The workspace agent calls it
# instead of running ffmpeg itself — letting the workspace main image shed
# ffmpeg's ~400 MB llvm/mesa/codec stack (the single largest slice of that
# per-chat image, and the dominant cold-start image-pull cost).
#
# Mirrors apps/workspace-tools/office (the "orbital workspace-tools" substrate).

FROM python:3.12-slim AS py-builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      gcc musl-dev \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim

# ffmpeg (with ffprobe) + its codec/render stack. This is the bulk we are
# deliberately concentrating HERE so the per-chat workspace image stays small.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=py-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=py-builder /usr/local/bin /usr/local/bin

COPY src ./src

ENV PYTHONPATH=/app

# Mirror the workspace pod's unprivileged identity (uid/gid 65532) so files
# ffmpeg writes onto the shared tenant PVC carry the ownership the main
# container expects (fsGroup 65532). See workspace Dockerfile + the operator
# podSpec securityContext.
RUN groupadd --system --gid 65532 tool \
 && useradd --system --uid 65532 --gid 65532 --home-dir /home/tool --shell /bin/bash tool \
 && mkdir -p /home/tool \
 && chown -R tool:tool /home/tool
ENV HOME=/home/tool

EXPOSE 8094

USER tool

ENTRYPOINT ["python", "-m", "src.server"]
