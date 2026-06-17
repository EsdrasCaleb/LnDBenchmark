FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Python em venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:/opt/Unity:${PATH}"

ENV LD_LIBRARY_PATH="/usr/local/lib:${LD_LIBRARY_PATH}"
ENV HF_HOME="/tmp/huggingface"
ENV PYTHONUNBUFFERED=1

# Dependências do sistema e da Unity
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    p7zip-full \
    unzip \
    xvfb \
    ca-certificates \
    xxd \
    build-essential \
    cmake \
    libgl1-mesa-glx \
    libgl1-mesa-dri \
    libglib2.0-0 \
    libgtk-3-0 \
    libgconf-2-4 \
    libnss3 \
    libxss1 \
    libasound2 \
    libxtst6 \
    libxshmfence1 \
    libgbm1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxrandr2 \
    libxrender1 \
    libxi6 \
    libxkbcommon0 \
    libxkbcommon-x11-0 \
    libsecret-1-0 \
    && rm -rf /var/lib/apt/lists/*

# Instala a Unity a partir do arquivo local
COPY unity_installs/Unity-6000.3.11f1.tar.xz /tmp/unity.tar.xz

RUN mkdir -p /opt/Unity \
    && tar -xJf /tmp/unity.tar.xz -C /opt/Unity --strip-components=1 \
    && rm -f /tmp/unity.tar.xz

# Cria ambiente virtual Python
RUN python3 -m venv ${VIRTUAL_ENV}

# Instala pacotes Python no venv
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir \
        huggingface_hub \
        pandas \
        requests \
        psutil \
        nvidia-ml-py

# Baixa o binário pré-compilado do llama.cpp
RUN wget \
        "https://github.com/ggml-org/llama.cpp/releases/download/b9673/llama-b9673-bin-ubuntu-vulkan-x64.tar.gz" \
        -O /tmp/llama.tar.gz \
    && mkdir -p /opt/llama \
    && tar -xzf /tmp/llama.tar.gz -C /opt/llama \
    && find /opt/llama -type f -executable -exec cp {} /usr/local/bin/ \; \
    && find /opt/llama -type f -name "*.so*" -exec cp {} /usr/local/lib/ \; \
    && ldconfig || true \
    && rm -rf /tmp/llama.tar.gz /opt/llama

WORKDIR /app

# Scripts da aplicação
COPY in_container/orchestrator.py /app/orchestrator.py
COPY in_container/parse_results.py /app/parse_results.py
COPY in_container/utils.py /app/utils.py
COPY in_container/pipeline.sh /app/pipeline.sh

RUN chmod +x /app/pipeline.sh

ENTRYPOINT ["/bin/bash", "/app/pipeline.sh"]