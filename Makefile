.PHONY: help init start venv install run test test-lti docker-start docker-status runner-build migrate collectstatic clean setup-env db-start db-stop db-logs db-shell web-start prod-init prod-stop prod-logs prod-status doctor
.NOTPARALLEL: init start prod-init

# Binários do Ambiente Virtual
PYTHON = venv/bin/python
PIP = venv/bin/pip
HOST_PYTHON ?= python3
ENV_FILE ?= .env
COMPOSE = ENV_FILE="$(ENV_FILE)" sh tools/compose.sh

help:
	@echo "======================================================================"
	@echo "                     EDX-AUTOGRADER MAKEFILE                          "
	@echo "======================================================================"
	@echo "Desenvolvimento local (SQLite):"
	@echo "  make init           - Inicializa o projeto (venv + dependências + banco)"
	@echo "  make start          - Roda migrações e inicia o servidor Django"
	@echo ""
	@echo "Produção (PostgreSQL via Docker Compose):"
	@echo "  make setup-env      - Verifica se o .env foi criado manualmente"
	@echo "  make db-start       - Sobe o container PostgreSQL"
	@echo "  make db-stop        - Para o container PostgreSQL"
	@echo "  make db-logs        - Exibe logs do container PostgreSQL"
	@echo "  make db-shell       - Abre terminal psql dentro do container"
	@echo "  make web-start      - Constrói e inicia o servidor web via Compose"
	@echo "  make prod-init      - Inicialização completa (env + DB + servidor web)"
	@echo ""
	@echo "Outros auxiliares:"
	@echo "  make venv           - Cria o ambiente virtual python (venv)"
	@echo "  make install        - Instala/atualiza todas as dependências no venv"
	@echo "  make run            - Inicia o servidor de desenvolvimento Django"
	@echo "  make migrate        - Executa as migrações do banco de dados"
	@echo "  make test           - Executa a suíte automatizada (Pytest + Django)"
	@echo "  make test-lti       - Envia uma submissão ao servidor local em execução"
	@echo "  make runner-build   - Prepara a imagem de correção com Pytest"
	@echo "  make doctor         - Verifica banco, Docker e correção real em produção"
	@echo "  make prod-logs      - Acompanha logs do servidor de produção"
	@echo "  make prod-status    - Mostra o estado dos serviços de produção"
	@echo "  make docker-start   - Inicializa o daemon do Docker (macOS)"
	@echo "  make docker-status  - Verifica a conectividade com o Docker"
	@echo "  make clean          - Limpa caches e arquivos temporários do Python"
	@echo "======================================================================"

init: install runner-build migrate collectstatic
	@echo "======================================================================"
	@echo " 🎉 Projeto inicializado com sucesso!"
	@echo " Para iniciar o servidor local, execute:"
	@echo "   make start"
	@echo "======================================================================"

start: runner-build migrate
	@echo "Iniciando servidor de desenvolvimento Django..."
	@$(PYTHON) manage.py runserver 8000

venv:
	@set -e; \
	if [ ! -d "venv" ]; then \
		$(HOST_PYTHON) -c 'import sys; sys.exit("Python 3.13+ é necessário. Use HOST_PYTHON=python3.13 ou o modo Compose.") if sys.version_info < (3, 13) else None'; \
		echo "Criando ambiente virtual (venv)..."; \
		$(HOST_PYTHON) -m venv venv; \
		echo "Ambiente virtual criado! Execute 'make install' para instalar as dependências."; \
	else \
		echo "Ambiente virtual venv já existe."; \
	fi; \
	$(PYTHON) -c 'import sys; sys.exit("O venv existente precisa usar Python 3.13+.") if sys.version_info < (3, 13) else None'

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

collectstatic:
	@$(PYTHON) manage.py collectstatic --noinput

test:
	@$(PYTHON) -m pytest

test-lti:
	@echo "Iniciando teste de integração LTI..."
	@$(PYTHON) test_lti.py

docker-start:
	@if [ "$$(uname -s)" = "Darwin" ]; then open -a Docker; \
	else echo "Inicie o serviço Docker da sua distribuição Linux."; exit 1; fi

docker-status:
	@docker info >/dev/null 2>&1 || (echo "Docker indisponível. Inicie o Docker e confira a permissão do socket."; exit 1)

runner-build: docker-status
	@docker build -t edx-autograder-web:latest .

clean:
	@echo "Limpando caches do Python..."
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@echo "Limpeza concluída!"

# ---------------------------------------------------------------------------
# Produção (PostgreSQL via Docker Compose)
# ---------------------------------------------------------------------------

setup-env:
	@if [ ! -f "$(ENV_FILE)" ]; then \
		echo "❌ Arquivo $(ENV_FILE) não encontrado."; \
		echo "Crie-o manualmente a partir de .env.example e preencha os valores reais."; \
	exit 1; \
	fi
	@echo "✅ Arquivo .env encontrado."

db-start: setup-env
	@echo "Subindo container PostgreSQL..."
	@$(COMPOSE) up -d --wait --wait-timeout 120 db
	@echo "✅ PostgreSQL pronto!"

db-stop:
	@echo "Parando container PostgreSQL..."
	@$(COMPOSE) stop db
	@echo "✅ PostgreSQL parado."

db-logs:
	@$(COMPOSE) logs -f db

db-shell:
	@echo "Abrindo terminal psql no container PostgreSQL..."
	@$(COMPOSE) exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

web-start: setup-env
	@echo "Construindo e iniciando o servidor web..."
	@$(COMPOSE) up -d --build --wait --wait-timeout 180 web
	@echo "✅ Servidor web pronto."

prod-init: web-start
	@$(COMPOSE) exec -T web python manage.py check_autograder
	@echo "======================================================================"
	@echo " 🎉 Ambiente de produção inicializado com sucesso!"
	@echo " O PostgreSQL e o servidor web estão em execução."
	@echo "======================================================================"

doctor: setup-env
	@$(COMPOSE) exec -T web python manage.py check_autograder

prod-stop:
	@$(COMPOSE) stop web db

prod-logs:
	@$(COMPOSE) logs -f web

prod-status:
	@$(COMPOSE) ps
