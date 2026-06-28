#!/bin/bash
#SBATCH --job-name=hf-bulk-download
#SBATCH --output=npad_artifacts/download_%j.log
#SBATCH --error=npad_artifacts/download_error_%j.log
#SBATCH --time=24:00:00        
#SBATCH --mem=16G       
#SBATCH --partition=amd-512,intel-128 

echo "🚀 Iniciando o Job de Download no nó $(hostname)"
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