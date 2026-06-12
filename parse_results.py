# parse_results.py
import xml.etree.ElementTree as ET
import os
import sys
import glob

def parse_test_results(xml_path):
    """Lê os resultados dos testes da Unity (Passou/Falhou)"""
    if not os.path.exists(xml_path):
        return {"status": "Não Encontrado", "passed": 0, "failed": 0, "total": 0}
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        return {
            "status": "OK",
            "total": int(root.get('total', 0)),
            "passed": int(root.get('passed', 0)),
            "failed": int(root.get('failed', 0)),
            "duration": root.get('duration', '0')
        }
    except:
        return {"status": "Erro de Leitura", "passed": 0, "failed": 0, "total": 0}

def calculate_opencover_metrics(coverage_dir):
    """
    Varre os arquivos gerados pelo OpenCover da Unity para calcular 
    as porcentagens exatas de Line Coverage e Method Coverage.
    """
    search_path = os.path.join(coverage_dir, "**", "*.xml")
    xml_files = glob.glob(search_path, recursive=True)
    
    # Filtra para evitar pegar relatórios do ReportGenerator (HTML) se existirem
    opencover_files = [f for f in xml_files if "CoverageReport" not in f]

    total_sequence_points = 0
    visited_sequence_points = 0
    total_methods = 0
    visited_methods = 0

    for file in opencover_files:
        try:
            tree = ET.parse(file)
            root = tree.getroot()
            
            # Percorre todos os métodos mapeados nas classes do projeto
            for method in root.findall(".//Method"):
                # Ignora construtores gerados automaticamente ou sem pontos de sequência válidos
                if method.get("skippedDueTo") is not None:
                    continue
                
                # Coleta dados de Métodos visitados
                is_visited = method.get("visited") == "true"
                total_methods += 1
                if is_visited:
                    visited_methods += 1

                # Coleta dados de Linhas de Código (SequencePoints no OpenCover)
                for sp in method.findall(".//SequencePoint"):
                    total_sequence_points += 1
                    if int(sp.get("vc", 0)) > 0: # vc = visit count
                        visited_sequence_points += 1
        except Exception as e:
            continue

    line_pct = (visited_sequence_points / total_sequence_points * 100) if total_sequence_points > 0 else 0.0
    method_pct = (visited_methods / total_methods * 100) if total_methods > 0 else 0.0

    return {
        "line": round(line_pct, 2),
        "method": round(method_pct, 2),
        "found_files": len(opencover_files)
    }

if __name__ == "__main__":
    artifacts_dir = sys.argv[1] if len(sys.argv) > 1 else "/app/artifacts"
    
    # 1. Parsing dos resultados dos testes
    edit_tests = parse_test_results(os.path.join(artifacts_dir, "editmode-results.xml"))
    play_tests = parse_test_results(os.path.join(artifacts_dir, "playmode-results.xml"))
    
    # 2. Parsing das coberturas de código em cada contexto
    edit_coverage = calculate_opencover_metrics(os.path.join(artifacts_dir, "coverage", "editmode"))
    play_coverage = calculate_opencover_metrics(os.path.join(artifacts_dir, "coverage", "playmode"))
    combined_coverage = calculate_opencover_metrics(os.path.join(artifacts_dir, "coverage"))

    # 3. Geração do Relatório report.txt unificado
    report_path = os.path.join(artifacts_dir, "report.txt")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("==================================================\n")
        f.write("📋 RELATÓRIO FINAL DE QUALIDADE E COBERTURA DA UNITY\n")
        f.write("==================================================\n\n")
        
        f.write("🟢 1. RESULTADOS DOS TESTES\n")
        f.write("--------------------------------------------------\n")
        f.write(f"🔬 EditMode Tests: {edit_tests['status']} (Passaram: {edit_tests['passed']}/{edit_tests['total']} | Falharam: {edit_tests['failed']})\n")
        f.write(f"🎮 PlayMode Tests: {play_tests['status']} (Passaram: {play_tests['passed']}/{play_tests['total']} | Falharam: {play_tests['failed']})\n\n")
        
        f.write("📊 2. MÉTRICAS DE COBERTURA DE CÓDIGO\n")
        f.write("--------------------------------------------------\n")
        f.write("📝 Apenas EditMode:\n")
        f.write(f"  └─ Line Coverage:   {edit_coverage['line']}%\n")
        f.write(f"  └─ Method Coverage: {edit_coverage['method']}%\n\n")
        
        f.write("🕹️  Apenas PlayMode:\n")
        f.write(f"  └─ Line Coverage:   {play_coverage['line']}%\n")
        f.write(f"  └─ Method Coverage: {play_coverage['method']}%\n\n")
        
        f.write("✨ Combinada (EditMode + PlayMode):\n")
        f.write(f"  └─ Line Coverage:   {combined_coverage['line']}%\n")
        f.write(f"  └─ Method Coverage: {combined_coverage['method']}%\n")
        f.write("==================================================\n")

    # Exibe no stdout para visualização rápida no console do supercomputador
    print("\n" + open(report_path, "r").read())

    # Define o código de saída com base no sucesso geral dos testes
    if edit_tests["failed"] == 0 and play_tests["failed"] == 0 and edit_tests["status"] == "OK" and play_tests["status"] == "OK":
        print("🎉 [SUCESSO] Todos os procedimentos executados e salvos em report.txt.")
        sys.exit(0)
    else:
        print("🔴 [ALERTA] Processo concluído, mas foram encontradas falhas em alguma das etapas.")
        sys.exit(1)