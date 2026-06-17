#!/bin/bash
set -e

mkdir -p ./tmp_build
export APPTAINER_TMPDIR="$PWD/tmp_build"
export APPTAINER_CACHEDIR="$PWD/tmp_build"
export UNITY_ARCHIVE="$PWD/unity_installs/Unity-6000.3.11f1.tar.xz"


echo "🚀 Construindo SIF direto pelo Apptainer (Adeus Docker, salvando o SSD)..."
sudo -E apptainer build --force unity-vllm-bench.sif singularity-unity-vllm.def

sudo rm -rf ./tmp_build
echo "✅ Concluído com sucesso!"