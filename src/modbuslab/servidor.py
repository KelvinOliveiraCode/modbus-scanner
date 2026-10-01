"""Servidor Modbus TCP sobre socket da biblioteca padrao.

Modbus TCP server on a standard-library socket.

Tres coisas que um servidor de campo faz e que um exemplo ingenuo costuma
errar, e que estao implementadas aqui:

**Despacho por unit id.** O MBAP carrega o unit id, que e o endereco do
dispositivo. Dois medidores podem ter o registrador 0 com valores diferentes, e
continuam sendo dois medidores. Um servidor que ignora o unit id e concatena os
registradores de todos os dispositivos responde com a fila errada para o cliente
que pediu uma coisa so.

**Leitura parcial de TCP.** ``recv`` devolve o que chegou ate agora, nao o
quadro inteiro. Um pedido de 12 bytes pode chegar em duas chamadas. O servidor
acumula em buffer ate ter MBAP mais PDU, e so entao interpreta.

**Varias requisicoes por conexao.** O cliente mantem a conexao aberta. O
servidor precisa atender em ciclo, nao fechar depois da primeira resposta.
"""

from __future__ import annotations

import socket
import struct
import threading
from typing import TYPE_CHECKING

from .protocolo import (
    EX_ENDERECO_ILEGAL,
    EX_FUNCAO_ILEGAL,
    EX_VALOR_ILEGAL,
    FC_READ_HOLDING,
    FC_READ_INPUT,
    FUNCOES_SUPORTADAS,
    MAX_REGISTRADORES_LEITURA,
    MIN_REGISTRADORES_LEITURA,
    BYTES_ANTES_DO_COMPRIMENTO,
    TAMANHO_MAXIMO_QUADRO,
    TAMANHO_MBAP,
    ErroModbus,
    Mbap,
    montar_excecao,
)

if TYPE_CHECKING:
    from .dispositivos import GerenciadorDispositivos


def _quadro_completo(dados: bytes) -> tuple[bytes, bytes] | None:
    """Extrai um quadro completo do buffer, se houver.

    Pull one complete frame out of the buffer, if present.

    Um comprimento de PDU fora de 1 a ``TAMANHO_MAXIMO_QUADRO - 7`` significa
    quadro corrompido. Nao da para sincronizar a partir dele, entao o buffer
    e descartado e a conexao fecha; tentar interpretar os bytes seguintes seria
    fabricar um pedido que o cliente nunca fez.

    Args:
        dados: Buffer acumulado da conexao.

    Returns:
        Par com o quadro e os bytes restantes, ou ``None`` se o quadro ainda
        nao chegou inteiro.
    """
    if len(dados) < TAMANHO_MBAP:
        return None

    comprimento = struct.unpack(">H", dados[4:6])[0]
    total = BYTES_ANTES_DO_COMPRIMENTO + comprimento

    if not (1 <= comprimento <= TAMANHO_MAXIMO_QUADRO - BYTES_ANTES_DO_COMPRIMENTO):
        return b"", b""  # sinal de descarte

    if len(dados) < total:
        return None
    return dados[:total], dados[total:]


