import os
import sys
import time
import argparse
import subprocess
import requests
import shutil
import pandas as pd
from huggingface_hub import HfApi, hf_hub_download
import xml.etree.ElementTree as ET

# =====================================================================
# 📊 FUNÇÕES COMPARTILHADAS DE PARSING E LIMPEZA
# =====================================================================

def parse_test_results(xml_path):
    """Extrai a quantidade total de testes e quantos passaram do relatório NUnit."""
    if not os.path.exists(xml_path):
        return 0, 0
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        passed = int(root.get("passed", 0))
        failed = int(root.get("failed", 0))
        total = int(root.get("total", 0))
        
        if total == 0:
            passed = len(root.findall(".//test-case[@result='Passed']"))
            failed = len(root.findall(".//test-case[@result='Failed']"))
            total = passed + failed
        return total, passed
    except Exception:
        return 0, 0

def parse_unity_coverage_detailed(summary_xml_path):
    """Extrai as métricas absolutas do arquivo Summary.xml."""
    default_metrics = {
        "lines_covered": "0", "lines_coverable": "0",
        "methods_covered": "0", "methods_total": "0"
    }
    if not os.path.exists(summary_xml_path):
        return default_metrics
    try:
        tree = ET.parse(summary_xml_path)
        root = tree.getroot()
        summary_node = root.find(".//Summary")
        if summary_node is not None:
            metrics = {child.tag.lower(): child.text.strip() for child in summary_node if child.text}
            return {
                "lines_covered": metrics.get("coveredlines", "0"),
                "lines_coverable": metrics.get("coverablelines", "0"),
                "methods_covered": metrics.get("coveredmethods", "0"),
                "methods_total": metrics.get("totalmethods", "0")
            }
    except Exception:
        pass
    return default_metrics

def clear_leftover_tests():
    """🚨 REQUISITO: Remove arquivos antigos das pastas de testes antes de rodar a Unity, preservando arquivos assembly."""
    print("🧹 Iniciando varredura e limpeza de testes antigos...")
    for env_var in ["PLAYTEST_FOLDER", "EDITORTEST_FOLDER"]:
        folder_path = os.environ.get(env_var)
        if not folder_path:
            continue
        
        if not os.path.isabs(folder_path):
            folder_path = os.path.join("/app/project", folder_path)
            
        if os.path.exists(folder_path):
            print(f"🗑️  Limpando resíduos antigos na pasta {env_var}: {folder_path}")
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if item.endswith((".asmdef", ".asmdef.meta", ".asmdev", ".asmdev.meta")):
                    continue
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                except Exception as e:
                    print(f"⚠️ Não foi possível remover resíduo {item}: {e}")

def move_generated_tests(env_var_name, destination_subfolder, model_dir):
    """Auxiliar para mover arquivos gerados liberando espaço mantendo os .asmdef."""
    folder_path = os.environ.get(env_var_name)
    folder_path = folder_path.replace('"', '').replace("'", "").strip()
    if not folder_path:
        return
    if not os.path.isabs(folder_path):
        folder_path = os.path.join("/app/project", folder_path)
    if not os.path.exists(folder_path):
        return

    target_dir = os.path.join(model_dir, destination_subfolder)
    os.makedirs(target_dir, exist_ok=True)

    print(f"📦 Movendo arquivos de: {folder_path} -> {target_dir}")
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        if item.endswith((".asmdef", ".asmdef.meta", ".asmdev", ".asmdev.meta")):
            continue
        try:
            shutil.move(item_path, os.path.join(target_dir, item))
        except Exception as e:
            print(f"⚠️ Falha ao mover {item}: {e}")

