# parse_results.py
import xml.etree.ElementTree as ET
import os
import sys

def parse_unity_report(xml_path, mode_name):
    if not os.path.exists(xml_path):
        print(f"❌ Erro: Relatório {mode_name} não foi encontrado em {xml_path}")
        return False
    
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        total = int(root.get('total', 0))
        passed = int(root.get('passed', 0))
        failed = int(root.get('failed', 0))
        skipped = int(root.get('skipped', 0))
        duration = root.get('duration', '0')
        
        print(f"\n📢 --- RESULTADOS: {mode_name.upper()} ---")
        print(f"⏱️  Duração: {duration} segundos")
        print(f"✅ Passaram:    {passed}")
        print(f"❌ Falharam:    {failed}")
        if skipped > 0:
            print(f"⚠️  Ignorados:   {skipped}")
        print(f"🔢 Total:       {total}")
        
        return failed == 0
            
    except Exception as e:
        print(f"❌ Falha crítica ao ler o XML de {mode_name}: {e}")
        return False

if __name__ == "__main__":
    # Aceita o diretório dos artefatos como argumento ou usa o padrão /app/artifacts
    artifacts_dir = sys.argv[1] if len(sys.argv) > 1 else "/app/artifacts"
    
    print("="*50)
    edit_ok = parse_unity_report(os.path.join(artifacts_dir, "editmode-results.xml"), "EditMode")
    play_ok = parse_unity_report(os.path.join(artifacts_dir, "playmode-results.xml"), "PlayMode")
    print("="*50)

    if edit_ok and play_ok:
        print("\n🎉 [SUCESSO] Todos os testes do Lost Crypt passaram com sucesso!")
        sys.exit(0)
    else:
        print("\n🔴 [ALERTA] O pipeline terminou, mas houve falhas nos testes.")
        sys.exit(1)