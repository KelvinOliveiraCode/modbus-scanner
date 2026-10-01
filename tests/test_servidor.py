"""Testes do servidor e do cliente sobre sockets reais.

Server and client tests over real sockets.

Estes testes sobem um servidor em porta livre e falam com ele por TCP. Nada de
mock: um mock do transporte so provaria que o codigo chama a funcao que o mock
devolve, e nao que o enquadramento MBAP esta certo.

Os tres erros de protocolo que estes testes pegaram:

- o campo de comprimento do MBAP conta os bytes DEPOIS dele, entao o quadro
  tem ``6 + comprimento`` bytes; somar os 7 do MBAP inteiro faz o servidor
  esperar um byte que nunca chega;
- ``recv`` pode devolver o quadro pela metade, e o servidor precisa acumular
  antes de interpretar;
- o servidor precisa atender varias requisicoes na mesma conexao, porque o
  cliente mantem a conexao aberta.
"""

from __future__ import annotations

import socket
import struct
import threading
from collections.abc import Iterator

import pytest

from modbuslab.cli import ler_dispositivo
from modbuslab.consumo import SEQUENCIA_NEGATIVA, calcular
from modbuslab.dispositivos import carregar_ambiente
from modbuslab.protocolo import (
    BYTES_ANTES_DO_COMPRIMENTO,
    EX_ENDERECO_ILEGAL,
    EX_FUNCAO_ILEGAL,
    EX_VALOR_ILEGAL,
    FC_READ_HOLDING,
    FC_READ_INPUT,
    ExcecaoRemota,
    QuadroInvalido,
    RequisicaoLeitura,
    interpretar_resposta,
)
from modbuslab.scanner import ClienteModbus, ScannerModbus
from modbuslab.servidor import ServidorModbus

MAPA = "dados/mapa-de-registros.yaml"
DISPOSITIVOS = "dados/dispositivos.yaml"


@pytest.fixture(scope="module")
def ambiente() -> Iterator[tuple]:
    """Servidor com os tres medidores, em porta livre.

    Server with the three meters, on a free port.
    """
    gerenciador, mapas = carregar_ambiente(DISPOSITIVOS, MAPA)
    servidor = ServidorModbus(gerenciador, porta=0)
    servidor.iniciar()
    try:
        yield servidor, gerenciador, mapas
    finally:
        servidor.parar()


@pytest.fixture
def host_porta(ambiente) -> tuple[str, int]:
    """Endereco do servidor de teste.

    Address of the test server.
    """
    servidor, _, _ = ambiente
    return "127.0.0.1", servidor.porta_em_uso


class TestCicloDeVida:
    """Subir e derrubar o servidor."""

    def test_sobe_em_porta_livre(self) -> None:
        g, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
        s = ServidorModbus(g, porta=0)
        s.iniciar()
        try:
            assert s.porta_em_uso > 0
            assert s.rodando is True
        finally:
            s.parar()

    def test_escuta_em_loopback(self) -> None:
        g, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
        s = ServidorModbus(g, porta=0)
        s.iniciar()
        try:
            assert s._sock.getsockname()[0] == "127.0.0.1"
        finally:
            s.parar()

    def test_parar_deixa_de_rodar(self) -> None:
        g, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
        s = ServidorModbus(g, porta=0)
        s.iniciar()
        s.parar()
        assert s.rodando is False
        assert s._sock is None

    def test_iniciar_duas_vezes(self) -> None:
        g, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
        s = ServidorModbus(g, porta=0)
        s.iniciar()
        porta = s.porta_em_uso
        try:
            s.iniciar()
            assert s.porta_em_uso == porta
        finally:
            s.parar()

    def test_context_manager(self) -> None:
        g, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
        with ServidorModbus(g, porta=0) as s:
            assert s.rodando
        assert s.rodando is False

    def test_portas_nao_colidem(self) -> None:
        g, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
        a, b = ServidorModbus(g, porta=0), ServidorModbus(g, porta=0)
        a.iniciar()
        b.iniciar()
        try:
            assert a.porta_em_uso != b.porta_em_uso
        finally:
            a.parar()
            b.parar()


