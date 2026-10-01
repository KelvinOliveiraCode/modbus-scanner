"""Testes dos medidores ficticios e da carga dos dados.

Fictitious meter and data-loading tests.

A validacao no carregamento e o que garante que um erro de digitacao no YAML
falha na hora de subir o servidor, e nao na primeira leitura, quando o valor ja
foi gravado no medidor. Um `fator_potencia: 962` no lugar de `0.962` estoura
uint16 e e recusado aqui.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modbuslab.dispositivos import (
    Dispositivo,
    GerenciadorDispositivos,
    carregar_ambiente,
    carregar_dispositivos,
    registradores_de_energia,
)
from modbuslab.servidor import ServidorModbus
from modbuslab.registros import (
    ErroDeRegistro,
    MapaDeRegistros,
    Registrador,
    carregar_mapa,
)

MAPA = "dados/mapa-de-registros.yaml"
DISPOSITIVOS = "dados/dispositivos.yaml"

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def ambiente() -> tuple:
    """Os tres medidores carregados do disco.

    The three meters loaded from disk.
    """
    return carregar_ambiente(RAIZ / DISPOSITIVOS, RAIZ / MAPA)


class TestDispositivo:
    """Um medidor com seus valores."""

    @pytest.fixture
    def medidor(self) -> Dispositivo:
        mapa = MapaDeRegistros(nome="t")
        mapa.adicionar(Registrador("tensao", 0, escala=10, unidade="V"))
        mapa.adicionar(Registrador("energia", 1, tipo="uint32", unidade="kWh"))
        return Dispositivo(
            id=1, nome="m", tipo="medidor monofasico", mapa=mapa, fases=1
        )

    def test_valor_padrao_e_zero(self, medidor: Dispositivo) -> None:
        assert medidor.valor("tensao") == 0.0

    def test_definir_e_ler(self, medidor: Dispositivo) -> None:
        medidor.definir("tensao", 220.0)
        assert medidor.valor("tensao") == 220.0

    def test_valor_de_registrador_inexistente(self, medidor: Dispositivo) -> None:
        assert medidor.valor("nao_existe") == 0.0

    def test_ler_bruto(self, medidor: Dispositivo) -> None:
        medidor.definir("tensao", 219.4)
        assert medidor.ler_bruto(0) == [2194]

    def test_ler_bruto_de_registrador_largo(self, medidor: Dispositivo) -> None:
        medidor.definir("energia", 91240)
        assert medidor.ler_bruto(1) == [1, 25704]

    def test_ler_bruto_de_endereco_inexistente(self, medidor: Dispositivo) -> None:
        with pytest.raises(KeyError):
            medidor.ler_bruto(99)

    def test_escrever_bruto(self, medidor: Dispositivo) -> None:
        medidor.escrever_bruto(0, 2194)
        assert medidor.valor("tensao") == pytest.approx(219.4)

    def test_escrever_bruto_de_largo(self, medidor: Dispositivo) -> None:
        medidor.escrever_bruto(1, [1, 25704])
        assert medidor.valor("energia") == pytest.approx(91240.0)

    def test_escrever_bruto_de_endereco_inexistente(self, medidor: Dispositivo) -> None:
        with pytest.raises(KeyError):
            medidor.escrever_bruto(99, 1)

    def test_leitura_traz_todos(self, medidor: Dispositivo) -> None:
        medidor.definir("tensao", 220.0)
        assert medidor.leitura() == {"tensao": 220.0, "energia": 0.0}

    def test_enderecos(self, medidor: Dispositivo) -> None:
        assert medidor.enderecos == {0, 1}


class TestGerenciador:
    """Conjunto de medidores."""

    @pytest.fixture
    def gerenciador(self) -> GerenciadorDispositivos:
        mapa = MapaDeRegistros(nome="t")
        mapa.adicionar(Registrador("x", 0))
        return GerenciadorDispositivos(dispositivos=[
            Dispositivo(1, "a", "medidor monofasico", mapa),
            Dispositivo(2, "b", "medidor monofasico", mapa),
        ])

    def test_buscar(self, gerenciador: GerenciadorDispositivos) -> None:
        assert gerenciador.buscar(2).nome == "b"

    def test_buscar_inexistente(self, gerenciador: GerenciadorDispositivos) -> None:
        assert gerenciador.buscar(99) is None

    def test_unit_ids_ordenados(self) -> None:
        mapa = MapaDeRegistros(nome="t")
        mapa.adicionar(Registrador("x", 0))
        g = GerenciadorDispositivos(dispositivos=[
            Dispositivo(3, "c", "medidor monofasico", mapa),
            Dispositivo(1, "a", "medidor monofasico", mapa),
        ])
        assert g.unit_ids == [1, 3]

    def test_unit_id_repetido(self, gerenciador: GerenciadorDispositivos) -> None:
        mapa = MapaDeRegistros(nome="t")
        mapa.adicionar(Registrador("x", 0))
        with pytest.raises(ValueError, match="unit id"):
            gerenciador.adicionar(Dispositivo(1, "c", "medidor monofasico", mapa))

    def test_tamanho(self, gerenciador: GerenciadorDispositivos) -> None:
        assert len(gerenciador) == 2

    def test_gerenciador_vazio(self) -> None:
        assert len(GerenciadorDispositivos()) == 0


class TestCargaDoDisco:
    """Os dados que acompanham o repositorio."""

    def test_carrega_tres_medidores(self, ambiente: tuple) -> None:
        gerenciador, _ = ambiente
        assert len(gerenciador) == 3
        assert gerenciador.unit_ids == [1, 2, 3]

    def test_nomes(self, ambiente: tuple) -> None:
        gerenciador, _ = ambiente
        assert [d.nome for d in gerenciador.dispositivos] == [
            "medidor-1pn", "medidor-3pn", "medidor-demanda"
        ]

    def test_tem_os_tres_tipos_de_medidor(self, ambiente: tuple) -> None:
        gerenciador, _ = ambiente
        tipos = {d.tipo for d in gerenciador.dispositivos}
        assert tipos == {
            "medidor monofasico", "medidor trifasico", "medidor de demanda"
        }

    def test_um_trifasico(self, ambiente: tuple) -> None:
        gerenciador, _ = ambiente
        trifasicos = [d for d in gerenciador.dispositivos if d.fases == 3]
        assert len(trifasicos) == 1
        assert trifasicos[0].fases == 3

    def test_sequencia_invertida_esta_no_dado(self, ambiente: tuple) -> None:
        # angulo_l1=0, angulo_l2=120: salto de 120, sequencia negativa.
        gerenciador, _ = ambiente
        t = gerenciador.buscar(2)
        assert t.valor("angulo_l1") == 0.0
        assert t.valor("angulo_l2") == 120.0
        assert t.valor("angulo_l3") == 240.0

    def test_energia_acima_de_16_bits(self, ambiente: tuple) -> None:
        gerenciador, _ = ambiente
        valores = [d.valores.get("energia", d.valores.get("energia_acumulada", 0))
                   for d in gerenciador.dispositivos]
        # Pelo menos um medidor precisa de 32 bits, senao o registrador largo
        # do mapa seria motivo inutil.
        assert max(valores) > 65535

    def test_frequencia_proxima_de_60(self, ambiente: tuple) -> None:
        gerenciador, _ = ambiente
        for d in gerenciador.dispositivos:
            assert 59.0 <= d.valor("frequencia") <= 61.0

    def test_tensoes_plausiveis(self, ambiente: tuple) -> None:
        gerenciador, _ = ambiente
        for d in gerenciador.dispositivos:
            for nome in ("tensao", "tensao_l1", "tensao_l2", "tensao_l3"):
                if nome in d.valores:
                    assert 200.0 <= d.valores[nome] <= 250.0

    def test_fator_de_potencia_no_intervalo(self, ambiente: tuple) -> None:
        gerenciador, _ = ambiente
        for d in gerenciador.dispositivos:
            assert 0.0 <= d.valor("fator_potencia") <= 1.0

    def test_nada_aponta_para_host_real(self, ambiente: tuple) -> None:
        # O servidor so escuta em loopback, entao o lab nao alcanca a rede.
        gerenciador, _ = ambiente
        assert ServidorModbus(gerenciador).host == "127.0.0.1"


class TestCargaComErro:
    """Dados invalidos recusados na carga."""

    def test_topo_nao_mapeado(self, tmp_path: Path) -> None:
        arquivo = tmp_path / "d.yaml"
        arquivo.write_text("- lista\n", encoding="utf-8")
        with pytest.raises(ValueError, match="mapeamento"):
            carregar_dispositivos(arquivo, {})

    def test_mapa_inexistente(self, tmp_path: Path) -> None:
        arquivo = tmp_path / "d.yaml"
        arquivo.write_text(
            "dispositivos:\n"
            "  - id: 1\n    nome: x\n    tipo: medidor monofasico\n"
            "    mapa: nao_existe\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="nao existe"):
            carregar_dispositivos(arquivo, {})

    def test_registrador_inexistente(self, tmp_path: Path) -> None:
        arquivo = tmp_path / "d.yaml"
        arquivo.write_text(
            "dispositivos:\n"
            "  - id: 1\n    nome: x\n    tipo: medidor monofasico\n"
            "    mapa: m\n    valores:\n      nao_existe: 1\n",
            encoding="utf-8",
        )
        mapa = {"m": MapaDeRegistros(nome="m")}
        with pytest.raises(ValueError, match="nao existe no mapa"):
            carregar_dispositivos(arquivo, mapa)

    def test_valor_fora_do_tipo(self, tmp_path: Path) -> None:
        arquivo = tmp_path / "d.yaml"
        arquivo.write_text(
            "dispositivos:\n"
            "  - id: 1\n    nome: x\n    tipo: medidor monofasico\n"
            "    mapa: m\n    valores:\n      tensao: 70000\n",
            encoding="utf-8",
        )
        mapa = {"m": MapaDeRegistros(nome="m")}
        mapa["m"].adicionar(Registrador("tensao", 0, escala=1))
        with pytest.raises(ErroDeRegistro):
            carregar_dispositivos(arquivo, mapa)

    def test_arquivo_inexistente(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            carregar_dispositivos(tmp_path / "nao_existe.yaml", {})

    def test_dicionario_vazio(self, tmp_path: Path) -> None:
        arquivo = tmp_path / "d.yaml"
        arquivo.write_text("dispositivos: []\n", encoding="utf-8")
        g = carregar_dispositivos(arquivo, {})
        assert len(g) == 0


class TestRegistradoresDeEnergia:
    """Filtro dos registradores de medicao."""

    def test_filtra_energia(self) -> None:
        mapa = carregar_mapa(RAIZ / MAPA)
        regs = registradores_de_energia(mapa["medidor_1pn"])
        nomes = {r.nome for r in regs}
        assert "tensao" in nomes
        assert "potencia_ativa" in nomes
        assert "energia" in nomes

    def test_exclui_angulo(self) -> None:
        mapa = carregar_mapa(RAIZ / MAPA)
        regs = registradores_de_energia(mapa["medidor_3pn"])
        # Angulo serve para sequencia de fase, nao para consumo.
        assert not any(r.nome.startswith("angulo") for r in regs)

    def test_em_ordem_de_endereco(self) -> None:
        mapa = carregar_mapa(RAIZ / MAPA)
        regs = registradores_de_energia(mapa["medidor_3pn"])
        assert [r.endereco for r in regs] == sorted(r.endereco for r in regs)