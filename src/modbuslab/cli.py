"""CLI do modbuslab: servidor, varredura e leitura de consumo.

CLI entry point: serve the lab, sweep the bus, read consumption over Modbus.

O comando ``ler`` monta o consumo a partir de registradores lidos **pela rede**.
Ele nao importa o objeto do medidor para isso. A distincao e o ponto do
projeto: um consumo calculado a partir do processo que gerou os numeros nao
demonstra nada sobre o protocolo, so sobre a aritmetica.

Para ler os valores de engenharia, o cliente precisa saber quantos registradores
existem em cada endereco e qual a escala de cada um. Isso vem do mapa, e o mapa
e documentacao: e a parte que todo cliente Modbus real carrega junto, porque o
protocolo nao diz o que um registrador significa.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .consumo import ResultadoConsumo, calcular
from .dispositivos import carregar_ambiente
from .protocolo import FC_READ_HOLDING, ExcecaoRemota, QuadroInvalido
from .registros import MapaDeRegistros, tabela_do_mapa
from .scanner import ClienteModbus, ScannerModbus
from .servidor import ServidorModbus, descrever_servidor

#: Caminhos padrao dos arquivos de dados.
MAPA_PADRAO = "dados/mapa-de-registros.yaml"
DISPOSITIVOS_PADRAO = "dados/dispositivos.yaml"


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def ler_dispositivo(
    cliente: ClienteModbus,
    unit_id: int,
    mapa: MapaDeRegistros,
    funcao: int = FC_READ_HOLDING,
) -> dict[str, float]:
    """Le um dispositivo inteiro pela rede e devolve os valores de engenharia.

    Read one device over the network and return engineering values.

    A leitura vem em bloco, do endereco zero ate o fim do mapa. Cada valor bruto
    e convertido pela escala do registrador daquele endereco.

    Registrador de 32 bits ocupa dois enderecos, entao as duas palavras entram
    juntas na conversao. Ler so a palavra alta daria metade do valor, e um
    medidor de energia com leitura pela metade e um medidor quebrado.

    Args:
        cliente: Cliente ja conectado.
        unit_id: Endereco do dispositivo.
        mapa: Mapa de registradores do dispositivo.
        funcao: Funcao de leitura.

    Returns:
        Mapa de nome de registrador para valor de engenharia.

    Raises:
        ExcecaoRemota: Se o dispositivo recusar a leitura.
        QuadroInvalido: Se a resposta vier malformada.
    """
    tamanho = mapa.tamanho
    brutos = cliente.ler(unit_id, 0, mapa.tamanho, funcao)

    dados: dict[str, float] = {}
    for reg in mapa.ordenar_por_endereco():
        palavras = brutos[reg.endereco:reg.endereco + reg.palavras]
        if len(palavras) < reg.palavras:
            # O bloco veio curto: o dispositivo nao expoe este registrador.
            continue
        dados[reg.nome] = reg.engenharia(palavras)
    return dados


def montar_tabela_consumo(
    leituras: list[tuple[int, str, str, ResultadoConsumo]],
) -> str:
    """Monta a tabela de consumo em texto.

    Render the consumption table.

    Args:
        leituras: Tuplas de unit id, nome, tipo e resultado.

    Returns:
        Tabela em texto.
    """
    cabecalho = (
        f"{'ID':>3}  {'Dispositivo':<16} {'Tipo':<20} {'V':>7} {'A':>7} "
        f"{'W':>8} {'var':>7} {'FP':>6} {'kWh':>9}  Fases"
    )
    linhas = [cabecalho, "-" * len(cabecalho)]
    for unit_id, nome, tipo, r in leituras:
        sequencia = f" ({r.sequencia_fase})" if r.sequencia_fase else ""
        linhas.append(
            f"{unit_id:>3}  {nome:<16} {tipo:<20} {r.tensao_v:>7.1f} "
            f"{r.corrente_a:>7.2f} {r.potencia_ativa_w:>8.0f} "
            f"{r.potencia_reativa_var:>7.0f} {r.fator_potencia:>6.3f} "
            f"{r.energia_kwh:>9.1f}  {r.fases}{sequencia}"
        )
    return "\n".join(linhas)


def montar_registros(
    leituras: list[tuple[int, str, str, ResultadoConsumo]],
    dados_por_dispositivo: dict[int, dict[str, float]],
    gerenciador,
) -> str:
    """Monta o detalhamento de registradores por dispositivo.

    Render the per-device register detail.

    Args:
        leituras: Leituras ja calculadas.
        dados_por_dispositivo: Valores de engenharia lidos, por unit id.
        gerenciador: Gerenciador de dispositivos. O mapa de registradores vem
            do proprio dispositivo, e nao de um indice por nome de mapa: o
            nome do medidor e o nome do mapa sao coisas diferentes, e buscar um
            pelo outro devolve vazio sem avisar.

    Returns:
        Bloco de texto com os registradores de cada medidor.
    """
    blocos: list[str] = []
    for unit_id, nome, _tipo, r in leituras:
        dados = dados_por_dispositivo.get(unit_id, {})
        dispositivo = gerenciador.buscar(unit_id)
        blocos.append(f"\nDispositivo {unit_id} ({nome}):")
        blocos.append(
            f"  {'End':>4}  {'Registrador':<20} {'Bruto':>8}  Valor"
        )
        blocos.append(
            f"  {'-' * 4}  {'-' * 20} {'-' * 8}  {'-' * 14}"
        )
        if dispositivo is None:
            blocos.append("  dispositivo nao encontrado")
            continue
        for reg in dispositivo.mapa.ordenar_por_endereco():
            valor = dados.get(reg.nome, 0.0)
            palavras = reg.brutos(valor)
            bruto = (
                " ".join(f"{p:04X}" for p in palavras)
                if len(palavras) > 1
                else str(palavras[0])
            )
            unidade = f" {reg.unidade}" if reg.unidade else ""
            blocos.append(
                f"  {reg.endereco:>4}  {reg.nome:<20} {bruto:>8}  "
                f"{valor:g}{unidade}"
            )
        if r.alertas:
            blocos.append("  Alertas:")
            for alerta in r.alertas:
                blocos.append(f"    - {alerta}")
    return "\n".join(blocos)


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def _cmd_servidor(args: argparse.Namespace) -> int:
    """Sobe o servidor Modbus TCP.

    Start the Modbus TCP server.
    """
    gerenciador, _mapa = carregar_ambiente(args.dispositivos, args.mapa)

    servidor = ServidorModbus(gerenciador, host=args.host, porta=args.porta)
    servidor.iniciar()

    print(descrever_servidor(servidor))
    print("Funcao 3 (holding) e 4 (input) / functions 3 and 4")
    for d in gerenciador.dispositivos:
        print(f"  unit id {d.id}: {d.nome} ({d.tipo}), "
              f"{d.mapa.tamanho} registradores")
    print("CTRL+C para encerrar / press CTRL+C to stop")

    try:
        while servidor.rodando:
            servidor._parar.wait(0.5)
    except KeyboardInterrupt:
        print("\nEncerrando / stopping...")
    finally:
        servidor.parar()
    return 0


def _cmd_varrer(args: argparse.Namespace) -> int:
    """Varre o barramento e lista quem responde.

    Sweep the bus and list who answers.
    """
    scanner = ScannerModbus(
        host=args.host, porta=args.porta, timeout=args.timeout
    )
    ids = _intervalo_ids(args)
    try:
        resultado = scanner.varrer_intervalo(ids)
    except OSError as exc:
        print(f"Erro / error: {exc}", file=sys.stderr)
        return 3

    print(f"Varredura em {args.host}:{args.porta} / bus sweep")
    print(f"Unit ids sondados: {len(ids)}")
    print()

    if not resultado.devices:
        print("Nenhum device respondeu / no device answered")
        return 0

    print(f"{'Unit':>5}  {'Respondeu':<10} {'Funcao':>7}  {'Registrador 0':>14}  Observacao")
    print(f"{'-' * 5}  {'-' * 10} {'-' * 7}  {'-' * 14}  {'-' * 26}")
    for d in resultado.devices:
        if d.tem_registrador_zero:
            nota = f"valor bruto {d.valores[0]}"
        elif d.excecao is not None:
            nota = f"excecao {d.excecao}"
        else:
            nota = d.erro or "sem dados"
        print(f"{d.unit_id:>5}  {'sim':<10} {d.funcao:>7}  "
              f"{(d.valores[0] if d.valores else '-'):>14}  {nota}")

    print()
    print(f"Devices encontrados: {resultado.total_respondidos} de {len(ids)} sondados")
    return 0


def _cmd_ler(args: argparse.Namespace) -> int:
    """Le o consumo dos medidores pela rede.

    Read consumption from the meters over the network.
    """
    gerenciador, _mapas = _carregar_dados(args)

    scanner = ScannerModbus(
        host=args.host, porta=args.porta, timeout=args.timeout
    )
    ids = _intervalo_ids(args)

    cliente = ClienteModbus(args.host, args.porta, args.timeout)
    leituras: list[tuple[int, str, str, ResultadoConsumo]] = []
    dados_por_dispositivo: dict[int, dict[str, float]] = {}
    falhas: list[str] = []

    try:
        cliente.conectar()
        for unit_id in ids:
            dispositivo = gerenciador.buscar(unit_id)
            if dispositivo is None:
                continue
            try:
                dados = ler_dispositivo(
                    cliente, unit_id, dispositivo.mapa, FC_READ_HOLDING
                )
            except (ExcecaoRemota, QuadroInvalido, OSError) as exc:
                falhas.append(f"unit id {unit_id}: {exc}")
                continue
            dados_por_dispositivo[unit_id] = dados
            leituras.append((
                unit_id,
                dispositivo.nome,
                dispositivo.tipo,
                calcular(dados, numero_fases=dispositivo.fases),
            ))
    except OSError as exc:
        print(f"Erro / error: nao foi possivel falar com {args.host}:{args.porta}: {exc}",
              file=sys.stderr)
        return 3
    finally:
        cliente.fechar()

    linhas: list[str] = []
    linhas.append("# Leitura de consumo por Modbus TCP")
    linhas.append(f"# host / port: {args.host}:{args.porta}")
    linhas.append(f"# mapa / map: {args.mapa}")
    linhas.append("# valores lidos pela rede / values read over the network")
    linhas.append("")

    if not leituras:
        linhas.append("Nenhum medidor respondeu / no meter answered")
    else:
        linhas.append(montar_tabela_consumo(leituras))
        linhas.append("")
        linhas.append(montar_registros(leituras, dados_por_dispositivo, gerenciador))

    if falhas:
        linhas.append("")
        linhas.append("Falhas de leitura / read failures:")
        linhas.extend(f"  - {f}" for f in falhas)

    saida = "\n".join(linhas) + "\n"

    if args.saida:
        destino = Path(args.saida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(saida, encoding="utf-8")
        print(f"Saida gravada em: {destino}")
    else:
        print(saida, end="")
    return 0


def _cmd_mapa(args: argparse.Namespace) -> int:
    """Mostra o mapa de registradores.

    Show the register map.
    """
    _gerenciador, mapas = carregar_ambiente(args.dispositivos, args.mapa)
    if args.nome:
        mapa = mapas.get(args.nome)
        if mapa is None:
            print(f"mapa desconhecido: {args.nome}. "
                  f"Disponiveis: {', '.join(sorted(mapas))}", file=sys.stderr)
            return 2
        print(f"Mapa {mapa.nome}")
        print(tabela_do_mapa(mapa))
        return 0
    for nome in sorted(mapas):
        print(f"\n=== {nome} ===")
        print(tabela_do_mapa(mapas[nome]))
    return 0


def _carregar_dados(args: argparse.Namespace):
    """Carrega mapa e dispositivos de configuracao.

    Load the register map and the configured devices.

    Returns:
        Par com o gerenciador e os mapas.
    """
    return carregar_ambiente(args.dispositivos, args.mapa)


def _intervalo_ids(args: argparse.Namespace) -> range:
    """Monta o intervalo de unit ids a sondar.

    Build the unit-id range to probe.

    Returns:
        Intervalo de unit ids.

    Raises:
        ValueError: Se ``--ate`` for menor que ``--de``.
    """
    inicio = int(args.de)
    fim = int(args.ate)
    if fim < inicio:
        raise ValueError(f"--ate ({fim}) menor que --de ({inicio})")
    return range(inicio, fim + 1)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _comum(p: argparse.ArgumentParser) -> None:
    """Argumentos comuns aos comandos que falam com o barramento.

    Arguments shared by the commands that talk to the bus.
    """
    p.add_argument("--host", default="127.0.0.1", help="Host do servidor")
    p.add_argument("--porta", type=int, default=5020, help="Porta TCP")
    p.add_argument("--timeout", type=float, default=0.5,
                   help="Tempo limite por requisicao, em segundos")
    p.add_argument("--de", type=int, default=1,
                   help="Primeiro unit id da varredura")
    p.add_argument("--ate", type=int, default=20,
                   help="Ultimo unit id da varredura")


def construir_parser() -> argparse.ArgumentParser:
    """Monta o parser de argumentos.

    Build the argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="modbuslab",
        description=(
            "Servidor Modbus TCP simulado com medidores de energia e scanner "
            "de barramento. Somente loopback. "
            "Simulated Modbus TCP server with energy meters and a bus scanner. "
            "Loopback only."
        ),
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p_serv = sub.add_parser("servidor", help="Sobe o servidor Modbus TCP")
    p_serv.add_argument("--host", default="127.0.0.1")
    p_serv.add_argument("--porta", type=int, default=5020)
    p_serv.add_argument("--mapa", default=MAPA_PADRAO)
    p_serv.add_argument("--dispositivos", default=DISPOSITIVOS_PADRAO)
    p_serv.set_defaults(func=_cmd_servidor)

    p_var = sub.add_parser("varrer", help="Varre o barramento e lista quem responde")
    _comum(p_var)
    p_var.set_defaults(func=_cmd_varrer)

    p_ler = sub.add_parser("ler", help="Le o consumo pela rede")
    _comum(p_ler)
    p_ler.add_argument("--mapa", default=MAPA_PADRAO)
    p_ler.add_argument("--dispositivos", default=DISPOSITIVOS_PADRAO)
    p_ler.add_argument("--saida", default=None, help="Grava a leitura neste caminho")
    p_ler.set_defaults(func=_cmd_ler)

    p_mapa = sub.add_parser("mapa", help="Mostra o mapa de registradores")
    p_mapa.add_argument("--mapa", default=MAPA_PADRAO)
    p_mapa.add_argument("--dispositivos", default=DISPOSITIVOS_PADRAO)
    p_mapa.add_argument("--nome", default=None, help="Mapa a mostrar")
    p_mapa.set_defaults(func=_cmd_mapa)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada da CLI.

    CLI entry point.

    Args:
        argv: Argumentos. Padrao: ``sys.argv[1:]``.

    Returns:
        ``0`` em sucesso, ``2`` para erro de uso ou de dados, ``3`` quando o
        servidor nao responde.
    """
    parser = construir_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError) as exc:
        print(f"Erro / error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrompido / interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())