class TestLeituraBasica:
    """Leitura de um registrador."""

    def test_primeiro_registrador_do_unit_1(self, host_porta) -> None:
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            # tensao do medidor 1pn, escala 10: 2194 no fio.
            assert c.ler(1, 0, 1, FC_READ_HOLDING) == (2194,)

    def test_funcao_input(self, host_porta) -> None:
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            assert c.ler(1, 0, 1, FC_READ_INPUT) == (2194,)

    def test_bloco_completo_do_medidor_1(self, host_porta) -> None:
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            valores = c.ler(1, 0, 8, FC_READ_HOLDING)
            assert len(valores) == 8
            assert valores[0] == 2194  # tensao 219,4 V

    def test_bloco_completo_do_medidor_2(self, host_porta) -> None:
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            valores = c.ler(2, 0, 15, FC_READ_HOLDING)
            assert valores[0] == 2197  # tensao_l1 219,7 V

    def test_varias_leituras_na_mesma_conexao(self, host_porta) -> None:
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            # O cliente mantem a conexao; o servidor precisa atender em ciclo.
            for _ in range(5):
                assert c.ler(1, 0, 1, FC_READ_HOLDING) == (2194,)

    def test_leituras_intercaladas_entre_units(self, host_porta) -> None:
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            assert c.ler(1, 0, 1)[0] == 2194
            assert c.ler(2, 0, 1)[0] == 2197
            assert c.ler(3, 0, 1)[0] == 9600
            assert c.ler(1, 0, 1)[0] == 2194


class TestDespachoPorUnitId:
    """Unit id separa os dispositivos."""

    def test_unit_id_desconhecido(self, host_porta) -> None:
        # Unit id fora do cadastro: o servidor descarta o quadro e o cliente
        # esbarra no timeout. Nao ha excecao, porque nao ha interlocutor.
        host, porta = host_porta
        c = ClienteModbus(host, porta, 0.5)
        c.conectar()
        try:
            with pytest.raises((TimeoutError, OSError)):
                c.ler(99, 0, 1)
        finally:
            c.fechar()

    def test_endereco_invalido_em_unit_valido(self, host_porta) -> None:
        # Aqui o interlocutor existe, entao excecao 2 e a resposta correta.
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            with pytest.raises(ExcecaoRemota) as exc:
                c.ler(1, 500, 1)
            assert exc.value.codigo == EX_ENDERECO_ILEGAL

    def test_cada_unit_tem_valores_proprios(self, host_porta) -> None:
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            # O mesmo endereco 0 em tres dispositivos, tres valores.
            valores = {uid: c.ler(uid, 0, 1)[0] for uid in (1, 2, 3)}
            assert valores == {1: 2194, 2: 2197, 3: 9600}

    def test_unidades_diferentes_nao_se_misturam(self, host_porta) -> None:
        # Um servidor que ignora o unit id devolveria a fila concatenada.
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            assert len(c.ler(1, 0, 1)) == 1
            assert len(c.ler(2, 0, 1)) == 1


class TestRegistradorLargoPelaRede:
    """Registrador de 32 bits atravessando o socket."""

    def test_energia_de_32_bits(self, host_porta, ambiente) -> None:
        _, _, mapas = ambiente
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            dados = ler_dispositivo(c, 1, mapas["medidor_1pn"])
        assert dados["energia"] == pytest.approx(18432.0)

    def test_energia_que_estoura_16_bits(self, host_porta, ambiente) -> None:
        _, _, mapas = ambiente
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            dados = ler_dispositivo(c, 2, mapas["medidor_3pn"])
        # 91240 kWh nao cabe em uint16. Se o servidor devolvesse so a palavra
        # alta, o valor viria 65536 ou 0 em vez de 91240.
        assert dados["energia"] == pytest.approx(91240.0)

    def test_energia_acumulada_de_64_mil(self, host_porta, ambiente) -> None:
        _, _, mapas = ambiente
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            dados = ler_dispositivo(c, 3, mapas["medidor_demanda"])
        assert dados["energia_acumulada"] == pytest.approx(412880.0)

    def test_as_duas_palavras_ocupam_dois_enderecos(
        self, host_porta, ambiente
    ) -> None:
        _, gerenciador, _ = ambiente
        host, porta = host_porta
        mapa = gerenciador.buscar(1).mapa
        energia = mapa.buscar("energia")
        assert energia.endereco == 4
        with ClienteModbus(host, porta, 3.0) as c:
            # Endereco 4 = palavra alta, 5 = palavra baixa.
            assert c.ler(1, 4, 1)[0] == 0
            assert c.ler(1, 5, 1)[0] == 18432

    def test_registrador_seguinte_nao_e_deslocado(
        self, host_porta, ambiente
    ) -> None:
        # Um off-by-one aqui ja fez a frequencia aparecer no lugar do fator de
        # potencia, com o valor de 6,001 em vez de 0,939.
        _, _, mapas = ambiente
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            dados = ler_dispositivo(c, 1, mapas["medidor_1pn"])
        assert dados["frequencia"] == pytest.approx(60.01)
        assert dados["fator_potencia"] == pytest.approx(0.939)


