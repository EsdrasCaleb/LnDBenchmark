# 1. Cria uma pasta temporária no seu disco atual (onde tem espaço de sobra)
mkdir -p ./tmp_build

# 2. Aponta os caches e os diretórios temporários para essa nova pasta
export APPTAINER_TMPDIR=$PWD/tmp_build
export APPTAINER_CACHEDIR=$PWD/tmp_build

# Se você estiver usando o SingularityCE clássico (AUR), use estas variáveis em vez das de cima:
export SINGULARITY_TMPDIR=$PWD/tmp_build
export SINGULARITY_CACHEDIR=$PWD/tmp_build

# 3. Agora sim, rode o build com o sudo preservando essas variáveis (-E)
sudo -E apptainer build unity-vllm-bench.sif unity-vllm.def