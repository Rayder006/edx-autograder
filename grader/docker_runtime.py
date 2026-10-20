"""Permissões e caminhos compartilhados pelos motores de avaliação."""
import os


def runner_user(directory, writable_directories=()):
    user = os.environ.get('AUTOGRADER_CONTAINER_USER') or str(os.getuid())
    parts = user.split(':')
    if len(parts) > 2 or not all(part.isdigit() for part in parts):
        raise ValueError('AUTOGRADER_CONTAINER_USER deve ser um UID numérico ou UID:GID.')
    uid = int(parts[0])
    gid = int(parts[1]) if len(parts) == 2 else os.getgid()
    if uid != os.getuid() and os.geteuid() != 0:
        raise PermissionError('O UID do avaliador deve ser o UID do processo Django.')
    # TemporaryDirectory tem modo 0700. Um override do UID só pode acessar a
    # pasta se o proprietário for ajustado pelo serviço que a criou.
    if os.geteuid() == 0:
        for path in (directory, *writable_directories):
            os.chown(path, uid, gid)
    return user


def host_path(path):
    """O daemon Docker resolve bind mounts no host, não no container web."""
    local_base = os.environ.get('AUTOGRADER_TMP_DIR')
    host_base = os.environ.get('AUTOGRADER_TMP_DIR_HOST')
    if local_base and host_base:
        relative_path = os.path.relpath(path, local_base)
        if relative_path == '..' or relative_path.startswith('..' + os.sep):
            raise ValueError('Diretório de avaliação fora do volume compartilhado.')
        return os.path.join(host_base, relative_path)
    return path