def generate_global_leaderboard(models_root_dir, backend_name):
    """Cria o ranking unificado de todos os modelos processados."""
    print(f"🏆 Compilando Tabela do Leaderboard Global ({backend_name.upper()})...")
    all_reports = []
    if not os.path.exists(models_root_dir):
        return

    for folder in os.listdir(models_root_dir):
        csv_path = os.path.join(models_root_dir, folder, "coverage_report.csv")
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path)
                all_reports.append(df)
            except Exception:
                pass
                
    if all_reports:
        leaderboard_df = pd.concat(all_reports, ignore_index=True)
        numeric_cols = ["editmodetestpassing", "playmodetestspassing", "coveredlines"]
        for col in numeric_cols:
            if col in leaderboard_df.columns:
                leaderboard_df[col] = pd.to_numeric(leaderboard_df[col], errors='coerce').fillna(0)
                
        leaderboard_df = leaderboard_df.sort_values(
            by=["playmodetestspassing", "coveredlines"], 
            ascending=[False, False]
        )
        
        output_path = "/app/artifacts/GLOBAL_LEADERBOARD.csv"
        leaderboard_df.to_csv(output_path, index=False)
        print(f"\n👑 RANKING FINAL DE QUALIDADE DE CÓDIGO ({backend_name.upper()}):")
        print(leaderboard_df.to_string(index=False))

# =====================================================================
# 🎮 PIPELINE DA ENGINE UNITY
# =====================================================================

