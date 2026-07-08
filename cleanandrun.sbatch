#!/bin/bash
#SBATCH --job-name=unity-license-cleanup
#SBATCH --output=npad_artifacts/cleanup_%j.log
#SBATCH --error=npad_artifacts/cleanup_error_%j.log
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --time=00:15:00               # 15 minutos é mais que suficiente para devolver a licença
#SBATCH --mem=8G
#SBATCH --partition=gpu-4-h200,gpu-8-h100,gpu-4-a100,gpu-8-v100  # Roda na mesma partição disponível



# 1. CARREGAMENTO INTELIGENTE DO .ENV
# Lemos linha por linha para evitar quebras por causa de espaços ou aspas
if [ -f ".env" ]; then
    echo "📋 Carregando e exportando variáveis do .env para o Singularity..."
    while IFS= read -r line || [ -n "$line" ]; do
        # Ignora linhas vazias e comentários
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line//[:space:]/}" ]] && continue

        # Limpa espaços ao redor do '=' e remove aspas extras do valor
        key=$(echo "$line" | cut -d= -f1 | xargs)
        val=$(echo "$line" | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")

        # Exporta localmente para o Slurm usar (ex: PROJECT_PATH)
        export "$key"="$val"

        # A MÁGICA: Exporta com o prefixo que o Singularity injeta AUTOMATICAMENTE no container
        export "SINGULARITYENV_$key"="$val"
    done < ".env"
else
    echo "❌ Erro: Arquivo .env não encontrado em $HOME"
    exit 1
fi

# 📁 Carregue suas variáveis de ambiente/caminhos aqui (ou faça um source no seu env.sh)
# source /app/projeto/definicoes_ambiente.sh
ARTIFACTS_DIR="unity_artifacts"
SCRATCH_DIR="../scratch"
PIPELINE_SCRIPT="run_benchmark.sbatch"  # Nome do seu script principal

echo "🔓 [CLEANUP] Iniciando processo de devolução de licença Unity..."

# Executa o comando que você definiu para liberar a licença na nuvem da Unity
singularity exec --nv --writable-tmpfs \
  --bind "$ARTIFACTS_DIR":/app/artifacts \
  "$SCRATCH_DIR/unity-vllm-bench.sif" \
  /opt/Unity/Unity -quit -batchmode -nographics \
  -returnlicense "$UNITY_SERIAL" \
  -username "$UNITY_EMAIL" \
  -password "$UNITY_PASSWORD" \
  -logFile /app/artifacts/return-log.txt

echo "✅ [CLEANUP] Comando de devolução executado. Verificando logs..."

# 🎯 Passo 2: Avaliar a Flag de Continuidade
FLAG_FILE="$ARTIFACTS_DIR/NO_MORE_MODELS.flag"

if [ -f "$FLAG_FILE" ]; then
    echo "🏁 [FIM] A flag '$FLAG_FILE' foi encontrada!"
    echo "🎉 Todos os modelos foram processados com sucesso. Encerrando o ciclo de automação."
    exit 0
else
    echo "🔄 [CONTINUAR] A flag de fim não foi encontrada. Ainda há modelos na fila!"
    echo "🚀 Agendando uma nova instância do pipeline na melhor partição livre..."

    # Re-submete o pipeline principal. O Slurm vai analisar a lista de partições
    # e colocar o job para rodar onde houver GPU vaga primeiro.
    sbatch "$PIPELINE_SCRIPT"
fi