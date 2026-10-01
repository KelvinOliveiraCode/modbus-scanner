"""Prova de aceite do modbuslab.

Acceptance proof for modbuslab.

O criterio de aceite da especificacao tem tres partes:

1. o scanner le os tres medidores;
2. ele identifica a sequencia de fase invertida no medidor trifasico;
3. o consumo calculado bate com o valor dos registradores lidos pela rede.

Roda fora do pytest de proposito. A suite cobre as funcoes; este script cobre
a pergunta que a suite nao responde sozinha: o fluxo inteiro, do servidor de
lab ao calculo de consumo, ainda entrega os tres medidores, ainda acha a
sequencia invertida e ainda bate com o que esta na rede.

Sobe um servidor em porta livre, varre o barramento, le cada medidor por
Modbus TCP e compara o consumo calculado com os registradores do medidor.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Permite executar o script direto do checkout, sem instalar o pacote.
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from modbuslab.cli import ler_dispositivo  # noqa: E402
from modbuslab.consumo import SEQUENCIA_NEGATIVA, calcular  # noqa: E402
from modbuslab.dispositivos import carregar_ambiente  # noqa: E402
from modbuslab.scanner import ClienteModbus, ScannerModbus  # noqa: E402
from modbuslab.servidor import ServidorModbus  # noqa: E402

#: Quantos medidores o lab planta.
TOTAL_ESPERADO = 3

#: Unit ids que a varredura deve encontrar.
UNIT_IDS_ESPERADOS = [1, 2, 3]


def main() -> int:
    """Sobe o lab, varre, le e compara com o esperado.

    Start the lab, sweep, read and compare against the expectation.
    """
    gerenciador, _mapas = carregar_ambiente(
        RAIZ / "dados" / "dispositivos.yaml",
        RAIZ / "dados" / "mapa-de-registros.yaml",
    )
    servidor = ServidorModbus(gerenciador, porta=0)
    servidor.iniciar()
    porta = servidor.porta_em_uso
    print(f"servidor em 127.0.0.1:{porta} com {len(gerenciador)} medidores")

    falhas: list[str] = []

    try:
        # 1. O scanner encontra os tres medidores sem conhecer a lista.
        scanner = ScannerModbus("127.0.0.1", porta, timeout=2.0)
        varredura = scanner.varrer_intervalo(range(1, 6))
        encontrados = [d.unit_id for d in varredura.devices]
        print(f"\nvarredura encontrou: {encontrados}")
        if encontrados != UNIT_IDS_ESPERADOS:
            falhas.append(
                f"varredura achou {encontrados}, esperava {UNIT_IDS_ESPERADOS}"
            )

        # 2 e 3. Le por Modbus TCP e compara com os registradores do medidor.
        cliente = ClienteModbus("127.0.0.1", porta, 5.0)
        cliente.conectar()
        try:
            for unit_id in gerenciador.unit_ids:
                dispositivo = gerenciador.buscar(unit_id)
                dados = ler_dispositivo(cliente, unit_id, dispositivo.mapa)
                resultado = calcular(dados, numero_fases=dispositivo.fases)
                print(
                    f"\nunit {unit_id} {dispositivo.nome}"
                    f" ({dispositivo.tipo}, {dispositivo.fases} fase(s))"
                )
                print(f"  V={resultado.tensao_v:.1f} V"
                      f"  A={resultado.corrente_a:.2f} A"
                      f"  P={resultado.potencia_ativa_w:.0f} W"
                      f"  FP={resultado.fator_potencia:.3f}"
                      f"  E={resultado.energia_kwh:.0f} kWh")
                if resultado.sequencia_fase:
                    print(f"  sequencia de fase: {resultado.sequencia_fase}")
                for alerta in resultado.alertas:
                    print(f"  ALERTA: {alerta}")

                # O consumo tem de bater com o registrador do medidor.
                chave = (
                    "potencia_ativa" if "potencia_ativa" in dados
                    else "demanda_ativa"
                )
                if abs(dados[chave] - resultado.potencia_ativa_w) > 1e-6:
                    falhas.append(
                        f"unit {unit_id}: {chave} lido {dados[chave]} "
                        f"diferente do consumo {resultado.potencia_ativa_w}"
                    )

                # E todo valor de engenharia tem de bater com o medidor.
                for nome, valor in dados.items():
                    esperado = dispositivo.valor(nome)
                    if abs(valor - esperado) > 1e-6:
                        falhas.append(
                            f"unit {unit_id}: {nome} lido {valor}, "
                            f"medidor tem {esperado}"
                        )

                if (
                    dispositivo.fases == 3
                    and resultado.sequencia_fase != SEQUENCIA_NEGATIVA
                ):
                    falhas.append(
                        f"unit {unit_id}: sequencia de fase deveria ser "
                        f"{SEQUENCIA_NEGATIVA}, veio {resultado.sequencia_fase}"
                    )
        finally:
            cliente.fechar()

        print(f"\n{len(gerenciador)} medidores lidos, "
              f"{servidor.requisicoes_atendidas} requisicoes atendidas, "
              f"{servidor.excecoes_emitidas} excecoes")
    finally:
        servidor.parar()

    if len(gerenciador) != TOTAL_ESPERADO:
        falhas.append(
            f"o lab planta {len(gerenciador)} medidores, esperava {TOTAL_ESPERADO}"
        )

    if falhas:
        print("\nFALHOU:")
        for f in falhas:
            print(f"  - {f}")
        return 1

    print(
        "\nok: os 3 medidores lidos pela rede, a sequencia de fase invertida "
        "identificada e o consumo batendo com os registradores"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())