def run_unity_pipeline(model_safe_name, model_dir, backend_name):
    """Dispara a bateria de testes da Unity dentro do container."""
    project_path = "/app/project"
    script_path = os.environ.get("SCRIPT_PATH", "Assets/Scripts")
    asm_name = os.environ.get("UNITY_ASM_NAME", "Assembly-CSharp")
    
    coverage_dir = os.path.join(model_dir, "coverage")
    shutil.rmtree(coverage_dir, ignore_errors=True)
    os.makedirs(coverage_dir, exist_ok=True)
    
    # 🚨 LIMPEZA EXECUTADA ANTES DA GENERATION CLI
    clear_leftover_tests()
    
    print(f"🛠️  [Unity] Executando geração de casos de teste via {backend_name.upper()}...")
    subprocess.run([
        "/opt/Unity/Unity", "-projectPath", project_path, "-batchmode", "-nographics",
        "-executeMethod", "LaundryNDishes.CLI.LndCommandLineInterface.GenerateTestsFolder",
        "-folder", script_path, "-csv", f"{model_dir}/testGeneration.csv",
        "-logFile", f"{model_dir}/generation-cli-log.txt"
    ], check=False)

    gen_csv_path = os.path.join(model_dir, "testGeneration.csv")
    has_success = False

    if os.path.exists(gen_csv_path):
        try:
            gen_df = pd.read_csv(gen_csv_path)
            if "Status" in gen_df.columns:
                statuses = gen_df["Status"].astype(str).str.upper().str.strip()
                has_success = statuses.isin(["SUCESS", "SUCCESS"]).any()
        except Exception as e:
            print(f"⚠️ Erro ao ler {gen_csv_path}: {e}")
            has_success = False
    else:
        print(f"❌ Erro Crítico: {gen_csv_path} não foi gerado.")
        has_success = False

    if not has_success:
        print(f"❌ {model_safe_name} não gerou nenhum caso válido. Movendo resíduos...")
        move_generated_tests("PLAYTEST_FOLDER", "Play_Test", model_dir)
        move_generated_tests("EDITORTEST_FOLDER", "EditorTests", model_dir)
        return False

    print("🎮 [Unity] Executando EditMode Tests + Code Coverage...")
    subprocess.run([
        "/opt/Unity/Unity", "-projectPath", project_path, "-batchmode", "-nographics",
        "-testPlatform", "editmode", "-runTests", "-debugCodeOptimization", "-enableCodeCoverage",
        "-coverageResultsPath", coverage_dir,
        "-coverageOptions", f"generateAdditionalMetrics;assemblyFilters:+{asm_name}",
        "-testResults", f"{model_dir}/editmode-results.xml",
        "-logFile", f"{model_dir}/editmode-log.txt"
    ], check=False)

    print("🎮 [Unity] Executando PlayMode Tests + Code Coverage...")
    subprocess.run([
        "/opt/Unity/Unity", "-projectPath", project_path, "-batchmode", "-nographics",
        "-testPlatform", "playmode", "-runTests", "-debugCodeOptimization", "-enableCodeCoverage",
        "-coverageResultsPath", coverage_dir,
        "-coverageOptions", f"generateAdditionalMetrics;assemblyFilters:+{asm_name}",
        "-testResults", f"{model_dir}/playmode-results.xml",
        "-logFile", f"{model_dir}/playmode-log.txt"
    ], check=False)

    print("📊 [Unity] Consolidando Relatório HTML Final...")
    subprocess.run([
        "/opt/Unity/Unity", "-projectPath", project_path, "-batchmode", "-nographics",
        "-debugCodeOptimization", "-enableCodeCoverage", "-coverageResultsPath", coverage_dir,
        "-coverageOptions", f"generateHtmlReport;generateBadgeReport;assemblyFilters:+{asm_name}",
        "-quit", "-logFile", f"{model_dir}/coverage-report-log.txt"
    ], check=False)

    print("📝 [Unity] Exportando Lista de Métricas de Sucesso...")
    subprocess.run([
        "/opt/Unity/Unity", "-projectPath", project_path, "-batchmode", "-nographics",
        "-executeMethod", "LaundryNDishes.CLI.LndCommandLineInterface.ExportTestReport",
        "-csv", f"{model_dir}/testList.csv",
        "-logFile", f"{model_dir}/export-cli-log.txt"
    ], check=False)

    move_generated_tests("PLAYTEST_FOLDER", "Play_Test", model_dir)
    move_generated_tests("EDITORTEST_FOLDER", "EditorTests", model_dir)

    editmode_xml = os.path.join(model_dir, "editmode-results.xml")
    playmode_xml = os.path.join(model_dir, "playmode-results.xml")
    
    combined_summary_xml = os.path.join(coverage_dir, "Summary.xml")
    if not os.path.exists(combined_summary_xml):
        combined_summary_xml = os.path.join(coverage_dir, "Report", "Summary.xml")
    
    em_total, em_pass = parse_test_results(editmode_xml)
    pm_total, pm_pass = parse_test_results(playmode_xml)
    cov = parse_unity_coverage_detailed(combined_summary_xml)
    
    headers = [
        "model", "editmodetests", "editmodetestpassing", 
        "playmodetests", "playmodetestspassing", 
        "coverablelines", "coveredlines", "methods", "covered_methods"
    ]
    
    row_values = [
        model_safe_name, str(em_total), str(em_pass),
        str(pm_total), str(pm_pass),
        str(cov["lines_coverable"]), str(cov["lines_covered"]),
        str(cov["methods_total"]), str(cov["methods_covered"])
    ]
    
    csv_content = ",".join(headers) + "\n" + ",".join(row_values) + "\n"
    
    print("\n📊 RELATÓRIO DE COBERTURA E TESTES COMPILADO (CSV):")
    print(csv_content)
    
    csv_output_path = os.path.join(model_dir, "coverage_report.csv")
    with open(csv_output_path, "w", encoding="utf-8") as f:
        f.write(csv_content)
        
    return True

