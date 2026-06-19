#!/bin/bash
set -e

mkdir -p ./tmp_build
export APPTAINER_TMPDIR="$PWD/tmp_build"
export APPTAINER_CACHEDIR="$PWD/tmp_build"

echo "🚀 Construindo SIF..."
sudo -E apptainer build --force unity-vllm-bench.sif singularity-unity-vllm.def

sudo rm -rf ./tmp_build
echo "✅ Concluído com sucesso!"