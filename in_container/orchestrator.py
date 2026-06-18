import os
import sys
import time
import argparse
import subprocess
import requests
import shutil
import pandas as pd
from huggingface_hub import HfApi, hf_hub_download
import psutil
import pynvml
import csv
import threading
from datetime import datetime, timedelta, timezone
from utils import kill_zombie_servers, ResourceMonitor, parse_test_results, clear_leftover_tests, move_generated_tests,parse_unity_coverage_detailed


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
    
    clear_leftover_tests()

    print(f"🛠️ [Unity] Executando geração de casos de teste via {backend_name.upper()}...")
    monitor = ResourceMonitor(model_name=model_safe_name, output_file="/app/artifacts/performance_report.csv")

    print(f"🛠️ [Unity] Iniciando geração e monitoramento: {model_safe_name}")
    monitor.start()

    # 1. Extrai os argumentos para uma variável estruturada
    cmd_args = [
        "/opt/Unity/Unity", "-projectPath", project_path, "-batchmode", "-nographics",
        "-executeMethod", "LaundryNDishes.CLI.LndCommandLineInterface.GenerateTestsFolder",
        "-folder", script_path, "-csv", f"{model_dir}/testGeneration.csv",
        "-logFile", f"{model_dir}/generation-cli-log.txt"
    ]

    try:
        # 2. Exibe os argumentos formatados de forma legível no log de debug
        print(f"🔹 [Debug] Comando enviado ao subprocess:\n{' '.join(cmd_args)}")
        
        # 3. Executa o processo passando a lista de argumentos
        subprocess.run(cmd_args, check=False)

    finally:
        monitor.stop()  
        print(f"✅ Monitoramento finalizado para {model_safe_name}.")

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
    
    try:
        cov = parse_unity_coverage_detailed(combined_summary_xml)
    except Exception:
        cov = {"lines_coverable": 0, "lines_covered": 0, "methods_total": 0, "methods_covered": 0}
    
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

    um_ano_atras = datetime.now(timezone.utc) - timedelta(days=365)

    print(f"🔍 Buscando os melhores modelos GGUF para CÓDIGO (atualizados após {um_ano_atras.strftime('%Y-%m-%d')})...")

    available_models = api.list_models(
        filter=["gguf", "text-generation", "code"],
        sort="downloads",
        full=True
    )

    filtered_models = []

    for model in available_models:
        model_id_lower = model.modelId.lower()
        last_modified = getattr(model, 'lastModified', None)
        if last_modified:
            if isinstance(last_modified, str):
                last_modified = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
            if last_modified < um_ano_atras:
                continue

        pipeline = getattr(model, 'pipeline_tag', '')
        tags = getattr(model, 'tags', [])
        tags_lower = [str(t).lower() for t in tags]

        try:
            repo_files =  list(api.list_repo_tree(model.modelId, expand=True))
        except Exception:
            continue

        valid_gguf_files = []
        for item in repo_files:
            if item.path.endswith(".gguf"):
                if item.security and item.security.safe is not True  and item.security.status == "unsafe":
                    print(f"⚠️ Modelo bloqueado por segurança: {model.modelId} ({item.path})")
                    continue

                # Ignora fragmentos
                if any(part in item.path.lower() for part in ["split", "-of-", "part", "mmproj"]):
                    continue
                
                size_bytes = getattr(item, 'size', 0) or 0
                size_gb = size_bytes / (1024 ** 3)

                if 0 < size_gb <= 9.0:
                    valid_gguf_files.append({"filename": item.path, "size_gb": size_gb})

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
        print(f"✅ Especialista em Código Encontrado: {model_identifier} (~{chosen_file['size_gb']:.2f} GB)")

        if limit and len(filtered_models) >= limit:
            break

    filtered_models.sort(key=lambda x: x["size_gb"])
    return filtered_models