# =====================================================================
# 🔥 BACKEND 1: VLLM (MODELOS NATIVOS / HUGGING FACE)
# =====================================================================
def get_best_code_models(limit=5, completed_models=None):
    if completed_models is None:
        completed_models = set()

    artifacts_dir = "/app/artifacts"
    blacklist_path = os.path.join(artifacts_dir, "modelblacklist.txt")
    blacklist = set()

    if os.path.exists(blacklist_path):
        with open(blacklist_path, "r") as f:
            blacklist = {line.strip() for line in f if line.strip()}
        print(f"📋 Blacklist carregada com {len(blacklist)} modelos ignorados.")

    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        print("⚠️ Aviso: HF_TOKEN não encontrado. Modelos protegidos serão ignorados.")

    print("🔍 Buscando modelos recomendados no Hugging Face...")
    api = HfApi(token=hf_token)

    # Foca explicitamente em geração de texto
    available_models = api.list_models(filter=["code", "text-generation"], sort=["trending_score"],direction=-1, full=True)

    filtered_models = []
    for model in available_models:
        if model.modelId in blacklist or model.modelId in completed_models:
            print("🚫 LISTA NEGRA: " + model.modelId)
            continue

        model_id_lower = model.modelId.lower()

        # 🚫 LISTA NEGRA: Formatos incompatíveis com vLLM
        bad_formats = ["gguf", "ggml", "mlx", "coreml", "openvino", "onnx", "exl2", "tflite"]
        if any(bad in model_id_lower for bad in bad_formats):
            print("🚫 LISTA NEGRA: Formatos incompatíveis com vLLM:"+model_id_lower)
            continue

        try:
            detailed_info = api.model_info(model.modelId, files_metadata=True)
        except Exception:
            print("Erro de extraçao:")
            print(ValueError)
            continue

        tags = getattr(detailed_info, 'tags', [])
        tags_lower = [str(t).lower() for t in tags]

        # 🚫 REJEIÇÃO 1: Precisa ser de geração de texto
        if "text-generation" not in tags_lower:
            print("🚫 REJEIÇÃO 1: Precisa ser de geração de texto:")
            print(tags_lower)
            continue

        # 🚫 REJEIÇÃO 2: Precisa ser compatível com a biblioteca transformers (Requisito do vLLM)
        if "transformers" not in tags_lower:
            print("🚫 REJEIÇÃO 2: Precisa ser compatível com a biblioteca transformers (Requisito do vLLM)")
            print(tags_lower)
            continue

        # 🚫 REJEIÇÃO 3: Filtro extra nas tags contra formatos concorrentes
        if any(bad in tags_lower for bad in bad_formats):
            print("🚫 REJEIÇÃO 3: Filtro extra nas tags contra formatos concorrentes:" )
            print(tags_lower)
            continue

        total_size_bytes = 0
        has_weights = False
        for sibling in detailed_info.siblings:
            # vLLM prefere safetensors (recomendado) ou bin/pt.
            if sibling.rfilename.endswith(('.safetensors', '.bin', '.pt')):
                has_weights = True
                if hasattr(sibling, 'size') and sibling.size is not None:
                    total_size_bytes += sibling.size

        size_gb = total_size_bytes / (1024 ** 3)
        is_small_by_params = False
        is_awq_gptq = any(q in model_id_lower for q in ["awq", "gptq", "4bit"])

        for tag in detailed_info.tags:
            if tag.startswith("params:"):
                try:
                    params = float(tag.replace("params:", "").replace("B", "").strip())
                    if params <= 3.2 or (params <= 7.5 and is_awq_gptq):
                        is_small_by_params = True
                except ValueError:
                    print("Erro de valor:")
                    print(ValueError)
                    pass

        if has_weights and ((0 < size_gb <= 7.8) or (total_size_bytes == 0 and is_small_by_params)):
            filtered_models.append(model.modelId)
            print(f"✅ Identificado p/ vLLM: {model.modelId} (~{size_gb:.2f} GB)")
            if limit > 0 and len(filtered_models) >= limit:
                break

    return filtered_models

