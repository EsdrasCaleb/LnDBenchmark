# parse_results.py
import xml.etree.ElementTree as ET
import os
import sys
import glob
from utils import parse_test_results,calculate_opencover_metrics

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