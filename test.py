import sys
import os
from pprint import pprint

# Garante que o Python reconheça a pasta raiz do seu projeto para importar o in_container
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Importa a sua função
from in_container.utils import get_best_gguf_models

def main():
    print("==================================================")
    print(" 🔍 INICIANDO TESTE DE BUSCA DE MODELOS GGUF... ")
    print("==================================================\n")
    
    try:
        # Se a sua função aceitar um limite (ex: limit=5), você pode passar aqui.
        # Caso contrário, só chama ela vazia mesmo.
        modelos =get_best_gguf_models(limit=1, author="Qwen", model_search="Qwen2.5-Coder-7B-Instruct-GGUF", max_size=9.0,
                                        modelt_filter=["gguf"],days_old=3065)
        # modelos = modelos+get_best_gguf_models(limit=50,model_search="Janus",author="unsloth",modelt_filter="gguf",max_size=11,short="lastModified")  
        # modelos = modelos+get_best_gguf_models(limit=50,model_search="Qwen3.5",author="unsloth",modelt_filter="gguf",max_size=11,short="lastModified")         
        # modelos =modelos+get_best_gguf_models(limit=50,model_search="Qwen3.5",author="bartowski",modelt_filter="gguf",max_size=11,short="lastModified")         
        # modelos =modelos+get_best_gguf_models(limit=50,model_search="code",author="bartowski",modelt_filter="gguf",max_size=7,short="lastModified")  
        # modelos =modelos+get_best_gguf_models(limit=50,model_search="Qwen",intruct_only=True,author="bartowski",modelt_filter="gguf",max_size=11,short="lastModified")  


        

        print(f"✅ Sucesso! A busca retornou {len(modelos)} modelos.\n")
        

            

    except ImportError as ie:
        print(f"💥 Erro de importação: {ie}")
        print("Dica: Verifique se existe um arquivo vazio chamado '__init__.py' dentro da pasta 'in_container'.")
    except Exception as e:
        print(f"💥 Erro inesperado ao rodar a função: {e}")

if __name__ == "__main__":
    main()