import os
import shutil
from huggingface_hub import hf_hub_download

# Configurações do diretório de destino
DEST_DIR = "../scratch/hf_scratch_download/"
os.makedirs(DEST_DIR, exist_ok=True)



# Lista bruta extraída do seu log
# modelos_novos = [
#     "unsloth/Qwen3.5-9B-GGUF/Qwen3.5-9B-Q6_K.gguf",
#     "unsloth/gemma-4-12b-it-GGUF/gemma-4-12b-it-Q5_K_M.gguf",
#     "unsloth/gemma-4-E2B-it-GGUF/gemma-4-E2B-it-UD-Q8_K_XL.gguf",
#     "unsloth/NVIDIA-Nemotron-3-Nano-4B-GGUF/NVIDIA-Nemotron-3-Nano-4B-BF16.gguf",
#     "unsloth/granite-4.1-8b-GGUF/granite-4.1-8b-UD-Q6_K_XL.gguf",
#     "unsloth/gemma-3-27b-it-GGUF/gemma-3-27b-it-UD-IQ2_XXS.gguf",
#     "unsloth/medgemma-4b-it-GGUF/medgemma-4b-it-BF16.gguf",
#     "unsloth/Mistral-Small-3.2-24B-Instruct-2506-GGUF/Mistral-Small-3.2-24B-Instruct-2506-UD-IQ2_M.gguf",
#     "unsloth/Devstral-Small-2507-GGUF/Devstral-Small-2507-UD-IQ2_M.gguf",
#     "unsloth/ERNIE-4.5-21B-A3B-Thinking-GGUF/ERNIE-4.5-21B-A3B-Thinking-UD-Q2_K_XL.gguf",
#     "unsloth/granite-4.0-h-tiny-GGUF/granite-4.0-h-tiny-UD-Q8_K_XL.gguf",
#     "unsloth/Apertus-8B-Instruct-2509-GGUF/Apertus-8B-Instruct-2509-Q8_0.gguf",
#     "unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF/Devstral-Small-2-24B-Instruct-2512-UD-IQ2_M.gguf",
#     "unsloth/Llama-3.2-3B-Instruct-GGUF/Llama-3.2-3B-Instruct-BF16.gguf",
#     "unsloth/gemma-3-4b-it-GGUF/gemma-3-4b-it-BF16.gguf",
#     "unsloth/gemma-3-12b-it-GGUF/gemma-3-12b-it-UD-Q5_K_XL.gguf",
#     "unsloth/Devstral-Small-2505-GGUF/Devstral-Small-2505-UD-IQ2_M.gguf",
#     "unsloth/Magistral-Small-2506-GGUF/Magistral-Small-2506-UD-IQ2_M.gguf",
#     "unsloth/gemma-3n-E2B-it-GGUF/gemma-3n-E2B-it-UD-Q8_K_XL.gguf",
#     "unsloth/gemma-3n-E2B-it-litert-preview-GGUF/gemma-3n-E2B-it-litert-preview-UD-Q8_K_XL.gguf",
#     "unsloth/gemma-3n-E4B-it-litert-preview-GGUF/gemma-3n-E4B-it-litert-preview-Q8_0.gguf",
#     "unsloth/SmolLM3-3B-GGUF/SmolLM3-3B-BF16.gguf",
#     "unsloth/Falcon-H1-1.5B-Deep-Instruct-GGUF/Falcon-H1-1.5B-Deep-Instruct-BF16.gguf",
#     "unsloth/Falcon-H1-34B-Instruct-GGUF/Falcon-H1-34B-Instruct-UD-IQ1_S.gguf",
#     "unsloth/ERNIE-4.5-21B-A3B-PT-GGUF/ERNIE-4.5-21B-A3B-PT-UD-Q2_K_XL.gguf",
#     "unsloth/Magistral-Small-2507-GGUF/Magistral-Small-2507-UD-IQ2_M.gguf",
#     "unsloth/GLM-4.1V-9B-Thinking-GGUF/GLM-4.1V-9B-Thinking-Q6_K.gguf",
#     "unsloth/Seed-OSS-36B-Instruct-GGUF/Seed-OSS-36B-Instruct-UD-IQ1_S.gguf",
#     "unsloth/Magistral-Small-2509-GGUF/Magistral-Small-2509-UD-IQ2_M.gguf",
#     "bartowski/gemma-4-12B-it-GGUF/gemma-4-12B-it-Q5_K_S.gguf",
#     "bartowski/mistralai_Voxtral-Small-24B-2507-GGUF/mistralai_Voxtral-Small-24B-2507-IQ2_M.gguf",
#     "bartowski/tencent_Hunyuan-1.8B-Instruct-GGUF/tencent_Hunyuan-1.8B-Instruct-bf16.gguf",
#     "bartowski/tencent_Hunyuan-4B-Instruct-GGUF/tencent_Hunyuan-4B-Instruct-bf16.gguf",
#     "bartowski/tencent_Hunyuan-7B-Instruct-GGUF/tencent_Hunyuan-7B-Instruct-Q8_0.gguf",
#     "bartowski/Qwen_Qwen3-4B-Thinking-2507-GGUF/Qwen_Qwen3-4B-Thinking-2507-bf16.gguf",
#     "bartowski/NousResearch_Hermes-4-14B-GGUF/NousResearch_Hermes-4-14B-Q3_K_XL.gguf",
#     "bartowski/mistralai_Mistral-Small-3.2-24B-Instruct-2506-GGUF/mistralai_Mistral-Small-3.2-24B-Instruct-2506-IQ2_M.gguf",
#     "bartowski/baidu_ERNIE-4.5-21B-A3B-PT-GGUF/baidu_ERNIE-4.5-21B-A3B-PT-Q2_K_L.gguf",
#     "bartowski/HuggingFaceTB_SmolLM3-3B-GGUF/HuggingFaceTB_SmolLM3-3B-bf16.gguf",
#     "bartowski/mistralai_Devstral-Small-2507-GGUF/mistralai_Devstral-Small-2507-IQ2_M.gguf",
#     "bartowski/RekaAI_reka-flash-3.1-GGUF/RekaAI_reka-flash-3.1-IQ2_M.gguf",
#     "bartowski/ibm-granite_granite-4.0-tiny-preview-GGUF/ibm-granite_granite-4.0-tiny-preview-Q8_0.gguf",
#     "bartowski/google_medgemma-4b-it-GGUF/google_medgemma-4b-it-bf16.gguf",
#     "bartowski/google_medgemma-27b-it-GGUF/google_medgemma-27b-it-IQ2_XS.gguf",
#     "bartowski/Dream-org_Dream-v0-Instruct-7B-GGUF/Dream-org_Dream-v0-Instruct-7B-Q8_0.gguf",
#     "bartowski/entfane_math-genius-7B-GGUF/entfane_math-genius-7B-Q8_0.gguf",
#     "bartowski/Menlo_Lucy-GGUF/Menlo_Lucy-bf16.gguf",
#     "bartowski/Menlo_Lucy-128k-GGUF/Menlo_Lucy-128k-bf16.gguf",
#     "bartowski/nvidia_OpenReasoning-Nemotron-1.5B-GGUF/nvidia_OpenReasoning-Nemotron-1.5B-bf16.gguf",
#     "bartowski/nvidia_OpenReasoning-Nemotron-7B-GGUF/nvidia_OpenReasoning-Nemotron-7B-Q8_0.gguf",
#     "bartowski/nvidia_OpenReasoning-Nemotron-14B-GGUF/nvidia_OpenReasoning-Nemotron-14B-Q4_K_S.gguf",
#     "bartowski/LGAI-EXAONE_EXAONE-4.0-1.2B-GGUF/LGAI-EXAONE_EXAONE-4.0-1.2B-bf16.gguf",
#     "bartowski/mistralai_Magistral-Small-2507-GGUF/mistralai_Magistral-Small-2507-IQ2_M.gguf",
#     "bartowski/Qwen_Qwen3-30B-A3B-Instruct-2507-GGUF/Qwen_Qwen3-30B-A3B-Instruct-2507-IQ2_XXS.gguf",
#     "bartowski/PowerInfer_SmallThinker-4BA0.6B-Instruct-GGUF/PowerInfer_SmallThinker-4BA0.6B-Instruct-bf16.gguf",
#     "bartowski/mistralai_Voxtral-Mini-3B-2507-GGUF/mistralai_Voxtral-Mini-3B-2507-bf16.gguf",
#     "bartowski/arcee-ai_AFM-4.5B-GGUF/arcee-ai_AFM-4.5B-Q8_0.gguf",
#     "bartowski/Qwen_Qwen3-30B-A3B-Thinking-2507-GGUF/Qwen_Qwen3-30B-A3B-Thinking-2507-IQ2_XXS.gguf",
#     "bartowski/HelpingAI_Dhanishtha-2.0-preview-0825-GGUF/HelpingAI_Dhanishtha-2.0-preview-0825-Q3_K_XL.gguf",
#     "bartowski/allura-org_MN-Lyrebird-12B-GGUF/allura-org_MN-Lyrebird-12B-Q5_K_S.gguf",
#     "bartowski/tencent_Hunyuan-0.5B-Instruct-GGUF/tencent_Hunyuan-0.5B-Instruct-bf16.gguf"
# ]



modelos = get_best_gguf_models(
    limit=30,
    author="unsloth",
    modelt_filter="gguf"
)

modelos += get_best_gguf_models(
    limit=50,
    author="bartowski",
    modelt_filter="gguf"
)



total = len(modelos)
print(f"📦 Total de modelos mapeados para download: {total}")

for idx, item in enumerate(modelos, 1):
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
        )
        print(f"✅ Concluído! Salvo em: {local_path}")
    except Exception as e:
        print(f"❌ Erro ao baixar {filename}: {e}")

print("\n🏁 Processo de download em lote finalizado!")