class ServidorModbus:
    """Servidor Modbus TCP monothread, com aceitacao por thread.

    Serve holding e input registers dos medidores registrados.

    Args:
        gerenciador: Medidores a servir.
        host: Endereco de escuta. O default e loopback.
        porta: Porta TCP. Zero escolhe uma porta livre.
    """

    def __init__(
        self,
        gerenciador: "GerenciadorDispositivos",
        host: str = "127.0.0.1",
        porta: int = 5020,
    ) -> None:
        self.gerenciador = gerenciador
        self.host = host
        self.porta = porta
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._parar = threading.Event()
        # Comeca marcado como parado. Sem isto o Event vazio leria como
        # "rodando" em __init__, e iniciar() sairia antes de abrir o socket.
        self._parar.set()
        self._lock = threading.Lock()
        self.requisicoes_atendidas = 0
        self.excecoes_emitidas = 0

    @property
    def rodando(self) -> bool:
        """Se o laco de aceitacao esta ativo.

        Whether the accept loop is running.
        """
        return not self._parar.is_set()

    @property
    def porta_em_uso(self) -> int:
        """Porta real, conhecida depois de ``iniciar``.

        The real port, known after :meth:`iniciar`.
        """
        if self._sock is None:
            return self.porta
        return int(self._sock.getsockname()[1])

    # -- atendimento de um pedido -------------------------------------------

    def atender_requisicao(self, quadro: bytes) -> bytes | None:
        """Interpreta um quadro de leitura e monta a resposta.

        Interpret a read frame and build the response.

        Args:
            quadro: Quadro completo, MBAP mais PDU.

        Returns:
            O quadro de resposta, ou ``None`` quando o quadro nao e para este
            servidor.
        """
        try:
            mbap = Mbap.desempacotar(quadro)
        except ErroModbus:
            return None

        pdu = quadro[TAMANHO_MBAP:]
        if not pdu:
            return None

        funcao = pdu[0]

        dispositivo = self.gerenciador.buscar(mbap.unidade)
        if dispositivo is None:
            # Unit id que nao e deste servidor: o quadro e descartado sem
            # resposta, e nao com excecao. Excecao 2 responde a endereco de
            # registrador invalido em um unit que existe; unit id desconhecido
            # e silencio. E esse silencio que torna a varredura de barramento
            # custar tempo, porque o cliente precisa esperar o timeout.
            return None

        if funcao not in FUNCOES_SUPORTADAS:
            self.excecoes_emitidas += 1
            return montar_excecao(
                mbap.transacao, mbap.unidade, funcao, EX_FUNCAO_ILEGAL
            )

        if len(pdu) < 5:
            self.excecoes_emitidas += 1
            return montar_excecao(
                mbap.transacao, mbap.unidade, funcao, EX_VALOR_ILEGAL
            )

        endereco, quantidade = struct.unpack(">HH", pdu[1:5])

        if not (MIN_REGISTRADORES_LEITURA <= quantidade <= MAX_REGISTRADORES_LEITURA):
            self.excecoes_emitidas += 1
            return montar_excecao(
                mbap.transacao, mbap.unidade, funcao, EX_VALOR_ILEGAL
            )

        with self._lock:
            brutos: list[int] = []
            respondidos = 0

            for indice in range(quantidade):
                alvo = endereco + indice
                dono = dispositivo.mapa.cobre(alvo)
                if dono is None:
                    # Endereco sem registrador: zero, como um medidor real
                    # devolve para endereco valido e nao implementado.
                    brutos.append(0)
                    continue

                reg, posicao = dono
                palavras = dispositivo.ler_bruto(reg.endereco)
                brutos.append(palavras[posicao] if posicao < len(palavras) else 0)
                respondidos += 1

            self.requisicoes_atendidas += 1

        if respondidos == 0:
            self.excecoes_emitidas += 1
            return montar_excecao(
                mbap.transacao, mbap.unidade, funcao, EX_ENDERECO_ILEGAL
            )

        dados = b"".join(b.to_bytes(2, "big") for b in brutos)
        pdu_resposta = bytes([funcao, len(dados)]) + dados
        resposta_mbap = Mbap(
            transacao=mbap.transacao,
            protocolo=0,
            comprimento=len(pdu_resposta) + 1,
            unidade=mbap.unidade,
        )
        return resposta_mbap.empacotar() + pdu_resposta

    # -- ciclo de vida ------------------------------------------------------

    def _atender_conexao(self, conn: socket.socket) -> None:
        """Atende um cliente ate ele fechar a conexao.

        Serve one client until it disconnects.

        Args:
            conn: Socket ja aceito.
        """
        buffer = b""
        conn.settimeout(1.0)
        try:
            while not self._parar.is_set():
                try:
                    pedaco = conn.recv(512)
                except socket.timeout:
                    continue
                except OSError:
                    break

                if not pedaco:
                    break

                buffer += pedaco

                # Pode ter chegado mais de um quadro no mesmo pedaco.
                while True:
                    resultado = _quadro_completo(buffer)
                    if resultado is None:
                        break
                    quadro, buffer = resultado
                    if not quadro:
                        # Quadro corrompido: o cliente perdeu a sincronia.
                        return
                    try:
                        resposta = self.atender_requisicao(quadro)
                        if resposta is not None:
                            conn.sendall(resposta)
                    except OSError:
                        return
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _loop(self) -> None:
        """Laco de aceitacao.

        Accept loop.
        """
        while not self._parar.is_set():
            sock = self._sock
            if sock is None:
                # parar() ja fechou o socket entre a checagem do evento e o
                # accept. Sem esta guarda a thread estourava com WinError
                # 10038 ao tentar usar um socket ja fechado.
                break
            try:
                conn, _endereco = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self._atender_conexao(conn)

    def iniciar(self) -> None:
        """Sobe o socket e o laco de aceitacao.

        Bind the socket and start the accept loop.
        """
        if self.rodando:
            return
        self._parar.clear()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # O timeout vai antes de listen: e o que faz o accept desistir a cada
        # meio segundo e o laco notar a flag de parada.
        self._sock.settimeout(0.5)
        self._sock.bind((self.host, self.porta))
        self._sock.listen(16)
        self.porta = self._sock.getsockname()[1]
        self._thread = threading.Thread(
            target=self._loop, name="modbus-aceite", daemon=True
        )
        self._thread.start()

    def parar(self) -> None:
        """Desliga o laco e fecha o socket.

        Stop the loop and close the socket.
        """
        self._parar.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    # Atributos antigos, mantidos para compatibilidade com a CLI e os testes.
    start = iniciar
    stop = parar

    def __enter__(self) -> "ServidorModbus":
        self.iniciar()
        return self

    def __exit__(self, *_excecao: object) -> None:
        self.parar()


def descrever_servidor(servidor: ServidorModbus) -> str:
    """Linha de identificacao do servidor.

    One-line server identity.

    Args:
        servidor: Servidor a descrever.

    Returns:
        Texto com host, porta e numero de medidores.
    """
    return (
        f"Modbus TCP em {servidor.host}:{servidor.porta_em_uso} "
        f"com {len(servidor.gerenciador)} medidor(es)"
    )