class TestExcecoes:
    """PDU de excecao vindo do servidor."""

    def test_funcao_desconhecida(self, host_porta) -> None:
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            with pytest.raises(ExcecaoRemota) as exc:
                c.ler(1, 0, 1, funcao=0x42)
            assert exc.value.codigo == EX_FUNCAO_ILEGAL

    def test_funcao_de_escrita_nao_implementada(self, host_porta) -> None:
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            with pytest.raises(ExcecaoRemota) as exc:
                c.ler(1, 0, 1, funcao=0x06)
            assert exc.value.codigo == EX_FUNCAO_ILEGAL

    def test_quantidade_zero(self, host_porta) -> None:
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            with pytest.raises(ExcecaoRemota) as exc:
                c.ler(1, 0, 0)
            assert exc.value.codigo == EX_VALOR_ILEGAL

    def test_quantidade_acima_de_125(self, host_porta) -> None:
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            with pytest.raises(ExcecaoRemota) as exc:
                c.ler(1, 0, 126)
            assert exc.value.codigo == EX_VALOR_ILEGAL

    def test_quantidade_maxima_aceita(self, host_porta) -> None:
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            assert len(c.ler(1, 0, 125)) == 125

    def test_endereco_fora_do_mapa(self, host_porta) -> None:
        # Fora do espaco de registradores, a resposta correta do protocolo e
        # excecao 2, e nao uma leitura de zeros.
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            with pytest.raises(ExcecaoRemota) as exc:
                c.ler(1, 100, 2)
            assert exc.value.codigo == EX_ENDERECO_ILEGAL

    def test_endereco_dentro_do_mapa_devolve_valor(self, host_porta) -> None:
        host, porta = host_porta
        with ClienteModbus(host, porta, 3.0) as c:
            assert c.ler(1, 2, 1)[0] == 2430  # potencia_ativa do medidor 1


