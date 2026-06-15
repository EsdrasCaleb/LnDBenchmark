import os
import sys
import time
import subprocess
import requests
import shutil
import pandas as pd
from huggingface_hub import HfApi
import os
import sys
import xml.etree.ElementTree as ET

def parse_test_results(xml_path):
    """Extrai a quantidade total de testes e quantos passaram do relatório NUnit."""
    if not os.path.exists(xml_path):
        return 0, 0  # total, passed
    
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        passed = int(root.get("passed", 0))
        failed = int(root.get("failed", 0))
        total = int(root.get("total", 0))
        
        # Fallback caso os atributos globais estejam zerados mas existam nós de teste
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
            # Converte todas as tags para minúsculo para evitar problemas de case-sensitivity
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

def get_best_code_models(limit=5, completed_models=None):
    """
    Busca modelos focados em código no Hugging Face pertencentes a Big Techs/Grandes Orgs,
    garante compatibilidade nativa com vLLM, tamanho menor que 5GB e ignora a Blacklist e os já Concluídos.
    """
    # Inicializa como set vazio caso o parâmetro não seja enviado
    if completed_models is None:
        completed_models = set()

    artifacts_dir = "/app/artifacts"
    blacklist_path = os.path.join(artifacts_dir, "modelblacklist.txt")
    blacklist = set()

    # Carrega a blacklist caso o arquivo já exista
    if os.path.exists(blacklist_path):
        with open(blacklist_path, "r") as f:
            blacklist = {line.strip() for line in f if line.strip()}
        print(f"📋 Blacklist carregada com {len(blacklist)} modelos ignorados.")

    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        print("⚠️ Aviso: HF_TOKEN não encontrado no ambiente. Modelos protegidos (Llama/Gemma) serão ignorados.")

    print("🔍 Buscando modelos recomendados de grandes empresas no Hugging Face...")
    api = HfApi(token=hf_token)
    
    # Organizações autorizadas (Grandes corporações e laboratórios de IA renomados)
    BIG_TECHS = ["google", "meta-llama", "microsoft", "qwen", "deepseek-ai", "mistralai", "codellama", "salesforce", "ibm-granite"]

    # Busca modelos de geração de texto com foco em código ordenados por downloads
    available_models = api.list_models(
        filter=["code", "text-generation"],
        sort="downloads",
        full=True
    )
    
    

    filtered_models = []
    
    for model in available_models:
        
        # REGRA DE CORTE 0a: Ignora o modelo se ele estiver na Blacklist
        if model.modelId in blacklist:
            print(f"🚫 Modelo {model.modelId} ignorado (está na Blacklist).")
            continue

        # REGRA DE CORTE 0b: Ignora o modelo se ele já foi CONCLUÍDO com sucesso
        if model.modelId in completed_models:
            print(f"⏩ Modelo {model.modelId} ignorado (já foi Concluído anteriormente).")
            continue

        # 1. Filtro de Empresa: O modelo precisa pertencer à lista de Big Techs
        parts = model.modelId.split("/")
        if len(parts) < 2:
            continue
        org = parts[0].lower()
        if org not in BIG_TECHS:
            continue
            
        # 2. Filtro de Compatibilidade vLLM: Ignorar formatos não suportados nativamente (GGUF, GGML, bitsandbytes)
        model_id_lower = model.modelId.lower()
        if any(bad in model_id_lower for bad in ["gguf", "ggml", "bnb", "quantized"]):
            continue
            
        # [MÁGICA AQUI] Fazemos a requisição detalhada apenas para os modelos que passaram nos filtros acima!
        try:
            detailed_info = api.model_info(model.modelId, files_metadata=True)
        except Exception as e:
            print(f"⚠️ Falha ao buscar detalhes de {model.modelId}: {e}")
            continue

        # 3. Filtro de Tamanho: Calcular tamanho real somando arquivos válidos
        total_size_bytes = 0
        has_weights = False
        
        # Agora estamos iterando nos siblings do 'detailed_info' que com certeza tem os tamanhos
        for sibling in detailed_info.siblings:
            if sibling.rfilename.endswith(('.safetensors', '.bin', '.pt')):
                has_weights = True
                if hasattr(sibling, 'size') and sibling.size is not None:
                    total_size_bytes += sibling.size
        
        size_gb = total_size_bytes / (1024 ** 3)
        
        # Fallback de estimativa por quantidade de parâmetros se o tamanho do arquivo estiver oculto
        is_small_by_params = False
        is_awq_gptq = any(q in model_id_lower for q in ["awq", "gptq", "4bit"]) 
        
        for tag in detailed_info.tags:
            if tag.startswith("params:"):
                try:
                    params = float(tag.replace("params:", "").replace("B", "").strip())
                    if params <= 3.2 or (params <= 7.5 and is_awq_gptq):
                        is_small_by_params = True
                except ValueError:
                    pass

        # Critério final de validação (< 7.8 GB de arquivos ou parâmetros baixos)
        if has_weights and ((0 < size_gb <= 7.8) or (total_size_bytes == 0 and is_small_by_params)):
            filtered_models.append(model.modelId)
            print(f"✅ Identificado: {model.modelId} [Empresa: {org.upper()}] (~{size_gb:.2f} GB)")
            if len(filtered_models) >= limit:
                break
        else:
            print(f"❌ Rejeitado (Muito grande): {model.modelId} [Empresa: {org.upper()}] (~{size_gb:.2f} GB)")
                
    return filtered_models

