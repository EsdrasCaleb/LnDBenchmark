import os
import csv
import time
import shutil
import threading
import xml.etree.ElementTree as ET
import psutil
import pynvml
from huggingface_hub import HfApi
from datetime import datetime, timedelta, timezone

# Inicializa NVML (GPU) uma vez
try:
    pynvml.nvmlInit()
except:
    pass


class ResourceMonitor:
    def __init__(self, model_name, output_file):
        self.model_name = model_name
        self.output_file = output_file
        self.running = False
        self.thread = None

    def _collect(self):
        # Coleta dados
        mem = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent()

        gpu_data = {"util": 0, "mem_used": 0, "mem_total": 0, "mem_percent": 0}
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpu_data = {
                "util": util.gpu,
                "mem_used": mem_info.used // (1024 ** 2),
                "mem_total": mem_info.total // (1024 ** 2),
                "mem_percent": (mem_info.used / mem_info.total) * 100
            }
        except:
            pass

        # Grava no CSV (Append)
        file_exists = os.path.isfile(self.output_file)
        with open(self.output_file, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "model", "ram_used_mb", "ram_total_mb", "ram_pct", "cpu_pct", "gpu_pct",
                                 "gpu_mem_used_mb", "gpu_mem_total_mb", "gpu_mem_pct"])

            writer.writerow([
                time.strftime('%Y-%m-%d %H:%M:%S'), self.model_name,
                mem.used // (1024 ** 2), mem.total // (1024 ** 2), mem.percent,
                cpu_percent, gpu_data["util"], gpu_data["mem_used"],
                gpu_data["mem_total"], round(gpu_data["mem_percent"], 2)
            ])

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run)
        self.thread.start()

    def _run(self):
        while self.running:
            self._collect()
            time.sleep(2)  # Intervalo de 2s entre coletas

    def stop(self):
        self.running = False
        self.thread.join()

def kill_unity_ghost_processes():
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and "Unity" in proc.info['name']:
                # Evita matar o orquestrador caso ele tenha Unity no nome por algum motivo
                if proc.pid != os.getpid():
                    proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

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
    kill_unity_ghost_processes()
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


def kill_zombie_servers(port="58291", kill_unity=False, project_path="/app/project"):
    """
    Limpeza cirúrgica de processos zumbis (LLM e Unity) e travas de arquivo.
    Protegido contra suicídio do próprio orquestrador Python.
    """
    print(f"🧹 [Limpeza] Iniciando faxina automatizada...")

    # Alvos específicos de cada ecossistema
    llm_targets = ["vllm", "llama-server", "server", "python"]
    unity_targets = ["unity", "licensingclient", "upm-"]

    meu_pid = os.getpid()

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            pid = proc.info['pid']
            # Anti-suicídio: Nunca deixa o orquestrador matar a si mesmo
            if pid == meu_pid:
                continue

            cmdline_list = proc.info['cmdline'] or []
            cmdline = " ".join(cmdline_list).lower()
            proc_name = (proc.info['name'] or "").lower()

            # 🛑 CASO 1: Caçar servidores de LLM travados na porta informada
            if any(t in cmdline for t in llm_targets) and str(port) in cmdline:
                print(f"💀 Matando zumbi LLM: {proc.info['name']} (PID: {pid})")
                proc.kill()  # Força bruta direta (SIGKILL) para não dar chance de travar

            # 🎮 CASO 2: Caçar instâncias órfãs da Unity e ferramentas de licença
            elif kill_unity and (any(t in proc_name for t in unity_targets) or "/opt/unity/unity" in cmdline):
                print(f"💀 Matando processo órfão da Unity: {proc.info['name']} (PID: {pid})")
                proc.kill()

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
            continue

    # 📁 CASO 3: Destruir o arquivo de trava que impede a Unity de abrir em lote (Batchmode)
    if kill_unity and project_path:
        lockfile_path = os.path.join(project_path, "Temp", "UnityLockfile")
        if os.path.exists(lockfile_path):
            try:
                print("🧹 [Limpeza] UnityLockfile antigo detectado! Removendo trava de disco...")
                os.remove(lockfile_path)
                print("🟢 Trava de disco removida com sucesso.")
            except Exception as e:
                print(f"⚠️ Alerta: Não foi possível remover o UnityLockfile: {e}")

    # Validação final da porta do LLM
    for _ in range(5):
        if os.system(f"fuser {port}/tcp >/dev/null 2>&1") != 0:
            print(f"🟢 Porta {port} livre e pronta para o próximo modelo.")
            return True
        time.sleep(1)

    return False


