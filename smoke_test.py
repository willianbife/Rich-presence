import os
import sys

# Adiciona o diretório atual ao sys.path para importar o 'app'
sys.path.append(os.getcwd())

try:
    from app.services.ai_generator import AIGeneratorService
    from app.core.models import PresenceConfig
    
    print("--- Teste de Geração por IA ---")
    service = AIGeneratorService()
    
    # Testa a leitura da chave
    key = service._api_key()
    if key:
        print(f"Chave API detectada: {key[:10]}...")
    else:
        print("ERRO: Chave API não detectada no .env")
        sys.exit(1)

    # Tenta uma geração simples
    print("Enviando prompt de teste para Gemini...")
    config = service.generate("programando em python no estilo cyberpunk", mode="generate")
    
    print("\nResultado da IA:")
    print(f"Details: {config.details}")
    print(f"State: {config.state}")
    print(f"Mood: {config.mood}")
    print(f"Botões: {[b.label for b in config.buttons if b.label]}")
    
    if config.details != "Cyber Terminal": # Detalhe padrão do fallback
        print("\nSUCESSO: A IA respondeu corretamente!")
    else:
        print("\nAVISO: A IA usou o fallback. Verifique se a chave é válida ou se há conexão.")

except Exception as e:
    print(f"\nERRO DURANTE O TESTE: {e}")
    import traceback
    traceback.print_exc()
