# syntax=docker/dockerfile:1.7

ARG CUDA_BASE_IMAGE=nvidia/cuda:13.0.0-cudnn-devel-ubuntu22.04
FROM ${CUDA_BASE_IMAGE} AS base

ARG TORCH_CUDA_ARCH="12.0"
ARG TORCH_INDEX_URL="https://download.pytorch.org/whl/nightly/cu130"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime && \
    echo ${TZ} > /etc/timezone && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        tzdata \
        ca-certificates \
        curl \
        gnupg \
        software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        python3.11 \
        python3.11-dev \
        python3.11-distutils \
        python3.11-venv \
        pkg-config && \
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 && \
    ln -sf /usr/bin/python3.11 /usr/local/bin/python && \
    ln -sf /usr/bin/python3.11 /usr/local/bin/python3 && \
    dpkg-reconfigure --frontend noninteractive tzdata && \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:${PATH}" \
    PYTHONPATH="/opt/app"

RUN python3.11 -m pip install --no-cache-dir --upgrade pip setuptools wheel

RUN python3.11 -m pip install --no-cache-dir --pre \
        --index-url ${TORCH_INDEX_URL} \
        torch \
        torchvision \
        torchaudio

RUN curl -fsSL https://ollama.com/install.sh | OLLAMA_INSTALL_GPU=true sh && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/app

COPY api/requirements-base.txt /tmp/requirements-base.txt
RUN python3.11 -m pip install --no-cache-dir -r /tmp/requirements-base.txt

COPY api/requirements.txt /tmp/requirements.txt
RUN python3.11 -m pip install --no-cache-dir -r /tmp/requirements.txt

COPY api/app /opt/app/app
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV OLLAMA_HOST=http://127.0.0.1:11434 \
    MODEL=qwen2.5:7b-instruct \
    TEMPERATURE=0.1 \
    MAX_TOKENS=1024 \
    NUMERIC_TOLERANCE=0.01 \
    USE_LLM=true \
    API_PORT=8000

EXPOSE 8000 11434

VOLUME ["/root/.ollama"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["/entrypoint.sh"]
