import os


def create_output_dir(dir_path: str) -> str:
    """Cria o diretorio de saida se nao existir e retorna o caminho absoluto."""
    os.makedirs(dir_path, exist_ok=True)
    return os.path.abspath(dir_path)
