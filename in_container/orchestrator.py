import os
import sys
import time
import argparse
import subprocess
import requests
import shutil
import pandas as pd
from huggingface_hub import hf_hub_download
import psutil
import pynvml
import csv
import threading
from utils import kill_zombie_servers, ResourceMonitor, parse_test_results, clear_leftover_tests, move_generated_tests,parse_unity_coverage_detailed,get_best_gguf_models
import os
import pandas as pd
import atexit
import signal
from multiprocessing import Process, Queue


def generate_global_leaderboard(models_root_dir, backend_name):
    """Cria o ranking unificado de todos os modelos processados, incluindo métricas de tempo e correções."""
    print(f"🏆 Compilando Tabela do Leaderboard Global ({backend_name.upper()})...")
    all_reports = []

    if not os.path.exists(models_root_dir):
        print("⚠️ Diretório raiz de modelos não encontrado.")
        return

    for folder in os.listdir(models_root_dir):
        folder_path = os.path.join(models_root_dir, folder)
        if not os.path.isdir(folder_path):
            continue

        csv_coverage_path = os.path.join(folder_path, "coverage_report.csv")
        csv_generation_path = os.path.join(folder_path, "testGeneration.csv")

        if os.path.exists(csv_coverage_path):
            try:
                # 1. Ler o relatório de cobertura padrão
                df_coverage = pd.read_csv(csv_coverage_path)

                # Valores padrão caso o arquivo de geração não exista ou esteja vazio
                total_gen_time_ms = 0
                avg_corrections_success = 0.0

                # 2. Processar o arquivo de geração de testes (testGeneration.csv)
                if os.path.exists(csv_generation_path):
                    try:
                        df_gen = pd.read_csv(csv_generation_path)
                        # Remove possíveis espaços em branco dos nomes das colunas
                        df_gen.columns = df_gen.columns.str.strip()

                        # Garantir tipos numéricos para evitar quebras
                        if 'TimeToGenerate(ms)' in df_gen.columns:
                            df_gen['TimeToGenerate(ms)'] = pd.to_numeric(df_gen['TimeToGenerate(ms)'],
                                                                         errors='coerce').fillna(0)
                            total_gen_time_ms = df_gen['TimeToGenerate(ms)'].sum()

                        if 'NumberOfCorrections' in df_gen.columns and 'Status' in df_gen.columns:
                            df_gen['NumberOfCorrections'] = pd.to_numeric(df_gen['NumberOfCorrections'],
                                                                          errors='coerce').fillna(0)

                            # Filtro defensivo aceitando 'SUCCESS' ou 'SUCESS' (com um C, como gerado pelo C#)
                            success_mask = df_gen['Status'].astype(str).str.upper().str.strip().isin(
                                ['SUCCESS', 'SUCESS'])
                            df_success = df_gen[success_mask]

                            if not df_success.empty:
                                avg_corrections_success = df_success['NumberOfCorrections'].mean()

                    except Exception as e:
                        print(f"⚠️ Alerta ao processar tempos/correções para {folder}: {e}")

                # 3. Injetar as novas colunas calculadas no DataFrame de cobertura deste modelo
                df_coverage['total_gen_time(s)'] = round(total_gen_time_ms / 1000.0,
                                                         2)  # Convertido para segundos para melhor leitura
                df_coverage['avg_corrections_success'] = round(avg_corrections_success, 2)

                all_reports.append(df_coverage)

            except Exception as e:
                print(f"⚠️ Erro ao ler coverage_report para {folder}: {e}")

    if all_reports:
        leaderboard_df = pd.concat(all_reports, ignore_index=True)

        # 1. Garante tipagem numérica de todas as colunas relevantes
        numeric_cols = [
            "editmodetestpassing", "playmodetestspassing", "coveredlines", "total_gen_time(s)"
        ]
        for col in numeric_cols:
            if col in leaderboard_df.columns:
                leaderboard_df[col] = pd.to_numeric(leaderboard_df[col], errors='coerce').fillna(0)

        # 2. Cria métricas auxiliares para ranqueamento justo
        # Trava: Exige pelo menos 1 teste em Edit E 1 teste em Play
        leaderboard_df["passes_both_modes"] = (
                (leaderboard_df["editmodetestpassing"] > 0) &
                (leaderboard_df["playmodetestspassing"] > 0)
        )

        # Total absoluto de testes passando (Edit + Play)
        leaderboard_df["total_tests_passing"] = (
                leaderboard_df["editmodetestpassing"] + leaderboard_df["playmodetestspassing"]
        )

        # Equilibrio: Pega o menor valor entre Edit e Play para priorizar modelos consistentes
        leaderboard_df["min_tests_passing"] = leaderboard_df[
            ["editmodetestpassing", "playmodetestspassing"]
        ].min(axis=1)

        # 3. Regras de Ordenação Hierárquica
        sort_cols = [
            "passes_both_modes",  # 1º: Passou nos dois modos? (True vem antes de False)
            "total_tests_passing",  # 2º: Maior soma total de testes aprovados
            "min_tests_passing",  # 3º: Maior equilíbrio entre edit/play
            "coveredlines",  # 4º: Maior cobertura de linhas
            "total_gen_time(s)"  # 5º: Menor tempo total de geração (desempate)
        ]

        ascending_rules = [False, False, False, False, True]

        # Filtra apenas colunas existentes no DataFrame
        valid_sort = []
        valid_asc = []
        for col, asc in zip(sort_cols, ascending_rules):
            if col in leaderboard_df.columns:
                valid_sort.append(col)
                valid_asc.append(asc)

        # Aplica a ordenação
        leaderboard_df = leaderboard_df.sort_values(by=valid_sort, ascending=valid_asc)

        # Limpa as colunas auxiliares para manter a estrutura original do relatório
        leaderboard_df = leaderboard_df.drop(
            columns=["passes_both_modes", "total_tests_passing", "min_tests_passing"],
            errors="ignore"
        )

        # Salva o arquivo unificado final em disco
        output_path = "/app/artifacts/GLOBAL_LEADERBOARD.csv"
        leaderboard_df.to_csv(output_path, index=False)

        print(f"\n👑 RANKING FINAL DE QUALIDADE E PERFORMANCE ({backend_name.upper()}):")
        print(leaderboard_df.to_string(index=False))

