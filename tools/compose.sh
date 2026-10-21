#!/bin/sh
# Não importa .env como script shell: a interpretação fica com o próprio Compose.
set -eu

env_file=${ENV_FILE:-.env}
if [ ! -f "$env_file" ]; then
    echo "Arquivo $env_file não encontrado. Crie-o manualmente a partir de .env.example." >&2
    exit 1
fi
AUTOGRADER_ENV_FILE=$(cd "$(dirname "$env_file")" && pwd)/$(basename "$env_file")
export AUTOGRADER_ENV_FILE

if ! docker compose version >/dev/null 2>&1; then
    echo 'Docker Compose v2 é necessário (docker compose). Não use docker-compose v1.' >&2
    exit 1
fi
if ! docker compose config --help | grep -q -- --environment; then
    echo 'Atualize apenas o plugin Docker Compose para v2.28+ (requer config --environment). Não é necessário atualizar o Python do sistema.' >&2
    exit 1
fi

# config não inicia serviços e não exibe credenciais no terminal.
compose_environment=$(docker compose --env-file "$env_file" config --environment)
configured() {
    printf '%s\n' "$compose_environment" | sed -n "s/^$1=//p"
}

AUTOGRADER_WEB_UID=$(configured AUTOGRADER_WEB_UID)
AUTOGRADER_WEB_UID=${AUTOGRADER_WEB_UID:-$(id -u)}
AUTOGRADER_WEB_GID=$(configured AUTOGRADER_WEB_GID)
AUTOGRADER_WEB_GID=${AUTOGRADER_WEB_GID:-$(id -g)}
AUTOGRADER_DOCKER_SOCKET=$(configured AUTOGRADER_DOCKER_SOCKET)
AUTOGRADER_DOCKER_SOCKET=${AUTOGRADER_DOCKER_SOCKET:-/var/run/docker.sock}
AUTOGRADER_DOCKER_GID=$(configured AUTOGRADER_DOCKER_GID)
if [ -z "$AUTOGRADER_DOCKER_GID" ]; then
    if [ "$(uname -s)" = Darwin ]; then
        # O socket montado pelo Docker Desktop pertence ao root dentro da VM.
        AUTOGRADER_DOCKER_GID=0
    elif [ -S "$AUTOGRADER_DOCKER_SOCKET" ]; then
        AUTOGRADER_DOCKER_GID=$(stat -Lc '%g' "$AUTOGRADER_DOCKER_SOCKET")
    else
        AUTOGRADER_DOCKER_GID=0
    fi
fi
export AUTOGRADER_WEB_UID AUTOGRADER_WEB_GID AUTOGRADER_DOCKER_GID AUTOGRADER_DOCKER_SOCKET

for numeric_id in "$AUTOGRADER_WEB_UID" "$AUTOGRADER_WEB_GID" "$AUTOGRADER_DOCKER_GID"; do
    case "$numeric_id" in
        ''|*[!0-9]*) echo 'UID/GID do serviço devem ser números.' >&2; exit 1 ;;
    esac
done

if [ "${1:-}" = up ]; then
    if [ "$AUTOGRADER_WEB_UID" = 0 ]; then
        echo 'Não execute a instalação como root. Use o usuário do serviço com acesso autorizado ao Docker.' >&2
        exit 1
    fi
    if [ "$AUTOGRADER_WEB_UID" != "$(id -u)" ] || [ "$AUTOGRADER_WEB_GID" != "$(id -g)" ]; then
        echo 'Execute a instalação com o mesmo UID/GID configurado para o serviço web.' >&2
        exit 1
    fi
    if ! docker compose up --help | grep -q -- --wait-timeout; then
        echo 'Atualize o plugin Docker Compose para v2.28+ (requer --wait-timeout).' >&2
        exit 1
    fi
    tmp_dir=$(configured AUTOGRADER_TMP_DIR_HOST)
    tmp_dir=${tmp_dir:-/tmp/autograder}
    case "$tmp_dir" in
        /|/tmp|/var|/home|/usr|/srv|'') echo 'Use um subdiretório exclusivo para AUTOGRADER_TMP_DIR_HOST.' >&2; exit 1 ;;
        /*) ;;
        *) echo 'AUTOGRADER_TMP_DIR_HOST deve ser um caminho absoluto.' >&2; exit 1 ;;
    esac
    # Criar antes do bind mount impede o Docker de criar uma pasta root-owned.
    (umask 077; mkdir -p "$tmp_dir")
    if [ ! -w "$tmp_dir" ] || [ ! -x "$tmp_dir" ]; then
        echo "Sem permissão no diretório $tmp_dir. Escolha uma pasta do usuário do serviço; não use sudo make." >&2
        exit 1
    fi
fi

exec docker compose --env-file "$env_file" "$@"
