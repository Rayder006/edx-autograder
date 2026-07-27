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

## 🚀 Como Executar o Servidor (Desenvolvimento)

O projeto possui um `Makefile` na raiz para simplificar todos os comandos do dia a dia.

1. **Primeira vez na máquina**:
   Execute o comando abaixo para criar o ambiente virtual, instalar dependências e rodar as migrações:
   ```bash
   make init
   ```
2. **Iniciar o Servidor**:
   Execute o comando abaixo. Ele verificará se o Docker está rodando (iniciando-o automaticamente no macOS caso esteja desligado), rodará as migrações pendentes e subirá o servidor Django na porta `8000`:
   ```bash
   make start
   ```
3. **Limpar Caches**:
   Para apagar arquivos `.pyc` e pastas `__pycache__` geradas localmente:
   ```bash
   make clean
   ```

---

## 🧪 Como Testar e Simular Localmente

Você tem duas formas de simular o comportamento da plataforma EdX na sua máquina:

### 1. Simulador Visual no Iframe (Recomendado)
Com o servidor rodando (`make start`), acesse em seu navegador:
```
http://127.0.0.1:8000/lti/test-launcher/
```
Esse simulador gera automaticamente assinaturas LTI válidas e renderiza o autograder dentro de um iframe, exatamente como o EdX faz.
- Use o **dropdown no topo direito** para alternar dinamicamente entre os exercícios descritos no `tests.json`.
- Escreva código na área do editor de texto ou faça o upload de um arquivo `.py` para validar.