def download_worker(queue, target, scratch_download_dir):
    try:
        path = hf_hub_download(
            repo_id=target["repo_id"],
            filename=target["filename"],
            token=os.environ.get("HF_TOKEN"),
            local_dir=scratch_download_dir,
            local_dir_use_symlinks=False,
            resume_download=True,
        )
        queue.put(("ok", path))
    except Exception as e:
        queue.put(("error", str(e)))

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
    csv_path = os.path.join(model_dir, "testGeneration.csv")
    if os.path.exists(csv_path):
        print(f"🧹 [Limpeza] Removendo arquivo de resultados anterior: {csv_path}")
        try:
            os.remove(csv_path)
        except Exception as e:
            print(f"⚠️ [Aviso] Não foi possível apagar o CSV antigo: {e}")

    print(f"🛠️ [Unity] Executando geração de casos de teste via {backend_name.upper()}...")
    monitor = ResourceMonitor(model_name=model_safe_name, output_file="/app/artifacts/performance_report.csv")

    print(f"🛠️ [Unity] Iniciando geração e monitoramento: {model_safe_name}")
    monitor.start()

    # 1. Extrai os argumentos para uma variável estruturada
    cmd_args = [
        "/opt/Unity/Unity", "-projectPath", project_path, "-batchmode", "-nographics",
        "-executeMethod", "LaundryNDishes.CLI.LndCommandLineInterface.GenerateTestsFolder",
        "-folder", script_path, "-csv", f"{model_dir}/testGeneration.csv",
        "-no-licensing",
        "-disable-assembly-updater",
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


    test_list_path = os.path.join(model_dir, "testList.csv")

    subprocess.run([
        "/opt/Unity/Unity", "-projectPath", project_path, "-batchmode", "-nographics",
        "-executeMethod", "LaundryNDishes.CLI.LndCommandLineInterface.ExportTestReport",
        "-no-licensing",
       "-disable-assembly-updater",
        "-csv", test_list_path,
        "-logFile", f"{model_dir}/export-cli-log.txt"
    ], check=False)

    # Valida se o CSV foi gerado e se possui dados além do cabeçalho
    if os.path.exists(test_list_path):
        try:
            test_df = pd.read_csv(test_list_path)
            if test_df.empty:
                print(f"🛑 [Unity] O arquivo {test_list_path} contém apenas o header. Parando o pipeline aqui.")
                move_generated_tests("PLAYTEST_FOLDER", "Play_Test", model_dir)
                move_generated_tests("EDITORTEST_FOLDER", "EditorTests", model_dir)
                return False
        except Exception as e:
            print(f"⚠️ Erro ao ler {test_list_path}: {e}")
            return False
    else:
        print(f"❌ Erro Crítico: {test_list_path} não foi gerado pela Unity.")
        return False



    print("🎮 [Unity] Executando EditMode Tests + Code Coverage...")
    subprocess.run([
        "/opt/Unity/Unity", "-projectPath", project_path, "-batchmode", "-nographics",
        "-testPlatform", "editmode", "-runTests", "-debugCodeOptimization", "-enableCodeCoverage",
        "-coverageResultsPath", coverage_dir,
        "-coverageOptions", f"generateAdditionalMetrics;assemblyFilters:+{asm_name}",
        "-disable-assembly-updater",
        "-no-licensing",
        "-testResults", f"{model_dir}/editmode-results.xml",
        "-logFile", f"{model_dir}/editmode-log.txt"
    ], check=False)

    print("🎮 [Unity] Executando PlayMode Tests + Code Coverage...")
    subprocess.run([
        "/opt/Unity/Unity", "-projectPath", project_path, "-batchmode", "-nographics",
        "-testPlatform", "playmode", "-runTests", "-debugCodeOptimization", "-enableCodeCoverage",
        "-coverageResultsPath", coverage_dir,
        "-disable-assembly-updater",
        "-no-licensing",
        "-coverageOptions", f"generateAdditionalMetrics;assemblyFilters:+{asm_name}",
        "-testResults", f"{model_dir}/playmode-results.xml",
        "-logFile", f"{model_dir}/playmode-log.txt"
    ], check=False)

    print("📊 [Unity] Consolidando Relatório HTML Final...")
    subprocess.run([
        "/opt/Unity/Unity", "-projectPath", project_path, "-batchmode", "-nographics",
        "-debugCodeOptimization", "-enableCodeCoverage", "-coverageResultsPath", coverage_dir,
        "-disable-assembly-updater",
        "-no-licensing",
        "-coverageOptions", f"generateHtmlReport;generateBadgeReport;assemblyFilters:+{asm_name}",
        "-quit", "-logFile", f"{model_dir}/coverage-report-log.txt"
    ], check=False)

    print("📝 [Unity] Exportando Lista de Métricas de Sucesso...")
    subprocess.run([
        "/opt/Unity/Unity", "-projectPath", project_path, "-batchmode", "-nographics",
        "-executeMethod", "LaundryNDishes.CLI.LndCommandLineInterface.ExportTestReport",
        "-disable-assembly-updater",
        "-no-licensing",
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


def run_llamacpp(local_model_path, identifier):
    kill_zombie_servers("58291")
    """Inicia o servidor binário C++ nativo do Llama.cpp."""
    has_gpu = os.environ.get("HAS_GPU", "false").lower() == "true"

    cmd = [
        "llama-server",
        "-m", local_model_path,
        "--port", "58291",
        "-c", "2048",
        "--alias", "vllmModel",
        "--context-shift",
        "-np", "1",
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
    session = requests.Session()

    for i in range(max_retries):
        if process.poll() is not None:
            print(f"❌ O Llama-Server crashou de imediato. Detalhes salvos em: {log_file_path}")
            process.wait()
            log_file.close()
            return None

        try:
            response = session.post(warmup_url, json=payload, timeout=60)
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
    os.environ["HF_HOME"] = "/app/scratch_models/.cache"
    os.environ["HUGGINGFACE_HUB_CACHE"] = "/app/scratch_models/.cache/hub"
    os.environ["HF_HUB_CACHE"] = "/app/scratch_models/.cache/hub"
    os.makedirs("/app/scratch_models/.cache/hub", exist_ok=True)
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
    # 📂 Nova pasta para armazenar os modelos que falharam no pipeline
    models_halsucess_dir = os.path.join(artifacts_dir, "models_halsucess")

    # Garante que as pastas de destino existam
    os.makedirs(models_root_dir, exist_ok=True)
    os.makedirs(models_halsucess_dir, exist_ok=True)

    tmp_model_file = "/tmp/current_active_model"
    blacklist_path = os.path.join(artifacts_dir, "modelblacklist.txt")
    completed_path = os.path.join(artifacts_dir, "completed_models.txt")

    completed_models = set()
    if os.path.exists(completed_path):
        with open(completed_path, "r") as f:
            completed_models = {line.strip() for line in f if line.strip()}
        print(f"💾 Histórico carregado: {len(completed_models)} modelos registrados anteriormente.")
    os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "60"  # Tempo em segundos

    os.environ["HF_HUB_ETAG_TIMEOUT"] = "60"  # Tempo em segundos
    print("🦙 MODO SELECIONADO: PIPELINE LLAMA.CPP (Modelos GGUF compactos)")
    has_gpu = os.environ.get("HAS_GPU", "false").lower() == "true"
    if has_gpu:
        # get_best_gguf_models(limit=0,model_search="code",modelt_filter="gguf",max_size=4,oder_size=False) 
        # get_best_gguf_models(limit=7,model_search="code",modelt_filter="gguf",max_size=12,oder_size=False)
        # models_to_test = get_best_gguf_models(limit=0, completed_models=completed_models, days_old=999,
        #                                       model_search="unity", modelt_filter=["gguf"], max_size=4.1)    
        # modelos =get_best_gguf_models(limit=1,author="unsloth",modelt_filter="gguf")
        # modelos = modelos + get_best_gguf_models(limit=10, author="unsloth",
        #                                          modelt_filter="gguf", short="lastModified")
        # modelos = modelos + get_best_gguf_models(limit=50, author="bartowski",
        #                                          modelt_filter="gguf", short="lastModified")
        #models_to_test =get_best_gguf_models(limit=200,author="mradermacher",modelt_filter="gguf",max_size=2, short="lastModified")
        models_to_test = get_best_gguf_models(limit=200, author="bartowski", modelt_filter="gguf", max_size=2,
                                              short="lastModified")
    else:
        models_to_test = get_best_gguf_models(limit=1, completed_models=completed_models,  max_size=1)


    if not models_to_test:
        print(f"🏁 [CONCLUÍDO] Nenhum modelo restante para processar com o backend {args.backend.upper()}!")
        flag_path = os.path.join(artifacts_dir, "NO_MORE_MODELS.flag")
        with open(flag_path, "w") as f:
            f.write("FINISHED")
        generate_global_leaderboard(models_root_dir, args.backend)
        sys.exit(0)

    for target in models_to_test:
        model_identifier = target["identifier"]
        model_safe = model_identifier.replace("/", "_").replace(".", "_")

        if model_identifier in completed_models:
            continue

        local_path = None
        engine_process = None

        try:
            print(f"\n📥 [Llama.cpp] Baixando arquivo GGUF alvo para o SCRATCH: {target['filename']}...")

            # 🎯 Aponta para o caminho que mapeamos no Singularity (--bind)
            scratch_download_dir = "/app/scratch_models"

            MAX_RETRIES = 5
            TIMEOUT = 3600  # 1 hora

            local_path = None

            for tentativa in range(1, MAX_RETRIES + 1):
                print(f"Tentativa {tentativa}/{MAX_RETRIES}")

                queue = Queue()
                p = Process(
                    target=download_worker,
                    args=(queue, target, scratch_download_dir)
                )

                p.start()
                p.join(TIMEOUT)

                if p.is_alive():
                    print("⚠️ Timeout. Matando processo...")
                    p.terminate()
                    p.join()
                    continue

                if queue.empty():
                    print("⚠️ Processo terminou sem retornar resultado.")
                    continue

                status, result = queue.get()

                if status == "ok":
                    local_path = result
                    break

                print(result)

            if local_path is None:
                print("❌ Não foi possível baixar o modelo.")
                continue

            # Print de debug para você monitorar no log se ele está indo para o lugar certo
            print(f"📍 Arquivo localizado em: {local_path}")

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

                # 📦 MOVE SE FALHAR: Transfere a pasta de resultados para 'models_halsucess'
                halsucess_target_dir = os.path.join(models_halsucess_dir, model_safe)
                shutil.rmtree(halsucess_target_dir, ignore_errors=True)

                if os.path.exists(model_dir):
                    shutil.move(model_dir, halsucess_target_dir)
                    print(f"⚠️ Pipeline falhou. Pasta movida para: {halsucess_target_dir}")
            else:
                print(f"✨ {model_identifier} finalizado com sucesso! Registrando nos concluídos...")
                with open(completed_path, "a") as f:
                    f.write(f"{model_identifier}\n")

        except Exception as main_err:
            print(f"⚠️ Falha catastrófica no processamento do modelo {model_identifier}: {main_err}")
            # Garantia de segurança: se estourar erro no meio do caminho, move a pasta mesmo assim
            halsucess_target_dir = os.path.join(models_halsucess_dir, model_safe)
            if os.path.exists(os.path.join(models_root_dir, model_safe)):
                shutil.rmtree(halsucess_target_dir, ignore_errors=True)
                shutil.move(os.path.join(models_root_dir, model_safe), halsucess_target_dir)
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