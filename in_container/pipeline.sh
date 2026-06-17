#!/bin/bash

# Garante que o script pare imediatamente se algum comando falhar criticamente
set -e
#temporario
pip install psutil nvidia-ml-py

COVERAGE_DIR="/app/artifacts/coverage"

# Tratamento do argumento opcional de Backend (vllm ou llamacpp)
# Se não for passado nenhum parâmetro, a variável fica vazia
BACKEND_ARG=""
if [ -n "$1" ]; then
    if [ "$1" == "vllm" ] || [ "$1" == "llamacpp" ]; then
        BACKEND_ARG="--backend $1"
        echo "🎯 Backend selecionado via parâmetro: $1"
    fi
else
    echo "💡 Nenhum backend especificado. O Orquestrador assumirá o padrão interno (vllm)."
fi

echo '=================================================='
echo '📊 VERIFICAÇÃO DE LIMITES DE MEMÓRIA (CONTAINER)'
echo '=================================================='
echo -n ' -> Memória Máxima do Container (Cgroups): '
[ -f /sys/fs/cgroup/memory.max ] && cat /sys/fs/cgroup/memory.max || echo 'Ilimitada'
echo '=================================================='

# Função para garantir a limpeza do ambiente e a correção das permissões
cleanup() {
    echo '🔓 Ajustando permissões de saída nos artefatos...'
    if [ -n "$USER_UID" ] && [ -n "$USER_GID" ]; then
        chown -R "$USER_UID":"$USER_GID" /app/artifacts || true
        chown -R "$USER_UID":"$USER_GID" /app/project || true
    fi

    # Devolve a licença no final de tudo de forma segura
    echo '🔓 Devolvendo licença Unity de forma segura...'
    /opt/Unity/Unity -quit -batchmode -nographics -returnlicense "$UNITY_SERIAL" -username "$UNITY_EMAIL" -password "$UNITY_PASSWORD" -logFile /app/artifacts/return-log.txt
}
trap cleanup EXIT

# --------------------------------------------------
# INICIALIZAÇÃO DA UNITY
# --------------------------------------------------
# Ativa a Licença da Unity uma única vez antes do Python assumir
echo '🔑 Ativando licença Unity global...'
/opt/Unity/Unity -batchmode -nographics -serial "$UNITY_SERIAL" -username "$UNITY_EMAIL" -password "$UNITY_PASSWORD" -logFile /app/artifacts/activation-log.txt

# --------------------------------------------------
# EXECUÇÃO DO ORQUESTRADOR PYTHON
# --------------------------------------------------
# Chama o Python passando o argumento tratado (ou vazio, aplicando o default do argparse)
echo "🚀 Iniciando orquestrador Python..."
PYTHONUNBUFFERED=1 python3 /app/orchestrator.py $BACKEND_ARG