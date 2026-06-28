#!/bin/bash
#SBATCH --job-name=hf-bulk-download
#SBATCH --output=npad_artifacts/download_%j.log
#SBATCH --error=npad_artifacts/download_error_%j.log
#SBATCH --time=24:00:00               
#SBATCH --partition=amd-512,intel-128 

echo "🚀 Iniciando o Job de Download no nó $(hostname)"
module load singularity
# O diretório do Scratch onde a imagem está
# Substitua pela sua variável real ou caminho fixo se o Slurm não puxar o $SCRATCH_DIR automaticamente
SIF_IMAGE="../scratch/unity-vllm-bench.sif" 

PYTHON_SCRIPT="baixar_modelos.py"

if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "❌ Erro: O arquivo '$PYTHON_SCRIPT' não foi encontrado no diretório atual!"
    exit 1
fi

if [ ! -f "$SIF_IMAGE" ]; then
    echo "❌ Erro: A imagem Singularity '$SIF_IMAGE' não foi encontrada!"
    exit 1
fi

echo "▶️ Rodando o download de dentro do container..."

# O Singularity por padrão já monta a pasta atual ($PWD), 
# então os caminhos relativos ("../scratch/...") vão funcionar perfeitamente!
singularity exec "$SIF_IMAGE" python3 "$PYTHON_SCRIPT"

echo "🏁 Processo de download em lote finalizado!"