def run_vllm(model_name):
    """Inicia o servidor vLLM lendo a flag de hardware do Docker e capturando logs."""
    has_gpu = os.environ.get("HAS_GPU", "false").lower() == "true"
    
    # 💡 ADICIONAMOS O '-u' PARA DESATIVAR O BUFFER E GRAVAR O LOG IMEDIATAMENTE
    cmd = [
        "python3", "-u", "-m", "vllm.entrypoints.openai.api_server",
        "--model", model_name,
        "--port", "11434",
        "--max-model-len", "2048",
        "--served-model-name", "vllm-model"
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
    
    print(f"⏳ Aguardando pesos... (Log em tempo real salvo em: {log_file_path})")
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
            
            # 💡 AGORA IMPRIMIMOS O CÓDIGO DE MORTE EXATO DO PROCESSO
            print(f"❌ Erro crítico: O vLLM crashou. Código de saída: {exit_code}")
            
            if exit_code == -9 or exit_code == 137:
                print("⚠️ DIAGNÓSTICO: O sistema operacional MATOU o processo por FALTA DE MEMÓRIA RAM (OOM Killer).")
            elif exit_code == -11 or exit_code == 139:
                print("⚠️ DIAGNÓSTICO: Segmentation Fault! O vLLM tentou acessar instruções de GPU que não existem na CPU.")
            
            print(f"📝 --- ÚLTIMAS LINHAS DO LOG DO VLLM ---")
            os.system(f"tail -n 15 {log_file_path}")
            print(f"----------------------------------------")
            return None
            
        if time.time() - start_time > 600:
            print("❌ Timeout: Download ou carregamento demorou demais.")
            process.terminate()
            return None
        time.sleep(5)

def move_generated_tests(env_var_name, destination_subfolder, model_dir):
    """Auxiliar para mover arquivos gerados liberando espaço mantendo os .asmdef."""
    folder_path = os.environ.get(env_var_name)
    if not folder_path:
        print(f"⚠️ Variável {env_var_name} não definida nas variáveis de ambiente. Movimentação pulada.")
        return

    # Garante caminho absoluto baseado na raiz do projeto caso venha relativo
    if not os.path.isabs(folder_path):
        folder_path = os.path.join("/app/project", folder_path)

    if not os.path.exists(folder_path):
        print(f"⚠️ Pasta mapeada em {env_var_name} ({folder_path}) não existe localmente.")
        return

    target_dir = os.path.join(model_dir, destination_subfolder)
    os.makedirs(target_dir, exist_ok=True)

    print(f"📦 Movendo arquivos de: {folder_path} -> {target_dir}")
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        
        # Ignora arquivos de definição de Assembly (tratando .asmdef e typos do usuário .asmdev)
        if item.endswith(".asmdef") or item.endswith(".asmdef.meta") or \
           item.endswith(".asmdev") or item.endswith(".asmdev.meta"):
            continue
            
        try:
            shutil.move(item_path, os.path.join(target_dir, item))
        except Exception as e:
            print(f"⚠️ Falha ao mover {item}: {e}")

def run_unity_pipeline(model_safe_name, model_dir):
    """Dispara a bateria de testes da Unity dentro do container."""
    project_path = "/app/project"
    script_path = os.environ.get("SCRIPT_PATH", "Assets/Scripts")
    asm_name = os.environ.get("UNITY_ASM_NAME", "Assembly-CSharp")
    
    
    # 1. Garante que a pasta de cobertura exista e comece limpa
    coverage_dir = os.path.join(model_dir, "coverage")
    shutil.rmtree(coverage_dir, ignore_errors=True)
    os.makedirs(coverage_dir, exist_ok=True)
    
    print("🛠️  [Unity] Executando geração de casos de teste via LLM...")
    subprocess.run([
        "/opt/Unity/Unity", "-projectPath", project_path, "-batchmode", "-nographics",
        "-executeMethod", "LaundryNDishes.CLI.LndCommandLineInterface.GenerateTestsFolder",
        "-folder", script_path, "-csv", f"{model_dir}/testGeneration.csv",
        "-logFile", f"{model_dir}/generation-cli-log.txt"
    ], check=False)

    # 2. Validação rigorosa do CSV de Geração
    gen_csv_path = os.path.join(model_dir, "testGeneration.csv")
    has_success = False

    if os.path.exists(gen_csv_path):
        try:
            gen_df = pd.read_csv(gen_csv_path)
            if "Status" in gen_df.columns:
                statuses = gen_df["Status"].astype(str).str.upper().str.strip()
                has_success = statuses.isin(["SUCESS", "SUCCESS"]).any()
            else:
                print(f"⚠️ Coluna 'Status' não encontrada em {gen_csv_path}.")
                has_success = False
        except Exception as e:
            print(f"⚠️ Erro ao ler {gen_csv_path} para análise de blacklist: {e}")
            has_success = False
    else:
        print(f"❌ Erro Crítico: {gen_csv_path} não foi gerado. O processo de geração falhou por completo.")
        has_success = False

    # Se NÃO teve sucesso (ou o arquivo não existe), limpa a casa ANTES de sair
    if not has_success:
        print(f"❌ {model_safe_name} não gerou nenhum caso válido. Movendo resíduos e aplicando Blacklist...")
        move_generated_tests("PLAYTEST_FOLDER", "Play_Test", model_dir)
        move_generated_tests("EDITORTEST_FOLDER", "EditorTests", model_dir)
        return False

    # 3. Execução dos Testes (Só roda se o modelo passou no critério acima)
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

    # REQUISITO 1: Move os arquivos corretos ao fim do pipeline com sucesso
    move_generated_tests("PLAYTEST_FOLDER", "Play_Test", model_dir)
    move_generated_tests("EDITORTEST_FOLDER", "EditorTests", model_dir)

    # 4. Processamento dos Resultados XML
    editmode_xml = os.path.join(model_dir, "editmode-results.xml")
    playmode_xml = os.path.join(model_dir, "playmode-results.xml")
    
    # Procura o Summary.xml na raiz ou na subpasta 'Report' gerada pela Unity
    combined_summary_xml = os.path.join(coverage_dir, "Summary.xml")
    if not os.path.exists(combined_summary_xml):
        combined_summary_xml = os.path.join(coverage_dir, "Report", "Summary.xml")
    
    em_total, em_pass = parse_test_results(editmode_xml)
    pm_total, pm_pass = parse_test_results(playmode_xml)
    cov = parse_unity_coverage_detailed(combined_summary_xml)
    
    # Headers corrigidos (removidos os erros de digitação para manter o padrão)
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
        numeric_cols = ["editmodetestpassing", "palymodetestspassing", "coveredlines"]
        for col in numeric_cols:
            if col in leaderboard_df.columns:
                leaderboard_df[col] = pd.to_numeric(leaderboard_df[col], errors='coerce').fillna(0)
                
        # Ordena pelo maior número de testes passando e maior quantidade de linhas cobertas
        leaderboard_df = leaderboard_df.sort_values(
            by=["palymodetestspassing", "coveredlines"], 
            ascending=[False, False]
        )
        
        output_path = "/app/artifacts/GLOBAL_LEADERBOARD.csv"
        leaderboard_df.to_csv(output_path, index=False)
        print("\n👑 RANKING FINAL DE QUALIDADE DE CÓDIGO:")
        print(leaderboard_df.to_string(index=False))

def main():
    artifacts_dir = "/app/artifacts"
    models_root_dir = os.path.join(artifacts_dir, "models")
    tmp_model_file = "/tmp/current_active_model"
    blacklist_path = os.path.join(artifacts_dir, "modelblacklist.txt")
    completed_path = os.path.join(artifacts_dir, "completed_models.txt")
    
    # 1. Carrega o histórico de modelos já concluídos com sucesso para pular reprocessamento
    completed_models = set()
    if os.path.exists(completed_path):
        with open(completed_path, "r") as f:
            completed_models = {line.strip() for line in f if line.strip()}
        print(f"💾 Histórico carregado: {len(completed_models)} modelos já foram concluídos anteriormente.")

    # Executa a busca dinâmica e inteligente
    models_to_test = get_best_code_models(limit=5, completed_models=completed_models)
    
    if not models_to_test:
        print("🏁 [CONCLUÍDO] Nenhum modelo restante para processar na lista do Hugging Face!")
        # Cria um arquivo de texto indicando fim absoluto fora do container
        flag_path = os.path.join(artifacts_dir, "NO_MORE_MODELS.flag")
        with open(flag_path, "w") as f:
            f.write("FINISHED")
        sys.exit(0) # Sai com sucesso
    

    for model in models_to_test:
        # PONTO DE CHECAGEM: Se o modelo já foi processado com sucesso no passado, pula!
        # (Nota: a filtragem da blacklist original já acontece dentro de get_best_code_models)
        if model in completed_models:
            print(f"⏩ Modelo {model} já consta como CONCLUÍDO. Pulando...")
            continue

        model_safe = model.replace("/", "_")
        model_dir = os.path.join(models_root_dir, model_safe)
        os.makedirs(model_dir, exist_ok=True)
        
        # ATUALIZAÇÃO SINCRO: Informa ao monitor do Bash quem está rodando agora
        with open(tmp_model_file, "w") as f:
            f.write(model)
            
        vllm_process = run_vllm(model)
        if vllm_process is None:
            continue
            
        pipeline_success = False
        try:
            # Aponta para o vLLM local fingindo ser a OpenAI
            os.environ["UNITY_LLM_API_KEY"] = "fake-vllm-token" 
            
            # Executa o pipeline completo (Geração + Testes + Cobertura + CSV)
            pipeline_success = run_unity_pipeline(model_safe, model_dir)
            
            if not pipeline_success:
                print(f"❌ Adicionando {model} à Blacklist (Sem nenhum caso SUCCESS)...")
                with open(blacklist_path, "a") as f:
                    f.write(f"{model}\n")
            else:
                # SE DEU TUDO CERTO: Salva imediatamente no arquivo de concluídos
                print(f"✨ {model} finalizado com sucesso! Registrando nos concluídos...")
                with open(completed_path, "a") as f:
                    f.write(f"{model}\n")
            
        finally:
            print(f"🛑 Terminando processo vLLM do modelo {model}...")
            vllm_process.terminate()
            vllm_process.wait()
            time.sleep(5) # Delay seguro para limpeza de cache de VRAM na GPU

    # Limpa a string do monitor no fim do pipeline
    with open(tmp_model_file, "w") as f:
        f.write("-")
        
    generate_global_leaderboard(models_root_dir)

if __name__ == "__main__":
    main()