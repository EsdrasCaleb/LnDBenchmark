#!/bin/bash

ARTIFACTS_DIR="$(pwd)/unity_artifacts"
mkdir -p "$ARTIFACTS_DIR"
CONTROL_FILE="$ARTIFACTS_DIR/manager_status.txt"

# Inicializa o arquivo de controle como ativo
echo "RUNNING" > "$CONTROL_FILE"

# Função para encontrar a melhor partição de GPU ociosa (IDLE)
get_best_idle_partition() {
    # Lista de partições permitidas por ordem de poder computacional
    PARTITIONS=("gpu-4-h200" "gpu-8-h100" "gpu-4-a100" "gpu-8-v100")
    
    for part in "${PARTITIONS[@]}"; do
        # sinfo filtra pela partição (-p) e checa se há o estado "idle" no output limpo (-h -o "%t")
        if sinfo -p "$part" -h -o "%t" | grep -q "idle"; then
            echo "$part"
            return 0
        fi
    done
    
    # Fallback: Se tudo estiver ocupado, joga na fila da H200 padrão
    echo "gpu-4-h200"
}

echo "========================================================="
echo "🧠 Orquestrador Automático de Benchmark NPAD Iniciado"
echo "💡 Para parar o script com segurança, execute:"
echo "   echo \"STOP\" > unity_artifacts/manager_status.txt"
echo "========================================================="

while true; do
    # VERIFICAÇÃO DE PARADA MANUAL INTERNA
    if [ "$(cat "$CONTROL_FILE" 2>/dev/null)" = "STOP" ]; then
        echo "🛑 Parada manual detectada no arquivo de controle. Encerrando..."
        break
    fi

    # 1. Limpa flags antigas de término
    rm -f "$ARTIFACTS_DIR/NO_MORE_MODELS.flag"

    # 2. Descobre qual partição usar agora
    CHOSEN_PARTITION=$(get_best_idle_partition)
    echo "🎯 [$(date '+%d/%m/%Y %H:%M:%S')] Partição escolhida: $CHOSEN_PARTITION"

    # 3. Submete o Job passando a partição dinamicamente (-p)
    # Captura a resposta do sbatch para isolar o ID do Job numérico
    SBATCH_OUTPUT=$(sbatch -p "$CHOSEN_PARTITION" run_benchmark.sbatch)
    JOB_ID=$(echo "$SBATCH_OUTPUT" | awk '{print $4}')

    if [ -z "$JOB_ID" ]; then
        echo "❌ Falha crítica ao submeter o sbatch. Tentando novamente em 30 minutos..."
        sleep 1800
        continue
    fi

    echo "⏳ Job SLURM [$JOB_ID] enviado com sucesso. Monitorando execução..."

    # 4. Loop de monitoramento do Job ativo
    while true; do
        # Se o usuário pedir para parar enquanto o job roda, cancela o job ativo no SLURM também
        if [ "$(cat "$CONTROL_FILE" 2>/dev/null)" = "STOP" ]; then
            echo "🛑 Parada solicitada! Cancelando Job $JOB_ID no cluster..."
            scancel "$JOB_ID"
            exit 0
        fi

        # Verifica se o Job ainda consta no squeue
        if ! squeue -j "$JOB_ID" -h | grep -q "$JOB_ID"; then
            echo "✅ Job $JOB_ID foi finalizado no SLURM."
            break
        fi

        # Aguarda 5 minutos antes de consultar o SLURM novamente (evita spam no cluster)
        sleep 300
    done

    # 5. Verifica se o Python levantou a flag de conclusão definitiva
    if [ -f "$ARTIFACTS_DIR/NO_MORE_MODELS.flag" ]; then
        echo "🏆 [FIM DO BENCHMARK] Todos os modelos elegíveis foram processados com sucesso!"
        rm -f "$ARTIFACTS_DIR/NO_MORE_MODELS.flag"
        break
    fi

    # 6. Aguarda o intervalo cíclico de 24 horas antes do próximo lote
    echo "⏳ Lote concluído. Aguardando 24 horas para a próxima varredura de modelos..."
    
    # Loop de repouso fracionado de 1h em 1h para responder rápido caso você mande um STOP
    for i in {1..24}; do
        if [ "$(cat "$CONTROL_FILE" 2>/dev/null)" = "STOP" ]; then
            echo "🛑 Parada detectada durante o tempo de espera. Encerrando..."
            exit 0
        fi
        sleep 3600
    done
done

echo "🏁 Orquestrador finalizado."