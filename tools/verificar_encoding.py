"""Confere encoding dos arquivos de texto versionados.

Check the encoding of every tracked text file.

Um caractere de substituicao (U+FFFD) ou um bloco CJK dentro de um arquivo de
codigo indica que alguma passagem de texto corrompeu a escrita. No GitHub o
resultado aparece como lixo no diff, entao e mais barato falhar aqui.

Um U+FFFD e um caractere de substituicao. Um bloco CJK e um texto em japones,
chines ou coreano. Nenhum dos dois pertence a este repositorio.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Raiz do repositorio.
RAIZ = Path(__file__).resolve().parent.parent

#: Extensoes varridas. Binarios ficam de fora de proposito.
EXTENSOES = {".py", ".md", ".toml", ".yml", ".yaml", ".cfg", ".txt"}

#: Diretorios e arquivos ignorados.
IGNORADOS = {
    ".git", ".pytest_cache", "__pycache__", "htmlcov", ".venv", "venv",
    "build", "dist", ".coverage", "coverage.xml",
}

#: Intervalo de ideogramas CJK.
CJK = range(0x3000, 0x9FFF + 1)

#: Caractere de substituicao.
SUBSTITUICAO = 0xFFFD


def varrer(raiz: Path = RAIZ) -> list[tuple[str, int, str]]:
    """Procura arquivo de texto com caractere invalido.

    Find text files holding an invalid character.

    Args:
        raiz: Diretorio a varrer.

    Returns:
        Lista de ``(caminho, linha, motivo)``.
    """
    problemas: list[tuple[str, int, str]] = []
    for caminho in sorted(raiz.rglob("*")):
        if not caminho.is_file():
            continue
        if any(parte in IGNORADOS for parte in caminho.parts):
            continue
        if caminho.suffix.lower() not in EXTENSOES and caminho.name != ".gitignore":
            continue
        try:
            texto = caminho.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            problemas.append((
                str(caminho.relative_to(raiz)), 0,
                f"nao decodifica como UTF-8: {exc}",
            ))
            continue
        for numero, linha in enumerate(texto.splitlines(), 1):
            for caractere in linha:
                ponto = ord(caractere)
                if ponto == SUBSTITUICAO:
                    problemas.append((
                        str(caminho.relative_to(raiz)), numero,
                        "caractere de substituicao U+FFFD",
                    ))
                    break
                if ponto in CJK:
                    problemas.append((
                        str(caminho.relative_to(raiz)), numero,
                        f"ideograma CJK U+{ponto:04X}",
                    ))
                    break
    return problemas


def main() -> int:
    """Executa a varredura e reporta.

    Run the sweep and report.
    """
    problemas = varrer()
    if not problemas:
        print("encoding ok: nenhum U+FFFD e nenhum ideograma CJK")
        return 0
    print(f"encoding FALHOU: {len(problemas)} ocorrencia(s)")
    for caminho, linha, motivo in problemas:
        onde = f"{caminho}:{linha}" if linha else caminho
        print(f"  {onde}: {motivo}")
    return 1


if __name__ == "__main__":
    sys.exit(main())