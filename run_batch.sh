#!/bin/bash

# ==========================================
# CARREGAR VARIÁVEIS DE AMBIENTE DO ARQUIVO .env
# ==========================================
if [ -f .env ]; then
    export $(echo $(grep -v '^#' .env | xargs))
else
    echo "❌ Erro: Arquivo .env não encontrado!"
    exit 1
fi

IMAGE_NAME="unity-vllm-bench"
PROJECT_PATH="/home/caleb/gameprojects/unityprojects/BenchMarkLostCrypt"
ARTIFACTS_DIR="$(pwd)/unity_artifacts"
COVERAGE_DIR="/app/artifacts/coverage"

echo "🚀 [1/4] Criando diretório de artefatos..."
mkdir -p "$ARTIFACTS_DIR"

echo "📦 [2/4] Construindo imagem Docker local..."
docker build -t $IMAGE_NAME .
if [ $? -ne 0 ]; then echo "❌ Erro no build."; exit 1; fi

# Detecção Automática de GPU
GPU_FLAG=""
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    echo "🟢 GPU NVIDIA detectada! Ativando aceleração por hardware."
    GPU_FLAG="--gpus all"
else
    echo "🟡 Nenhuma GPU detectada. Rodando em modo CLI Puro (CPU)."
    GPU_FLAG=""
fi

echo "🎮 [3/4] Executando Pipeline CLI Puro com Monitor de Recursos..."
docker run --rm \
  $GPU_FLAG \
  --shm-size=4gb \
  --entrypoint bash \
  -v "$PROJECT_PATH":/app/project \
  -v "$ARTIFACTS_DIR":/app/artifacts \
  --env UNITY_SERIAL \
  --env UNITY_EMAIL \
  --env UNITY_PASSWORD \
  $IMAGE_NAME \
  -c "
    echo '=================================================='
    echo '📊 VERIFICAÇÃO DE LIMITES DE MEMÓRIA (CONTAINER)'
    echo '=================================================='
    echo -n ' -> Memória Máxima do Container (Cgroups): '
    [ -f /sys/fs/cgroup/memory.max ] && cat /sys/fs/cgroup/memory.max || echo 'Ilimitada'
    echo '=================================================='

    # Configurações de Sanidade do OS (Necessário para a telemetria da Unity 6)
    mkdir -p /var/lib/dbus /etc
    echo \$(head -c 16 /dev/urandom | xxd -p) > /etc/machine-id
    cp /etc/machine-id /var/lib/dbus/machine-id

    # Inicialização do Monitor de Recursos para o Supercomputador
    REPORT_FILE=\"/app/artifacts/performance_report.log\"
    (while true; do
        echo \"--- [\$(date '+%Y-%m-%d %H:%M:%S')] ---\" >> \"\$REPORT_FILE\"
        echo \"[RAM livre/usada em MB]:\" >> \"\$REPORT_FILE\"
        free -m | grep -E 'Mem|Total' >> \"\$REPORT_FILE\"
        sleep 2
    done) &
    MONITOR_PID=\$!

    # --------------------------------------------------
    # EXECUÇÃO DO PIPELINE UNITY 6 (CLI Headless)
    # --------------------------------------------------
    echo '🔑 Ativando licença Unity...'
    /opt/Unity/Unity -batchmode -nographics -serial \"\$UNITY_SERIAL\" -username \"\$UNITY_EMAIL\" -password \"\$UNITY_PASSWORD\" -logFile /app/artifacts/activation-log.txt
    
    if [ ! -f /app/artifacts/activation-log.txt ] || grep -q 'License activation failed' /app/artifacts/activation-log.txt; then
        echo '⚠️  [AVISO] Possível problema na ativação da licença. Verifique activation-log.txt'
    fi

    echo '🎮 PASSO 1: Rodando EditMode Tests + Coverage...'
    /opt/Unity/Unity -projectPath /app/project -batchmode -nographics \
      -testPlatform editmode -runTests -debugCodeOptimization -enableCodeCoverage \
      -coverageResultsPath $COVERAGE_DIR \
      -coverageOptions \"generateAdditionalMetrics;assemblyFilters:+Assembly-CSharp\" \
      -testResults /app/artifacts/editmode-results.xml \
      -logFile /app/artifacts/editmode-log.txt

    if [ ! -f /app/artifacts/editmode-results.xml ]; then
        echo '❌ Erro no EditMode! Mostrando últimas linhas do log:'
        echo '----------------------------------------------------------------------'
        tail -n 30 /app/artifacts/editmode-log.txt 2>/dev/null || echo 'Log editmode-log.txt não foi criado.'
        echo '----------------------------------------------------------------------'
    fi
    
    echo '🎮 PASSO 2: Rodando PlayMode Tests + Coverage...'
    /opt/Unity/Unity -projectPath /app/project -batchmode -nographics \
      -testPlatform playmode -runTests -debugCodeOptimization -enableCodeCoverage \
      -coverageResultsPath $COVERAGE_DIR \
      -coverageOptions \"generateAdditionalMetrics;assemblyFilters:+Assembly-CSharp\" \
      -testResults /app/artifacts/playmode-results.xml \
      -logFile /app/artifacts/playmode-log.txt

    if [ ! -f /app/artifacts/playmode-results.xml ]; then
        echo '❌ Erro no PlayMode! Mostrando últimas linhas do log:'
        echo '----------------------------------------------------------------------'
        tail -n 30 /app/artifacts/playmode-log.txt 2>/dev/null || echo 'Log playmode-log.txt não foi criado.'
        echo '----------------------------------------------------------------------'
    fi

    echo '📊 PASSO 3: Gerando Relatório HTML Final...'
    /opt/Unity/Unity -projectPath /app/project -batchmode -nographics \
      -debugCodeOptimization -enableCodeCoverage \
      -coverageResultsPath $COVERAGE_DIR \
      -coverageOptions \"generateHtmlReport;generateBadgeReport;assemblyFilters:+Assembly-CSharp\" \
      -quit \
      -logFile /app/artifacts/coverage-report-log.txt

    echo '🔓 Devolvendo licença Unity...'
    /opt/Unity/Unity -batchmode -nographics -returnlicense -logFile /app/artifacts/return-log.txt

    # Encerramento do Monitor
    kill \$MONITOR_PID

    echo '📊 [4/4] Processando resumos finais...'
    python3 /app/parse_results.py /app/artifacts
  " 2>&1 | tee "$ARTIFACTS_DIR/pipeline_execution.log"