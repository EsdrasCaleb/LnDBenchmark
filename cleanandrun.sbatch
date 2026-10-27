#!/bin/bash
#SBATCH --job-name=unity-license-cleanup
#SBATCH --output=npad_artifacts/cleanup_%j.log
#SBATCH --error=npad_artifacts/cleanup_error_%j.log
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --gres=gpu:1
#SBATCH --time=00:15:00
#SBATCH --mem=8G
#SBATCH --partition=gpu-4-h200,gpu-8-h100,gpu-4-a100,gpu-8-v100

# 📍 FORÇA O DIRETÓRIO DE TRABALHO PARA O LOCAL DE SUBMISSÃO
if [ -n "$SLURM_SUBMIT_DIR" ]; then
    cd "$SLURM_SUBMIT_DIR"
fi

# 1. CARREGAMENTO INTELIGENTE DO .ENV
if [ -f ".env" ]; then
    echo "📋 Carregando e exportando variáveis do .env para o Singularity..."
    while IFS= read -r line || [ -n "$line" ]; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line//[:space:]/}" ]] && continue

        key=$(echo "$line" | cut -d= -f1 | xargs)
        val=$(echo "$line" | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")

        export "$key"="$val"
        export "SINGULARITYENV_$key"="$val"
    done < ".env"
else
    echo "❌ Erro: Arquivo .env não encontrado em $HOME"
    exit 1
fi

ARTIFACTS_DIR="unity_artifacts"
SCRATCH_DIR="../scratch"

# 🎯 RECEBE O NOME DO SCRIPT VIA ARGUMENTO $1 (COM FALLBACK SE NÃO FOR PASSADO)
PIPELINE_SCRIPT="${1:-run_benchmark.sbatch}"

echo "🔓 [CLEANUP] Iniciando processo de devolução de licença Unity..."
echo "📌 Script agendado para a próxima iteração: $PIPELINE_SCRIPT"

# Executa o comando para liberar a licença na nuvem da Unity
singularity exec --nv --writable-tmpfs \
  --bind "$ARTIFACTS_DIR":/app/artifacts \
  "$HOME/unity-vllm-bench.sif" \
  /opt/Unity/Unity -quit -batchmode -nographics \
  -returnlicense "$UNITY_SERIAL" \
  -username "$UNITY_EMAIL" \
  -password "$UNITY_PASSWORD" \
  -logFile /app/artifacts/return-log.txt

echo "✅ [CLEANUP] Comando de devolução executado. Verificando logs..."

# 🎯 PASSO 2: INSPEÇÃO E AVALIAÇÃO DA FLAG
FLAG_FILE="$ARTIFACTS_DIR/NO_MORE_MODELS.flag"

if [ -f "$FLAG_FILE" ]; then
    echo "🏁 [FIM] A flag '$FLAG_FILE' foi encontrada!"
    echo "🎉 Todos os modelos foram processados com sucesso. Encerrando o ciclo de automação."
    exit 0
else
    echo "🔄 [CONTINUAR] A flag de fim não foi encontrada. Ainda há modelos na fila!"
    echo "🚀 Re-submetendo o script '$PIPELINE_SCRIPT' na fila do Slurm..."

    # Garante que o arquivo do script existe antes de submeter
    if [ -f "$PIPELINE_SCRIPT" ]; then
        sbatch "$PIPELINE_SCRIPT"
    else
        echo "❌ [ERRO] O script de pipeline '$PIPELINE_SCRIPT' não foi encontrado no diretório!"
        exit 1
    fi
fi