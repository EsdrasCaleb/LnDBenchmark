#!/bin/bash
#SBATCH --job-name=test-vllm-curl
#SBATCH --output=npad_artifacts/test_curl_%j.log
#SBATCH --error=npad_artifacts/test_curl_error_%j.log
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --partition=gpu-4-a100,gpu-8-v100
#SBATCH --time=01:00:00         
#SBATCH --mem=32G               
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
module load singularity || module load softwares/singularity || true

echo "========================================================="
echo "🌐 Iniciando Servidor vLLM + Requisição Curl (Unity Mimic)"
echo "========================================================="

# Executa o bloco de comandos bash direto dentro do container
singularity exec --nv --writable-tmpfs \
  --bind ./in_container:/app \
  --bind ./npad_artifacts:/app/artifacts \
  --bind "$HF_CACHE_DIR":/tmp/huggingface \
  "$SCRATCH_DIR/unity-vllm-bench.sif" /bin/bash -c "

    # 1. Inicia o servidor da API em background (Igual o orchestrator vai fazer)
    echo '🚀 Levantando o servidor vLLM na porta $PORTA_TESTE...'
    python3 -m vllm.entrypoints.openai.api_server \
        --model google/gemma-3-1b-it \
        --served-model-name vllm-model \
        --port $PORTA_TESTE \
        --trust-remote-code &
    VLLM_PID=\$!

    # Função de segurança para matar o server se o script cair
    cleanup_test() {
        echo '🛑 Desligando o servidor vLLM de teste...'
        kill \$VLLM_PID 2>/dev/null || true
    }
    trap cleanup_test EXIT

    # 2. Loop de verificação (Aguarda o modelo carregar na VRAM e ficar pronto)
    echo '⏳ Aguardando o endpoint responder (Isso pode levar de 1 a 3 minutos)...'
    until curl -s http://localhost:$PORTA_TESTE/v1/models > /dev/null; do
        sleep 5
    done
    echo '✅ Servidor vLLM está ONLINE e pronto!'

    # 3. Executa o CURL imitando perfeitamente o Payload JSON da Unity
    echo '📡 Enviando requisição HTTP POST (Estilo UnityWebRequest)...'
    curl -s -X POST http://localhost:$PORTA_TESTE/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{
        \"model\": \"vllm-model\",
        \"messages\": [
          {\"role\": \"user\", \"content\": \"Olá! Teste de infraestrutura do supercomputador via HTTP API. Você está funcionando na GPU?\"}
        ],
        \"temperature\": 0.7,
        \"max_tokens\": 150
      }' > /app/artifacts/testeresult.txt

    echo '📝 Resposta capturada com sucesso!'
"

echo "🏁 Teste de rede local finalizado!"