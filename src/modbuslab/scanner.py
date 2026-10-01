"""Cliente Modbus TCP e varredura de dispositivos.

Modbus TCP client and device discovery.

O scanner nao recebe a lista de medidores. Ele varre o intervalo de unit id e
descobre quem responde. Um scanner que so sonda os ids que ja conhece nao
descobre nada: ele confirma o que alguem ja disse.

Cada unit id e sondado com uma leitura de um unico registrador. Tres respostas
possiveis:

- excecao de endereco: existe alguem no barramento, mas nao neste unit id;
- excecao de funcao: o device existe e respondeu, mas nao implementa a funcao;
- dados: existe e responde.

Um unit id que nao devolve nada dentro do prazo e considerado ausente. E por
isso que a varredura leva tempo: cada id morto custa um timeout.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass, field

from .protocolo import (
    BYTES_ANTES_DO_COMPRIMENTO,
    TAMANHO_MAXIMO_QUADRO,
    TAMANHO_MBAP,
    ExcecaoRemota,
    FC_READ_HOLDING,
    FC_READ_INPUT,
    QuadroInvalido,
    RequisicaoLeitura,
    interpretar_resposta,
)

#: Unit id inicial da varredura. Zero e reservado para broadcast.
PRIMEIRO_UNIT_ID = 1

#: Unit id final da varredura, exclusivo.
ULTIMO_UNIT_ID = 247

#: Endereco sondado na varredura. O registrador zero e o ponto de entrada
#: mais comum em medidor Modbus.
ENDERECO_SONDA = 0

#: Funcao preferida na varredura. Input register e somente leitura, entao e a
#: sonda mais segura para um dispositivo que nao seja seu.
FUNCAO_SONDA = FC_READ_INPUT


@dataclass
class DispositivoDescoberto:
    """Um device que respondeu a varredura.

    A device that answered the sweep.
    """

    unit_id: int
    respondeu: bool
    funcao: int = 0
    valores: tuple[int, ...] = ()
    excecao: int | None = None
    erro: str = ""

    @property
    def tem_registrador_zero(self) -> bool:
        """Se o registrador zero respondeu com valor.

        Whether register zero came back with a value.
        """
        return bool(self.valores)

    def para_dict(self) -> dict[str, object]:
        """Converte para dict simples.

        Convert to a plain dict.
        """
        return {
            "unit_id": self.unit_id,
            "respondeu": self.respondeu,
            "funcao": self.funcao,
            "valores": list(self.valores),
            "excecao": self.excecao,
            "erro": self.erro,
        }


class ClienteModbus:
    """Cliente Modbus TCP minimo, com conexao persistente.

    A connection is kept open for the whole life of the client, the way a real
    polling client behaves.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        porta: int = 5020,
        timeout: float = 1.0,
    ) -> None:
        self.host = host
        self.porta = porta
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._transacao = 0

    @property
    def conectado(self) -> bool:
        """Se a conexao esta aberta.

        Whether the connection is open.
        """
        return self._sock is not None

    def conectar(self) -> None:
        """Abre a conexao, se ainda nao estiver aberta.

        Open the connection if it is not open yet.
        """
        if self._sock is not None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect((self.host, self.porta))
        self._sock = sock

    def fechar(self) -> None:
        """Fecha a conexao.

        Close the connection.
        """
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _proxima_transacao(self) -> int:
        """Gera o proximo identificador de transacao.

        Produce the next transaction identifier.

        O protocolo deixa o cliente escolher. Rodar de 1 ate 65535 e voltar a 1
        torna a saida reproduzivel, o que ajuda quando se compara duas varreduras.
        """
        self._transacao = self._transacao % 0xFFFF + 1
        return self._transacao

    def _ler_quadro(self, tamanho: int) -> bytes:
        """Le um quadro de tamanho conhecido do socket.

        Read a frame of known size from the socket.

        Args:
            tamanho: Quantos bytes ler.

        Returns:
            Os bytes lidos.

        Raises:
            QuadroInvalido: Se o servidor fechar antes de entregar tudo.
        """
        assert self._sock is not None
        buffer = b""
        while len(buffer) < tamanho:
            pedaco = self._sock.recv(tamanho - len(buffer))
            if not pedaco:
                raise QuadroInvalido("conexao fechada pelo servidor")
            buffer += pedaco
        return buffer

    def ler(
        self,
        unit_id: int,
        endereco: int,
        quantidade: int,
        funcao: int = FC_READ_HOLDING,
    ) -> tuple[int, ...]:
        """Le registradores de um dispositivo.

        Read registers from a device.

        A resposta tem tamanho variavel, porque uma excecao ocupa 9 bytes e uma
        leitura de N registradores ocupa ``9 + 2N``. O cliente le primeiro o MBAP,
        que declara o comprimento, e so entao le o resto. Assumir o tamanho da
        leitura antes de ver o cabecalho trava o cliente esperando bytes que uma
        resposta de excecao nunca manda.

        Args:
            unit_id: Endereco do dispositivo no barramento.
            endereco: Primeiro registrador.
            quantidade: Quantos registradores ler.
            funcao: :data:`~modbuslab.protocolo.FC_READ_HOLDING` ou
                :data:`~modbuslab.protocolo.FC_READ_INPUT`.

        Returns:
            Os valores brutos lidos.

        Raises:
            ExcecaoRemota: Se o dispositivo recusou a leitura.
            QuadroInvalido: Se a resposta vier malformada.
            OSError: Se a conexao falhar.
        """
        self.conectar()
        assert self._sock is not None

        requisicao = RequisicaoLeitura(
            transacao=self._proxima_transacao(),
            unidade=unit_id,
            funcao=funcao,
            endereco=endereco,
            quantidade=quantidade,
        )
        self._sock.sendall(requisicao.empacotar())

        cabecalho = self._ler_quadro(TAMANHO_MBAP)
        tamanho = BYTES_ANTES_DO_COMPRIMENTO + int.from_bytes(
            cabecalho[4:6], "big"
        )
        if not (TAMANHO_MBAP < tamanho <= TAMANHO_MAXIMO_QUADRO):
            raise QuadroInvalido(f"comprimento de PDU invalido: {tamanho}")

        resto = self._ler_quadro(tamanho - TAMANHO_MBAP)
        resposta = interpretar_resposta(cabecalho + resto)

        if resposta.transacao != requisicao.transacao:
            raise QuadroInvalido(
                f"transacao {resposta.transacao} nao bate com o pedido "
                f"{requisicao.transacao}"
            )
        return resposta.valores

    def __enter__(self) -> "ClienteModbus":
        self.conectar()
        return self

    def __exit__(self, *_excecao: object) -> None:
        self.fechar()


