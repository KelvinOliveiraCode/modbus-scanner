"""Testes do enquadramento Modbus TCP.

Modbus TCP framing tests.

O quadro de 12 bytes de uma leitura de um registrador e o caso central deste
modulo: transacao 1, protocolo 0, comprimento 6, unidade 1, funcao 4,
endereco 0, quantidade 1. Se algum desses campos derivar uma casa, a
comunicacao quebra de um jeito que so aparece em tempo de execucao.
"""

from __future__ import annotations

import struct

import pytest

from modbuslab.protocolo import (
    BYTES_ANTES_DO_COMPRIMENTO,
    ExcecaoRemota,
    EX_ENDERECO_ILEGAL,
    EX_FUNCAO_ILEGAL,
    EX_VALOR_ILEGAL,
    FC_READ_HOLDING,
    FC_READ_INPUT,
    Mbap,
    QuadroInvalido,
    RequisicaoLeitura,
    RespostaLeitura,
    TAMANHO_MBAP,
    descricao_excecao,
    interpretar_resposta,
    ler_requisicao,
    montar_excecao,
)


class TestMbap:
    """Cabecalho de 7 bytes."""

    def test_empacotar_tem_sete_bytes(self) -> None:
        mbap = Mbap(transacao=1, protocolo=0, comprimento=6, unidade=1)
        assert len(mbap.empacotar()) == TAMANHO_MBAP

    def test_ida_e_volta(self) -> None:
        original = Mbap(transacao=513, protocolo=0, comprimento=300, unidade=247)
        lido = Mbap.desempacotar(original.empacotar())
        assert lido == original

    def test_campos_no_lugar_certo(self) -> None:
        bruto = Mbap(1, 0, 6, 9).empacotar()
        assert bruto[:2] == b"\x00\x01"
        assert bruto[2:4] == b"\x00\x00"
        assert bruto[4:6] == b"\x00\x06"
        assert bruto[6] == 9

    def test_truncado(self) -> None:
        with pytest.raises(QuadroInvalido):
            Mbap.desempacotar(b"\x00\x01\x00")

    def test_vazio(self) -> None:
        with pytest.raises(QuadroInvalido):
            Mbap.desempacotar(b"")

    def test_bytes_antes_do_comprimento(self) -> None:
        # O campo de comprimento conta o que vem DEPOIS dele. Somar os 7 bytes
        # do MBAP inteiro daria um quadro um byte maior do que o cliente
        # envia, e o servidor ficaria esperando um byte que nunca chega.
        assert BYTES_ANTES_DO_COMPRIMENTO == 6


class TestRequisicaoLeitura:
    """Requisicao de leitura."""

    def test_requisição_de_um_registrador(self) -> None:
        req = RequisicaoLeitura(
            transacao=1, unidade=1, funcao=FC_READ_INPUT, endereco=0, quantidade=1
        )
        assert req.empacotar().hex() == "000100000006010400000001"

    def test_tamanho_total(self) -> None:
        req = RequisicaoLeitura(1, 1, FC_READ_INPUT, 0, 1)
        # 7 do MBAP + 5 do PDU de leitura.
        assert len(req.empacotar()) == 12

    def test_comprimento_certa_unidade_e_pdu(self) -> None:
        req = RequisicaoLeitura(1, 1, FC_READ_INPUT, 0, 1)
        mbap = Mbap.desempacotar(req.empacotar())
        # 1 (unidade) + 5 (PDU).
        assert mbap.comprimento == 6

    def test_ida_e_volta(self) -> None:
        original = RequisicaoLeitura(4242, 17, FC_READ_HOLDING, 300, 25)
        lida = ler_requisicao(original.empacotar())
        assert lida == original

    def test_endereco_alto(self) -> None:
        req = RequisicaoLeitura(1, 1, FC_READ_HOLDING, 65535, 1)
        assert ler_requisicao(req.empacotar()).endereco == 65535

    def test_ida_e_volta_com_funcao_input(self) -> None:
        original = RequisicaoLeitura(7, 3, FC_READ_INPUT, 10, 125)
        assert ler_requisicao(original.empacotar()) == original


class TestLerRequisicaoInvalida:
    """Requisicao malformada."""

    def test_pdu_curto(self) -> None:
        quadro = struct.pack(">HHHB", 1, 0, 3, 1) + b"\x04\x00\x00"
        with pytest.raises(QuadroInvalido):
            ler_requisicao(quadro)

    def test_sem_pdu(self) -> None:
        with pytest.raises(QuadroInvalido):
            ler_requisicao(struct.pack(">HHHB", 1, 0, 1, 1))

    def test_quadro_muito_curto(self) -> None:
        with pytest.raises(QuadroInvalido):
            ler_requisicao(b"\x00\x01")