def run_llamacpp(local_model_path, identifier):
    kill_zombie_servers("58291")
    """Inicia o servidor binário C++ nativo do Llama.cpp."""
    has_gpu = os.environ.get("HAS_GPU", "false").lower() == "true"

    cmd = [
        "llama-server",
        "-m", local_model_path,
        "--port", "58291",
        "-c", "2048",  
        "--alias", "vllmModel"
    ]

    if has_gpu:
        print(f"🚀 Subindo Llama-Server (C++) para: {identifier} [Modo: GPU (Full Offload)]")
        cmd += ["-ngl", "999"]
    else:
        print(f"🚀 Subindo Llama-Server (C++) para: {identifier} [Modo: CPU Nativo]")
        cmd += ["-ngl", "0"]

    # 📂 Gerenciamento Centralizado de Logs em uma pasta dedicada da Unity Artifacts
    logs_dir = "/app/artifacts/llamacpp_logs"
    os.makedirs(logs_dir, exist_ok=True)

    safe_name = identifier.replace('/', '_').replace('.', '_')
    log_file_path = os.path.join(logs_dir, f"{safe_name}.log")

    log_file = open(log_file_path, "w")
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = "/usr/local/lib:" + env.get("LD_LIBRARY_PATH", "")

    process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, env=env)

    time.sleep(5)

    warmup_url = "http://localhost:58291/v1/chat/completions"
    payload = {
        "model": "vllmModel",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
        "temperature": 0.0
    }

    print(f"🔄 Aguardando inicialização do backend para {identifier}...")
    max_retries = 20
    for i in range(max_retries):
        if process.poll() is not None:
            print(f"❌ O Llama-Server crashou de imediato. Detalhes salvos em: {log_file_path}")
            log_file.close()
            return None

        try:
            response = requests.post(warmup_url, json=payload, timeout=60)
            if response.status_code == 200:
                print("🟢 Llama-Server nativo online e integrado com sucesso!")
                log_file.close()
                return process
        except Exception as err:
            # Renomeado para 'err' evitando colisões locais de escopo no interpretador
            print(f"⏳ Alocando tensores... ({i + 1}/{max_retries}) Status: Aguardando resposta do Servidor C++")

        time.sleep(2)

    print(f"❌ Timeout: O Llama-Server congelou ou demorou demais para responder.")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()

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
        default="llamacpp",
        help="Selecione o motor de execução (padrão: llamacpp)"
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

    print("🦙 MODO SELECIONADO: PIPELINE LLAMA.CPP (Modelos GGUF compactos)")
    has_gpu = os.environ.get("HAS_GPU", "false").lower() == "true"
    if has_gpu:
        models_to_test = get_best_gguf_models(limit=200, completed_models=completed_models)
    else:
        models_to_test = get_best_gguf_models(limit=5, completed_models=completed_models)

    if not models_to_test:
        print(f"🏁 [CONCLUÍDO] Nenhum modelo restante para processar com o backend {args.backend.upper()}!")
        flag_path = os.path.join(artifacts_dir, "NO_MORE_MODELS.flag")
        with open(flag_path, "w") as f:
            f.write("FINISHED")
        sys.exit(0)

    for target in models_to_test:
        model_identifier = target["identifier"]
        model_safe = model_identifier.replace("/", "_").replace(".", "_")

        if model_identifier in completed_models:
            continue

        
            
        local_path = None
        engine_process = None
        
        try:
            print(f"\n📥 [Llama.cpp] Baixando arquivo GGUF alvo: {target['filename']}...")
            local_path = hf_hub_download(
                repo_id=target["repo_id"],
                filename=target["filename"],
                token=os.environ.get("HF_TOKEN")
            )
            engine_process = run_llamacpp(local_path, model_identifier)
                
            if engine_process is None:
                print(f"❌ Adicionando {model_identifier} à Blacklist por não iniciar")
                with open(blacklist_path, "a") as f:
                    f.write(f"{model_identifier}\n")
                continue
            model_dir = os.path.join(models_root_dir, model_safe)
            os.makedirs(model_dir, exist_ok=True)

            with open(tmp_model_file, "w") as f:
                f.write(model_identifier)
            pipeline_success = run_unity_pipeline(model_safe, model_dir, args.backend)
            
            if not pipeline_success:
                print(f"❌ Adicionando {model_identifier} à Blacklist...")
                with open(blacklist_path, "a") as f:
                    f.write(f"{model_identifier}\n")
            else:
                print(f"✨ {model_identifier} finalizado com sucesso! Registrando nos concluídos...")
                with open(completed_path, "a") as f:
                    f.write(f"{model_identifier}\n")
                    
        except Exception as main_err:
            print(f"⚠️ Falha catastrófica no processamento do modelo {model_identifier}: {main_err}")
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