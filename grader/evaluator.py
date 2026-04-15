# Este arquivo é legado, preciso apagar
import json
import os

def avaliar_submissao(problem_id, student_output_list):
    """
    Compara as saídas do aluno com o gabarito no JSON.
    student_output_list: Lista de strings capturadas do Docker para cada caso.
    """
    json_path = os.path.join(os.path.dirname(__file__), 'entrada_teste.json')
    
    with open(json_path, 'r') as f:
        gabarito = json.load(f)
        
    if problem_id not in gabarito:
        return 0.0, "Problema não encontrado no gabarito."

    test_cases = gabarito[problem_id]['test_cases']
    nota_final = 0.0
    logs = []

    for i, case in enumerate(test_cases):
        output_aluno = student_output_list[i].strip()
        output_esperado = case['expected'].strip()
        if output_aluno == output_esperado:
            nota_final += case['weight']
            logs.append(f"Caso {i+1}: Sucesso!")
        else:
            logs.append(f"Caso {i+1}: Erro. Esperado '{output_esperado}', recebido '{output_aluno}'")

    return nota_final, "\n".join(logs)