class TestRespostaLeitura:
    """Resposta bem-sucedida."""

    def test_um_registrador(self) -> None:
        resp = RespostaLeitura(1, 1, FC_READ_INPUT, (2194,))
        # funcao 04, 2 bytes de dados, 2194 = 0x0892
        assert resp.empacotar().hex() == "0001000000050104020892"

    def test_varios_registradores(self) -> None:
        resp = RespostaLeitura(1, 1, FC_READ_INPUT, (1, 2, 3))
        bruto = resp.empacotar()
        # O MBAP ocupa os indices 0 a 6; o PDU comeca no 7.
        assert bruto[7] == FC_READ_INPUT
        assert bruto[8] == 6  # 3 registradores * 2 bytes

    def test_ida_e_volta(self) -> None:
        original = RespostaLeitura(9, 2, FC_READ_HOLDING, (10, 20, 30))
        lida = interpretar_resposta(original.empacotar())
        assert lida.valores == (10, 20, 30)
        assert lida.transacao == 9
        assert lida.unidade == 2
        assert lida.funcao == FC_READ_HOLDING

    def test_valor_zero(self) -> None:
        assert interpretar_resposta(
            RespostaLeitura(1, 1, FC_READ_INPUT, (0,)).empacotar()
        ).valores == (0,)

    def test_valor_maximo(self) -> None:
        assert interpretar_resposta(
            RespostaLeitura(1, 1, FC_READ_INPUT, (65535,)).empacotar()
        ).valores == (65535,)


class TestInterpretarRespostaInvalida:
    """Resposta malformada ou de excecao."""

    def test_protocolo_errado(self) -> None:
        quadro = bytearray(
            RespostaLeitura(1, 1, FC_READ_INPUT, (1,)).empacotar()
        )
        quadro[2:4] = b"\x00\x01"
        with pytest.raises(QuadroInvalido):
            interpretar_resposta(bytes(quadro))

    def test_pdu_vazio(self) -> None:
        quadro = struct.pack(">HHHB", 1, 0, 1, 1)
        with pytest.raises(QuadroInvalido):
             interpretar_resposta(quadro)

    def test_excecao(self) -> None:
        quadro = montar_excecao(1, 1, FC_READ_HOLDING, EX_ENDERECO_ILEGAL)
        with pytest.raises(ExcecaoRemota) as exc:
             interpretar_resposta(quadro)
        assert exc.value.codigo == EX_ENDERECO_ILEGAL
        assert exc.value.funcao == FC_READ_HOLDING

    def test_excecao_sem_codigo(self) -> None:
        quadro = struct.pack(">HHHB", 1, 0, 2, 1) + bytes([0x83])
        with pytest.raises(QuadroInvalido):
             interpretar_resposta(quadro)

    def test_funcao_desconhecida_na_resposta(self) -> None:
        quadro = struct.pack(">HHHB", 1, 0, 4, 1) + bytes([0x10, 2, 0, 0])
        with pytest.raises(QuadroInvalido):
             interpretar_resposta(quadro)

    def test_contagem_de_bytes_incoerente(self) -> None:
        # Anuncia 4 bytes e entrega 2.
        quadro = struct.pack(">HHHB", 1, 0, 5, 1) + bytes([FC_READ_INPUT, 4, 0, 1])
        with pytest.raises(QuadroInvalido):
            interpretar_resposta(quadro)

    def test_numero_impar_de_bytes(self) -> None:
        quadro = struct.pack(">HHHB", 1, 0, 4, 1) + bytes([FC_READ_INPUT, 3, 0, 1])
        with pytest.raises(QuadroInvalido):
             interpretar_resposta(quadro)

    def test_sem_contagem_de_bytes(self) -> None:
        quadro = struct.pack(">HHHB", 1, 0, 2, 1) + bytes([FC_READ_INPUT])
        with pytest.raises(QuadroInvalido):
             interpretar_resposta(quadro)


class TestMontarExcecao:
    """Quadros de excecao."""

    def test_marca_o_bit_de_excecao(self) -> None:
        quadro = montar_excecao(1, 1, FC_READ_HOLDING, EX_FUNCAO_ILEGAL)
        assert quadro[7] == FC_READ_HOLDING | 0x80
        assert quadro[8] == EX_FUNCAO_ILEGAL

    def test_echo_da_transacao(self) -> None:
        quadro = montar_excecao(777, 5, FC_READ_INPUT, EX_VALOR_ILEGAL)
        mbap = Mbap.desempacotar(quadro)
        assert mbap.transacao == 777
        assert mbap.unidade == 5

    def test_tamanho_total(self) -> None:
        # 6 do MBAP ate o comprimento + 2 do PDU de excecao.
        assert len(montar_excecao(1, 1, FC_READ_HOLDING, EX_VALOR_ILEGAL)) == 9

    def test_todas_as_excecoes_tem_nome(self) -> None:
        for codigo in (EX_FUNCAO_ILEGAL, EX_ENDERECO_ILEGAL, EX_VALOR_ILEGAL):
            assert descricao_excecao(codigo) != f"excecao {codigo} nao mapeada"

    def test_excecao_desconhecida(self) -> None:
        assert "99" in descricao_excecao(99)


class TestRoundTripCompleto:
    """Requisicao seguida de resposta, como o fio faz."""

    def test_ciclo_de_uma_leitura(self) -> None:
        req = RequisicaoLeitura(1234, 6, FC_READ_INPUT, 2, 3)
        resp = RespostaLeitura(
            req.transacao, req.unidade, req.funcao, (100, 200, 300)
        )
        lida = interpretar_resposta(resp.empacotar())
        assert lida.transacao == req.transacao
        assert lida.unidade == req.unidade
        assert lida.funcao == req.funcao
        assert lida.valores == (100, 200, 300)