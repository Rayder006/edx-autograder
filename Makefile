.PHONY: help init start venv install run test docker-start docker-status migrate clean

# Binários do Ambiente Virtual
PYTHON = venv/bin/python
PIP = venv/bin/pip

help:
	@echo "======================================================================"
	@echo "                     EDX-AUTOGRADER MAKEFILE                          "
	@echo "======================================================================"
	@echo "Comandos principais:"
	@echo "  make init           - Inicializa o projeto pela primeira vez (venv + dependências + banco)"
	@echo "  make start          - Roda as migrações do banco de dados e inicia o servidor Django"
	@echo ""
	@echo "Outros comandos auxiliares:"
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