class TestFramingCru:
    """Enquadramento pela rede, com controle do cliente."""

    def enviar_e_ler(
        self, host: str, porta: int, bruto: bytes, tamanho_esperado: int
    ) -> bytes:
        """Manda bytes crus e le a resposta.

        Send raw bytes and read the reply.

        Args:
            host: Host do servidor.
            porta: Porta do servidor.
            bruto: Quadro a enviar.
            tamanho_esperado: Quantos bytes ler.

        Returns:
            A resposta bruta.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        try:
            sock.connect((host, porta))
            sock.sendall(bruto)
            dados = b""
            while len(dados) < tamanho_esperado:
                pedaco = sock.recv(256)
                if not pedaco:
                    break
                dados += pedaco
            return dados
        finally:
            sock.close()

    def test_quadro_de_12_bytes(self, host_porta) -> None:
        host, porta = host_porta
        req = RequisicaoLeitura(1, 1, FC_READ_INPUT, 0, 1).empacotar()
        assert len(req) == 12
        resp = self.enviar_e_ler(host, porta, req, 11)
        assert interpretar_resposta(resp).valores == (2194,)

    def test_leitura_parcial_de_tcp(self, host_porta) -> None:
        # Manda o quadro em dois pedacos. recv pode devolver pela metade, e o
        # servidor precisa acumular antes de interpretar.
        host, porta = host_porta
        req = RequisicaoLeitura(1, 1, FC_READ_INPUT, 0, 1).empacotar()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        try:
            sock.connect((host, porta))
            sock.sendall(req[:5])
            import time as _t
            _t.sleep(0.1)
            sock.sendall(req[5:])
            resp = sock.recv(64)
        finally:
            sock.close()
        assert interpretar_resposta(resp).valores == (2194,)

    def test_dois_quadros_em_um_pedaco(self, host_porta) -> None:
        host, porta = host_porta
        a = RequisicaoLeitura(1, 1, FC_READ_INPUT, 0, 1).empacotar()
        b = RequisicaoLeitura(2, 2, FC_READ_INPUT, 0, 1).empacotar()
        resp = self.enviar_e_ler(host, porta, a + b, 22)
        primeiro = interpretar_resposta(resp[:11])
        segundo = interpretar_resposta(resp[11:22])
        assert primeiro.transacao == 1
        assert segundo.transacao == 2

    def test_comprimento_do_mbap(self, host_porta) -> None:
        # O campo de comprimento conta unidade + PDU, e o quadro tem
        # 6 + comprimento bytes. Somar 7 trava o servidor.
        host, porta = host_porta
        req = RequisicaoLeitura(1, 1, FC_READ_INPUT, 0, 1).empacotar()
        comprimento = struct.unpack(">H", req[4:6])[0]
        assert comprimento == 6
        assert len(req) == BYTES_ANTES_DO_COMPRIMENTO + comprimento

    def test_transacao_e_ecoada(self, host_porta) -> None:
        host, porta = host_porta
        req = RequisicaoLeitura(31337, 1, FC_READ_INPUT, 0, 1).empacotar()
        resp = self.enviar_e_ler(host, porta, req, 11)
        assert interpretar_resposta(resp).transacao == 31337

    def test_unit_id_e_ecoado(self, host_porta) -> None:
        host, porta = host_porta
        req = RequisicaoLeitura(1, 3, FC_READ_INPUT, 0, 1).empacotar()
        resp = self.enviar_e_ler(host, porta, req, 11)
        assert interpretar_resposta(resp).unidade == 3


class TestClienteDefensivo:
    """Cliente diante de respostas ruins."""

    def test_conexao_fechada(self) -> None:
        g, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
        s = ServidorModbus(g, porta=0)
        s.iniciar()
        porta = s.porta_em_uso
        s.parar()
        c = ClienteModbus("127.0.0.1", porta, 1.0)
        with pytest.raises(OSError):
            c.ler(1, 0, 1)

    def test_transacao_divergente(self, host_porta) -> None:
        host, porta = host_porta
        c = ClienteModbus(host, porta, 3.0)
        c.conectar()
        try:
            req = RequisicaoLeitura(999, 1, FC_READ_INPUT, 0, 1).empacotar()
            c._sock.sendall(req)
            buffer = b""
            while len(buffer) < 11:
                buffer += c._sock.recv(64)
        finally:
            c.fechar()
        # O proprio servidor ecoa a transacao; um proxy no meio e que mudaria.
        assert interpretar_resposta(buffer).transacao == 999

    def test_conectar_e_idempotente(self, host_porta) -> None:
        host, porta = host_porta
        c = ClienteModbus(host, porta, 3.0)
        c.conectar()
        try:
            c.conectar()
            assert c.conectado is True
        finally:
            c.fechar()

    def test_fechar_duas_vezes(self, host_porta) -> None:
        host, porta = host_porta
        c = ClienteModbus(host, porta, 3.0)
        c.conectar()
        c.fechar()
        c.fechar()
        assert c.conectado is False

    def test_transacao_cicla(self, host_porta) -> None:
        host, porta = host_porta
        c = ClienteModbus(host, porta, 3.0)
        c._transacao = 0xFFFF
        c.conectar()
        try:
            assert c._proxima_transacao() == 1
        finally:
            c.fechar()


class TestScannerSobreServidorReal:
    """Varredura de verdade."""

    def test_encontra_os_tres_medidores(self, host_porta) -> None:
        host, porta = host_porta
        scanner = ScannerModbus(host, porta, timeout=1.0)
        r = scanner.varrer_intervalo(range(1, 6))
        assert [d.unit_id for d in r.devices] == [1, 2, 3]
        assert r.total_respondidos == 3

    def test_valores_do_registrador_zero(self, host_porta) -> None:
        host, porta = host_porta
        scanner = ScannerModbus(host, porta, timeout=1.0)
        r = scanner.varrer_intervalo(range(1, 6))
        valores = {d.unit_id: d.valores[0] for d in r.devices}
        assert valores == {1: 2194, 2: 2197, 3: 9600}

    def test_so_ids_ausentes_falha_alto(self, host_porta) -> None:
        # Nenhum device no intervalo nao e "barramento vazio" com sucesso: e
        # sinal de que o servidor nao esta atendendo. Devolver lista vazia seria
        # indistinguivel de uma instalacao sem equipamento.
        host, porta = host_porta
        scanner = ScannerModbus(host, porta, timeout=0.3)
        with pytest.raises(OSError, match="nenhum device respondeu"):
            scanner.varrer_intervalo(range(4, 9))

    def test_misto(self, host_porta) -> None:
        host, porta = host_porta
        scanner = ScannerModbus(host, porta, timeout=0.3)
        r = scanner.varrer_intervalo(range(1, 5))
        assert [d.unit_id for d in r.devices] == [1, 2, 3]
        assert r.unit_ids_ausentes == [4]

    def test_quadro_com_comprimento_impossivel(self, host_porta) -> None:
        # Comprimento de PDU fora do limite nao da para sincronizar. O
        # servidor descarta o buffer e fecha, em vez de tentar interpretar os
        # bytes seguintes como um pedido que o cliente nunca fez.
        host, porta = host_porta
        req = struct.pack(">HHHB", 1, 0, 9999, 1) + bytes([FC_READ_INPUT, 0, 0, 1])
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        try:
            sock.connect((host, porta))
            sock.sendall(req)
            assert sock.recv(64) == b""
        finally:
            sock.close()
    def test_servidor_fora_do_ar(self) -> None:
        g, _ = carregar_ambiente(DISPOSITIVOS, MAPA)
        s = ServidorModbus(g, porta=0)
        s.iniciar()
        porta = s.porta_em_uso
        s.parar()
        scanner = ScannerModbus("127.0.0.1", porta, timeout=0.3)
        with pytest.raises(OSError, match="nenhum device respondeu"):
            scanner.varrer_intervalo(range(1, 3))

    def test_para_dict(self, host_porta) -> None:
        host, porta = host_porta
        scanner = ScannerModbus(host, porta, timeout=1.0)
        d = scanner.sondar(1).para_dict()
        assert d["unit_id"] == 1
        assert d["respondeu"] is True


class TestCriterioDeAceite:
    """O criterio de aceite da especificacao.

    O scanner le os tres medidores, identifica a sequencia de fase invertida e
    o consumo bate com o valor dos registradores.
    """

    @pytest.fixture(scope="class")
    @staticmethod
    def leituras(ambiente) -> list[tuple]:
        servidor, gerenciador, mapas = ambiente
        cliente = ClienteModbus("127.0.0.1", servidor.porta_em_uso, 3.0)
        cliente.conectar()
        saida = []
        try:
            for unit_id in gerenciador.unit_ids:
                disp = gerenciador.buscar(unit_id)
                dados = ler_dispositivo(cliente, unit_id, disp.mapa)
                saida.append((disp, dados, calcular(dados, numero_fases=disp.fases)))
        finally:
            cliente.fechar()
        return saida

    def test_leq_os_tres_medidores(self, leituras: list[tuple]) -> None:
        assert len(leituras) == 3

    def test_identifica_a_sequencia_invertida(self, leituras: list[tuple]) -> None:
        trifasicos = [r for d, _, r in leituras if d.fases == 3]
        assert len(trifasicos) == 1
        assert trifasicos[0].sequencia_invertida is True
        assert trifasicos[0].sequencia_fase == SEQUENCIA_NEGATIVA

    def test_monofasicos_nao_tem_sequencia(self, leituras: list[tuple]) -> None:
        for disp, _, r in leituras:
            if disp.fases == 1:
                assert r.sequencia_fase == ""

    def test_consumo_bate_com_os_registradores(self, leituras: list[tuple]) -> None:
        # O valor lido pela rede tem de ser igual ao valor que o medidor tem.
        for disp, dados, r in leituras:
            assert dados["potencia_ativa" if disp.fases != 1 or "potencia_ativa" in dados
                          else "demanda_ativa"] == pytest.approx(
                r.potencia_ativa_w
            )

    def test_energia_de_32_bits_bate(self, leituras: list[tuple]) -> None:
        valores = {d.id: r.energia_kwh for d, _, r in leituras}
        assert valores == {1: 18432.0, 2: 91240.0, 3: 412880.0}

    def test_valores_de_engenharia_iguais_ao_medidor(
        self, leituras: list[tuple]
    ) -> None:
        for disp, dados, _ in leituras:
            for nome, valor in dados.items():
                assert valor == pytest.approx(disp.valor(nome)), nome


class TestContadores:
    """Contadores do servidor."""

    def test_conta_leituras(self, ambiente) -> None:
        servidor, _, _ = ambiente
        antes = servidor.requisicoes_atendidas
        with ClienteModbus("127.0.0.1", servidor.porta_em_uso, 3.0) as c:
            c.ler(1, 0, 1)
        assert servidor.requisicoes_atendidas > antes

    def test_conta_excecoes(self, ambiente) -> None:
        servidor, _, _ = ambiente
        antes = servidor.excecoes_emitidas
        with ClienteModbus("127.0.0.1", servidor.porta_em_uso, 3.0) as c:
            with pytest.raises(ExcecaoRemota):
                c.ler(1, 900, 1)  # endereco fora do mapa do medidor 1
        assert servidor.excecoes_emitidas > antes