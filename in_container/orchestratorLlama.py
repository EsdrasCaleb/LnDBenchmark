import os
import sys
import time
import subprocess
import requests
import shutil
import pandas as pd
from huggingface_hub import HfApi, hf_hub_download
import xml.etree.ElementTree as ET

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

def get_best_gguf_models(limit=5, completed_models=None):
    """
    Busca modelos no formato GGUF ordenados por downloads.
    Filtra estritamente por tamanho (<= 8GB) e garante que o modelo seja de arquivo único.
    """
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
    api = HfApi(token=hf_token)
    
    print("🔍 Buscando modelos GGUF no Hugging Face...")
    # Filtra exclusivamente pela tag estrutural 'gguf'
    available_models = api.list_models(
        filter=["gguf"],
        sort="downloads",
        full=True
    )
    
    filtered_models = []
    
    for model in available_models:
        try:
            detailed_info = api.model_info(model.modelId, files_metadata=True)
        except Exception:
            continue

        valid_gguf_files = []

        # Varre os arquivos internos do repositório procurando os pesos GGUF
        for sibling in detailed_info.siblings:
            filename = sibling.rfilename
            
            if filename.endswith(".gguf"):
                # Restrição de arquivo único: ignora shards/splits fracionados
                is_split = any(part in filename.lower() for part in ["split", "-of-", "part"])
                if is_split:
                    continue
                
                size_bytes = getattr(sibling, 'size', 0) or 0
                size_gb = size_bytes / (1024 ** 3)
                
                # Restrição estrita de Tamanho: Máximo de 8 GB
                if 0 < size_gb <= 8.0:
                    valid_gguf_files.append({
                        "filename": filename,
                        "size_gb": size_gb
                    })
        
        if not valid_gguf_files:
            continue
            
        # Ordena para pegar a melhor quantização disponível dentro do teto de 8GB
        valid_gguf_files.sort(key=lambda x: x["size_gb"], reverse=True)
        chosen_file = valid_gguf_files[0]
        
        # O identificador único composto evita colisões de repositórios multi-arquivos
        model_identifier = f"{model.modelId}/{chosen_file['filename']}"
        
        if model_identifier in blacklist:
            continue
        if model_identifier in completed_models:
            continue
            
        filtered_models.append({
            "repo_id": model.modelId,
            "filename": chosen_file["filename"],
            "size_gb": chosen_file["size_gb"],
            "identifier": model_identifier
        })
        
        print(f"✅ Selecionado: {model_identifier} (~{chosen_file['size_gb']:.2f} GB)")
        if len(filtered_models) >= limit:
            break
                
    return filtered_models

def run_llamacpp(local_model_path, identifier):
    """Inicia o servidor emulando a API da OpenAI através do Llama.cpp."""
    has_gpu = os.environ.get("HAS_GPU", "false").lower() == "true"
    
    cmd = [
        "python3", "-u", "-m", "llama_cpp.server",
        "--model", local_model_path,
        "--port", "11434",
        "--n_ctx", "2048"
        "--a", "vllm-model"
    ]
    
    if has_gpu:
        print(f"🚀 Subindo Llama.cpp para: {identifier} [Modo: GPU (Full Offload)]")
        cmd += ["--n_gpu_layers", "-1"]
    else:
        print(f"🚀 Subindo Llama.cpp para: {identifier} [Modo: CPU Nativo]")
        cmd += ["--n_gpu_layers", "0"]
    
    safe_name = identifier.replace('/', '_').replace('.', '_')
    log_file_path = f"/app/artifacts/llamacpp_{safe_name}_debug.log"
    log_file = open(log_file_path, "w")
    
    process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
    
    print(f"⏳ Inicializando o Engine... (Log salvo em: {log_file_path})")
    start_time = time.time()
    
    while True:
        try:
            # Mantém a compatibilidade com a rota universal de checagem do endpoint
            response = requests.get("http://localhost:11434/v1/models", timeout=2)
            if response.status_code == 200:
                print("🟢 Llama.cpp conectado e pronto para responder à Unity!")
                return process
        except requests.RequestException:
            pass
        
        exit_code = process.poll()
        if exit_code is not None:
            log_file.flush()
            log_file.close()
            print(f"❌ Erro crítico: O backend do Llama.cpp crashou. Código de saída: {exit_code}")
            print(f"📝 --- ÚLTIMAS LINHAS DO LOG DO LLAMACPP ---")
            os.system(f"tail -n 15 {log_file_path}")
            print(f"--------------------------------------------")
            return None
            
        if time.time() - start_time > 300:
            print("❌ Timeout: O carregamento do modelo GGUF demorou mais de 5 minutos.")
            process.terminate()
            return None
        time.sleep(5)

def move_generated_tests(env_var_name, destination_subfolder, model_dir):
    """Auxiliar para mover arquivos gerados liberando espaço mantendo os .asmdef."""
    folder_path = os.environ.get(env_var_name)
    if not folder_path:
        return

    if not os.path.isabs(folder_path):
        folder_path = os.path.join("/app/project", folder_path)

    if not os.path.exists(folder_path):
        return

    target_dir = os.path.join(model_dir, destination_subfolder)
    os.makedirs(target_dir, exist_ok=True)

    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        if item.endswith((".asmdef", ".asmdef.meta", ".asmdev", ".asmdev.meta")):
            continue
        try:
            shutil.move(item_path, os.path.join(target_dir, item))
        except Exception:
            pass

