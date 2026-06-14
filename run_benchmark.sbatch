#!/bin/bash
#SBATCH --job-name=unity-vllm-bench
#SBATCH --output=npad_artifacts/slurm_job_%j.log
#SBATCH --error=npad_artifacts/slurm_error_%j.log
#SBATCH --time=72:00:00        
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8      
#SBATCH --mem=32G              
#SBATCH --gres=gpu:1           

PROJECT_PATH="$HOME/seu_projeto_unity"
ARTIFACTS_DIR="$HOME/unity_artifacts"
SCRATCH_DIR="$HOME/scratch"

export SINGULARITY_CACHEDIR="$SCRATCH_DIR/.singularity/cache"
export SINGULARITY_TMPDIR="$SCRATCH_DIR/.singularity/tmp"

# Carrega os módulos do NPAD
module load softwares/singularity
module load softwares/squashfs
module load compilers/nvidia/cuda/12.6

export $(echo $(grep -v '^#' "$HOME/.env" | xargs))
export HAS_GPU="true"

echo "========================================================="
echo "🎮 Executando Container enviado do PC local para o Scratch"
echo "========================================================="

singularity exec --nv \
  --bind "$PROJECT_PATH":/app/project \
  --bind "$ARTIFACTS_DIR":/app/artifacts \
  --env HAS_GPU="true" \
  --env HF_TOKEN="$HF_TOKEN" \
  "$SCRATCH_DIR/unity-vllm-bench.sif" /app/pipeline.sh