#!/bin/bash

# 🍏 GARANTIA DO CRON: Carrega o ambiente base do cluster
source /etc/profile
export PATH=$PATH:/usr/bin:/usr/local/bin

ARTIFACTS_DIR="$HOME/napd_artfacts"

# 1. Trava de segurança: Se o benchmark terminou ou foi pausado, encerra na hora
if [ -f "$ARTIFACTS_DIR/NO_MORE_MODELS.flag" ]; then
    exit 0
fi

if [ "$(cat "$ARTIFACTS_DIR/manager_status.txt" 2>/dev/null)" = "STOP" ]; then
    exit 0
fi

# 2. Verifica se o seu Job JÁ ESTÁ ativo ou na fila do SLURM
if squeue -u "$USER" -h -o "%j" | grep -q "unity-vllm-bench"; then
    exit 0
fi

# 3. Prioriza partições IDLE
CHOSEN_PARTITION=$(sinfo -h -o "%P %t" \
    | grep "^gpu" \
    | awk '$2=="idle" {print $1}' \
    | tr -d '*' \
    | head -n 1)

# Se não houver IDLE, tenta MIX
if [ -z "$CHOSEN_PARTITION" ]; then
    CHOSEN_PARTITION=$(sinfo -h -o "%P %t" \
        | grep "^gpu" \
        | awk '$2=="mix" {print $1}' \
        | tr -d '*' \
        | head -n 1)
fi

# 🚨 Nenhuma GPU disponível
if [ -z "$CHOSEN_PARTITION" ]; then
    echo "[$(date)] Todas as GPUs ocupadas/indisponíveis (Sem nós idle/mix). Aguardando..." >> "$ARTIFACTS_DIR/cron_debug.log"
    exit 0
fi

# 4. Dispara o sbatch enviando para a partição encontrada
cd "$HOME"
sbatch -p "$CHOSEN_PARTITION" run_benchmark.sbatch