"""
Módulo de Avaliação e Cálculo de Pontuação por Baterias de Testes.

Regra de Negócio (Coursera/Part 1):
1. Cada exercício é composto por uma ou mais Baterias de Testes (blocos).
2. Cada bateria possui um peso pré-estabelecido (ex: 0.8, 0.2).
3. Regra Tudo-ou-Nada por Bateria:
   - Para que o aluno obtenha os pontos de uma bateria, ele DEVE passar em TODOS os testes daquela bateria.
   - Se o aluno errar pelo menos um teste da bateria, a nota obtida naquela bateria será 0.0.
4. A nota final é a soma das pontuações obtidas nas baterias (escala 0.0 a 1.0).
"""

def extrair_lista_testes(config_exercicio):
    """
    Retorna uma lista plana com todos os testes contidos na configuração do exercício,
    preservando a informação de a qual bateria cada teste pertence.
    """
    testes_planos = []
    
    if "baterias" in config_exercicio:
        for idx_bat, bat in enumerate(config_exercicio["baterias"]):
            nome_bat = bat.get("nome", f"bateria_{idx_bat + 1}")
            peso_bat = bat.get("peso", 1.0)
            desc_bat = bat.get("descricao", f"Bateria {idx_bat + 1}")
            
            for idx_t, teste in enumerate(bat.get("testes", [])):
                t_copy = dict(teste)
                t_copy["_bateria_nome"] = nome_bat
                t_copy["_bateria_peso"] = peso_bat
                t_copy["_bateria_desc"] = desc_bat
                t_copy["_bateria_idx"] = idx_bat
                testes_planos.append(t_copy)
    elif "testes" in config_exercicio:
        for idx_t, teste in enumerate(config_exercicio["testes"]):
            t_copy = dict(teste)
            nome_bat = t_copy.get("bloco") or t_copy.get("bateria") or f"bateria_{idx_t + 1}"
            peso_bat = t_copy.get("peso_bloco") or t_copy.get("peso", 1.0)
            desc_bat = t_copy.get("descricao_bloco") or t_copy.get("descricao", f"Bateria {idx_t + 1}")
            t_copy["_bateria_nome"] = nome_bat
            t_copy["_bateria_peso"] = peso_bat
            t_copy["_bateria_desc"] = desc_bat
            t_copy["_bateria_idx"] = 0 if "bloco" not in t_copy and "bateria" not in t_copy else idx_t
            testes_planos.append(t_copy)

    return testes_planos

def calcular_nota_baterias(config_exercicio, resultados_testes):
    """
    Calcula a nota final do exercício aplicando a regra "tudo-ou-nada" por bateria.

    :param config_exercicio: dicionário de configuração do exercício (com "baterias" ou "testes").
    :param resultados_testes: lista de dicionários contendo os resultados individuais de cada teste:
           [{"caso": 1, "passou": True, "bateria_idx": 0, ...}, ...]
    :return: dict contendo a nota final (0.0 a 1.0), detalhes por bateria e lista plana de detalhes.
    """
    if "baterias" in config_exercicio:
        baterias_config = config_exercicio["baterias"]
    else:
        # Se for formato antigo (plano), agrupa por bloco/bateria se existirem
        baterias_map = {}
        for r in resultados_testes:
            b_nome = r.get("bateria_nome", r.get("descricao", "geral"))
            b_peso = r.get("bateria_peso", r.get("peso", 1.0))
            b_desc = r.get("bateria_desc", b_nome)
            if b_nome not in baterias_map:
                baterias_map[b_nome] = {
                    "nome": b_nome,
                    "descricao": b_desc,
                    "peso": b_peso,
                    "testes": []
                }
        baterias_config = list(baterias_map.values())

    # Prepara estruturas para avaliação das baterias
    baterias_resultado = []
    soma_pesos_totais = 0.0
    nota_acumulada = 0.0

    # Indexa resultados dos testes
    for idx_bat, bat in enumerate(baterias_config):
        nome_bat = bat.get("nome", f"bateria_{idx_bat + 1}")
        peso_bat = bat.get("peso", 0.0)
        desc_bat = bat.get("descricao", nome_bat)
        
        # Filtra os resultados de teste pertencentes a esta bateria
        testes_da_bateria = [
            r for r in resultados_testes 
            if r.get("bateria_idx") == idx_bat or r.get("bateria_nome") == nome_bat
        ]
        
        # Se não encontrou por idx/nome (ex: formato antigo sem filtro), usa correspondência por caso de teste
        if not testes_da_bateria and idx_bat < len(resultados_testes):
            testes_da_bateria = [resultados_testes[idx_bat]]

        # Regra Tudo-ou-Nada: Todos os testes da bateria devem passar
        todos_passaram = len(testes_da_bateria) > 0 and all(r.get("passou", False) for r in testes_da_bateria)
        nota_bateria = peso_bat if todos_passaram else 0.0

        soma_pesos_totais += peso_bat
        nota_acumulada += nota_bateria

        baterias_resultado.append({
            "nome": nome_bat,
            "descricao": desc_bat,
            "peso": peso_bat,
            "passou": todos_passaram,
            "nota_obtida": round(nota_bateria, 4),
            "testes": testes_da_bateria
        })

    # Normalização da nota final entre 0.0 e 1.0
    if soma_pesos_totais > 1.0:
        nota_final = round(nota_acumulada / soma_pesos_totais, 4)
    else:
        nota_final = round(nota_acumulada, 4)

    # Garante limite [0.0, 1.0]
    nota_final = max(0.0, min(1.0, nota_final))

    return {
        "sucesso": True,
        "nota": nota_final,
        "baterias": baterias_resultado,
        "detalhes": resultados_testes
    }