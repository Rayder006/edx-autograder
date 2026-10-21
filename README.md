# EdX Autograder

Corretor de exercícios Python integrado ao EdX por LTI 1.1. O EdX faz um POST assinado para abrir o formulário em um iframe. O aluno envia código ou um arquivo Python; o servidor executa os testes Pytest em um container isolado, salva o resultado e transmite a maior nota ao EdX pelo Basic Outcomes Service.

São 32 exercícios. As especificações ficam em `exercises/test_<id>.py`, divididas em baterias com a regra de pontuação “tudo ou nada”: só ganha o peso de uma bateria quem passa em todos os seus casos. A nota interna vai de 0 a 10; o retorno LTI usa 0 a 1.

## Requisitos

- Docker Engine ou Docker Desktop em execução.
- Docker Compose v2.28 ou superior, disponível como `docker compose` (não `docker-compose` v1).
- Para executar diretamente no host: Python 3.13+ e `make`.
- Para produção com Compose, Python e PostgreSQL são instalados nas imagens; não é necessário um ambiente virtual no servidor.

Python 3.13 e Django 6.0.4 já eram usados antes da migração Pytest/PostgreSQL. O projeto não atualiza o Python do sistema nem depende dele no modo Compose. A imagem usa Debian Bookworm explicitamente para não acompanhar silenciosamente mudanças de distribuição. Não é possível garantir compatibilidade com qualquer Linux antigo: o kernel e o Docker da USP precisam suportar essas imagens e os limites de recursos usados pelo corretor.

O wrapper verifica os recursos necessários do Compose antes de iniciar a instalação. A descoberta segura das variáveis usa `config --environment`, disponível a partir da série 2.28; se o plugin for antigo, atualize somente esse plugin com o administrador, sem substituir o Python da distribuição. A interpretação do `.env` é feita pelo Compose, não executada como script shell.

## Instalação em produção na USP

Crie manualmente o arquivo `.env`, usando `.env.example` como referência. O projeto não gera esse arquivo automaticamente e falha se ele estiver ausente.

Restrinja a leitura desse arquivo ao usuário do serviço, por exemplo com `chmod 600 .env`.

Preencha pelo menos:

| Variável | Valor |
| --- | --- |
| `DJANGO_SECRET_KEY` | Chave aleatória, exclusiva da instalação |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | IP/domínio acessado pelo EdX, sem protocolo nem porta, separado por vírgulas |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Banco, usuário e senha reais |
| `LTI_PASSPORTS` | Credenciais combinadas com o EdX |

Para gerar uma chave Django, por exemplo:

```bash
python3 -c "import secrets; print(secrets.token_hex(50))"
```

O passaporte aceita três formatos:

```dotenv
# Um par:
LTI_PASSPORTS=chave:segredo

# Formato do EdX, incluindo o identificador:
LTI_PASSPORTS=corretor-usp:chave:segredo

# Várias integrações, sem ambiguidade quando o segredo contém dois-pontos:
LTI_PASSPORTS='{"chave1":"segredo1","chave2":"segredo:com:dois-pontos"}'
```

Também é possível usar apenas `LTI_CONSUMER_KEY` e `LTI_SHARED_SECRET`. As credenciais de desenvolvimento não são aceitas como padrão em produção. `.env` é ignorado pelo Git e não entra na imagem Docker.

Depois de configurar:

```bash
make prod-init
```

O comando constrói a imagem, inicia o PostgreSQL, aplica as migrações, coleta os arquivos estáticos e inicia o Gunicorn. Aguarda banco e web ficarem saudáveis e executa uma correção de diagnóstico real em Docker. Uma falha nessas etapas interrompe o comando com erro.

Execute com o usuário normal do serviço, **sem `sudo make`**. O Make usa `tools/compose.sh` para descobrir UID/GID, acrescentar apenas o grupo necessário para acessar o socket e criar a pasta temporária antes de montá-la. O processo web e os avaliadores não rodam como root; a instalação de pacotes como root ocorre somente durante a construção da imagem. O PostgreSQL oficial administra as permissões do próprio volume.

