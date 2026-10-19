"""Confere os links e as ancoras dos READMEs.

Check the links and the anchors of both READMEs.

Um README com link quebrado e pior do que README sem link: o leitor segue a
link, nao encontra nada, e perde a confianca no resto do documento. A caixa
de correcao do GitHub nao ajuda, porque ela valida o link contra a branch
principal e nao contra o arquivo que o README realmente cita.

O verificador cobre:

- link relativo para arquivo que nao existe;
- ancora interna que nao corresponde a nenhuma secao do proprio README.

Links externos e enderecos de e-mail sao ignorados: o verificador nao tem
acesso a rede, e um link externo que quebra nao se broken por causa do
README.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: Raiz do repositorio.
RAIZ = Path(__file__).resolve().parent.parent

#: READMEs verificados.
READMES = ("README.md", "README.en.md")

#: Link markdown: [texto](destino).
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")

#: Titulo de secao, de um a seis cerquilhas.
TITULO = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


def ancora_de(titulo: str) -> str:
    """Converte um titulo de secao na ancora que o GitHub gera.

    Turn a section title into the anchor GitHub generates.

    O GitHub nao remove acento: "Início rápido" vira "início-rápido", e nao
    "inicio-rapido". O que ele remove e pontuacao, e o que ele troca por
    hifen e o espaco.

    Args:
        titulo: Titulo da secao, como aparece no arquivo.

    Returns:
        A ancora correspondente.
    """
    minusculo = titulo.lower()
    sem_pontuacao = re.sub(r"[^\w\s-]", "", minusculo, flags=re.UNICODE)
    return re.sub(r"\s+", "-", sem_pontuacao.strip())


def validar(arquivo: str) -> list[str]:
    """Reporta os links quebrados de um README.

    Report the broken links of one README.

    Args:
        arquivo: Caminho do README, relativo a raiz do repositorio.

    Returns:
        Lista de problemas encontrados.
    """
    caminho = RAIZ / arquivo
    texto = caminho.read_text(encoding="utf-8")
    problemas: list[str] = []

    ancoras = {ancora_de(titulo) for titulo in TITULO.findall(texto)}

    for destino in LINK.findall(texto):
        if destino.startswith(("http://", "https://", "mailto:")):
            continue
        if destino.startswith("#"):
            if destino[1:] not in ancoras:
                problemas.append(f"{arquivo}: ancora interna inexistente {destino}")
            continue
        alvo = destino.split("#", 1)[0]
        if not alvo:
            continue
        if not (caminho.parent / alvo).exists():
            problemas.append(f"{arquivo}: arquivo inexistente {alvo}")

    return problemas


def main() -> int:
    """Executa a verificacao e reporta.

    Run the check and report.
    """
    problemas: list[str] = []
    for arquivo in READMES:
        problemas.extend(validar(arquivo))

    if problemas:
        print(f"links FALHARAM: {len(problemas)} problema(s)")
        for problema in problemas:
            print(f"  {problema}")
        return 1

    print("links ok: todos os links relativos e as ancoras existem nos dois READMEs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
