"""Mapa de registradores: nomes, enderecos, escala e conversao de valor.

Register map: names, addresses, scaling and value conversion.

Um medidor real nao manda tensao em volts, e sim um inteiro. Com escala 10, um
registrador que vale 2200 no fio significa 220,0 V. A conversao e sempre
``bruto / escala``, e o mesmo par de funcoes serve para os dois sentidos, para
que nao exista assimetria entre o que o servidor grava e o que o cliente le.

Os enderecos de cada dispositivo comecam em zero e sao independentes entre si. O
que separa um medidor do outro na rede e o unit id do MBAP, nao o endereco.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

#: Tipos de registrador suportados.
TIPOS_VALIDOS = frozenset({"uint16", "int16", "uint32", "int32"})

#: Tipos que ocupam dois enderecos de 16 bits.
TIPOS_LARGOS = frozenset({"uint32", "int32"})

#: Valor maximo de um registrador sem sinal de 16 bits.
UINT16_MAX = 0xFFFF

#: Valor maximo de um registrador sem sinal de 32 bits.
UINT32_MAX = 0xFFFFFFFF

#: Faixa de um registrador com sinal de 16 bits.
INT16_MIN = -32768
INT16_MAX = 32767

#: Faixa de um registrador com sinal de 32 bits.
INT32_MIN = -2147483648
INT32_MAX = 2147483647


class ErroDeRegistro(ValueError):
    """Valor fora do que o registrador aceita."""


@dataclass(frozen=True)
class Registrador:
    """Um registrador nomeado, com endereco, tipo, unidade e escala.

    A single named register.

    ## Registrador largo

    Energia acumulada passa de 65535 cedo: um medidor que marcou 100 kWh
    estoura um registrador de 16 bits. A solucao no mundo real e ocupar dois
    enderecos, e e o que os tipos ``uint32`` e ``int32`` fazem aqui. A ordem das
    palavras e a de uso comum em automacao: **palavra alta primeiro**, que e a
    convencao da Modicon e a mais encontravel em medidor.

    Args:
        nome: Identificador logico, como ``potencia_ativa``.
        endereco: Endereco Modbus dentro do espaco do dispositivo. Em
            registrador largo, o endereco da palavra alta.
        tipo: Um de :data:`TIPOS_VALIDOS`.
        unidade: Unidade de engenharia, vazia para valores adimensionais.
        escala: Divisor do valor de engenharia. ``bruto = valor * escala``.
        descricao: Texto curto para o mapa documentado.
    """

    nome: str
    endereco: int
    tipo: str = "uint16"
    unidade: str = ""
    escala: float = 1.0
    descricao: str = ""

    def __post_init__(self) -> None:
        """Valida os campos no momento da construcao.

        Validate fields at construction time.
        """
        if self.tipo not in TIPOS_VALIDOS:
            raise ErroDeRegistro(
                f"{self.nome}: tipo {self.tipo!r} invalido, use {sorted(TIPOS_VALIDOS)}"
            )
        if not (0 <= self.endereco <= UINT16_MAX):
            raise ErroDeRegistro(
                f"{self.nome}: endereco {self.endereco} fora de 0..{UINT16_MAX}"
            )
        if self.escala <= 0:
            raise ErroDeRegistro(
                f"{self.nome}: escala {self.escala} precisa ser maior que zero"
            )

    @property
    def palavras(self) -> int:
        """Quantos enderecos de 16 bits o registrador ocupa.

        How many 16-bit addresses this register spans.
        """
        return 2 if self.tipo in TIPOS_LARGOS else 1

    @property
    def offset(self) -> int:
        """Deslocamento em bytes do registrador no bloco de dados.

        Byte offset of the register inside a read block.
        """
        return self.endereco * 2

    @property
    def _faixa_bruta(self) -> tuple[int, int]:
        """Faixa de inteiro que o tipo aceita.

        Integer range the type accepts.
        """
        if self.tipo == "uint16":
            return (0, UINT16_MAX)
        if self.tipo == "int16":
            return (INT16_MIN, INT16_MAX)
        if self.tipo == "uint32":
            return (0, UINT32_MAX)
        return (INT32_MIN, INT32_MAX)

    @property
    def _faixa_engenharia(self) -> tuple[float, float]:
        """Faixa de engenharia correspondente.

        Matching engineering range.
        """
        menor, maior = self._faixa_bruta
        return (menor / self.escala, maior / self.escala)

    @property
    def faixa(self) -> tuple[float, float]:
        """Faixa de engenharia que o registrador representa.

        Engineering range this register can represent.
        """
        return self._faixa_engenharia

    def brutos(self, valor: float) -> list[int]:
        """Converte valor de engenharia para os inteiros do fio.

        Convert an engineering value to the on-wire integers.

        Args:
            valor: Valor na unidade do registrador.

        Returns:
            Uma palavra por endereco ocupado, palavra alta primeiro em
            registrador largo.

        Raises:
            ErroDeRegistro: Se o valor nao couber no tipo do registrador.
        """
        bruto = int(round(valor * self.escala))
        menor, maior = self._faixa_bruta
        if not (menor <= bruto <= maior):
            raise ErroDeRegistro(
                f"{self.nome}: {valor} {self.unidade} vira {bruto}, "
                f"fora de {self.tipo} ({menor}..{maior})"
            )
        if self.palavras == 1:
            return [bruto & UINT16_MAX]
        if self.tipo == "uint32":
            return [(bruto >> 16) & UINT16_MAX, bruto & UINT16_MAX]
        sinal = bruto & 0xFFFFFFFF
        return [(sinal >> 16) & UINT16_MAX, sinal & UINT16_MAX]

    def engenharia(self, brutos: list[int] | int) -> float:
        """Converte os inteiros do fio para valor de engenharia.

        Convert the on-wire integers to an engineering value.

        Args:
            brutos: Uma palavra, ou a lista de palavras do registrador.

        Returns:
            O valor na unidade do registrador.

        Raises:
            ErroDeRegistro: Se faltarem palavras ou os valores nao couberem
                no tipo.
        """
        palavras = [brutos] if isinstance(brutos, int) else list(brutos)
        if len(palavras) < self.palavras:
            raise ErroDeRegistro(
                f"{self.nome}: esperado {self.palavras} palavra(s), "
                f"recebi {len(palavras)}"
            )
        if len(palavras) > self.palavras:
            palavras = palavras[:self.palavras]

        for p in palavras:
            if not (0 <= p <= UINT16_MAX):
                raise ErroDeRegistro(
                    f"{self.nome}: palavra {p} fora de 0..{UINT16_MAX}"
                )

        # Cada tipo tem um valor inteiro proprio, e ele vem do mesmo par de 16
        # bits que o cliente leu. int16 e int32 precisam reconverter o padrao
        # para signed ANTES da checagem de faixa, senao 64036, que e -1500 em
        # complemento a dois, seria recusado como fora de int16.
        if self.tipo == "uint16":
            bruto = palavras[0]
        elif self.tipo == "int16":
            bruto = palavras[0] - 0x10000 if palavras[0] & 0x8000 else palavras[0]
        else:
            sinal = (palavras[0] << 16) | palavras[1]
            if self.tipo == "uint32":
                bruto = sinal
            else:
                bruto = sinal - 0x100000000 if sinal & 0x80000000 else sinal

        menor, maior = self._faixa_bruta
        if not (menor <= bruto <= maior):
            raise ErroDeRegistro(
                f"{self.nome}: valor {bruto} fora de {self.tipo} "
                f"({menor}..{maior})"
            )
        return bruto / self.escala


@dataclass
class MapaDeRegistros:
    """Espaco de registradores de um dispositivo.

    The register space of one device.
    """

    nome: str
    registradores: list[Registrador] = field(default_factory=list)

    def adicionar(self, reg: Registrador) -> None:
        """Acrescenta um registrador, recusando endereco ocupado.

        Add a register, refusing an occupied address.

        Args:
            reg: Registrador a acrescentar.

        Raises:
            ErroDeRegistro: Se algum dos enderecos do registrador ja existir,
                o que inclui o segundo endereco de um registrador largo.
        """
        ocupados = self.enderecos_ocupados()
        conflitos = [e for e in range(reg.endereco, reg.endereco + reg.palavras)
                     if e in ocupados]
        if conflitos:
            raise ErroDeRegistro(
                f"{self.nome}: endereco {reg.endereco} ({reg.nome}) "
                f"conflita com {conflitos}"
            )
        self.registradores.append(reg)

    def enderecos_ocupados(self) -> set[int]:
        """Todos os enderecos cobertos, incluindo os segundos de largos.

        Every address covered, including the second word of wide registers.
        """
        ocupados: set[int] = set()
        for r in self.registradores:
            ocupados.update(range(r.endereco, r.endereco + r.palavras))
        return ocupados

    def buscar(self, nome: str) -> Registrador | None:
        """Acha um registrador pelo nome.

        Find a register by name.
        """
        for r in self.registradores:
            if r.nome == nome:
                return r
        return None

    def buscar_por_endereco(self, endereco: int) -> Registrador | None:
        """Acha um registrador que COMECA no endereco.

        Find a register that STARTS at the address.

        Em registrador largo, so o endereco de inicio devolve o registrador. A
        segunda palavra nao comeca registrador nenhum; para ela use
        :meth:`cobre`.
        """
        for r in self.registradores:
            if r.endereco == endereco:
                return r
        return None

    def cobre(self, endereco: int) -> tuple[Registrador, int] | None:
        """Acha o registrador que contem o endereco e a posicao da palavra.

        Find the register containing the address and the word position.

        Registrador de 32 bits ocupa dois enderecos, e cada palavra tem o seu
        proprio endereco no fio. Ler o bloco inteiro exige servir as duas, cada
        uma na sua posicao.

        Args:
            endereco: Endereco do fio.

        Returns:
            Par com o registrador e o indice da palavra, ou ``None`` se o
            endereco nao pertence a nenhum registrador.
        """
        for r in self.registradores:
            if r.endereco <= endereco < r.endereco + r.palavras:
                return (r, endereco - r.endereco)
        return None

    @property
    def enderecos(self) -> set[int]:
        """Enderecos de inicio de registrador.

        Register start addresses.
        """
        return {r.endereco for r in self.registradores}

    @property
    def tamanho(self) -> int:
        """Quantos enderecos o mapa ocupa, contando registradores largos.

        How many addresses the map spans, counting wide registers.

        O mapa com os dois enderecos de um registrador de 32 bits tem tamanho
        maior que a contagem de registradores, porque a segunda palavra ocupa um
        endereco que nao comeca nenhum registrador.
        """
        ocupados = self.enderecos_ocupados()
        return (max(ocupados) + 1) if ocupados else 0

    def ordenar_por_endereco(self) -> list[Registrador]:
        """Registradores em ordem de endereco.

        Registers sorted by address.
        """
        return sorted(self.registradores, key=lambda r: r.endereco)

    def bloco(self, endereco: int, quantidade: int) -> list[Registrador]:
        """Registradores do intervalo pedido, ou o mais proximo disponivel.

        Registers in the requested range, or the nearest available ones.

        Um mapa pode ter lacunas. Quando o cliente pede um intervalo que cruza
        uma, o servidor entrega os registradores que existem a partir do
        endereco pedido e devolve excecao de endereco so quando nao sobra
        nenhum. Isso evita que uma lacuna interna vire erro para o cliente,
        que so quer ler os medidores.

        Args:
            endereco: Primeiro endereco pedido.
            quantidade: Quantos enderecos foram pedidos.

        Returns:
            Lista de registradores encontrados, em ordem de endereco.

        Raises:
            ErroDeRegistro: Se ``quantidade`` for menor que 1.
        """
        if quantidade < 1:
            raise ErroDeRegistro(f"quantidade {quantidade} precisa ser ao menos 1")
        candidatos = [r for r in self.registradores if r.endereco >= endereco]
        return sorted(candidatos, key=lambda r: r.endereco)[:quantidade]


def _registrador_de_dict(dado: dict[str, Any]) -> Registrador:
    """Constroi um registrador a partir de um dicionario de YAML.

    Build a register from a YAML mapping.
    """
    return Registrador(
        nome=str(dado["nome"]),
        endereco=int(dado["endereco"]),
        tipo=str(dado.get("tipo", "uint16")),
        unidade=str(dado.get("unidade", "")),
        escala=float(dado.get("escala", 1.0)),
        descricao=str(dado.get("descricao", "")),
    )


def carregar_mapa(caminho: str | Path) -> dict[str, MapaDeRegistros]:
    """Le um mapa de registradores de um arquivo YAML.

    Load a register map from a YAML file.

    Args:
        caminho: Caminho do YAML, no formato
            ``nome_do_mapa: [lista de registradores]``.

    Returns:
        Dicionario de nome do mapa para :class:`MapaDeRegistros`.

    Raises:
        ValueError: Se o topo do arquivo nao for um mapeamento.
    """
    with open(caminho, "r", encoding="utf-8") as fh:
        dados = yaml.safe_load(fh)
    if not isinstance(dados, dict):
        raise ValueError(
            f"{caminho}: esperado um mapeamento no topo do arquivo"
        )
    resultado: dict[str, MapaDeRegistros] = {}
    for nome_mapa, definicao in dados.items():
        mapa = MapaDeRegistros(nome=str(nome_mapa))
        if isinstance(definicao, list):
            for item in definicao:
                mapa.adicionar(_registrador_de_dict(item))
        resultado[str(nome_mapa)] = mapa
    return resultado


def tabela_do_mapa(mapa: MapaDeRegistros) -> str:
    """Monta a tabela do mapa em texto.

    Render the register map as a text table.

    Args:
        mapa: Mapa a descrever.

    Returns:
        Tabela em texto com endereco, nome, tipo, largura, escala e unidade.
    """
    cabecalho = (
        f"{'End':>4}  {'Nome':<20} {'Tipo':<7} {'Pal':>3} {'Escala':>7}  "
        f"{'Unidade':<8} Descricao"
    )
    linhas = [cabecalho, "-" * len(cabecalho)]
    for reg in mapa.ordenar_por_endereco():
        linhas.append(
            f"{reg.endereco:>4}  {reg.nome:<20} {reg.tipo:<7} "
            f"{reg.palavras:>3} {reg.escala:>7g}  {reg.unidade:<8} "
            f"{reg.descricao}"
        )
    return "\n".join(linhas)