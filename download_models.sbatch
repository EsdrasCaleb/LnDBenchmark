#!/bin/bash
#SBATCH --job-name=hf-bulk-download
#SBATCH --output=npad_artifacts/download_%j.log
#SBATCH --error=npad_artifacts/download_error_%j.log
#SBATCH --time=24:00:00               # 4 horas é suficiente para pular o cache e checar os arquivos
#SBATCH --partition=amd-512,intel-128   # Força a execução especificamente no nó amd-512

# 📁 Definindo caminhos no Scratch para o ambiente virtual

VENV_DIR="../scratch/hf_download_venv"

echo "🚀 Iniciando o Job no nó $(hostname)"

# 🛠️ Passo 1: Carrega a versão exata do Python 3.11 disponível no seu cluster
echo "🔄 Carregando o módulo correto do Python..."
module load python/3.11.9-gcc-12.3.0-egxne7o

# 🧹 Passo EXTRA: Se o venv antigo existia com o Python 3.6 quebrado, remove ele para recriar com 3.11
if [ -d "$VENV_DIR" ] && [[ "$(python3 -V)" == *"3.11"* ]]; then
    # Checa se o venv existente aponta para o Python velho. Se sim, limpa.
    if [[ "$("$VENV_DIR/bin/python" -V 2>&1)" == *"3.6"* ]]; then
        echo "🧹 Removendo venv antigo do Python 3.6 para evitar conflitos..."
        rm -rf "$VENV_DIR"
    fi
fi

# 📦 Passo 2: Criar o Virtual Environment usando o Python 3.11.9 recém-carregado
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Criando ambiente virtual Python 3.11 em: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

echo "🔄 Ativando ambiente virtual..."
source "$VENV_DIR/bin/activate"

# 🆙 Passo 3: Atualizar o pip e instalar a biblioteca necessária
echo "📥 Instalando dependência (huggingface_hub)..."
pip install --upgrade pip
pip install huggingface_hub, dataclasses

# 🏃 Passo 4: Executar o arquivo Python de download
PYTHON_SCRIPT="baixar_modelos.py"

if [ -f "$PYTHON_SCRIPT" ]; then
    echo "▶️ Iniciando o script Python: $PYTHON_SCRIPT"
    python3 "$PYTHON_SCRIPT"
else
    echo "❌ Erro: O arquivo Python '$PYTHON_SCRIPT' não foi encontrado no diretório atual!"
    exit 1
fi

echo "🏁 Processo concluído com sucesso!"