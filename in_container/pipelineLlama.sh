#!/bin/bash

# Garante que o script pare imediatamente se algum comando falhar criticamente
set -e

COVERAGE_DIR="/app/artifacts/coverage"
TMP_MODEL_FILE="/tmp/current_active_model"

echo '=================================================='
echo '📊 VERIFICAÇÃO DE LIMITES DE MEMÓRIA (CONTAINER)'
echo '=================================================='
echo -n ' -> Memória Máxima do Container (Cgroups): '
[ -f /sys/fs/cgroup/memory.max ] && cat /sys/fs/cgroup/memory.max || echo 'Ilimitada'
echo '=================================================='

# Garante um estado inicial para o arquivo do modelo
echo "-" > "$TMP_MODEL_FILE"

# --------------------------------------------------
# INICIALIZAÇÃO DO MONITOR DE RECURSOS (CSV)
# --------------------------------------------------
REPORT_FILE="/app/artifacts/performance_report.csv"

# Cria o cabeçalho do arquivo CSV
echo "timestamp,used_ram,free_ram,used_cpu,free_cpu,model" > "$REPORT_FILE"

(while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    
    # 1. Coleta dados de RAM (em MB) usando awk no comando 'free -m'
    RAM_DATA=$(free -m | awk '/Mem:/ {print $3","$4}')
    USED_RAM=$(echo "$RAM_DATA" | cut -d',' -f1)
    FREE_RAM=$(echo "$RAM_DATA" | cut -d',' -f2)
    
    # 2. Coleta dados de CPU (%) usando o arquivo estatístico do Linux (/proc/stat) de forma eficiente
    CPU_DATA=($(grep 'cpu ' /proc/stat))
    IDLE1=${CPU_DATA[4]}
    TOTAL1=0
    for VALUE in "${CPU_DATA[@]:1}"; do TOTAL1=$((TOTAL1 + VALUE)); done
    
    sleep 1
    
    CPU_DATA2=($(grep 'cpu ' /proc/stat))
    IDLE2=${CPU_DATA2[4]}
    TOTAL2=0
    for VALUE in "${CPU_DATA2[@]:1}"; do TOTAL2=$((TOTAL2 + VALUE)); done
    
    DIFF_IDLE=$((IDLE2 - IDLE1))
    DIFF_TOTAL=$((TOTAL2 - TOTAL1))
    
    # Evita divisão por zero caso o intervalo seja curto demais
    if [ "$DIFF_TOTAL" -gt 0 ]; then
        # Multiplicamos por 100 para trabalhar com inteiros no bash
        USED_CPU=$((100 * (DIFF_TOTAL - DIFF_IDLE) / DIFF_TOTAL))
        FREE_CPU=$((100 - USED_CPU))
    else
        USED_CPU=0
        FREE_CPU=100
    fi
    
    # MÁGICA AQUI: O monitor lê o arquivo que o Python atualiza em tempo real!
    MODEL=$(cat "$TMP_MODEL_FILE" 2>/dev/null || echo "-")
    
    # Grava a linha formatada no CSV
    echo "${TIMESTAMP},${USED_RAM},${FREE_RAM},${USED_CPU}%,${FREE_CPU}%,${MODEL}" >> "$REPORT_FILE"
    
    # Dorme o restante do tempo para fechar o ciclo de aproximadamente 2 segundos
    sleep 1
done) &
MONITOR_PID=$!

# Função para garantir que os processos morram e as permissões sejam corrigidas
cleanup() {
    echo '🔓 Finalizando processos paralelos e ajustando permissões de saída...'
    echo "-" > "$TMP_MODEL_FILE"
    kill $MONITOR_PID || true
    if [ -n "$USER_UID" ] && [ -n "$USER_GID" ]; then
        chown -R "$USER_UID":"$USER_GID" /app/artifacts || true
        chown -R "$USER_UID":"$USER_GID" /app/project || true
    fi
    # Devolve a licença no final de tudo
    echo '🔓 Devolvendo licença Unity de forma segura...'
    /opt/Unity/Unity -quit -batchmode -nographics -returnlicense "$UNITY_SERIAL" -username "$UNITY_EMAIL" -password "$UNITY_PASSWORD" -logFile /app/artifacts/return-log.txt
}
trap cleanup EXIT

# --------------------------------------------------
# PIPELINE DE EXECUÇÃO - VALIDAÇÃO E GERAÇÃO
# --------------------------------------------------
# Ativa a Licença da Unity uma única vez antes do Python assumir
echo '🔑 Ativando licença Unity global...'
/opt/Unity/Unity -batchmode -nographics -serial "$UNITY_SERIAL" -username "$UNITY_EMAIL" -password "$UNITY_PASSWORD" -logFile /app/artifacts/activation-log.txt

# Deixa o Orquestrador Python tomar conta de todo o benchmark dinâmico
python3 /app/orchestrator.py  --backend llamacpp
