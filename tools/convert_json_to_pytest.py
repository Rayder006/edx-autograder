import json
import os

tests_json_path = '/Users/joni/Documents/edx-autograder/tests.json'
exercises_dir = '/Users/joni/Documents/edx-autograder/exercises'

os.makedirs(exercises_dir, exist_ok=True)

with open(tests_json_path, 'r', encoding='utf-8') as f:
    exercises_data = json.load(f)

for ex_key, ex_config in exercises_data.items():
    tipo = ex_config.get("tipo", "script")
    nome_funcao = ex_config.get("nome_funcao", None)
    baterias = ex_config.get("baterias", [])
    
    file_name = f"test_{ex_key}.py"
    file_path = os.path.join(exercises_dir, file_name)
    
    lines = []
    lines.append("# -*- coding: utf-8 -*-")
    lines.append("import pytest")
    
    if tipo == "funcao" and nome_funcao:
        lines.append(f"from solution import {nome_funcao}")
    
    lines.append("")
    
    for idx_b, bat in enumerate(baterias):
        nome_bat = bat.get("nome", f"bateria_{idx_b+1}")
        peso_bat = bat.get("peso", 1.0)
        desc_bat = bat.get("descricao", nome_bat)
        testes = bat.get("testes", [])
        
        func_name = f"test_{nome_bat}"
        
        lines.append(f'@pytest.mark.bateria(nome={repr(nome_bat)}, peso={peso_bat}, descricao={repr(desc_bat)})')
        
        if tipo == "script":
            param_tuples = [(t.get("input", ""), t.get("expected", "")) for t in testes]
            lines.append(f'@pytest.mark.parametrize("entrada, esperado", {repr(param_tuples)})')
            lines.append(f"def {func_name}(script_runner, entrada, esperado):")
            lines.append('    saida = script_runner.run("solution.py", stdin=entrada)')
            lines.append('    assert script_runner.validar_saida(saida, esperado)')
        
        elif tipo == "funcao":
            param_tuples = [(t.get("args", []), t.get("expected", None)) for t in testes]
            lines.append(f'@pytest.mark.parametrize("args, esperado", {repr(param_tuples)})')
            lines.append(f"def {func_name}(args, esperado):")
            lines.append(f"    assert {nome_funcao}(*args) == esperado")
            
        lines.append("")

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

print(f"Generated {len(exercises_data)} Pytest test files in {exercises_dir}!")
