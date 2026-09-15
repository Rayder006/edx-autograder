.PHONY: help init start venv install run test docker-start docker-status migrate clean setup-env db-start db-stop db-logs db-shell prod-init

# Binários do Ambiente Virtual
PYTHON = venv/bin/python
PIP = venv/bin/pip

help:
	@echo "======================================================================"
	@echo "                     EDX-AUTOGRADER MAKEFILE                          "
	@echo "======================================================================"
	@echo "Desenvolvimento local (SQLite):"
	@echo "  make init           - Inicializa o projeto (venv + dependências + banco)"
	@echo "  make start          - Roda migrações e inicia o servidor Django"
	@echo ""
	@echo "Produção (PostgreSQL via Docker Compose):"
	@echo "  make setup-env      - Cria o .env a partir de .env.example"
	@echo "  make db-start       - Sobe o container PostgreSQL"
	@echo "  make db-stop        - Para o container PostgreSQL"
	@echo "  make db-logs        - Exibe logs do container PostgreSQL"
	@echo "  make db-shell       - Abre terminal psql dentro do container"
	@echo "  make prod-init      - Inicialização completa (setup-env + db-start + migrate)"
	@echo ""
	@echo "Outros auxiliares:"
	@echo "  make venv           - Cria o ambiente virtual python (venv)"
	@echo "  make install        - Instala/atualiza todas as dependências no venv"
	@echo "  make run            - Inicia o servidor de desenvolvimento Django"
	@echo "  make migrate        - Executa as migrações do banco de dados"
	@echo "  make test           - Executa o script de teste de integração LTI"
	@echo "  make docker-start   - Inicializa o daemon do Docker (macOS)"
	@echo "  make docker-status  - Verifica a conectividade com o Docker"
	@echo "  make clean          - Limpa caches e arquivos temporários do Python"
	@echo "======================================================================"

init: install migrate
	@echo "======================================================================"
	@echo " 🎉 Projeto inicializado com sucesso!"
	@echo " Para iniciar o servidor local, execute:"
	@echo "   make start"
	@echo "======================================================================"

start:
	@echo "Verificando status do Docker..."
	@docker ps >/dev/null 2>&1 || (echo "⚠️ Docker não está rodando. Inicializando Docker Desktop..." && open -a Docker && echo "Aguardando 10 segundos para o daemon carregar..." && sleep 10)
	@echo "Executando migrações do banco de dados..."
	@$(PYTHON) manage.py migrate
	@echo "Iniciando servidor de desenvolvimento Django..."
	@$(PYTHON) manage.py runserver 8000

venv:
	@if [ ! -d "venv" ]; then \
		echo "Criando ambiente virtual (venv)..."; \
		python3 -m venv venv; \
		echo "Ambiente virtual criado! Execute 'make install' para instalar as dependências."; \
	else \
		echo "Ambiente virtual venv já existe."; \
	fi

install: venv
	@echo "Instalando dependências..."
	@$(PIP) install --upgrade pip
	@$(PIP) install -r requirements.txt
	@echo "Instalação concluída com sucesso!"

run:
	@echo "Iniciando servidor de desenvolvimento Django..."
	@$(PYTHON) manage.py runserver 8000

migrate:
	@echo "Executando migrações do banco de dados..."
	@$(PYTHON) manage.py migrate

test:
	@echo "Iniciando teste de integração LTI..."
	@$(PYTHON) test_lti.py

docker-start:
	@echo "Abrindo o Docker Desktop..."
	@open -a Docker
	@echo "Aguardando 5 segundos para inicialização..."
	@sleep 5

docker-status:
	@docker ps >/dev/null 2>&1 && echo "Docker está ativo e rodando! 👍" || echo "Docker não está ativo. Use 'make docker-start' primeiro."

clean:
	@echo "Limpando caches do Python..."
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@echo "Limpeza concluída!"

# ---------------------------------------------------------------------------
# Produção (PostgreSQL via Docker Compose)
# ---------------------------------------------------------------------------

setup-env:
	@if [ ! -f ".env" ]; then \
		cp .env.example .env; \
		echo "✅ Arquivo .env criado a partir de .env.example."; \
		echo ""; \
		echo "⚠️  ATENÇÃO: Edite o arquivo .env antes de continuar!"; \
		echo "   Variáveis obrigatórias:"; \
		echo "     DJANGO_SECRET_KEY    → python -c 'import secrets; print(secrets.token_hex(50))'"; \
		echo "     DJANGO_ALLOWED_HOSTS → domínio real (ex: autograder.ime.usp.br)"; \
		echo "     POSTGRES_PASSWORD    → senha forte para o banco"; \
		echo "     LTI_PASSPORTS        → chave:segredo igual ao configurado no EdX Studio"; \
	else \
		echo "Arquivo .env já existe. Nenhuma alteração feita."; \
	fi

db-start:
	@echo "Subindo container PostgreSQL..."
	@docker-compose up -d db
	@echo "Aguardando PostgreSQL ficar pronto (healthcheck)..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		docker-compose exec db pg_isready -U autograder_user -d autograder >/dev/null 2>&1 \
			&& echo "✅ PostgreSQL pronto!" && break \
			|| (echo "  Tentativa $$i/10 — aguardando..." && sleep 3); \
	done

db-stop:
	@echo "Parando container PostgreSQL..."
	@docker-compose stop db
	@echo "✅ PostgreSQL parado."

db-logs:
	@docker-compose logs -f db

db-shell:
	@echo "Abrindo terminal psql no container PostgreSQL..."
	@docker-compose exec db psql -U autograder_user -d autograder

prod-init: setup-env db-start migrate
	@echo "======================================================================"
	@echo " 🎉 Ambiente de produção inicializado com sucesso!"
	@echo " Para iniciar o servidor Django, execute:"
	@echo "   make run"
	@echo "======================================================================"
