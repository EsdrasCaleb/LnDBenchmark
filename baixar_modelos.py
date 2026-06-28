import os
import shutil
from huggingface_hub import hf_hub_download

# Configurações do diretório de destino
DEST_DIR = "../scratch/hf_scratch_download/"
os.makedirs(DEST_DIR, exist_ok=True)



# Lista bruta extraída do seu log
modelos_brutos = [
    "bartowski/North-Mini-Code-1.0-GGUF/North-Mini-Code-1.0-Q2_K_L.gguf",
    "bartowski/cerebras_Qwen3-Coder-REAP-25B-A3B-GGUF/cerebras_Qwen3-Coder-REAP-25B-A3B-Q3_K_M.gguf",
    "unsloth/JanusCoder-14B-GGUF/JanusCoder-14B-UD-Q5_K_XL.gguf",
    "unsloth/JanusCoder-8B-GGUF/JanusCoder-8B-UD-Q8_K_XL.gguf",
    "unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF/Qwen3-Coder-30B-A3B-Instruct-UD-Q2_K_XL.gguf",
    "unsloth/Qwen3-Coder-30B-A3B-Instruct-1M-GGUF/Qwen3-Coder-30B-A3B-Instruct-1M-Q2_K_L.gguf",
    "unsloth/Qwen3.6-27B-GGUF/Qwen3.6-27B-UD-IQ2_M.gguf",
    "unsloth/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-IQ2_M.gguf",
    "bartowski/allura-org_Qwen3.6-35B-A3B-Anko-GGUF/allura-org_Qwen3.6-35B-A3B-Anko-IQ2_S.gguf",
    "bartowski/Qwen_Qwen3.6-27B-GGUF/Qwen_Qwen3.6-27B-IQ2_M.gguf",
    "bartowski/Qwen_Qwen3.6-35B-A3B-GGUF/Qwen_Qwen3.6-35B-A3B-IQ2_XS.gguf",
    "unsloth/Qwen3.5-35B-A3B-GGUF/Qwen3.5-35B-A3B-UD-IQ2_M.gguf",
    "unsloth/Qwen3.5-27B-GGUF/Qwen3.5-27B-UD-IQ3_XXS.gguf",
    "unsloth/Qwen3.5-9B-GGUF/Qwen3.5-9B-Q8_0.gguf",
    "unsloth/Qwen3.5-4B-GGUF/Qwen3.5-4B-BF16.gguf",
    "unsloth/Qwen3.5-0.8B-GGUF/Qwen3.5-0.8B-BF16.gguf",
    "bartowski/Qwen_Qwen3.5-27B-GGUF/Qwen_Qwen3.5-27B-IQ2_M.gguf",
    "bartowski/Qwen_Qwen3.5-35B-A3B-GGUF/Qwen_Qwen3.5-35B-A3B-IQ2_XS.gguf",
    "bartowski/Qwen_Qwen3.5-9B-GGUF/Qwen_Qwen3.5-9B-Q8_0.gguf",
    "bartowski/Qwen_Qwen3.5-4B-GGUF/Qwen_Qwen3.5-4B-bf16.gguf",
    "bartowski/Qwen_Qwen3.5-2B-GGUF/Qwen_Qwen3.5-2B-bf16.gguf",
    "bartowski/Qwen_Qwen3.5-0.8B-GGUF/Qwen_Qwen3.5-0.8B-bf16.gguf",
    "bartowski/ArliAI_Qwen3.5-27B-RpRMax-v1-GGUF/ArliAI_Qwen3.5-27B-RpRMax-v1-Q2_K.gguf",
    "bartowski/allura-org_Qwen3.5-27B-Anko-GGUF/allura-org_Qwen3.5-27B-Anko-Q2_K.gguf",
    "bartowski/Jackrong_Qwen3.5-9B-Neo-GGUF/Jackrong_Qwen3.5-9B-Neo-Q8_0.gguf",
    "bartowski/Jackrong_Qwen3.5-4B-Neo-GGUF/Jackrong_Qwen3.5-4B-Neo-bf16.gguf",
    "bartowski/ConicCat_Qwen3.5-27B-Writer-GGUF/ConicCat_Qwen3.5-27B-Writer-Q2_K.gguf"
]

total = len(modelos_brutos)
print(f"📦 Total de modelos mapeados para download: {total}")

for idx, item in enumerate(modelos_brutos, 1):
    # Separa o repo_id (ex: bartowski/North-Mini-Code-1.0-GGUF) do nome do arquivo .gguf
    parts = item.split('/')
    repo_id = f"{parts[0]}/{parts[1]}"
    filename = "/".join(parts[2:]) # Captura se o arquivo estiver dentro de subpastas do repo
    caminho_local_esperado = os.path.join(DEST_DIR, filename)
    if os.path.exists(caminho_local_esperado):
        tamanho_gb = os.path.getsize(caminho_local_esperado) / (1024 ** 3)
        print(f"⏭️  [{idx}/{total}] Já existe (pulado): {filename} ({tamanho_gb:.2f} GB)")
        continue
    print(f"\n📥 [{idx}/{total}] Baixando: {repo_id} -> {filename}")
    
    try:
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            token=os.environ.get("HF_TOKEN"),
            local_dir=DEST_DIR,
            local_dir_use_symlinks=False,  # Grava o arquivo direto no scratch físico
            resume_download=True           # Caso a rede oscile, continua de onde parou
        )
        print(f"✅ Concluído! Salvo em: {local_path}")
    except Exception as e:
        print(f"❌ Erro ao baixar {filename}: {e}")

print("\n🏁 Processo de download em lote finalizado!")