#!/bin/bash

# ==========================================
# CARREGAR VARIÁVEIS DE AMBIENTE DO ARQUIVO .env
# ==========================================
if [ -f .env ]; then
    export $(echo $(grep -v '^#' .env | xargs))
else
    echo "❌ Erro: Arquivo .env não encontrado!"
    exit 1
fi

IMAGE_NAME="unity-vllm-bench"
ARTIFACTS_DIR="$(pwd)/unity_artifacts"

echo "🚀 [1/4] Criando diretório de artefatos..."
mkdir -p "$ARTIFACTS_DIR"

echo "📦 [2/4] Construindo imagem Docker local..."
docker build -t $IMAGE_NAME .
if [ $? -ne 0 ]; then echo "❌ Erro no build."; exit 1; fi

# Detecção Automática de GPU
GPU_FLAG=""
HAS_GPU="false"

if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    echo "🟢 GPU NVIDIA detectada! Ativando aceleração por hardware."
    GPU_FLAG="--gpus all"
    HAS_GPU="true"
    VLLM_FLAG=""
else
    echo "🟡 Nenhuma GPU detectada. Rodando em modo CLI Puro (CPU)."
    GPU_FLAG=""
    HAS_GPU="false"
    VLLM_FLAG="--env VLLM_TARGET_DEVICE=cpu"
fi

USER_UID=$(id -u)
USER_GID=$(id -g)

echo "🎮  Executando Pipeline via Script Interno Isolado..."
docker run --rm \
  $GPU_FLAG \
  $VLLM_FLAG \
  --entrypoint /bin/bash \
  --shm-size=4gb \
  -v "$PROJECT_PATH":/app/project \
  -v "$ARTIFACTS_DIR":/app/artifacts \
  --env UNITY_SERIAL \
  --env UNITY_EMAIL \
  --env UNITY_PASSWORD \
  --env UNITY_ASM_NAME \
  --env UNITY_LLM_API_KEY \
  --env SCRIPT_PATH \
  --env USER_UID \
  --env USER_GID \
  --env HF_TOKEN \
  --env PLAYTEST_FOLDER \
  --env EDITORTEST_FOLDER \
  --env HAS_GPU="$HAS_GPU" \
  $IMAGE_NAME \
  /app/pipeline.sh 2>&1 | tee "$ARTIFACTS_DIR/pipeline_execution.log"