#!/bin/bash
#SBATCH --job-name=unity-llama-bench
#SBATCH --output=npad_artifacts/slurm_job_%j.log
#SBATCH --error=npad_artifacts/slurm_error_%j.log
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --partition=gpu-4-h200,gpu-8-h100,gpu-4-a100
#SBATCH --time=72:00:00         
#SBATCH --mem=32G
#SBATCH --gres=gpu:1
#SBATCH --signal=TERM@60

ARTIFACTS_DIR="unity_artifacts"
SCRATCH_DIR="$HOME/scratch"

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

# Garante variáveis de controle do ecossistema do benchmark
export SINGULARITYENV_HAS_GPU="true"

# 2. Carrega os módulos do NPAD
module load singularity
module load softwares/squashfs
module load compilers/nvidia/cuda/12.6

# Configura caminhos do Singularity para usar o Scratch e evitar estouro de cota na Home
export SINGULARITY_CACHEDIR="$SCRATCH_DIR/.singularity/cache"
export SINGULARITY_TMPDIR="$SCRATCH_DIR/.singularity/tmp"
mkdir -p "$SINGULARITY_CACHEDIR" "$SINGULARITY_TMPDIR"

# =====================================================================
# LÓGICA DE CAPTURA DE SINAL (TRAP) PARA DEVOLUÇÃO DA LICENÇA
# =====================================================================
devolver_licenca() {
    echo "⚠️ [SLURM] Sinal de cancelamento ou Timeout detectado!"
    echo "🔓 Devolvendo licença Unity de forma segura antes do nó fechar..."
    
    # Como a Unity está dentro do container, executamos um comando rápido nela
    singularity exec --nv --writable-tmpfs \
      --bind "$ARTIFACTS_DIR":/app/artifacts \
      "$SCRATCH_DIR/unity-vllm-bench.sif" \
      /opt/Unity/Unity -quit -batchmode -nographics \
      -returnlicense "$UNITY_SERIAL" \
      -username "$UNITY_EMAIL" \
      -password "$UNITY_PASSWORD" \
      -logFile /app/artifacts/return-log.txt

    echo "✅ Licença devolvida com sucesso. Encerrando o Job."
    exit 0
}

# Registra a função para rodar se o SLURM mandar o aviso de tempo (USR1) ou cancelamento (TERM)
trap 'devolver_licenca' USR1 TERM
trap 'devolver_licenca' EXIT
# =====================================================================

# =====================================================================
# LÓGICA SLURM DE AUTO-REEXECUÇÃO POR TIMEOUT OU CRASH
# =====================================================================
CURRENT_JOB_ID=$SLURM_JOB_ID

if [ -f "$ARTIFACTS_DIR/NO_MORE_MODELS.flag" ]; then
    echo "🏁 Todos os modelos elegíveis foram processados. Fim das auto-submissões."
else
    echo "🔄 Criando gatilho de segurança no SLURM..."
    echo "    Se este Job ($CURRENT_JOB_ID) estourar as 12 horas ou crashar, o próximo assume dinamicamente."
    sbatch --dependency=afternotok:$CURRENT_JOB_ID "$0"
fi
# =====================================================================

echo "========================================================="
echo "🎮 Executando Container Llama.cpp + Unity com Suporte a GPU"
echo "========================================================="

# 🌟 Executa o Singularity com o novo --bind apontando para o Scratch
exec singularity exec --nv --writable-tmpfs \
  --bind "$SCRATCH_DIR/unityprojects/BenchMark2RogueLite":/app/project \
  --bind "$ARTIFACTS_DIR":/app/artifacts \
  --bind "$SCRATCH_DIR/hf_scratch_download":/app/scratch_models \
  --bind "$SCRATCH_DIR/container_tmp":/tmp \
  --bind "$SCRATCH_DIR/container_tmp_var":/var/tmp \
  --bind ./in_container/orchestrator.py:/app/orchestrator.py \
  --bind ./in_container/utils.py:/app/utils.py \
  --bind ./in_container/pipeline.sh:/app/pipeline.sh \
  "$SCRATCH_DIR/unity-vllm-bench.sif" /app/pipeline.sh

echo "✅ Bloco de execução finalizado com sucesso!"