def run_vllm(model_name):
    """Inicia o servidor vLLM de forma pública."""
    kill_zombie_servers("11434")
    has_gpu = os.environ.get("HAS_GPU", "false").lower() == "true"
    
    cmd = [
        "python3", "-u", "-m", "vllm.entrypoints.openai.api_server",
        "--model", model_name,
        "--port", "11434",
        "--max-model-len", "2048",
        "--served-model-name", "vllmModel",
        "--trust-remote-code"
    ]
    
    run_env = os.environ.copy()
    
    safe_name = model_name.replace('/', '_')
    log_file_path = f"/app/artifacts/vllm_{safe_name}_debug.log"
    log_file = open(log_file_path, "w")
    
    if has_gpu:
        print(f"🚀 Subindo instância vLLM para: {model_name} [Modo: GPU]")
    else:
        print(f"🚀 Subindo instância vLLM para: {model_name} [Modo: CPU Forçado]")
        cmd += ["--device", "cpu"]
        run_env["VLLM_TARGET_DEVICE"] = "cpu"
        run_env["CUDA_VISIBLE_DEVICES"] = "" 
        run_env["RAY_CUDA_VISIBLE_DEVICES"] = "" 
    
    process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, env=run_env)
    start_time = time.time()
    
    while True:
        try:
            response = requests.get("http://localhost:11434/v1/models", timeout=2)
            if response.status_code == 200:
                print("🟢 vLLM conectado e pronto para receber requisições Unity!")
                return process
        except requests.RequestException:
            pass
        
        exit_code = process.poll()
        if exit_code is not None:
            log_file.flush()
            log_file.close()
            print(f"❌ Erro crítico: O vLLM crashou. Código de saída: {exit_code}")
            os.system(f"tail -n 15 {log_file_path}")
            return None
            
        if time.time() - start_time > 600:
            print("❌ Timeout no carregamento do vLLM.")
            process.terminate()
            return None
        time.sleep(5)

def kill_zombie_servers(port="11434"):
    """Força a liberação da porta matando qualquer processo preso nela."""
    try:
        # Comando de SO para matar processos segurando a porta
        subprocess.run(f"fuser -k {port}/tcp", shell=True, check=False, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, capture_output=True)
        time.sleep(3) # Dá tempo para o sistema operacional liberar o socket
    except Exception:
        print(Exception)
        pass

# =====================================================================
# 🦙 BACKEND 2: LLAMA.CPP (MODELOS GGUF QUANTISED)
# =====================================================================

def get_best_gguf_models(limit=5, completed_models=None):
    if completed_models is None:
        completed_models = set()

    artifacts_dir = "/app/artifacts"
    blacklist_path = os.path.join(artifacts_dir, "modelblacklist.txt")
    blacklist = set()

    if os.path.exists(blacklist_path):
        with open(blacklist_path, "r") as f:
            blacklist = {line.strip() for line in f if line.strip()}

    hf_token = os.environ.get("HF_TOKEN")
    api = HfApi(token=hf_token)
    
    print("🔍 Buscando modelos GGUF no Hugging Face...")
    # 🔥 COMBINAÇÃO VENCEDORA: Só traz GGUFs que são listados como Text-Generation
    available_models = api.list_models(filter=["gguf", "text-generation"], sort="downloads", full=True)
    filtered_models = []
    
    for model in available_models:
        model_id_lower = model.modelId.lower()

        try:
            detailed_info = api.model_info(model.modelId, files_metadata=True)
        except Exception:
            continue
        # 1. Pega as tags oficiais e a categoria principal
        pipeline = getattr(detailed_info, 'pipeline_tag', '')
        tags = getattr(detailed_info, 'tags', [])
        tags_lower = [str(t).lower() for t in tags]

        # 2. Rejeição Oficial: Se o Hugging Face diz que é de vetorização, cai fora
        bad_pipelines = ["feature-extraction", "sentence-similarity", "text-classification"]
        if pipeline in bad_pipelines or any(b in tags_lower for b in bad_pipelines):
            continue

        # 3. Aprovação Principal: O Hugging Face PRECISA dizer que é gerador de texto
        if pipeline != "text-generation" and "text-generation" not in tags_lower:
            continue

        # 4. Verificação de Instruct/Chat: 
        # O modelo tem as tags oficiais de chat/instrução?
        is_chat_tagged = any(t in tags_lower for t in ["conversational", "instruction-tuning", "chat", "instruct"])
        
        # Fallback de segurança: às vezes quem upou o GGUF esqueceu de colocar as tags oficiais,
        # então se a tag falhar, checamos o nome apenas como última esperança.
        is_chat_named = any(word in model_id_lower for word in ["instruct", "chat", "-it", "it-"])

        if not (is_chat_tagged or is_chat_named):
            continue
        valid_gguf_files = []
        for sibling in detailed_info.siblings:
            filename = sibling.rfilename
            if filename.endswith(".gguf"):
                if any(part in filename.lower() for part in ["split", "-of-", "part", "mmproj"]):
                    continue
                size_bytes = getattr(sibling, 'size', 0) or 0
                size_gb = size_bytes / (1024 ** 3)
                
                if 0 < size_gb <= 8.0:
                    valid_gguf_files.append({"filename": filename, "size_gb": size_gb})
        
        if not valid_gguf_files:
            continue
            
        valid_gguf_files.sort(key=lambda x: x["size_gb"], reverse=True)
        chosen_file = valid_gguf_files[0]
        model_identifier = f"{model.modelId}/{chosen_file['filename']}"
        
        if model_identifier in blacklist or model_identifier in completed_models:
            continue
            
        filtered_models.append({
            "repo_id": model.modelId,
            "filename": chosen_file["filename"],
            "size_gb": chosen_file["size_gb"],
            "identifier": model_identifier
        })
        print(f"✅ Selecionado GGUF: {model_identifier} (~{chosen_file['size_gb']:.2f} GB)")
        if limit and len(filtered_models) >= limit:
            break
            
    filtered_models.sort(key=lambda x: x["size_gb"])
    return filtered_models