> [!IMPORTANT]
> **Segurança do Simulador em Produção**:
> Por motivos de segurança, a rota do simulador visual (`/lti/test-launcher/`) está configurada para ser **desativada automaticamente** em ambiente de produção (quando `DJANGO_DEBUG=False` em seu servidor).
> 
> Caso queira remover completamente essa rota ou o suporte a testes locais, remova ou comente a seguinte condicional ao final do arquivo [grader/urls.py](file:///Users/joni/Documents/edx-autograder/grader/urls.py):
> ```python
> if settings.DEBUG:
>     urlpatterns.append(path('test-launcher/', views.test_launcher_view, name='test_launcher_view'))
> ```

### 2. Script de Teste via Terminal
Você também pode disparar requisições automatizadas que devolvem respostas em texto puro (mantendo a compatibilidade de automações antigas):
```bash
make test
```
*(Você pode customizar o código do aluno ou o ID do exercício alterando o arquivo [test_lti.py](test_lti.py)).*

---

## 🌐 Configuração e Implantação em Produção (Deployment)

Para colocar o corretor no ar em segurança (evitando expor chaves no Git), configure o ambiente de produção seguindo os passos abaixo.

### Passo 1: Configurar Variáveis de Ambiente no Servidor
Nunca escreva chaves diretamente no repositório público. Configure as seguintes variáveis no seu ambiente de produção (no seu container Docker, Heroku, AWS, etc.):

| Variável | Descrição | Exemplo em Produção |
|---|---|---|
| `DJANGO_DEBUG` | **Obrigatório como `False`** para desativar tracebacks públicos e modo debug. | `False` |
| `DJANGO_SECRET_KEY` | Chave criptográfica única e aleatória do Django. | `sua-chave-secreta-muito-segura-e-aleatoria` |
| `DJANGO_ALLOWED_HOSTS` | Lista (separada por vírgula) de domínios ou IPs que respondem pelo servidor. | `autograder.suaurl.com` |
| `LTI_CONSUMER_KEY` | Chave pública que o EdX enviará para identificar a requisição. | `usp_edx_prod_key` |
| `LTI_SHARED_SECRET` | Segredo criptográfico compartilhado apenas entre o EdX e o Autograder. | `segredo-super-secretao-para-hmac` |

### Passo 2: Configurar o Exercício na Plataforma EdX
No painel do instrutor do EdX (EdX Studio), configure o componente de ferramenta externa (**LTI Consumer**) seguindo os parâmetros abaixo:

1. **LTI URL**: Configure a URL apontando para o endpoint de avaliação contendo o parâmetro do exercício em query string. Isso faz com que cada exercício aponte para sua respectiva configuração no `tests.json`:
   ```
   https://autograder.suaurl.com/lti/avaliacao/?exercise=week_4_fatorial
   ```
2. **LTI Passport (Credenciais)**:
   - No EdX, configure o passaporte LTI ligando a chave pública (`LTI_CONSUMER_KEY`) e o segredo compartilhado (`LTI_SHARED_SECRET`).
   - O formato no EdX é: `id_do_passaporte:LTI_CONSUMER_KEY:LTI_SHARED_SECRET`.
   - **Exemplo**: `corretor-usp:usp_edx_prod_key:segredo-super-secretao-para-hmac`.
   - No componente LTI do exercício, defina o campo **LTI ID** (ou LTI Passport) como `corretor-usp`.
3. **Parâmetros LTI Recomendados**:
   - **Aceitar Notas (Accept Grades)**: Defina como **True** (Sim) para permitir que o autograder lance as notas diretamente no livro de notas do EdX.
   - **Enviar Nome/E-mail do Usuário (Request user name/email)**: Opcional (pode ser False, pois o autograder identifica o aluno anonimamente pelo ID `lis_result_sourcedid` enviado pelo EdX).

---

## 🗄️ Persistência de Dados e Banco de Dados

O Autograder utiliza o Django ORM para persistir e gerenciar o progresso dos alunos no banco de dados.

### Modelos de Dados
1. **`Aluno`**: Registra o ID único de usuário (`user_id`) enviado pelo EdX.
2. **`Submissao`**: Armazena o código enviado, a nota e o resultado completo em formato JSON por exercício de cada aluno.

### Configuração do Banco
Por padrão, o projeto utiliza **SQLite** (`db.sqlite3`), o que é ideal para desenvolvimento e turmas pequenas. 

> [!WARNING]
> **Banco de Dados em Produção**:
> Para ambientes de produção reais com múltiplos acessos simultâneos (ex: centenas de alunos submetendo código próximos ao prazo de entrega), o SQLite pode apresentar travamentos por concorrência de escrita (`database is locked`).
> **Recomenda-se configurar um banco de dados relacional robusto (como PostgreSQL ou MySQL)** no arquivo [config/settings.py](file:///Users/joni/Documents/edx-autograder/config/settings.py) através de variáveis de ambiente.

---

## 💡 Possíveis Melhorias Futuras

Caso queira evoluir este corretor automático, aqui estão algumas melhorias altamente recomendadas:

1. **Lançamento Automático de Notas no EdX (LTI Outcomes)**:
   - Atualmente, as notas são gravadas localmente e exibidas para o aluno no Iframe. 
   - É altamente recomendável implementar a chamada de retorno (OAuth SOAP XML request) usando os parâmetros `lis_outcome_service_url` e `lis_result_sourcedid` recebidos no launch LTI. Isso enviará a nota final do aluno automaticamente de volta para a planilha de notas (Gradebook) do EdX assim que o código for corrigido.
2. **Fila de Execução Assíncrona (Task Queue)**:
   - Atualmente, a execução do contêiner Docker para testes roda de forma síncrona dentro da requisição HTTP do Django.
   - Sob alta carga, isso pode esgotar os workers do servidor e travar a aplicação. O uso de uma fila (como **Celery** ou **Huey** com **Redis**) permitiria enfileirar as correções de forma assíncrona, definindo um limite máximo de contêineres rodando em paralelo.
3. **Limite de Recursos Adicionais no Docker**:
   - Limitar as cotas de CPU (`nano_cpus` ou `cpu_period`/`cpu_quota`) e taxa de I/O de escrita em disco nos contêineres Alpine de teste para mitigar ataques de negação de serviço (fork bombs ou loops infinitos de I/O) originados do código dos alunos.
4. **Upgrade para LTI 1.3**:
   - O projeto utiliza LTI 1.1 (OAuth 1.0a). Embora simples, o LTI 1.1 está sendo depreciado pelas principais plataformas LMS. Um upgrade futuro para **LTI 1.3 (LTI Advantage)** trará maior segurança usando tokens JWT (JSON Web Tokens) assinados de forma assimétrica e fluxos OpenID Connect (OIDC).
