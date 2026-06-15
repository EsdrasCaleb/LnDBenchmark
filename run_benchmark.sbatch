#!/bin/bash
#SBATCH --job-name=unity-llama-bench
#SBATCH --output=npad_artifacts/slurm_job_%j.log
#SBATCH --error=npad_artifacts/slurm_error_%j.log
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --partition=gpu-4-a100,gpu-8-v100,gpu-4-h200
#SBATCH --time=12:00:00         
#SBATCH --mem=32G          
#SBATCH --gres=gpu:1            

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
    done < "$HOME/.env"
else
    echo "❌ Erro: Arquivo .env não encontrado em $HOME"
    exit 1
fi

# Garante variáveis de controle do ecossistema do benchmark
export SINGULARITYENV_HAS_GPU="true"

# 2. Carrega os módulos do NPAD
module load softwares/singularity
module load softwares/squashfs
module load compilers/nvidia/cuda/12.6

# Configura caminhos do Singularity para usar o Scratch e evitar estouro de cota na Home
export SINGULARITY_CACHEDIR="$SCRATCH_DIR/.singularity/cache"
export SINGULARITY_TMPDIR="$SCRATCH_DIR/.singularity/tmp"
mkdir -p "$SINGULARITY_CACHEDIR" "$SINGULARITY_TMPDIR"

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

# 💡 VEJA COMO FICOU LIMPO: Não precisa de nenhuma flag --env aqui! 
# O Singularity coleta tudo que começa com SINGULARITYENV_ sozinho.
singularity exec --nv \
  --bind "$PROJECT_PATH":/app/project \
  --bind "$ARTIFACTS_DIR":/app/artifacts \
  "$SCRATCH_DIR/unity-vllm-bench.sif" /app/pipeline.sh

echo "✅ Bloco de execução finalizado com sucesso!"