def run_llamacpp(local_model_path, identifier):
    kill_zombie_servers("11434")
    """Inicia o servidor binário C++ nativo do Llama.cpp."""
    has_gpu = os.environ.get("HAS_GPU", "false").lower() == "true"
    
    # Chamada direta para o executável compilado no Dockerfile
    cmd = [
        "llama-server",
        "-m", local_model_path,
        "--port", "11434",
        "-c", "2048",            # Contexto
        "--alias", "vllmModel"   # No C++, o argumento é puramente --alias
    ]
    
    # Controle de GPU no executável nativo
    if has_gpu:
        print(f"🚀 Subindo Llama-Server (C++) para: {identifier} [Modo: GPU (Full Offload)]")
        cmd += ["-ngl", "999"]   # Joga todas as camadas para a placa de vídeo
    else:
        print(f"🚀 Subindo Llama-Server (C++) para: {identifier} [Modo: CPU Nativo]")
        cmd += ["-ngl", "0"]
    
    safe_name = identifier.replace('/', '_').replace('.', '_')
    log_file_path = f"/app/artifacts/llamacpp_{safe_name}_debug.log"
    log_file = open(log_file_path, "w")
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = "/usr/local/lib:" + env.get("LD_LIBRARY_PATH", "")
    # Subimos o processo nativo
    process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, env=env)
    
    time.sleep(5)
    
    # 🧠 Warmup (Aguardando o Llama-Server ficar online)
    warmup_url = "http://localhost:11434/v1/chat/completions"
    payload = {
        "model": "vllmModel",
        "messages": [{"role": "user", "content": "hi"}]
    }
    print("Enviando requisição de.")
    max_retries = 20
    for i in range(max_retries):
        if process.poll() is not None:
            print("❌ O Llama-Server C++ nativo crashou durante a inicialização.")
            log_file.close()
            return None
            
        try:
            # Envia a requisição; se o binário carregou a VRAM, ele responde 200 na hora.
            response = requests.post(warmup_url, json=payload, timeout=15)
            print(response)
            print(response.status_code)
            if response.status_code == 200:
                print("🟢 Llama-Server nativo online, com memória alocada e pronto para a Unity!")
                log_file.close()
                return process
        except e:
            print(f"⏳ Aguardando alocação de memória no C++... ({i+1}/{max_retries}) Excecao:{e}")
        
        time.sleep(10)
        
    print("❌ Timeout: O modelo demorou demais para inicializar.")
    process.terminate()
    log_file.close()
    return None

# =====================================================================
# ⚙️ MÓDULO ORQUESTRADOR CENTRAL (MAIN)
# =====================================================================