# =====================================================================
# 🔥 BACKEND DEPREACED: VLLM (MODELOS NATIVOS / HUGGING FACE)
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
    available_models = api.list_models(filter=["code", "text-generation"], sort="downloads", direction=-1, full=True)
    BIG_TECHS = ["google", "meta-llama", "microsoft", "qwen", "deepseek-ai", "mistralai", "codellama", "salesforce",
                 "ibm-granite"]

    filtered_models = []
    for model in available_models:
        if model.modelId in blacklist or model.modelId in completed_models:
            continue
        parts = model.modelId.split("/")
        if len(parts) < 2 or parts[0].lower() not in BIG_TECHS:
            continue

        model_id_lower = model.modelId.lower()

        # 🚫 LISTA NEGRA: Formatos incompatíveis com vLLM
        bad_formats = ["gguf", "ggml", "mlx", "coreml", "openvino", "onnx", "exl2", "tflite"]
        if any(bad in model_id_lower for bad in bad_formats):
            print("Regeitado por formato:" + model_id_lower)
            continue

        try:
            detailed_info = api.model_info(model.modelId, files_metadata=True)
        except Exception as e:
            print("Erro ao obter modelo:" + e)
            continue

        pipeline = getattr(detailed_info, 'pipeline_tag', '').lower()
        tags = [str(t).lower() for t in getattr(detailed_info, 'tags', [])]

        # 2. Relaxamento dos filtros:
        # Google e DeepSeek às vezes usam 'text-generation' e nada mais.
        is_text_gen = (pipeline == "text-generation" or "text-generation" in tags)

        # O vLLM consegue rodar modelos que não têm a tag 'transformers' explícita
        # Removido a exigência de "transformers" na tag
        if not is_text_gen:
            print("Regeitado por tag:" + model_id_lower)
            continue

        safetensors_size = 0
        bin_size = 0
        has_weights = False

        for sibling in detailed_info.siblings:
            rfile = sibling.rfilename.lower()
            if rfile.endswith('.safetensors'):
                has_weights = True
                if hasattr(sibling, 'size') and sibling.size is not None:
                    safetensors_size += sibling.size
            elif rfile.endswith(('.bin', '.pt')):
                has_weights = True
                if hasattr(sibling, 'size') and sibling.size is not None:
                    bin_size += sibling.size

        total_size_bytes = safetensors_size if safetensors_size > 0 else bin_size

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
        "--gpu-memory-utilization", "0.75",  # 🛑 REDUÇÃO AGRESSIVA: De 90% para 75%
        "--max-model-len", "2048",  # 🛑 REDUÇÃO AGRESSIVA: De 4096 para 2048
        "--dtype", "float16",  # 🛑 FORÇAR FP16: Evita conflito com bfloat16
        "--served-model-name", "vllmModel",
        "--trust-remote-code",
        "--enforce-eager",  # Mantém isso para evitar CUDA Graphs
        "--disable-custom-all-reduce"  # Mantém isso para evitar problemas de rede interna
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
    

def get_best_gguf_models(limit=5, completed_models=None,
                         intruct_only=False,days_old=365,
                         modelt_filter=["gguf", "text-generation", "code","llama.cpp"],
                         model_search="", max_size=8.0,
                         bigger_first=False,oder_size=True,author=None,short="trending_score"):
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

    um_ano_atras = datetime.now(timezone.utc) - timedelta(days=days_old)

    print(f"🔍 Buscando os melhores modelos GGUF para CÓDIGO (atualizados após {um_ano_atras.strftime('%Y-%m-%d')})...")

    available_models = api.list_models(
        filter=modelt_filter,
        search=model_search,
        sort=short,
        author=author,
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

        eh_instruct_ou_it = (
            "instruct" in model_id_lower or 
            "-i" in model_id_lower or 
            "instruct" in tags_lower or 
            "it" in tags_lower
        )
        
        if intruct_only and not eh_instruct_ou_it:
            continue

        try:
            repo_files =  list(api.list_repo_tree(model.modelId, expand=True))
        except Exception:
            continue

        valid_gguf_files = []
        for item in repo_files:
            if item.path.endswith(".gguf"):
                security_info = getattr(item, 'security', None)

                if security_info and security_info.safe is not True and security_info.status == "unsafe":
                    print(f"⚠️ Modelo bloqueado por segurança: {model.modelId} ({item.path})")
                    continue

                # Ignora fragmentos
                if any(part in item.path.lower() for part in ["split", "-of-", "part", "mmproj",'mtp','imatrix']):
                    continue
                
                size_bytes = getattr(item, 'size', 0) or 0
                size_gb = size_bytes / (1024 ** 3)

                if 0 < size_gb <= max_size:
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
    if(oder_size):
        filtered_models.sort(key=lambda x: x["size_gb"], reverse=bigger_first)
    return filtered_models