Se uma instalação antiga deixou `/tmp/autograder` pertencendo ao root, escolha um novo diretório exclusivo e gravável em `AUTOGRADER_TMP_DIR_HOST`, em vez de tornar pastas públicas graváveis ou executar todo o projeto como root. Não altere dono/permissões de arquivos antigos sem conferir se contêm dados ou se há avaliações em andamento.

Comandos úteis:

```bash
make prod-status
make prod-logs
make doctor
make prod-stop
```

O serviço web escuta na porta 8000, alterável por `AUTOGRADER_WEB_PORT`. O PostgreSQL persiste no volume `postgres_data`; sua porta publicada é acessível apenas por 127.0.0.1, e pode ser alterada com `POSTGRES_PORT_HOST`. `make prod-stop` preserva os dados.

No Compose, a conexão interna usa `POSTGRES_HOST=db` e porta 5432. `DATABASE_URL`, quando definida, tem prioridade: para usar o banco do próprio Compose, o hostname dessa URL também precisa ser `db`. Diretamente no host, use localhost e a porta publicada.

Para usar outro arquivo de ambiente:

```bash
make prod-init ENV_FILE=/caminho/configuracao.env
```

O servidor precisa de acesso ao socket do Docker para criar os containers de correção. O Compose já monta o socket e o diretório compartilhado. Se o Django rodar diretamente no Linux, o usuário do serviço precisa ter permissão para usar o Docker.

Essa autorização deve ser feita uma vez pelo administrador da infraestrutura. Acesso ao grupo/socket Docker concede poderes equivalentes a root no host, mesmo com um processo web sem privilégios; não use `chmod 666` no socket. O fluxo fornecido presume um daemon Docker local, sem remapeamento de usuários. Docker remoto/rootless/user namespaces precisam de adaptação dos caminhos e UIDs pela infraestrutura.

Para comandos Compose adicionais, prefira o mesmo wrapper, que também respeita `ENV_FILE`:

```bash
ENV_FILE=/caminho/configuracao.env sh tools/compose.sh ps
```

Se chamar `docker compose` diretamente, configure manualmente `AUTOGRADER_ENV_FILE`, `AUTOGRADER_WEB_UID`, `AUTOGRADER_WEB_GID` e `AUTOGRADER_DOCKER_GID` e prepare a pasta compartilhada. Os exemplos de importação abaixo usam o wrapper para evitar essa diferença.

### HTTPS e proxy reverso

O navegador do aluno precisa alcançar o autograder. Se o EdX usa HTTPS, o iframe também precisa usar HTTPS. Configure TLS no proxy da infraestrutura, encaminhando para o serviço web na porta 8000.

O proxy deve preservar o caminho e a query string, e informar corretamente `Host` (ou `X-Forwarded-Host`) e `X-Forwarded-Proto`. A assinatura OAuth depende da URL externa exata, incluindo protocolo e porta. Cabeçalhos encaminhados devem ser definidos pelo proxy confiável.

O timeout do proxy deve comportar a correção síncrona e o callback (o Gunicorn usa 90 segundos). Não há fila assíncrona: dimensionamento para uma turma inteira submetendo ao mesmo tempo precisa ser validado à parte.

Não permita acesso público que contorne esse proxy confiável; restrinja a porta web por firewall/rede conforme a infraestrutura. O proxy não deve acrescentar `X-Frame-Options: DENY/SAMEORIGIN` nem uma política `frame-ancestors` que bloqueie o domínio EdX. Para código de até 256 KiB, configure também um limite de upload no proxy que comporte o formulário completo.

O callback sai do servidor para o endereço `lis_outcome_service_url` fornecido pelo launch assinado. Libere DNS e saída HTTPS para o LMS. A verificação TLS permanece ativa; CA institucional e proxy podem ser configurados por `REQUESTS_CA_BUNDLE`, `HTTPS_PROXY` e `NO_PROXY`. Se necessário, monte o arquivo da CA somente para leitura no serviço web. Não resolva erros de certificado desligando a verificação TLS.

O endpoint de LTI permite iframe e dispensa cookies de terceiros: a sessão do formulário usa um token assinado com validade de uma hora. Ao expirar, o aluno deve reabrir o exercício no EdX.

