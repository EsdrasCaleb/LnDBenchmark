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

USER_UID=$(id -u)
USER_GID=$(id -g)

echo "🎮 [3/4] Executando Pipeline CLI Customizado com Cobertura Unificada..."
docker run --rm \
  $GPU_FLAG \
  --shm-size=4gb \
  --entrypoint bash \
  -v "$PROJECT_PATH":/app/project \
  -v "$ARTIFACTS_DIR":/app/artifacts \
  --env UNITY_SERIAL \
  --env UNITY_EMAIL \
  --env UNITY_PASSWORD \
  --env UNITY_ASM_NAME \
  --env UNITY_LLM_API_KEY \
  --env USER_UID \
  --env SCRIPT_PATH \
  $IMAGE_NAME \
  -c "
    echo '=================================================='
    echo '📊 VERIFICAÇÃO DE LIMITES DE MEMÓRIA (CONTAINER)'
    echo '=================================================='
    echo -n ' -> Memória Máxima do Container (Cgroups): '
    [ -f /sys/fs/cgroup/memory.max ] && cat /sys/fs/cgroup/memory.max || echo 'Ilimitada'
    echo '=================================================='

    # Configurações de Sanidade do OS
    mkdir -p /var/lib/dbus /etc
    echo \$(head -c 16 /dev/urandom | xxd -p) > /etc/machine-id
    cp /etc/machine-id /var/lib/dbus/machine-id

    # Inicialização do Monitor de Recursos
    REPORT_FILE=\"/app/artifacts/performance_report.log\"
    (while true; do
        echo \"--- [\$(date '+%Y-%m-%d %H:%M:%S')] ---\" >> \"\$REPORT_FILE\"
        echo \"[RAM livre/usada em MB]:\" >> \"\$REPORT_FILE\"
        free -m | grep -E 'Mem|Total' >> \"\$REPORT_FILE\"
        sleep 2
    done) &
    MONITOR_PID=\$!

    # --------------------------------------------------
    # PIPELINE DE EXECUÇÃO - VALIDAÇÃO E GERAÇÃO
    # --------------------------------------------------
    echo '🔑 Ativando licença Unity...'
    /opt/Unity/Unity -batchmode -nographics -serial \"\$UNITY_SERIAL\" -username \"\$UNITY_EMAIL\" -password \"\$UNITY_PASSWORD\" -logFile /app/artifacts/activation-log.txt

    echo '🛠️  [MÉTODO] Gerando Testes via CLI...'
    /opt/Unity/Unity -projectPath /app/project -batchmode -nographics \
      -executeMethod LaundryNDishes.CLI.LndCommandLineInterface.GenerateTestsFolder \
      -folder $SCRIPT_PATH -csv \"/app/artifacts/testGeneration.csv\" \
      -logFile /app/artifacts/generation-cli-log.txt

    # Criando a pasta base de cobertura antes dos testes começarem
    mkdir -p $COVERAGE_DIR

    echo '🎮 PASSO 1: Rodando EditMode Tests + Coverage...'
    /opt/Unity/Unity -projectPath /app/project -batchmode -nographics \
      -testPlatform editmode -runTests -debugCodeOptimization -enableCodeCoverage \
      -coverageResultsPath $COVERAGE_DIR \
      -coverageOptions \"generateAdditionalMetrics;assemblyFilters:+\$UNITY_ASM_NAME\" \
      -testResults /app/artifacts/editmode-results.xml \
      -logFile /app/artifacts/editmode-log.txt

    echo '🎮 PASSO 2: Rodando PlayMode Tests + Coverage...'
    /opt/Unity/Unity -projectPath /app/project -batchmode -nographics \
      -testPlatform playmode -runTests -debugCodeOptimization -enableCodeCoverage \
      -coverageResultsPath $COVERAGE_DIR \
      -coverageOptions \"generateAdditionalMetrics;assemblyFilters:+\$UNITY_ASM_NAME\" \
      -testResults /app/artifacts/playmode-results.xml \
      -logFile /app/artifacts/playmode-log.txt

    echo '📊 PASSO 3: Gerando Relatório Cobertura HTML Final (PlayMode + EditMode combinados)...'
    /opt/Unity/Unity -projectPath /app/project -batchmode -nographics \
      -debugCodeOptimization -enableCodeCoverage \
      -coverageResultsPath $COVERAGE_DIR \
      -coverageOptions \"generateHtmlReport;generateBadgeReport;assemblyFilters:+\$UNITY_ASM_NAME\" \
      -quit \
      -logFile /app/artifacts/coverage-report-log.txt

    echo '📝 [MÉTODO] Exportando Relatório de Lista de Testes Final...'
    /opt/Unity/Unity -projectPath /app/project -batchmode -nographics \
      -executeMethod LaundryNDishes.CLI.LndCommandLineInterface.ExportTestReport \
      -csv \"/app/artifacts/testList.csv\" \
      -logFile /app/artifacts/export-cli-log.txt

    echo '🔓 Devolvendo licença Unity...'
    /opt/Unity/Unity  -quit  -batchmode -nographics -returnlicense \"\$UNITY_SERIAL\" -username \"\$UNITY_EMAIL\" -password \"\$UNITY_PASSWORD\"  -logFile /app/artifacts/return-log.txt

    # Encerramento do Monitor
    kill \$MONITOR_PID
    
    # --------------------------------------------------
    # CORREÇÃO DE PERMISSÕES DENTRO DO CONTAINER
    # --------------------------------------------------
    echo '🔐 Ajustando permissões dos artefatos e do projeto para o usuário local...'
    chown -R $USER_UID:$USER_GID /app/artifacts
    chown -R $USER_UID:$USER_GID /app/project
  " 2>&1 | tee "$ARTIFACTS_DIR/pipeline_execution.log"