@dataclass
class ResultadoVarredura:
    """Resultado de uma varredura de barramento.

    Outcome of a bus sweep.

    Tres situacoes distintas, que nao podem ser confundidas:

    - **device**: devolveu dados de registrador. Existe naquele unit id.
    - **respondeu sem dados**: devolveu PDU de excecao. Ha alguem no barramento,
      mas nao naquele unit id. Num device Modbus de campo, excecao 2 e a
      resposta normal de um endereco de unidade que nao existe.
    - **ausente**: nao respondeu nada dentro do prazo. Ninguem naquela unidade.
    """

    devices: list[DispositivoDescoberto] = field(default_factory=list)
    sem_dados: list[DispositivoDescoberto] = field(default_factory=list)
    unit_ids_ausentes: list[int] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)

    @property
    def total_respondidos(self) -> int:
        """Quantos unit ids devolveram dado de registrador.

        How many unit ids returned register data.
        """
        return len(self.devices)

    @property
    def barramento_ocupado(self) -> bool:
        """Se alguem respondeu no barramento.

        Whether anything answered on the bus.
        """
        return bool(self.devices or self.sem_dados)

    def classificar(self, achado: DispositivoDescoberto) -> None:
        """Coloca o resultado da sonda na lista certa.

        File the probe result in the right bucket.

        Args:
            achado: Resultado de uma sonda.
        """
        if not achado.respondeu:
            self.unit_ids_ausentes.append(achado.unit_id)
        elif achado.tem_registrador_zero:
            self.devices.append(achado)
        else:
            self.sem_dados.append(achado)


class ScannerModbus:
    """Varre o barramento e identifica quem responde.

    Sweeps the bus and finds who answers.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        porta: int = 5020,
        timeout: float = 0.25,
        primeiro_unit_id: int = PRIMEIRO_UNIT_ID,
        ultimo_unit_id: int = ULTIMO_UNIT_ID,
    ) -> None:
        self.host = host
        self.porta = porta
        self.timeout = timeout
        self.primeiro_unit_id = primeiro_unit_id
        self.ultimo_unit_id = ultimo_unit_id

    def sondar(self, unit_id: int) -> DispositivoDescoberto:
        """Sonda um unico unit id.

        Probe a single unit id.

        Uma conexao por sonda. E o que um scanner faz: nao pode presumir que o
        dispositivo que responde no id 1 e o mesmo processo que atende o id 2.

        Args:
            unit_id: Endereco a sondar.

        Returns:
            O resultado da sonda, com ``respondeu`` indicando se houve sinal.
        """
        cliente = ClienteModbus(self.host, self.porta, self.timeout)
        try:
            cliente.conectar()
            valores = cliente.ler(unit_id, ENDERECO_SONDA, 1, FUNCAO_SONDA)
            return DispositivoDescoberto(
                unit_id=unit_id,
                respondeu=True,
                funcao=FUNCAO_SONDA,
                valores=valores,
            )
        except ExcecaoRemota as exc:
            # Excecao de endereco e o modo normal de "nao sou eu".
            return DispositivoDescoberto(
                unit_id=unit_id,
                respondeu=True,
                funcao=exc.funcao,
                excecao=exc.codigo,
            )
        except (OSError, QuadroInvalido):
            return DispositivoDescoberto(unit_id=unit_id, respondeu=False)
        finally:
            cliente.fechar()

    def varrer(self, intervalo: range | None = None) -> ResultadoVarredura:
        """Varre um intervalo de unit ids.

        Sweep a range of unit ids.

        O intervalo padrao cobre a faixa util de unit id. Cada id morto custa um
        timeout inteiro, e por isso que o chamador normalmente passa a lista do
        cadastro em vez de varrer o espaco todo.

        Args:
            intervalo: Unit ids a sondar. O default e a faixa configurada.

        Returns:
            Devices, ids que responderam sem dado e ids ausentes.

        Raises:
            OSError: Se nada responder. Devolver uma varredura vazia seria
                indistinguivel de um barramento sem dispositivo, e essa
                confusao e exatamente o que uma ferramenta de diagnostico nao
                pode produzir.
        """
        alvo = intervalo if intervalo is not None else range(
            self.primeiro_unit_id, self.ultimo_unit_id + 1
        )
        resultado = ResultadoVarredura()
        for unit_id in alvo:
            resultado.classificar(self.sondar(unit_id))

        if not resultado.barramento_ocupado:
            raise OSError(
                f"nenhum device respondeu em {self.host}:{self.porta} nos unit ids "
                f"{alvo.start}..{alvo.stop - 1}. O servidor esta no ar?"
            )
        return resultado

    #: Nome antigo, mantido porque a CLI e a documentacao o usam.
    varrer_intervalo = varrer