Launches exigem timestamp/nonce OAuth e não podem ser repetidos. O banco compartilha essa proteção entre workers e descarta nonces expirados; a tolerância é de 90 minutos, conforme o guia LTI 1.1. Mantenha os relógios do LMS e do servidor sincronizados. O token do formulário não reutiliza o nonce do launch para as submissões seguintes.

### Configuração no EdX Studio

No curso, cadastre o passaporte no formato:

```text
corretor-usp:chave:segredo
```

No componente LTI, use o ID `corretor-usp`, habilite **Accept Grades** e configure a URL:

```text
https://DOMINIO-OU-IP/lti/avaliacao/?exercise=week_4_fatorial
```

O launch precisa fornecer `user_id` e, para retorno da nota, `lis_outcome_service_url` e `lis_result_sourcedid`. O identificador de resultado é tratado como opaco e preservado no XML.

Dependendo da versão do EdX Studio, a opção de notas pode aparecer como **This activity is graded / Graded**, em vez de **Accept Grades**. A unidade precisa estar em uma subseção avaliada para a nota contar no curso; confira também a aceitação de notas depois do prazo. Consulte a [documentação oficial do Open edX](https://docs.openedx.org/en/latest/educators/how-tos/course_development/exercise_tools/set_up_lti_1_1_component.html).

As rotas antigas `/lti/introcomp2024/<exercicio>` continuam disponíveis com e sem barra final. Por exemplo, `/lti/introcomp2024/paridade`. Não é necessário trocar essas URLs para usar Pytest.

## Atualização de uma instalação existente

Faça backup do banco antes da atualização e mantenha a chave Django e as credenciais LTI existentes.

Se a instalação já usa PostgreSQL, atualize o código e execute `make prod-init`. As migrações preservam a nota antiga como maior nota quando necessário e convertem relatórios JSON legados. Não apague o volume do banco.

Se o Django já roda diretamente no Linux como UID 1005 ou outro usuário, esse modo continua suportado: execute `make init` para atualizar dependências, preparar a imagem e aplicar migrações, e reinicie o serviço web usado pela infraestrutura. Não é necessário passar a executar o próprio Django em Docker. Sem `POSTGRES_DB` nem `DATABASE_URL`, a instalação continua usando seu SQLite existente.

Trocar a configuração de SQLite para PostgreSQL cria um banco separado: isso não copia automaticamente os dados do SQLite. Para conservar alunos e submissões, existe uma importação explícita que abre a origem somente para leitura e exige que o destino ainda não contenha alunos ou submissões.

Com a aplicação antiga parada, mantenha o acesso de alunos suspenso até terminar a importação e faça um backup consistente do SQLite:

```bash
sqlite3 db.sqlite3 ".backup 'legacy-backup.sqlite3'"
```

Depois de subir o PostgreSQL/web com o código novo, copie esse backup para o container:

```bash
sh tools/compose.sh cp legacy-backup.sqlite3 web:/tmp/legacy-backup.sqlite3
sh tools/compose.sh exec -T web python manage.py import_legacy_sqlite --source /tmp/legacy-backup.sqlite3 --dry-run
sh tools/compose.sh exec -T web python manage.py import_legacy_sqlite --source /tmp/legacy-backup.sqlite3
```

O primeiro comando de importação valida os dados e desfaz a transação; o segundo efetiva a importação. São preservados código, relatório, notas, tentativas disponíveis e datas. Essa operação importa os modelos do corretor, não usuários administrativos do Django. O backup original não é alterado. Se o destino já tiver alunos, a importação é recusada para impedir sobreposição de dados.

As novas submissões são separadas por consumidor LTI, curso (`context_id`) e componente (`resource_link_id`), além de aluno/exercício. Registros antigos não continham esses identificadores: ficam preservados e são associados uma única vez ao primeiro contexto autenticado que reabrir aquele exercício para o aluno. Se o banco antigo reuniu vários cursos/componentes, não é possível reconstruir automaticamente a origem: confira essa associação antes de liberar acessos. A importação de um SQLite já atualizado conserva os contextos e estados de callback existentes.

## Desenvolvimento local

Sem `.env` e sem variáveis de banco, o Django usa SQLite. O Docker continua necessário para avaliar código.

```bash
make init
make start
```

Se `python3` no Linux aponta a uma versão antiga, selecione explicitamente um Python 3.13+ já instalado: `make init HOST_PYTHON=python3.13`. O instalador falha sem anunciar sucesso caso esse interpretador ou o suporte a `venv` esteja ausente. Não substitua o Python da distribuição. Um ambiente virtual antigo deve ser preservado como backup e recriado com o interpretador correto; não o atualize com `sudo pip`.

`make init` instala as dependências, prepara a imagem do corretor e aplica as migrações. `make start` atualiza a imagem, aplica migrações pendentes e inicia o servidor em `http://127.0.0.1:8000`.

Se já existir `.env`, o Django o carrega automaticamente sem sobrescrever variáveis exportadas pelo processo. Para selecionar SQLite e modo de desenvolvimento apesar de uma configuração PostgreSQL no arquivo:

```bash
POSTGRES_DB= DATABASE_URL= DJANGO_DEBUG=True make start
```

O simulador visual está em:

```text
http://127.0.0.1:8000/lti/test-launcher/
```

Escolha um exercício, escreva código ou carregue um arquivo `.py` em UTF-8. O editor também funciona em modo texto quando a biblioteca visual externa não está disponível. A rota do simulador responde 404 com `DJANGO_DEBUG=False`.

`make test-lti` envia uma solução válida de fatorial ao servidor local. O script carrega as credenciais do `.env` e usa um aluno de teste novo. Para apontar a outro endereço, defina `AUTOGRADER_TEST_URL`. Um callback de teste só é enviado se `AUTOGRADER_TEST_OUTCOME_URL` estiver configurado.

## Testes

Após `make init`:

```bash
make test
# equivalente:
venv/bin/python -m pytest

# Alternativa com o test runner do Django:
venv/bin/python manage.py test grader
```

A suíte inclui autenticação LTI, passback XML/OAuth, formulário, upload, maior nota, retransmissão de nota, erros de infraestrutura, migração de banco e execução real em Docker. Com PostgreSQL configurado, também verifica concorrência de submissões. O banco de teste é separado do banco da aplicação; o usuário de teste PostgreSQL precisa poder criar bancos.

As especificações em `exercises/` são executadas pelo corretor junto de cada solução, e não devem ser coletadas diretamente pela suíte da aplicação. `pytest.ini` configura essa separação.

Com o material original do curso disponível localmente, também é possível verificar os 32 exercícios com suas soluções de referência:

```bash
venv/bin/python tools/verify_reference_solutions.py
# ou:
venv/bin/python tools/verify_reference_solutions.py --reference-root /caminho/part_1
```

Essa verificação usa Docker e roda em série. O material original e suas respostas não são incluídos na imagem nem adicionados ao Git.

## Motor de correção e permissões

A imagem `edx-autograder-web:latest` já contém Pytest. Não há instalação de pacotes durante a correção.

Cada avaliação usa um container efêmero sem rede, com 128 MB de memória, 64 processos e até uma CPU. Os arquivos de código e testes são somente leitura. O relatório é gravado em um diretório separado. O limite total por avaliação Pytest é de 30 segundos, incluindo todos os casos. Há também um watchdog no container para interrompê-lo se o processo web for encerrado.

O container usa o UID do processo Django automaticamente e desativa `.pytest_cache`. Isso resolve o problema de permissão relatado na USP sem fixar o UID 1005 no código. Se necessário, `AUTOGRADER_CONTAINER_USER` permite um UID numérico ou UID:GID; um processo sem privilégios deve usar seu próprio UID.

Quando Django está em um container, o daemon Docker resolve os volumes no host. O Compose compartilha `/tmp/autograder` e o runner traduz esse caminho para `AUTOGRADER_TMP_DIR_HOST`, inclusive quando o caminho configurado no host é diferente.

O motor legado pode ser selecionado explicitamente com `AUTOGRADER_ENGINE=docker`. Falta de especificação Pytest não dispara troca silenciosa de motor. Sem Docker, o corretor retorna indisponibilidade e não grava uma nota zero. O fallback local exige `AUTOGRADER_ALLOW_LOCAL_FALLBACK=1`, é destinado somente a desenvolvimento e fica forçado a `0` no Compose.

## Notas, resultados e diagnóstico

Cada aluno tem uma submissão por exercício **e contexto LTI**, com o código/resultado mais recente, a maior nota e o total de tentativas. A interface distingue nota da tentativa e maior nota. O EdX recebe sempre a maior nota daquele contexto; atualizações concorrentes são serializadas para impedir regressão.

O banco mantém também o destino de retorno (sem segredo nem assinatura OAuth), a confirmação/falha, a data da última tentativa e a última nota confirmada em escala 0–1. O relatório/código salvo corresponde à tentativa mais recente, não necessariamente à maior nota; não é um histórico completo de códigos/tentativas. A maior nota é preservada separadamente.

Ao alcançar nota máxima, novas correções são bloqueadas. Se o retorno de nota falhar, a interface permite retransmitir a nota sem executar o código novamente nem contar outra tentativa. A nota local é preservada quando o EdX fica indisponível.

O administrador também pode recuperar retornos pendentes sem depender do token do navegador:

```bash
sh tools/compose.sh exec -T web python manage.py retry_lti_passbacks --dry-run
sh tools/compose.sh exec -T web python manage.py retry_lti_passbacks --limit 100
```

Para Django no host, use os mesmos comandos com `venv/bin/python manage.py`. Não há fila/agendamento automático: execute novamente após resolver a indisponibilidade do LMS. A confirmação local registra a resposta recebida naquele momento, não consulta alterações posteriores feitas diretamente no EdX.

`GET /health/` verifica o acesso ao banco. `make doctor` verifica banco, migrações pendentes e uma avaliação real em Docker com o motor configurado, sem criar alunos ou notas. Use `make prod-logs` para acompanhar erros. Conexões persistentes PostgreSQL são verificadas antes de serem reutilizadas após uma reinicialização do banco.

No modo host, execute também `venv/bin/python manage.py check_autograder` antes de reiniciar/liberar o serviço. A aplicação não configura o serviço de boot da USP: o administrador deve manter o serviço existente ou configurar um gerenciador de processos. O Compose usa a política de reinício dos containers; o daemon Docker precisa iniciar com o sistema.

`manage.py check --deploy` pode avisar sobre redirecionamento HTTPS e HSTS: neste modelo, essas políticas pertencem ao proxy TLS. Confira-as nesse proxy; não habilite redirecionamento interno cegamente, pois o healthcheck local usa HTTP.

### Checklist para a infraestrutura

- Backup consistente do banco e credenciais originais preservadas; migração/importação terminada antes de permitir alunos.
- Usuário do serviço com acesso autorizado ao Docker, pasta compartilhada gravável e `make prod-init`/diagnóstico sem erros.
- TLS válido, DNS/IP corretos, proxy preservando URL/cabeçalhos e iframe permitido no EdX.
- Relógios sincronizados e saída HTTPS liberada para o callback; componente EdX configurado para receber notas.
- Disco disponível para banco, logs e imagens. Monitore/rotacione logs; nunca remova volumes do PostgreSQL para liberar espaço sem backup.
- Uma submissão real de homologação no EdX deve confirmar a nota na plataforma. Testes locais não validam firewall, TLS, prazos ou credenciais da USP.

Logs detalhados de LTI ficam desligados. `LTI_DEBUG=1` os habilita durante uma investigação; desligue depois, pois contêm dados da integração. Os atalhos de diagnóstico de assinatura/nota ficam limitados ao modo de desenvolvimento.

## Manutenção das especificações

O motor Pytest usa `exercises/test_<id>.py` como fonte de testes. O `tests.json` permanece como catálogo/metadados e para o motor legado.

O conversor não tem caminhos específicos do computador do desenvolvedor e, por padrão, apenas verifica divergências:

```bash
venv/bin/python tools/convert_json_to_pytest.py --check
```

Quando a intenção for migrar ou sincronizar casos vindos do JSON:

```bash
venv/bin/python tools/convert_json_to_pytest.py --write
```

Essa última operação regenera as especificações; revise o diff antes do commit, especialmente se algum teste Pytest foi editado manualmente.

Para carga maior de alunos simultâneos, uma fila de correções e retransmissão de notas pode ser adicionada futuramente. O fluxo atual permanece síncrono.