def main():
    print("DEBUG: Entrou no main do orquestrador.")
    parser = argparse.ArgumentParser(description="Orquestrador Unificado de IA para Testes de Cobertura Unity")
    parser.add_argument(
        "--backend", 
        type=str, 
        choices=["vllm", "llamacpp"], 
        default="vllm",
        help="Selecione o motor de execução (padrão: vllm)"
    )
    args = parser.parse_args()

    artifacts_dir = "/app/artifacts"
    models_root_dir = os.path.join(artifacts_dir, "models")
    tmp_model_file = "/tmp/current_active_model"
    blacklist_path = os.path.join(artifacts_dir, "modelblacklist.txt")
    completed_path = os.path.join(artifacts_dir, "completed_models.txt")
    
    completed_models = set()
    if os.path.exists(completed_path):
        with open(completed_path, "r") as f:
            completed_models = {line.strip() for line in f if line.strip()}
        print(f"💾 Histórico carregado: {len(completed_models)} modelos registrados anteriormente.")

    if args.backend == "vllm":
        print("🟢 MODO SELECIONADO: PIPELINE STANDARD VLLM (Modelos nativos HF)")
        models_to_test = get_best_code_models(limit=0, completed_models=completed_models)
    else:
        print("🦙 MODO SELECIONADO: PIPELINE LLAMA.CPP (Modelos GGUF compactos)")
        models_to_test = get_best_gguf_models(limit=5, completed_models=completed_models)

    if not models_to_test:
        print(f"🏁 [CONCLUÍDO] Nenhum modelo restante para processar com o backend {args.backend.upper()}!")
        flag_path = os.path.join(artifacts_dir, "NO_MORE_MODELS.flag")
        with open(flag_path, "w") as f:
            f.write("FINISHED")
        sys.exit(0)

    for target in models_to_test:
        if args.backend == "vllm":
            model_identifier = target
            model_safe = model_identifier.replace("/", "_")
        else:
            model_identifier = target["identifier"]
            model_safe = model_identifier.replace("/", "_").replace(".", "_")

        if model_identifier in completed_models:
            continue

        model_dir = os.path.join(models_root_dir, model_safe)
        os.makedirs(model_dir, exist_ok=True)
        
        with open(tmp_model_file, "w") as f:
            f.write(model_identifier)
            
        local_path = None
        engine_process = None
        
        try:
            if args.backend == "vllm":
                engine_process = run_vllm(model_identifier)
            else:
                print(f"\n📥 [Llama.cpp] Baixando arquivo GGUF alvo: {target['filename']}...")
                local_path = hf_hub_download(
                    repo_id=target["repo_id"], 
                    filename=target["filename"], 
                    token=os.environ.get("HF_TOKEN")
                )
                engine_process = run_llamacpp(local_path, model_identifier)
                
            if engine_process is None:
                continue

            pipeline_success = run_unity_pipeline(model_safe, model_dir, args.backend)
            
            if not pipeline_success:
                print(f"❌ Adicionando {model_identifier} à Blacklist...")
                with open(blacklist_path, "a") as f:
                    f.write(f"{model_identifier}\n")
            else:
                print(f"✨ {model_identifier} finalizado com sucesso! Registrando nos concluídos...")
                with open(completed_path, "a") as f:
                    f.write(f"{model_identifier}\n")
                    
        except Exception as e:
            print(f"⚠️ Falha catastrófica no processamento do modelo {model_identifier}: {e}")
        finally:
            if engine_process:
                print(f"🛑 Desligando servidor ativo do backend {args.backend.upper()}...")
                engine_process.terminate()
                engine_process.wait()
            
            if args.backend == "llamacpp" and local_path and os.path.exists(local_path):
                print(f"🧹 Liberando espaço em disco: Removendo cache do GGUF {target['filename']}...")
                try:
                    os.remove(local_path)
                except OSError:
                    pass
            time.sleep(5)

    with open(tmp_model_file, "w") as f:
        f.write("-")
        
    generate_global_leaderboard(models_root_dir, args.backend)

if __name__ == "__main__":
    main()