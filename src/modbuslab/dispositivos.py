"""Medidores ficticios com seus registradores.

Fictitious energy meters and their registers.

Cada medidor tem um unit id, um mapa de registradores e valores de engenharia.
O servidor Modbus expoe um medidor por unit id, entao o endereco do registrador
so precisa ser unico dentro do dispositivo, e nao no barramento inteiro.

Os valores sao inventados. Um medidor real teria memoria persistente, aqui cada
processo comeca do zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .registros import MapaDeRegistros, Registrador

#: Tipos de medidor reconhecidos.
TIPOS_MEDIDOR = ("medidor monofasico", "medidor trifasico", "medidor de demanda")

#: Numero de fases de cada tipo de medidor.
FASES_POR_TIPO = {
    "medidor monofasico": 1,
    "medidor trifasico": 3,
    "medidor de demanda": 1,
}


@dataclass
class Dispositivo:
    """Um medidor simulado, com seus valores correntes.

    One simulated meter with its current values.
    """

    id: int
    nome: str
    tipo: str
    mapa: MapaDeRegistros
    fases: int = 1
    valores: dict[str, float] = field(default_factory=dict)

    @property
    def enderecos(self) -> set[int]:
        """Enderecos que este dispositivo atende.

        Addresses this device answers on.
        """
        return self.mapa.enderecos

    def valor(self, nome: str) -> float:
        """Valor de engenharia de um registrador.

        Engineering value of a register.

        Args:
            nome: Nome logico do registrador.

        Returns:
            O valor, ou zero se o registrador nao existir.
        """
        return self.valores.get(nome, 0.0)

    def definir(self, nome: str, valor: float) -> None:
        """Grava o valor de engenharia de um registrador.

        Write the engineering value of a register.
        """
        self.valores[nome] = float(valor)

    def ler_bruto(self, endereco: int) -> list[int]:
        """Le as palavras do fio de um endereco.

        Read the on-wire words at an address.

        Args:
            endereco: Endereco Modbus dentro do dispositivo.

        Returns:
            Uma palavra por endereco ocupado. Registrador de 32 bits devolve
            duas, palavra alta primeiro.

        Raises:
            KeyError: Se o endereco nao existir no mapa do dispositivo.
        """
        reg = self.mapa.buscar_por_endereco(endereco)
        if reg is None:
            raise KeyError(f"{self.nome}: endereco {endereco} nao existe")
        return reg.brutos(self.valores.get(reg.nome, 0.0))

    def escrever_bruto(self, endereco: int, brutos: list[int] | int) -> None:
        """Grava palavras vindas da rede.

        Write words coming from the network.

        Args:
            endereco: Endereco Modbus dentro do dispositivo.
            brutos: Uma palavra, ou a lista de palavras.

        Raises:
            KeyError: Se o endereco nao existir no mapa do dispositivo.
        """
        reg = self.mapa.buscar_por_endereco(endereco)
        if reg is None:
            raise KeyError(f"{self.nome}: endereco {endereco} nao existe")
        self.valores[reg.nome] = reg.engenharia(brutos)

    def leitura(self) -> dict[str, float]:
        """Todos os valores de engenharia, por nome de registrador.

        All engineering values, keyed by register name.
        """
        return {
            reg.nome: self.valores.get(reg.nome, 0.0)
            for reg in self.mapa.registradores
        }


@dataclass
class GerenciadorDispositivos:
    """Conjunto de medidores servidos por um servidor Modbus.

    The set of meters served by one Modbus server.
    """

    dispositivos: list[Dispositivo] = field(default_factory=list)

    def adicionar(self, dispositivo: Dispositivo) -> None:
        """Acrescenta um medidor, recusando unit id repetido.

        Add a meter, refusing a duplicate unit id.

        Args:
            dispositivo: Medidor a acrescentar.

        Raises:
            ValueError: Se o unit id ja existir.
        """
        if self.buscar(dispositivo.id) is not None:
            raise ValueError(f"unit id {dispositivo.id} ja em uso")
        self.dispositivos.append(dispositivo)

    def buscar(self, unit_id: int) -> Dispositivo | None:
        """Acha um medidor pelo unit id.

        Find a meter by unit id.
        """
        for d in self.dispositivos:
            if d.id == unit_id:
                return d
        return None

    @property
    def unit_ids(self) -> list[int]:
        """Unit ids em ordem crescente.

        Unit ids in ascending order.
        """
        return sorted(d.id for d in self.dispositivos)

    def __len__(self) -> int:
        return len(self.dispositivos)


def carregar_dispositivos(
    caminho: str | Path,
    mapa: dict[str, MapaDeRegistros],
) -> GerenciadorDispositivos:
    """Le os medidores de um arquivo YAML.

    Load the meters from a YAML file.

    Args:
        caminho: Caminho do YAML de dispositivos.
        mapa: Mapas de registradores ja carregados, por nome.

    Returns:
        O gerenciador com todos os medidores.

    Raises:
        ValueError: Se o YAML for invalido, se um mapa nao existir ou se um
            valor nao couber no registrador correspondente.
    """
    with open(caminho, "r", encoding="utf-8") as fh:
        dados = yaml.safe_load(fh)
    if not isinstance(dados, dict):
        raise ValueError(f"{caminho}: esperado um mapeamento no topo do arquivo")

    gerenciador = GerenciadorDispositivos()

    for item in dados.get("dispositivos", []):
        unit_id = int(item["id"])
        nome = str(item["nome"])
        tipo = str(item["tipo"])
        nome_mapa = str(item["mapa"])

        mapa_do_dispositivo = mapa.get(nome_mapa)
        if mapa_do_dispositivo is None:
            raise ValueError(
                f"{nome}: mapa '{nome_mapa}' nao existe no mapa de registradores"
            )

        fases = int(item.get("fases", FASES_POR_TIPO.get(tipo, 1)))

        dispositivo = Dispositivo(
            id=unit_id,
            nome=nome,
            tipo=tipo,
            mapa=mapa_do_dispositivo,
            fases=fases,
        )

        for nome_reg, valor in (item.get("valores") or {}).items():
            reg = mapa_do_dispositivo.buscar(str(nome_reg))
            if reg is None:
                raise ValueError(
                    f"{nome}: registrador '{nome_reg}' nao existe no mapa "
                    f"'{nome_mapa}'"
                )
            dispositivo.valores[reg.nome] = float(valor)
            # Valida o valor agora, e nao no primeiro atendimento do servidor.
            reg.brutos(float(valor))

        gerenciador.adicionar(dispositivo)

    return gerenciador


def carregar_ambiente(
    caminho_dispositivos: str | Path,
    caminho_mapa: str | Path,
) -> tuple[GerenciadorDispositivos, dict[str, MapaDeRegistros]]:
    """Carrega mapa e dispositivos de uma vez.

    Load the register map and the devices together.

    Args:
        caminho_dispositivos: Caminho do YAML de dispositivos.
        caminho_mapa: Caminho do YAML de mapa de registradores.

    Returns:
        Par com o gerenciador e os mapas.
    """
    from .registros import carregar_mapa

    mapa = carregar_mapa(caminho_mapa)
    gerenciador = carregar_dispositivos(caminho_dispositivos, mapa)
    return gerenciador, mapa


def registradores_de_energia(mapa: MapaDeRegistros) -> list[Registrador]:
    """Registradores que descrevem medicao de energia.

    Registers that describe an energy measurement.

    Args:
        mapa: Mapa do dispositivo.

    Returns:
        Registradores de tensao, corrente, potencia, energia e frequencia,
        em ordem de endereco.
    """
    relevantes = {
        "tensao", "tensao_l1", "tensao_l2", "tensao_l3",
        "corrente", "corrente_l1", "corrente_l2", "corrente_l3",
        "potencia_ativa", "potencia_reativa",
        "demanda_ativa", "demanda_reativa",
        "energia", "energia_acumulada",
        "frequencia", "fator_potencia",
    }
    return [r for r in mapa.ordenar_por_endereco() if r.nome in relevantes]