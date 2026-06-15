#!/bin/bash
set -e

mkdir -p ./tmp_build
export APPTAINER_TMPDIR="$PWD/tmp_build"
export APPTAINER_CACHEDIR="$PWD/tmp_build"

echo "🚀 Construindo SIF direto pelo Apptainer (Adeus Docker, salvando o SSD)..."
sudo -E apptainer build --force unity-vllm-bench.sif unity-vllm.def

rm -rf ./tmp_build
echo "✅ Concluído com sucesso!"