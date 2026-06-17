# 1. Base robusta e oficial com CUDA e Python prontos (Muito mais leve que a do vLLM)
FROM pytorch/pytorch:2.4.0-cuda12.1-cudnn9-devel

ENV DEBIAN_FRONTEND=noninteractive

# Configura caminhos globais de execução e bibliotecas CUDA
ENV PATH="/usr/local/cuda/bin:${PATH}"
ENV LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH}"

# 2. Instala dependências da Unity, do Monitor, do Chromium (CEF), Git e ferramentas de compilação
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    curl \
    wget \
    p7zip-full \
    unzip \
    xvfb \
    ca-certificates \
    xxd \
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

# 3. Instalação da Unity utilizando o Changeset correto
RUN mkdir -p /tmp/unity-download \
    && curl -fSL -o /tmp/unity-download/unity.tar.xz https://download.unity3d.com/download_unity/3000ef702840/LinuxEditorInstaller/Unity-6000.3.11f1.tar.xz \
    && mkdir -p /opt/Unity \
    && tar -xJf /tmp/unity-download/unity.tar.xz -C /opt/Unity --strip-components=1 \
    && rm -rf /tmp/unity-download

# 🔥 4. COMPILAÇÃO NATIVA DO LLAMA.CPP COM SUPORTE CUDA (Infinita performance e estabilidade)
RUN git clone https://github.com/ggml-org/llama.cpp.git /tmp/llama.cpp \
    && cd /tmp/llama.cpp \
    && mkdir build \
    && cd build \
    && cmake .. -GGML_CUDA=ON \
    && cmake --build . --config Release --target llama-server \
    && cp bin/llama-server /usr/local/bin/ \
    && cd / \
    && rm -rf /tmp/llama.cpp

# 5. Instala bibliotecas do Python (Incluindo os novos monitores)
RUN pip3 install --no-cache-dir huggingface_hub pandas requests psutil nvidia-ml-py llama-cpp-python

ENV PATH="/opt/Unity:${PATH}"
ENV HF_HOME="/tmp/huggingface"

WORKDIR /app

# 6. Puxa os scripts de análise para dentro do container
COPY in_container/orchestrator.py /app/orchestrator.py
COPY in_container/parse_results.py /app/parse_results.py
COPY in_container/utils.py /app/utils.py
COPY in_container/pipeline.sh /app/pipeline.sh

RUN chmod +x /app/pipeline.sh \