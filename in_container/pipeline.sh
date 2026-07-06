#!/bin/bash

# Garante que o script pare imediatamente se algum comando falhar criticamente
set -e


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
CLEANED=0

cleanup() {
    if [ "$CLEANED" -eq 1 ]; then
        return
    fi
    CLEANED=1

    echo "🧹 encerrando python"
    kill -TERM "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true

    echo "🔓 devolvendo licença unity"
    /opt/Unity/Unity \
        -quit -batchmode -nographics \
        -returnlicense \
        "$UNITY_SERIAL" \
        -username "$UNITY_EMAIL" \
        -password "$UNITY_PASSWORD" \
        -logFile /app/artifacts/return-log.txt || true
}

trap cleanup TERM INT

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
PYTHONUNBUFFERED=1 python3 /app/orchestrator.py &
PID=$!

wait $PID

cleanup