def run_unity_pipeline(model_safe_name, model_dir):
    """Dispara a bateria de testes da Unity dentro do container."""
    project_path = "/app/project"
    script_path = os.environ.get("SCRIPT_PATH", "Assets/Scripts")
    asm_name = os.environ.get("UNITY_ASM_NAME", "Assembly-CSharp")
    
    coverage_dir = os.path.join(model_dir, "coverage")
    shutil.rmtree(coverage_dir, ignore_errors=True)
    os.makedirs(coverage_dir, exist_ok=True)
    
    print("🛠️  [Unity] Executando geração de casos de teste via GGUF...")
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
        except Exception:
            has_success = False
    else:
        has_success = False

    if not has_success:
        print(f"❌ O modelo não gerou nenhum caso estrutural válido. Aplicando penalidades...")
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
    
    csv_output_path = os.path.join(model_dir, "coverage_report.csv")
    with open(csv_output_path, "w", encoding="utf-8") as f:
        f.write(csv_content)
        
    return True

def generate_global_leaderboard(models_root_dir):
    """Cria o ranking unificado de todos os modelos processados."""
    print("🏆 Compilando Tabela do Leaderboard Global...")
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
        print("\n👑 RANKING FINAL DE QUALIDADE DE CÓDIGO (GGUF):")
        print(leaderboard_df.to_string(index=False))

def main():
    artifacts_dir = "/app/artifacts"
    models_root_dir = os.path.join(artifacts_dir, "models")
    tmp_model_file = "/tmp/current_active_model"
    blacklist_path = os.path.join(artifacts_dir, "modelblacklist.txt")
    completed_path = os.path.join(artifacts_dir, "completed_models.txt")
    
    completed_models = set()
    if os.path.exists(completed_path):
        with open(completed_path, "r") as f:
            completed_models = {line.strip() for line in f if line.strip()}
        print(f"💾 Histórico: {len(completed_models)} modelos GGUF concluídos anteriormente.")

    # Executa a filtragem por tamanho e arquivo único
    models_to_test = get_best_gguf_models(limit=5, completed_models=completed_models)
    
    if not models_to_test:
        print("🏁 [CONCLUÍDO] Nenhum modelo restante dentro dos critérios (GGUF, <=8GB, arquivo único).")
        flag_path = os.path.join(artifacts_dir, "NO_MORE_MODELS.flag")
        with open(flag_path, "w") as f:
            f.write("FINISHED")
        sys.exit(0)

    for target in models_to_test:
        repo_id = target["repo_id"]
        filename = target["filename"]
        identifier = target["identifier"]

        if identifier in completed_models:
            continue

        model_safe = identifier.replace("/", "_").replace(".", "_")
        model_dir = os.path.join(models_root_dir, model_safe)
        os.makedirs(model_dir, exist_ok=True)
        
        with open(tmp_model_file, "w") as f:
            f.write(identifier)
            
        local_path = None
        try:
            # Realiza o download pontual apenas do arquivo .gguf escolhido
            print(f"\n📥 Baixando arquivo GGUF alvo: {filename} do repositório {repo_id}...")
            local_path = hf_hub_download(
                repo_id=repo_id, 
                filename=filename, 
                token=os.environ.get("HF_TOKEN")
            )
            
            # Inicializa o Llama.cpp apontando para o arquivo físico baixado
            llamacpp_process = run_llamacpp(local_path, identifier)
            if llamacpp_process is None:
                continue
                
            try:
                os.environ["UNITY_LLM_API_KEY"] = "fake-llamacpp-token"
                pipeline_success = run_unity_pipeline(model_safe, model_dir)
                
                if not pipeline_success:
                    print(f"❌ Adicionando {identifier} à Blacklist...")
                    with open(blacklist_path, "a") as f:
                        f.write(f"{identifier}\n")
                else:
                    print(f"✨ {identifier} finalizado com sucesso! Registrando...")
                    with open(completed_path, "a") as f:
                        f.write(f"{identifier}\n")
            finally:
                print(f"🛑 Encerrando instância ativa do Llama.cpp...")
                llamacpp_process.terminate()
                llamacpp_process.wait()
                
        except Exception as e:
            print(f"⚠️ Falha catastrófica no processamento do modelo {identifier}: {e}")
        finally:
            # 🔥 LIMPEZA DE DISCO CRUCIAL: Deleta os pesos GGUF de 8GB para evitar estouro de armazenamento
            if local_path and os.path.exists(local_path):
                print(f"🧹 Liberando espaço em disco: Removendo cache do arquivo {filename}...")
                try:
                    os.remove(local_path)
                except OSError:
                    pass
            time.sleep(5)

    with open(tmp_model_file, "w") as f:
        f.write("-")
        
    generate_global_leaderboard(models_root_dir)

if __name__ == "__main__":
    main()