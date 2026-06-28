# Autograder Django LTI (EdX)

Este projeto é um Autograder (corretor automático) desenvolvido em Django projetado para avaliar submissões de código Python de estudantes integrando-se via protocolo **LTI 1.1** (focado na plataforma EdX).

---

## 🛠️ Como o Autograder Funciona

O sistema recebe o código do estudante enviado via requisição POST LTI 1.1 e realiza os seguintes passos:

1. **Validação Criptográfica LTI**: Valida a assinatura OAuth 1.0 (HMAC-SHA1) de forma nativa para garantir a legitimidade da requisição do EdX.
2. **Resolução do Exercício**: Identifica o ID do exercício solicitado (via parâmetro `custom_exercise_id` ou `resource_link_id`).
3. **Mapeamento de Casos de Teste**: Consulta a configuração centralizada em [tests.json](tests.json) para obter as entradas e saídas esperadas do exercício.
4. **Isolamento via Docker**:
   - Cria um diretório temporário no host com o código do aluno (`solution.py`).
   - Sobe um container Docker efêmero `python:3.13-alpine` sem acesso à rede (`network_disabled=True`), com limite de memória de `128MB` e limite de tempo de execução (timeout).
   - Executa o código e captura os resultados.
5. **Cálculo da Nota**: Retorna a nota final do aluno (de `0.0` a `1.0`) e os detalhes de sucesso/erro de cada caso de teste executado.

---

## 🏗️ Tipos de Exercícios Suportados

O Autograder suporta dois tipos principais de correção definidos no [tests.json](tests.json):

### 1. Scripts de I/O (`tipo: "script"`)
Destinado a exercícios onde o aluno interage usando `input()` e `print()` (ex: calcular médias, segundos, fatorial).
* **Execução**: O motor injeta as entradas passadas em `input` via stdin (`< /app/input.txt`) e lê a saída padrão (`stdout`).
* **Validação**: As saídas são validadas usando uma técnica de normalização robusta que:
  * Remove acentos e caracteres diacríticos.
  * Converte o texto para minúsculas.
  * Remove pontuações finais e separa o texto em palavras inteiras (`\b`).
  * Efetua a busca sequencial das palavras chaves esperadas na saída do aluno.
  * **Vantagem**: Alunos não falham por divergências estéticas de formatação (ex: maiúsculas/minúsculas, espaços duplos ou prompts internos de `input()`).

### 2. Funções Puras (`tipo: "funcao"`)
Destinado a exercícios onde o aluno deve apenas definir uma função (ex: `soma_elementos(lista)`).
* **Execução**: O motor cria um script `wrapper.py` temporário no Docker que importa a função definida no arquivo do aluno (`solution.py`), executa-a com os argumentos `args` definidos no JSON e imprime o retorno serializado em formato JSON (`json.dumps`).
* **Validação**: O Python do Host desserializa o resultado retornado pelo wrapper (`json.loads`) e efetua uma comparação direta de tipo do objeto.
* **Vantagem**: Previne falsos negativos de tipagem do retorno (ex: listas, dicionários, booleanos).

---

## 🚀 Como Executar o Servidor

1. Certifique-se de ter o Docker instalado e rodando em sua máquina.
2. Ative o ambiente virtual e inicie o servidor de desenvolvimento Django:
   ```bash
   source venv/bin/activate
   python manage.py runserver
   ```
3. O servidor estará escutando no endereço `http://127.0.0.1:8000/`. A rota de avaliação LTI é:
   ```
   POST http://127.0.0.1:8000/lti/avaliacao/
   ```

---

## 🧪 Como Testar Localmente

O repositório inclui o script [test_lti.py](test_lti.py) para simular o disparo de requisições de submissão do EdX assinadas com OAuth 1.0.

### Passo 1: Configuração do Teste
Edite o payload no script [test_lti.py](test_lti.py) de acordo com o exercício que deseja testar:
```python
payload = {
    'lti_message_type': 'basic-lti-launch-request',
    'lti_version': 'LTI-1p0',
    # ID do exercício presente no tests.json (ex: week_4_fatorial, week_8_soma_elementos)
    'resource_link_id': 'week_4_fatorial', 
    'lis_result_sourcedid': 'aluno_test',
    'lis_outcome_service_url': 'https://dummy.edx.org/grades',
    # Código que o aluno submeteu
    'custom_student_code': 'n = int(input())\nfat = 1\nfor i in range(1, n + 1):\n    fat *= i\nprint(fat)'
}
```

### Passo 2: Execução
Com o servidor Django rodando, execute o script de testes:
```bash
python test_lti.py
```

### Passo 3: Analisar os Resultados
O terminal exibirá a resposta obtida do servidor com a validação:
```
=== RETORNO DO DJANGO ===
Status Code : 200
Mensagem    : Submissão LTI executada com sucesso. Nota obtida: 1.0
=========================
```
No console de execução do Django, os logs detalhados de cada caso de teste serão exibidos para depuração.
