"""Enquadramento Modbus TCP: cabecalho MBAP e PDU.

Modbus TCP framing: the MBAP header and the PDU.

Um quadro de requisicao tem 7 bytes de MBAP seguidos pelo PDU. O MBAP carrega
o identificador de transacao, o identificador de protocolo, o comprimento do PDU
e o **unit id**, que e o endereco do dispositivo dentro do barramento. Servidor e
cliente usam este mesmo modulo: e o formato do fio, nao uma escolha de lado.

Quadro de resposta tem o mesmo MBAP, com o comprimento ajustado, e um PDU que ou
comeca com o codigo de funcao, ou com o mesmo codigo mais 0x80 e o codigo de
excecao no byte seguinte.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Codigos de funcao suportados
# ---------------------------------------------------------------------------

#: Read Holding Registers. Le e escreve.
FC_READ_HOLDING = 0x03

#: Read Input Registers. Somente leitura.
FC_READ_INPUT = 0x04

#: Write Single Register.
FC_WRITE_HOLDING = 0x06

#: Write Multiple Registers.
FC_WRITE_MULTIPLE = 0x10

#: Bit que, ligado na resposta, marca PDU de excecao.
BIT_EXCECAO = 0x80

#: Funcoes que este simulador implementa.
FUNCOES_SUPORTADAS = frozenset({FC_READ_HOLDING, FC_READ_INPUT})

# ---------------------------------------------------------------------------
# Codigos de excecao
# ---------------------------------------------------------------------------

#: Funcao desconhecida para este servidor.
EX_FUNCAO_ILEGAL = 0x01

#: Endereco de registrador fora do espaco do dispositivo.
EX_ENDERECO_ILEGAL = 0x02

#: Valor ou quantidade fora do que o protocolo aceita.
EX_VALOR_ILEGAL = 0x03

#: Excecoes por nome, para mensagem de log.
EXCECOES = {
    EX_FUNCAO_ILEGAL: "funcao ilegal / illegal function",
    EX_ENDERECO_ILEGAL: "endereco ilegal / illegal data address",
    EX_VALOR_ILEGAL: "valor ilegal / illegal data value",
}

# ---------------------------------------------------------------------------
# Limites do protocolo
# ---------------------------------------------------------------------------

#: Quantidade maxima de registradores em uma leitura, pela especificacao.
MAX_REGISTRADORES_LEITURA = 125

#: Quantidade minima de uma leitura.
MIN_REGISTRADORES_LEITURA = 1

#: Tamanho do cabecalho MBAP em bytes.
TAMANHO_MBAP = 7

#: Bytes do MBAP que vemem **antes** do campo de comprimento: identificador de
#: transacao (2) e identificador de protocolo (2), mais o proprio campo (2).
#: O campo de comprimento conta o que vem depois dele, ou seja, o unit id e o
#: PDU. Por isso o quadro inteiro tem ``6 + comprimento`` bytes e nao
#: ``7 + comprimento``. Somar 7 trava a leitura esperando um byte que nunca vem.
BYTES_ANTES_DO_COMPRIMENTO = 6

#: Tamanho maximo de um quadro Modbus TCP aceito. A especificacao limita o PDU
#: a 253 bytes, o que da 259 bytes de quadro. O limite um pouco mais folgado
#: abaixo absorve um device que responde com bloco grande sem quebrar o leitor.
TAMANHO_MAXIMO_QUADRO = 260

#: Tamanho do PDU de requisicao de leitura, em bytes: funcao + endereco + qtde.
TAMANHO_PDU_LEITURA = 5

#: Numero de protocolo do Modbus TCP. Sempre zero.
PROTOCOLO_MODBUS = 0

# ---------------------------------------------------------------------------
# Excecoes
# ---------------------------------------------------------------------------


class ErroModbus(Exception):
    """Erro de protocolo Modbus.

    Base de todos os erros de protocolo deste modulo.
    """


class QuadroInvalido(ErroModbus):
    """Quadro recebido malformado."""


class ExcecaoRemota(ErroModbus):
    """O servidor respondeu com PDU de excecao.

    O codigo vem do proprio dispositivo e diz por que a requisicao foi recusada.
    """

    def __init__(self, funcao: int, codigo: int) -> None:
        self.funcao = funcao
        self.codigo = codigo
        nome = EXCECOES.get(codigo, "excecao desconhecida / unknown exception")
        super().__init__(f"excecao {codigo} na funcao {funcao}: {nome}")


# ---------------------------------------------------------------------------
# Estruturas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Mbap:
    """Cabecalho MBAP de 7 bytes.

    Transaction identifier, protocol identifier, length and unit id.
    """

    transacao: int
    protocolo: int
    comprimento: int
    unidade: int

    def empacotar(self) -> bytes:
        """Serializa o cabecalho.

        Serialise the header.

        Returns:
            Os 7 bytes do MBAP.
        """
        return struct.pack(">HHHB", self.transacao, self.protocolo,
                           self.comprimento, self.unidade)

    @classmethod
    def desempacotar(cls, dados: bytes) -> "Mbap":
        """Le o cabecalho de um quadro.

        Parse the header of a frame.

        Args:
            dados: Quadro recebido, com pelo menos 7 bytes.

        Returns:
            O cabecalho lido.

        Raises:
            QuadroInvalido: Se o quadro tiver menos de 7 bytes.
        """
        if len(dados) < TAMANHO_MBAP:
            raise QuadroInvalido(
                f"quadro com {len(dados)} bytes, minimo {TAMANHO_MBAP}"
            )
        return cls(*struct.unpack(">HHHB", dados[:TAMANHO_MBAP]))


@dataclass(frozen=True)
class RequisicaoLeitura:
    """Requisicao de leitura de registradores.

    Read request for holding or input registers.
    """

    transacao: int
    unidade: int
    funcao: int
    endereco: int
    quantidade: int

    def empacotar(self) -> bytes:
        """Serializa em MBAP + PDU.

        Serialise to MBAP + PDU.

        Returns:
            O quadro completo pronto para o socket.

        Raises:
            ExcecaoNao Permitida: Se a quantidade estiver fora do protocolo.
        """
        pdu = struct.pack(">BHH", self.funcao, self.endereco, self.quantidade)
        mbap = Mbap(
            transacao=self.transacao,
            protocolo=PROTOCOLO_MODBUS,
            comprimento=len(pdu) + 1,
            unidade=self.unidade,
        )
        return mbap.empacotar() + pdu


@dataclass(frozen=True)
class RespostaLeitura:
    """Resposta bem-sucedida de uma leitura.

    Successful read response: the function code, the values and the echoed
    transaction id.
    """

    transacao: int
    unidade: int
    funcao: int
    valores: tuple[int, ...]

    def empacotar(self) -> bytes:
        """Serializa em MBAP + PDU.

        Serialise to MBAP + PDU.
        """
        dados = b"".join(v.to_bytes(2, "big") for v in self.valores)
        pdu = bytes([self.funcao, len(dados)]) + dados
        mbap = Mbap(
            transacao=self.transacao,
            protocolo=PROTOCOLO_MODBUS,
            comprimento=len(pdu) + 1,
            unidade=self.unidade,
        )
        return mbap.empacotar() + pdu


# ---------------------------------------------------------------------------
# Decodificacao de respostas
# ---------------------------------------------------------------------------


def interpretar_resposta(quadro: bytes) -> RespostaLeitura:
    """Le um quadro de resposta e devolve os valores lidos.

    Parse a response frame and return the read values.

    Levanta :class:`ExcecaoRemota` quando o PDU traz excecao. Um PDU de
    excecao tem o bit 0x80 ligado na funcao e o codigo no byte seguinte, e nao
    tem bloco de dados.

    Args:
        quadro: Quadro completo, MBAP mais PDU.

    Returns:
        A resposta decodificada.

    Raises:
        QuadroInvalido: Se o quadro estiver truncado ou com tamanho inconsistente.
        ExcecaoRemota: Se o servidor respondeu com excecao.
    """
    mbap = Mbap.desempacotar(quadro)

    if mbap.protocolo != PROTOCOLO_MODBUS:
        raise QuadroInvalido(
            f"identificador de protocolo {mbap.protocolo}, esperado 0"
        )

    pdu = quadro[TAMANHO_MBAP:]
    if not pdu:
        raise QuadroInvalido("PDU vazio / empty PDU")

    funcao = pdu[0]

    if funcao & BIT_EXCECAO:
        if len(pdu) < 2:
            raise QuadroInvalido("PDU de excecao sem codigo")
        raise ExcecaoRemota(funcao & ~BIT_EXCECAO, pdu[1])

    if funcao not in FUNCOES_SUPORTADAS:
        raise QuadroInvalido(f"funcao {funcao} em resposta de leitura")

    if len(pdu) < 2:
        raise QuadroInvalido("PDU de leitura sem contagem de bytes")

    esperado = pdu[1]
    if esperado != len(pdu) - 2:
        raise QuadroInvalido(
            f"contagem de bytes {esperado} nao bate com o PDU de {len(pdu) - 2}"
        )

    corpo = pdu[2:]
    if len(corpo) % 2 != 0:
        raise QuadroInvalido("bloco de dados com numero impar de bytes")

    valores = tuple(
        int.from_bytes(corpo[i:i + 2], "big") for i in range(0, len(corpo), 2)
    )
    return RespostaLeitura(
        transacao=mbap.transacao,
        unidade=mbap.unidade,
        funcao=funcao,
        valores=valores,
    )


def ler_requisicao(quadro: bytes) -> RequisicaoLeitura:
    """Le um quadro de requisicao de leitura.

    Parse a read request frame.

    Args:
        quadro: Quadro completo, MBAP mais PDU.

    Returns:
        A requisicao decodificada.

    Raises:
        QuadroInvalido: Se o quadro estiver truncado ou a funcao nao for de
            leitura.
    """
    mbap = Mbap.desempacotar(quadro)
    pdu = quadro[TAMANHO_MBAP:]

    if len(pdu) < TAMANHO_PDU_LEITURA:
        raise QuadroInvalido(
            f"PDU de requisicao com {len(pdu)} bytes, esperado "
            f"{TAMANHO_PDU_LEITURA}"
        )

    funcao, endereco, quantidade = struct.unpack(">BHH", pdu[:TAMANHO_PDU_LEITURA])
    return RequisicaoLeitura(
        transacao=mbap.transacao,
        unidade=mbap.unidade,
        funcao=funcao,
        endereco=endereco,
        quantidade=quantidade,
    )


def montar_excecao(
    transacao: int, unidade: int, funcao: int, codigo: int
) -> bytes:
    """Monta um quadro de resposta de excecao.

    Build an exception response frame.

    Args:
        transacao: Id de transacao a ecoar.
        unidade: Unit id a ecoar.
        funcao: Codigo de funcao original, sem o bit de excecao.
        codigo: Codigo de excecao.

    Returns:
        O quadro completo.
    """
    pdu = bytes([funcao | BIT_EXCECAO, codigo])
    mbap = Mbap(
        transacao=transacao,
        protocolo=PROTOCOLO_MODBUS,
        comprimento=len(pdu) + 1,
        unidade=unidade,
    )
    return mbap.empacotar() + pdu


def descricao_excecao(codigo: int) -> str:
    """Nome legivel de um codigo de excecao.

    Human-readable name of an exception code.
    """
    return EXCECOES.get(codigo, f"excecao {codigo} nao mapeada")