#!/bin/bash
#SBATCH --job-name=hf-bulk-download
#SBATCH --output=npad_artifacts/download_%j.log
#SBATCH --error=npad_artifacts/download_error_%j.log
#SBATCH --time=24:00:00               # 4 horas é suficiente para pular o cache e checar os arquivos
#SBATCH --partition=amd-512,intel-128   # Força a execução especificamente no nó amd-512

# 📁 Definindo caminhos no Scratch para o ambiente virtual
VENV_DIR="../scratch/hf_download_venv"

echo "🚀 Iniciando o Job no nó $(hostname)"

# 🛠️ Passo 1: Carregar o módulo do Python do Cluster (se aplicável)
# Caso seu cluster use environment modules, descomente a linha abaixo e mude para a versão instalada:
module load python/3.10.8 || module load python/3.10 || module load python/3.9

# Se o comando 'python3' padrão do nó ainda for o 3.6, mas existir o comando 'python3.10' ou 'python3.9':
# Vamos forçar a criação do venv usando ele:
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Criando ambiente virtual..."
    if command -v python3.10 &>/dev/null; then
        python3.10 -m venv "$VENV_DIR"
    elif command -v python3.9 &>/dev/null; then
        python3.9 -m venv "$VENV_DIR"
    else
        python3 -m venv "$VENV_DIR" # Cai no 3.6 se não houver outro
    fi

# 📦 Passo 2: Criar e ativar o Virtual Environment (venv) se não existir
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Criando ambiente virtual Python em: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

echo "🔄 Ativando ambiente virtual..."
source "$VENV_DIR/bin/activate"

# 🆙 Passo 3: Atualizar o pip e instalar as dependências necessárias
echo "📥 Instalando/Atualizando dependências (huggingface_hub)..."
pip install --upgrade pip
pip install dataclasses
pip install huggingface_hub

# 🔑 Passo 4: Exportar o Token do Hugging Face se necessário
# Seus repositórios privados ou com limite de taxa precisam do token. 
# Recomenda-se definir isso no seu terminal antes de rodar o sbatch ou preencher aqui:
# export HF_TOKEN="seu_token_aqui"

# 🏃 Passo 5: Executar o arquivo Python de download
# Substitua 'seu_arquivo_download.py' pelo nome real do arquivo que salvamos no passo anterior
PYTHON_SCRIPT="baixar_modelos.py"

if [ -f "$PYTHON_SCRIPT" ]; then
    echo "▶️ Iniciando o script Python: $PYTHON_SCRIPT"
    python3 "$PYTHON_SCRIPT"
else
    echo "❌ Erro: O arquivo Python '$PYTHON_SCRIPT' não foi encontrado no diretório atual!"
    exit 1
fi

echo "🏁 Processo concluído com sucesso!"