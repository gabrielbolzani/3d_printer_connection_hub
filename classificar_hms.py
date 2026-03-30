import json
import re

def classify_message(msg):
    msg_lower = msg.lower()
    
    # 5 - Crítico
    critico_kw = ['fogo', 'incêndio', 'curto-circuito', 'curto', 'fumaça', 'superaquecimento', 'muito alta', 'muito elevado', 'extintor', 'sobreaquecimento', 'queimando']
    if any(k in msg_lower for k in critico_kw):
        return 5, "Crítico"
        
    # 1 - Informativo
    info_kw = ['aquecendo', 'pronto', 'inicializando', 'secando', 'pausada pelo comando do usuário', 'pausada pelo usuário', 'concluída', 'atualização', 'atualizando', 'atualizado', 'inspecionando', 'espera', 'aguarde']
    if any(k in msg_lower for k in info_kw):
        return 1, "Informativo"

    # 3 - Médio
    medio_kw = ['entupid', 'filamento', 'carregamento', 'descarregamento', 'tampa', 'porta', 'placa de construção', 'mesa de aquecimento', 'caiu', 'caíram', 'cortador', 'preso', 'obstruíd', 'interrompida', 'pausada', 'intervenção', 'ams', 'reabastec', 'bobina', 'esgotad']
    if any(k in msg_lower for k in medio_kw):
        return 3, "Médio"

    # 2 - Baixo
    baixo_kw = ['calibração', 'offset', 'suja', 'sujo', 'limpar', 'limpe', 'tempo limite', 'desatualizado', 'inconsistente', 'câmera', 'lente', 'manutenção', 'aviso', 'lubrific', 'resíduos', 'verifique o status']
    if any(k in msg_lower for k in baixo_kw):
        return 2, "Baixo"

    # 4 - Alto
    alto_kw = ['motor', 'sensor', 'ventilador', 'ventoinha', 'comunicação', 'placa', 'memória', 'sinal', 'eixo', 'homing', 'referenciamento', 'falhou', 'falha', 'anormal', 'erro', 'defeito', 'danificad', 'inválido', 'hardware', 'desconectad', 'curto', 'rede']
    if any(k in msg_lower for k in alto_kw):
        return 4, "Alto"

    # Fallback based on certain verb commands
    if "verifique" in msg_lower or "substitua" in msg_lower or "insira" in msg_lower:
        return 3, "Médio"

    if "não" in msg_lower:
        return 4, "Alto"

    return 2, "Baixo"

def process_dict(d):
    for key, value in d.items():
        if isinstance(value, dict):
            process_dict(value)
        elif isinstance(value, list):
            crit, status = classify_message(key)
            d[key] = {
                "criticidade": crit,
                "status": status
            }

def main():
    try:
        with open("hms_pt-br.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        process_dict(data)

        with open("hms_Classificado_pt-br.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print("Arquivo hms_Classificado_pt-br.json gerado com sucesso!")
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    main()
