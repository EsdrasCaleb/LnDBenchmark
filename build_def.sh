Bootstrap: docker
From: vllm/vllm-openai:latest

%environment
    export DEBIAN_FRONTEND=noninteractive
    export PATH="/usr/local/cuda/bin:/opt/Unity:${PATH}"
    export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH}"
    export HF_HOME="/tmp/huggingface"
    export GGML_CUDA=on

%post
    export DEBIAN_FRONTEND=noninteractive
    
    # 1. Instala dependências do sistema
    apt-get update && apt-get install -y \
        build-essential cmake git curl wget p7zip-full unzip xvfb \
        ca-certificates xxd libgl1-mesa-glx libgl1-mesa-dri libglib2.0-0 \
        libgtk-3-0 libgconf-2-4 libnss3 libxss1 libasound2 libxtst6 \
        libxshmfence1 libgbm1 libxcomposite1 libxcursor1 libxdamage1 \
        libxrandr2 libxrender1 libxi6 libxkbcommon0 libxkbcommon-x11-0 \
        libsecret-1-0
    rm -rf /var/lib/apt/lists/*

    # 2. Instala pacotes Python e Llama.cpp Python
    pip3 install huggingface_hub pandas requests
    
    # 🌟 CORREÇÃO AQUI: Removeu-se a palavra 'ENV' para virar Bash legítimo
    GGML_CUDA=on pip3 install --no-cache-dir llama-cpp-python[server]

    # 3. Baixa e instala a Unity
    mkdir -p /tmp/unity-download
    curl -fSL -o /tmp/unity-download/unity.tar.xz https://download.unity3d.com/download_unity/3000ef702840/LinuxEditorInstaller/Unity-6000.3.11f1.tar.xz
    mkdir -p /opt/Unity
    tar -xJf /tmp/unity-download/unity.tar.xz -C /opt/Unity --strip-components=1
    rm -rf /tmp/unity-download

    # 4. Cria a pasta da aplicação
    mkdir -p /app

%files
    # Injeta os scripts direto para dentro do container na hora do build
    in_container/orchestrator.py /app/orchestrator.py
    in_container/parse_results.py /app/parse_results.py
    in_container/orchestratorLlama.py /app/orchestratorLlama.py
    in_container/pipeline.sh /app/pipeline.sh
    in_container/pipelineLlama.sh /app/pipelineLlama.sh

%runscript
    # Garante permissão e define o comportamento padrão se rodar com 'apptainer run'
    chmod +x /app/pipeline.sh
    chmod +x /app/pipelineLlama.sh
    exec /bin/bash /app/pipeline.sh 