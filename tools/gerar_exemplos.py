"""Gera os exemplos do repositorio com saida real.

Generate the repository examples from real output.

Sobe o servidor de lab em porta livre, varre o barramento, le os tres medidores
por Modbus TCP e grava as tres saidas da CLI. Nada aqui e escrito a mao: se o
scanner ou o calculo mudar, os exemplos mudam junto, e o CI falha se ficarem
desatualizados.

Uso: python tools/gerar_exemplos.py
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

#: Permite executar o script direto do checkout, sem instalar o pacote.
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from modbuslab.cli import main as cli_main  # noqa: E402
from modbuslab.dispositivos import carregar_ambiente  # noqa: E402
from modbuslab.servidor import ServidorModbus  # noqa: E402

EXEMPLOS = RAIZ / "exemplos"

#: Unit ids que a CLI sonda por padrao nos exemplos.
IDS = "1"
ATE = "3"

#: Porta que aparece escrita nos exemplos. O lab sobe numa porta livre para nao
#: colidir com nada, mas o arquivo gerado precisa ser identico a cada execucao,
#: senao o gate `git diff --exit-code` do CI falha sempre. A porta real e
#: substituida por esta antes de gravar.
PORTA_DOCUMENTADA = "5020"


def normalizar_porta(texto: str, porta_real: int) -> str:
    """Troca a porta efemera pela porta documentada.

    Replace the ephemeral port with the documented one.

    Args:
        texto: Saida capturada da CLI.
        porta_real: Porta que o servidor ocupou de fato.

    Returns:
        O texto com a porta documentada.
    """
    return texto.replace(str(porta_real), PORTA_DOCUMENTADA)


def rodar_cli(argumentos: list[str]) -> tuple[int, str]:
    """Roda um comando da CLI e captura a saida.

    Run a CLI command and capture its output.

    Args:
        argumentos: Argumentos do comando.

    Returns:
        Par com o codigo de saida e o texto produzido.
    """
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        codigo = cli_main(argumentos)
    return codigo, buffer.getvalue()


def main() -> int:
    """Regera os tres artefatos de exemplo.

    Regenerate the three example artefacts.
    """
    EXEMPLOS.mkdir(exist_ok=True)

    gerenciador, _mapas = carregar_ambiente(
        RAIZ / "dados" / "dispositivos.yaml",
        RAIZ / "dados" / "mapa-de-registros.yaml",
    )
    servidor = ServidorModbus(gerenciador, porta=0)
    servidor.iniciar()
    porta = servidor.porta_em_uso

    mapa = str(RAIZ / "dados" / "mapa-de-registros.yaml")
    dispositivos = str(RAIZ / "dados" / "dispositivos.yaml")

    try:
        _cod, varredura = rodar_cli([
            "varrer", "--porta", str(porta),
            "--de", IDS, "--ate", ATE, "--timeout", "3",
        ])

        _cod, leitura = rodar_cli([
            "ler", "--porta", str(porta),
            "--de", IDS, "--ate", ATE, "--timeout", "3",
            "--mapa", mapa, "--dispositivos", dispositivos,
        ])

        _cod, mapa_saida = rodar_cli([
            "mapa", "--mapa", mapa, "--dispositivos", dispositivos,
        ])
    finally:
        servidor.parar()

    # A porta efemera nao pode vazar para o arquivo: o exemplo precisa ser
    # identico a cada execucao para o gate do CI passar.
    varredura = normalizar_porta(varredura, porta)
    leitura = normalizar_porta(leitura, porta)
    mapa_saida = normalizar_porta(mapa_saida, porta)

    if "11" in leitura and "negativa" not in leitura:
        print("FALHOU: a leitura nao traz a sequencia de fase invertida")
        return 1
    if "Devices encontrados: 3" not in varredura:
        print("FALHOU: a varredura nao encontrou os 3 medidores")
        return 1

    cabecalho = (
        "# Leitura de consumo por Modbus TCP\n\n"
        "Gerado por `python tools/gerar_exemplos.py`. O servidor de lab sobe\n"
        "numa porta livre e o consumo e lido **pela rede**, nao do objeto que\n"
        "originou os valores. Nada aqui foi escrito a mao.\n\n"
        "O lab planta 3 medidores, a varredura encontra os 3, e o medidor\n"
        "trifasico esta com a sequencia de fase invertida de proposito.\n\n"
    )

    (EXEMPLOS / "leitura-consumo.txt").write_text(
        cabecalho
        + "## 1. Varredura do barramento\n\n```\n"
        + "PS> python -m modbuslab varrer --porta 5020 --de 1 --ate 3\n"
        + varredura + "```\n\n"
        + "## 2. Leitura de consumo pela rede\n\n```\n"
        + "PS> python -m modbuslab ler --porta 5020 --de 1 --ate 3\n"
        + leitura + "```\n\n"
        + "## 3. Mapa de registradores\n\n```\n"
        + "PS> python -m modbuslab mapa\n"
        + mapa_saida + "```\n",
        encoding="utf-8",
    )

    print(f"exemplos regravados em {EXEMPLOS}")
    for nome in sorted(p.name for p in EXEMPLOS.iterdir() if p.is_file()):
        tamanho = (EXEMPLOS / nome).stat().st_size
        print(f"  {nome:<28} {tamanho:>7} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())