# 🎮 Pipeline de Benchmark: Unity + vLLM no NPAD/UFRN

Este repositório contém a infraestrutura para rodar testes automatizados da Unity integrados ao vLLM utilizando o gerenciador de jobs SLURM e automação via Crontab no supercomputador da UFRN.

## 🏗️ Arquitetura de Armazenamento Inteligente

Para respeitar as cotas de disco do supercomputador, o projeto é dividido em duas áreas:
* **`$HOME` (Persistente):** Armazena os códigos-fonte, projeto Unity, scripts de gerenciamento, variáveis de ambiente (`.env`) e os artefatos/logs gerados (`unity_artifacts`).
* **`~/scratch` (Volátil/Rápido):** Armazena estritamente a imagem do container (`unity-vllm-bench.sif`) e os caches pesados de download do Singularity/Hugging Face.

---

## 🚀 Guia de Uso: Como Compilar e Enviar o Container

> **⚠️ ATENÇÃO:** O supercomputador NPAD bloqueia o uso da flag `--fakeroot`. Por motivos de segurança, **o build do container DEVE ser feito na sua máquina local** e o arquivo final transferido para o cluster.

### Passo 1: Compilar o Container na sua Máquina Local
No seu computador pessoal (Linux ou WSL no Windows), navegue até a pasta onde está o arquivo `unity-vllm.def` e execute o comando de compilação:

```bash
sudo singularity build unity-vllm-bench.sif unity-vllm.def

```

*Nota: Se a sua máquina local for um Mac com chip Apple M1/M2/M3/M4, não faça o build local, pois a arquitetura gerada será incompatível (ARM64 vs x86_64 do cluster).*

### Passo 2: Transferir o arquivo `.sif` para o Scratch do NPAD

Envie o arquivo consolidado direto para a sua pasta de alta performance (`scratch`) no supercomputador utilizando `scp`:

```bash
scp unity-vllm-bench.sif seu_usuario@hpc.npad.ufrn.br:~/scratch/

```

### Passo 3: Configurar os Scripts na sua HOME

Certifique-se de que os seguintes arquivos estão na sua pasta de usuário (`~`) no cluster e possuem permissão de execução:

* `run_benchmark.sbatch` (Script de submissão do SLURM)
* `cron_manager.sh` (O orquestrador inteligente do Cron)

Para garantir as permissões, rode no terminal do NPAD:

```bash
chmod +x ~/cron_manager.sh

```

### Passo 4: Ativar a Automação via Crontab

Para que o sistema verifique a cada minuto se há GPUs livres no cluster sem que você precise monitorar manualmente, configure a `crontab` do servidor de login do NPAD:

1. Abra o editor do cron:
```bash
crontab -e

```


2. Adicione a linha abaixo ao final do arquivo (ajustando o seu usuário):
```cron
* * * * * /bin/bash /home/SEU_USUARIO/cron_manager.sh >> /home/SEU_USUARIO/unity_artifacts/cron_debug.log 2>&1

```



---

## 📊 Funcionamento do Orquestrador (`cron_manager.sh`)

O script que roda em background a cada minuto segue uma lógica restrita para não desperdiçar seus créditos e não te deixar travado na fila:

1. **Verificação de Atividade:** Se o seu job já estiver rodando ou aguardando na fila do SLURM, ele encerra silenciosamente.
2. **Filtro de Saúde das GPUs:** Ele varre todas as partições que começam com `gpu` buscando nós que estejam estritamente em estado **`idle`** (100% livres) ou **`mix`** (parcialmente livres).
3. **Fila Inteligente:** Se todas as GPUs do supercomputador estiverem em estado `alloc` (totalmente ocupadas) ou `down` (em manutenção), **o script não envia nada** e espera o próximo minuto para evitar que seu job fique eternamente preso em uma fila travada.

---

## 🛑 Como Controlar o Fluxo (Pausar / Parar)

Você não precisa desconfigurar a `crontab` para pausar os testes. O sistema lê arquivos "flag" na sua pasta de resultados:

* **Pausar/Parar novos envios:**
```bash
echo "STOP" > ~/npad_artifacts/manager_status.txt

```


*(O cron irá ignorar novos envios até que o arquivo seja removido ou alterado para `RUNNING`).*
* **Interromper um Job que já está rodando agora:**
```bash
scancel -u seu_usuario

```


* **Fim Automático:** Quando o script Python (`orchestrator.py`) processar todos os modelos disponíveis no Hugging Face, ele gerará automaticamente o arquivo `NO_MORE_MODELS.flag`, fazendo com que o orquestrador encerre o ciclo de forma definitiva.

