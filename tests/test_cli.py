"""Testes da linha de comando.

CLI tests.

O comando `ler` so pode ser considered correto se o consumo que ele mostra veio
pela rede. Estes testes sobem um servidor de verdade e conferem que a saida bate
com os registradores do medidor, e nao com o objeto local que os originou.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from modbuslab.cli import (
    construir_parser,
    ler_dispositivo,
    main,
    montar_registros,
    montar_tabela_consumo,
)
from modbuslab.consumo import calcular
from modbuslab.dispositivos import GerenciadorDispositivos, carregar_ambiente
from modbuslab.protocolo import FC_READ_HOLDING
from modbuslab.scanner import ClienteModbus
from modbuslab.servidor import ServidorModbus, descrever_servidor

RAIZ = Path(__file__).resolve().parent.parent
MAPA = str(RAIZ / "dados" / "mapa-de-registros.yaml")
DISPOSITIVOS = str(RAIZ / "dados" / "dispositivos.yaml")


@pytest.fixture(scope="module")
def lab() -> Iterator[str]:
    """Servidor real em porta livre.

    Real server on a free port.
    """
    gerenciador, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
    servidor = ServidorModbus(gerenciador, porta=0)
    servidor.iniciar()
    try:
        yield str(servidor.porta_em_uso)
    finally:
        servidor.parar()


def argumentos_ler(porta: str, extra: list[str] | None = None) -> list[str]:
    """Monta os argumentos do comando `ler`.

    Build the arguments for the read command.
    """
    base = [
        "ler", "--porta", porta, "--de", "1", "--ate", "3",
        "--timeout", "3", "--mapa", MAPA, "--dispositivos", DISPOSITIVOS,
    ]
    return base + (extra or [])


class TestLerConsumo:
    """O comando de leitura, ponta a ponta."""

    def test_le_os_tres_medidores(self, lab: str, capsys) -> None:
        assert main(argumentos_ler(lab)) == 0
        saida = capsys.readouterr().out
        assert "medidor-1pn" in saida
        assert "medidor-3pn" in saida
        assert "medidor-demanda" in saida

    def test_consumo_vem_dos_registradores(self, lab: str, capsys) -> None:
        main(argumentos_ler(lab))
        saida = capsys.readouterr().out
        # 2430 W do medidor 1pn, lido pela rede e convertido pela escala.
        assert "2430" in saida
        assert "219.4" in saida

    def test_energia_de_32_bits_appears(self, lab: str, capsys) -> None:
        main(argumentos_ler(lab))
        saida = capsys.readouterr().out
        # 412880 kWh nao cabe em uint16.
        assert "412880" in saida

    def test_marca_a_leitura_pela_rede(self, lab: str, capsys) -> None:
        main(argumentos_ler(lab))
        assert "pela rede" in capsys.readouterr().out

    def test_mostra_a_sequencia_de_fase(self, lab: str, capsys) -> None:
        main(argumentos_ler(lab))
        assert "negativa" in capsys.readouterr().out

    def test_mostra_o_alerta_de_fase(self, lab: str, capsys) -> None:
        main(argumentos_ler(lab))
        assert "invertida" in capsys.readouterr().out

    def test_mostra_os_brutos(self, lab: str, capsys) -> None:
        main(argumentos_ler(lab))
        saida = capsys.readouterr().out
        # 2194 no fio, 219,4 V em engenharia.
        assert "2194" in saida

    def test_grava_em_arquivo(self, lab: str, tmp_path: Path) -> None:
        destino = tmp_path / "sub" / "leitura.txt"
        assert main(argumentos_ler(lab, ["--saida", str(destino)])) == 0
        texto = destino.read_text(encoding="utf-8")
        assert "medidor-3pn" in texto
        assert "negativa" in texto

    def test_saida_e_utf8_valido(self, lab: str, tmp_path: Path) -> None:
        destino = tmp_path / "leitura.txt"
        main(argumentos_ler(lab, ["--saida", str(destino)]))
        bruto = destino.read_bytes()
        assert not any(b == 0xFF for b in bruto)
        bruto.decode("utf-8")

    def test_intervalo_reduzido(self, lab: str, capsys) -> None:
        assert main([
            "ler", "--porta", lab, "--de", "2", "--ate", "2",
            "--timeout", "3", "--mapa", MAPA, "--dispositivos", DISPOSITIVOS,
        ]) == 0
        saida = capsys.readouterr().out
        assert "medidor-3pn" in saida
        assert "medidor-1pn" not in saida

    def test_intervalo_vazio(self, lab: str, capsys) -> None:
        assert main([
            "ler", "--porta", lab, "--de", "8", "--ate", "9",
            "--timeout", "0.3", "--mapa", MAPA, "--dispositivos", DISPOSITIVOS,
        ]) == 0
        assert "Nenhum medidor respondeu" in capsys.readouterr().out

    def test_servidor_fora_do_ar(self, tmp_path: Path, capsys) -> None:
        g, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
        s = ServidorModbus(g, porta=0)
        s.iniciar()
        porta = s.porta_em_uso
        s.parar()
        codigo = main(argumentos_ler(str(porta)))
        assert codigo == 3
        assert "nao foi possivel falar" in capsys.readouterr().err


class TestVarrer:
    """O comando de varredura."""

    def test_encontra_os_medidores(self, lab: str, capsys) -> None:
        assert main(["varrer", "--porta", lab, "--de", "1", "--ate", "3",
                     "--timeout", "3"]) == 0
        saida = capsys.readouterr().out
        assert "Devices encontrados: 3" in saida

    def test_mostra_o_registrador_zero(self, lab: str, capsys) -> None:
        main(["varrer", "--porta", lab, "--de", "1", "--ate", "1", "--timeout", "3"])
        assert "2194" in capsys.readouterr().out

    def test_sem_device(self, lab: str, capsys) -> None:
        # Intervalo sem nenhum device e sinal de que o servidor nao atende,
        # nao de que o barramento esta vazio. A saida e codigo 3.
        assert main(["varrer", "--porta", lab, "--de", "8", "--ate", "9",
                     "--timeout", "0.3"]) == 3
        assert "nenhum device respondeu" in capsys.readouterr().err

    def test_servidor_fora_do_ar(self, capsys) -> None:
        g, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
        s = ServidorModbus(g, porta=0)
        s.iniciar()
        porta = s.porta_em_uso
        s.parar()
        assert main(["varrer", "--porta", str(porta), "--de", "1", "--ate", "2",
                     "--timeout", "0.3"]) == 3
        assert "Erro" in capsys.readouterr().err


class TestMapa:
    """O comando de mapa."""

    def test_mostra_todos(self, capsys) -> None:
        assert main(["mapa", "--mapa", MAPA, "--dispositivos", DISPOSITIVOS]) == 0
        saida = capsys.readouterr().out
        assert "medidor_1pn" in saida
        assert "medidor_3pn" in saida
        assert "medidor_demanda" in saida

    def test_mostra_um_mapa(self, capsys) -> None:
        assert main(["mapa", "--mapa", MAPA, "--dispositivos", DISPOSITIVOS,
                     "--nome", "medidor_3pn"]) == 0
        saida = capsys.readouterr().out
        assert "angulo_l2" in saida
        assert "medidor_1pn" not in saida

    def test_mapa_desconhecido(self, capsys) -> None:
        assert main(["mapa", "--mapa", MAPA, "--dispositivos", DISPOSITIVOS,
                     "--nome", "nao_existe"]) == 2
        assert "mapa desconhecido" in capsys.readouterr().err

    def test_mostra_a_largura(self, capsys) -> None:
        main(["mapa", "--mapa", MAPA, "--dispositivos", DISPOSITIVOS,
              "--nome", "medidor_1pn"])
        assert "uint32" in capsys.readouterr().out


class TestParser:
    """Parsing de argumentos."""

    def test_padroes_do_servidor(self) -> None:
        args = construir_parser().parse_args(["servidor"])
        assert args.porta == 5020
        assert args.host == "127.0.0.1"

    def test_padroes_do_ler(self) -> None:
        args = construir_parser().parse_args(["ler"])
        assert args.de == 1
        assert args.ate == 20
        assert args.saida is None

    def test_ajuda(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0

    @pytest.mark.parametrize("comando", ["servidor", "varrer", "ler", "mapa"])
    def test_ajuda_de_cada_comando(self, comando: str) -> None:
        with pytest.raises(SystemExit) as exc:
            main([comando, "--help"])
        assert exc.value.code == 0

    def test_sem_subcomando(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code != 0

    def test_subcomando_desconhecido(self) -> None:
        with pytest.raises(SystemExit):
            main(["nao_existe"])

    def test_porta_invalida(self) -> None:
        with pytest.raises(SystemExit):
            main(["servidor", "--porta", "abc"])

    def test_ate_menor_que_de(self, capsys) -> None:
        codigo = main(["ler", "--de", "5", "--ate", "2"])
        assert codigo == 2
        assert "Erro" in capsys.readouterr().err

    def test_mapa_inexistente(self, capsys) -> None:
        codigo = main(["mapa", "--mapa", "nao_existe.yaml",
                       "--dispositivos", DISPOSITIVOS])
        assert codigo == 2


class TestLerDispositivo:
    """A funcao que traduz palavras do fio em valores de engenharia."""

    @pytest.fixture(scope="class")
    @staticmethod
    def ambiente() -> tuple:
        """Gerenciador e mapas carregados do disco.

        Manager and maps loaded from disk.
        """
        return carregar_ambiente(DISPOSITIVOS, MAPA)

    @pytest.fixture(scope="class")
    @staticmethod
    def cliente(lab: str) -> Iterator[ClienteModbus]:
        c = ClienteModbus("127.0.0.1", int(lab), 3.0)
        c.conectar()
        try:
            yield c
        finally:
            c.fechar()

    def test_le_todos_os_registradores(self, cliente, ambiente) -> None:
        g, mapas = ambiente
        dados = ler_dispositivo(cliente, 1, mapas["medidor_1pn"])
        assert len(dados) == len(mapas["medidor_1pn"].registradores)

    def test_converte_escala(self, cliente, ambiente) -> None:
        _, mapas = ambiente
        dados = ler_dispositivo(cliente, 1, mapas["medidor_1pn"])
        assert dados["tensao"] == pytest.approx(219.4)
        assert dados["corrente"] == pytest.approx(12.35)
        assert dados["frequencia"] == pytest.approx(60.01)

    def test_converte_fator_de_potencia(self, cliente, ambiente) -> None:
        _, mapas = ambiente
        dados = ler_dispositivo(cliente, 1, mapas["medidor_1pn"])
        assert dados["fator_potencia"] == pytest.approx(0.939)

    def test_converte_registrador_largo(self, cliente, ambiente) -> None:
        _, mapas = ambiente
        dados = ler_dispositivo(cliente, 2, mapas["medidor_3pn"])
        assert dados["energia"] == pytest.approx(91240.0)

    def test_energia_acumulada_larga(self, cliente, ambiente) -> None:
        _, mapas = ambiente
        dados = ler_dispositivo(cliente, 3, mapas["medidor_demanda"])
        assert dados["energia_acumulada"] == pytest.approx(412880.0)

    def test_calcula_consumo_com_os_valores_da_rede(self, cliente, ambiente) -> None:
        g, mapas = ambiente
        disp = g.buscar(2)
        dados = ler_dispositivo(cliente, 2, mapas["medidor_3pn"])
        r = calcular(dados, numero_fases=disp.fases)
        assert r.potencia_ativa_w == pytest.approx(10980.0)
        assert r.sequencia_invertida is True

    def test_funcao_escolhida(self, cliente, ambiente) -> None:
        _, mapas = ambiente
        # Holding e input devolvem o mesmo valor nos dois casos.
        a = ler_dispositivo(cliente, 1, mapas["medidor_1pn"], FC_READ_HOLDING)
        b = ler_dispositivo(cliente, 1, mapas["medidor_1pn"], 0x04)
        assert a == b


class TestFormatacao:
    """Montagem dos blocos de texto."""

    @pytest.fixture(scope="class")
    @staticmethod
    def leituras(lab: str) -> list[tuple]:
        g, mapas = carregar_ambiente(DISPOSITIVOS, MAPA)
        c = ClienteModbus("127.0.0.1", int(lab), 3.0)
        c.conectar()
        saida = []
        try:
            for uid in g.unit_ids:
                disp = g.buscar(uid)
                dados = ler_dispositivo(c, uid, disp.mapa)
                saida.append((uid, disp.nome, disp.tipo,
                              calcular(dados, numero_fases=disp.fases)))
        finally:
            c.fechar()
        return saida

    def test_tabela_tem_cabecalho(self, leituras: list[tuple]) -> None:
        tabela = montar_tabela_consumo(leituras)
        assert "Dispositivo" in tabela
        assert "kWh" in tabela

    def test_tabela_uma_linha_por_medidor(self, leituras: list[tuple]) -> None:
        linhas = [l for l in montar_tabela_consumo(leituras).splitlines()[2:] if l]
        assert len(linhas) == 3

    def test_tabela_mostra_a_sequencia(self, leituras: list[tuple]) -> None:
        assert "negativa" in montar_tabela_consumo(leituras)

    def test_registros_um_bloco_por_medidor(self, leituras: list[tuple]) -> None:
        g, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
        texto = montar_registros(leituras, {1: {"tensao": 219.4}}, g)
        assert "Dispositivo 1" in texto
        assert "Dispositivo 3" in texto

    def test_registros_mostra_bruto_e_valor(self) -> None:
        g, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
        leitura = (1, "medidor-1pn", "medidor monofasico", calcular({}))
        texto = montar_registros([leitura], {1: {"tensao": 219.4}}, g)
        # 2194 no fio, 219,4 V em engenharia.
        assert "2194" in texto
        assert "219.4" in texto

    def test_registros_largo_em_duas_palavras(self) -> None:
        g, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
        leitura = (2, "medidor-3pn", "medidor trifasico", calcular({}))
        texto = montar_registros([leitura], {2: {"energia": 91240.0}}, g)
        # 91240 = 0x00016468, palavra alta primeiro.
        assert "0001" in texto and "6468" in texto

    def test_registros_com_dispositivo_ausente(self) -> None:
        leitura = (9, "x", "y", calcular({}))
        texto = montar_registros([leitura], {}, GerenciadorDispositivos())
        assert "nao encontrado" in texto


class TestDescreverServidor:
    """Identidade do servidor."""

    def test_descreve_host_e_porta(self) -> None:
        g, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
        s = ServidorModbus(g, porta=0)
        texto = descrever_servidor(s)
        assert "127.0.0.1" in texto
        assert "3 medidor" in texto

    def test_nao_exige_servidor_no_ar(self) -> None:
        g, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
        assert "5020" in descrever_servidor(ServidorModbus(g))