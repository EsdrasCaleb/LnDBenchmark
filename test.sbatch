#!/bin/bash
#SBATCH --job-name=test-vllm-curl
#SBATCH --output=npad_artifacts/test_curl_%j.log
#SBATCH --error=npad_artifacts/test_curl_error_%j.log
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --partition=gpu-4-a100,gpu-8-v100   # Certifique-se de que essas filas estão ativas
#SBATCH --time=00:30:00         
#SBATCH --mem=40G                           # Subi um pouco a RAM para garantir folga no load
#SBATCH --gres=gpu:1            

SCRATCH_DIR="$HOME/scratch"
HF_CACHE_DIR="$SCRATCH_DIR/hf_cache"
PORTA_TESTE=11434

mkdir -p npad_artifacts
mkdir -p "$HF_CACHE_DIR"

# 1. Carrega as variáveis do .env (Para pegar o HF_TOKEN)
if [ -f "./.env" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line//[:space:]/}" ]] && continue
        key=$(echo "$line" | cut -d= -f1 | xargs)
        val=$(echo "$line" | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
        export "$key"="$val"
        export "SINGULARITYENV_$key"="$val"
    done < "./.env"
else
    echo "❌ Erro: Arquivo .env necessário."
    exit 1
fi

export SINGULARITYENV_HF_HOME="/tmp/huggingface"

# 2. Carrega os módulos
module load cuda || module load drivers/cuda || true
module load singularity || module load softwares/singularity || true

echo "========================================================="
echo "🌐 Iniciando Servidor vLLM + Requisição Curl (Unity Mimic)"
echo "========================================================="

singularity exec --nv --writable-tmpfs \
  --bind ./in_container:/app \
  --bind ./npad_artifacts:/app/artifacts \
  --bind "$HF_CACHE_DIR":/tmp/huggingface \
  "$SCRATCH_DIR/unity-vllm-bench.sif" /bin/bash -c "

    # 🔥 Força o Python a cuspir logs em tempo real
    export PYTHONUNBUFFERED=1

    echo '🚀 Levantando o servidor vLLM na porta $PORTA_TESTE...'
    # 🔥 Redireciona a saída do vLLM para um arquivo de log dedicado
    python3 -m vllm.entrypoints.openai.api_server \
        --model google/gemma-3-1b-it \
        --port $PORTA_TESTE \
        --served-model-name vllm-model \
        --trust-remote-code > /app/artifacts/vllm_server.log 2>&1 &
    VLLM_PID=\$!

    cleanup_test() {
        echo '🛑 Desligando o servidor vLLM de teste...'
        kill \$VLLM_PID 2>/dev/null || true
    }
    trap cleanup_test EXIT

    echo '⏳ Aguardando o endpoint responder...'
    
    # Loop inteligente com checagem de pulso do processo
    while ! curl -s http://localhost:$PORTA_TESTE/v1/models > /dev/null; do
        
        # 🕵️ MÁGICA: Se o PID do vLLM sumiu, ele crashou!
        if ! kill -0 \$VLLM_PID 2>/dev/null; then
            echo ''
            echo '❌ CRITICAL ERROR: O servidor vLLM MORREU antes de ficar pronto!'
            echo '👉 Abra o arquivo npad_artifacts/vllm_server.log para ver o culpado.'
            exit 1
        fi
        echo 'sleeping'
        sleep 4
        echo 'try again'
    done
    
    echo '✅ Servidor vLLM está ONLINE e pronto!'

    echo '📡 Enviando requisição HTTP POST...'
    curl -s -X POST http://localhost:$PORTA_TESTE/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{
        \"model\": \"vllm-model\",
        \"messages\": [
          {\"role\": \"user\", \"content\": \"Olá! Teste de infraestrutura do supercomputador via HTTP API. Você está funcionando na GPU?\"}
        ],
        \"temperature\": 0.3,
        \"max_tokens\": 100
      }' > /app/artifacts/testeresult.txt

    echo '📝 Resposta capturada com sucesso!'
"

echo "🏁 Processo do sbatch finalizado."