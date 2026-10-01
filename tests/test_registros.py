"""Testes do mapa de registradores e da conversao de valores.

Register map and value conversion tests.

O caso que domina estes testes e o registrador de 32 bits. Energia acumulada
passa de 65535 cedo, e um uint16 nao comporta. A solucao do mundo real e ocupar
dois enderecos, palavra alta primeiro. Um dos bugs encontrados neste projeto foi
o servidor devolver a palavra alta e a baixa como dois registradores zero, o que
fazia 91240 kWh virar 65536.
"""

from __future__ import annotations

import pytest

from modbuslab.registros import (
    INT16_MAX,
    INT16_MIN,
    INT32_MAX,
    INT32_MIN,
    UINT16_MAX,
    UINT32_MAX,
    ErroDeRegistro,
    MapaDeRegistros,
    Registrador,
    carregar_mapa,
    tabela_do_mapa,
)


class TestRegistradorValidacao:
    """Campos invalidos recusados na construcao."""

    def test_tipo_desconhecido(self) -> None:
        with pytest.raises(ErroDeRegistro):
            Registrador("x", 0, tipo="float64")

    @pytest.mark.parametrize("tipo", ["uint16", "int16", "uint32", "int32"])
    def test_tipos_validos(self, tipo: str) -> None:
        assert Registrador("x", 0, tipo=tipo).palavras >= 1

    def test_endereco_negativo(self) -> None:
        with pytest.raises(ErroDeRegistro):
            Registrador("x", -1)

    def test_endereco_acima_do_maximo(self) -> None:
        with pytest.raises(ErroDeRegistro):
            Registrador("x", 65536)

    def test_escala_zero(self) -> None:
        with pytest.raises(ErroDeRegistro):
            Registrador("x", 0, escala=0.0)

    def test_escala_negativa(self) -> None:
        with pytest.raises(ErroDeRegistro):
            Registrador("x", 0, escala=-1.0)

    def test_padroes_sao_validos(self) -> None:
        reg = Registrador("x", 0)
        assert reg.tipo == "uint16"
        assert reg.escala == 1.0
        assert reg.palavras == 1


class TestLarguraDoRegistrador:
    """Quantos enderecos cada tipo ocupa."""

    def test_16_bits_uma_palavra(self) -> None:
        assert Registrador("x", 0, tipo="uint16").palavras == 1

    def test_int16_uma_palavra(self) -> None:
        assert Registrador("x", 0, tipo="int16").palavras == 1

    def test_uint32_duas_palavras(self) -> None:
        assert Registrador("x", 0, tipo="uint32").palavras == 2

    def test_int32_duas_palavras(self) -> None:
        assert Registrador("x", 0, tipo="int32").palavras == 2

    def test_offset_em_bytes(self) -> None:
        assert Registrador("x", 5).offset == 10


class TestConversao16Bits:
    """Escala em registrador de 16 bits."""

    def test_tensao_com_escala_dez(self) -> None:
        reg = Registrador("tensao", 0, escala=10)
        assert reg.brutos(219.4) == [2194]
        assert reg.engenharia([2194]) == 219.4

    def test_corrente_com_escala_cem(self) -> None:
        reg = Registrador("corrente", 1, escala=100)
        assert reg.brutos(12.35) == [1235]

    def test_fator_de_potencia_com_escala_mil(self) -> None:
        reg = Registrador("fp", 7, escala=1000)
        assert reg.brutos(0.962) == [962]
        assert reg.engenharia([962]) == pytest.approx(0.962)

    def test_int16_negativo(self) -> None:
        reg = Registrador("reativa", 3, tipo="int16")
        # No fio vai o complemento a dois mascarado em 16 bits.
        assert reg.brutos(-1500) == [(-1500) & UINT16_MAX]
        assert reg.engenharia(reg.brutos(-1500)) == -1500.0

    def test_int16_limite_inferior(self) -> None:
        reg = Registrador("x", 0, tipo="int16")
        assert reg.brutos(INT16_MIN) == [0x8000]
        assert reg.engenharia([0x8000]) == float(INT16_MIN)

    def test_int16_limite_superior(self) -> None:
        reg = Registrador("x", 0, tipo="int16")
        assert reg.engenharia([INT16_MAX]) == float(INT16_MAX)

    def test_uint16_aceita_inteiro(self) -> None:
        assert Registrador("x", 0, escala=1).brutos(1234) == [1234]

    def test_engenharia_aceita_inteiro_solto(self) -> None:
        assert Registrador("x", 0).engenharia(500) == 500.0

    def test_valor_que_estoura_uint16(self) -> None:
        reg = Registrador("x", 0, escala=1, tipo="uint16")
        with pytest.raises(ErroDeRegistro):
            reg.brutos(70000)

    def test_valor_negativo_em_uint16(self) -> None:
        reg = Registrador("x", 0, tipo="uint16")
        with pytest.raises(ErroDeRegistro):
            reg.brutos(-1)

    def test_valor_que_estoura_int16(self) -> None:
        reg = Registrador("x", 0, tipo="int16")
        with pytest.raises(ErroDeRegistro):
            reg.brutos(40000)

    def test_bruto_fora_do_tipo_na_engenharia(self) -> None:
        with pytest.raises(ErroDeRegistro):
            Registrador("x", 0, tipo="uint16").engenharia([70000])

    def test_bruto_negativo_na_engenharia(self) -> None:
        with pytest.raises(ErroDeRegistro):
            Registrador("x", 0, tipo="uint16").engenharia([-1])

    def test_mensagem_de_erro_nomeia_o_registrador(self) -> None:
        reg = Registrador("minha_tensao", 0, escala=1, tipo="uint16", unidade="V")
        with pytest.raises(ErroDeRegistro, match="minha_tensao"):
            reg.brutos(99999)


class TestConversao32Bits:
    """Registrador largo, dois enderecos."""

    def test_energia_acima_de_uint16(self) -> None:
        reg = Registrador("energia", 4, tipo="uint32", escala=1)
        # 91240 nao cabe em uint16. E o caso que motiva o registrador largo.
        assert reg.brutos(91240) == [1, 25704]

    def test_ida_e_volta_de_energia(self) -> None:
        reg = Registrador("energia", 4, tipo="uint32", escala=1)
        for valor in (0, 18432, 91240, 412880, UINT32_MAX):
            assert reg.engenharia(reg.brutos(valor)) == pytest.approx(float(valor))

    def test_palavra_alta_primeiro(self) -> None:
        # Convencao Modicon: o endereco menor guarda a palavra alta.
        reg = Registrador("e", 0, tipo="uint32")
        assert reg.brutos(0x00010000) == [1, 0]
        assert reg.brutos(0x00000001) == [0, 1]

    def test_int32_negativo(self) -> None:
        reg = Registrador("e", 0, tipo="int32")
        palavras = reg.brutos(-100000)
        assert len(palavras) == 2
        assert reg.engenharia(palavras) == pytest.approx(-100000.0)

    def test_int32_extremos(self) -> None:
        reg = Registrador("e", 0, tipo="int32")
        assert reg.engenharia(reg.brutos(INT32_MAX)) == pytest.approx(float(INT32_MAX))
        assert reg.engenharia(reg.brutos(INT32_MIN)) == pytest.approx(float(INT32_MIN))
        assert len(reg.brutos(INT32_MIN)) == 2

    def test_escala_em_registrador_largo(self) -> None:
        reg = Registrador("e", 0, tipo="uint32", escala=100)
        # 1234,56 * 100 = 123456 = 0x01E240
        assert reg.brutos(1234.56) == [1, 57920]
        assert reg.engenharia([1, 57920]) == pytest.approx(1234.56)

    def test_palavra_faltando(self) -> None:
        reg = Registrador("e", 0, tipo="uint32")
        with pytest.raises(ErroDeRegistro):
            reg.engenharia([1])

    def test_palavra_excedente_ignorada(self) -> None:
        reg = Registrador("e", 0, tipo="uint16")
        assert reg.engenharia([10, 20]) == 10.0

    def test_palavra_fora_de_16_bits(self) -> None:
        with pytest.raises(ErroDeRegistro):
            Registrador("e", 0, tipo="uint32").engenharia([70000, 0])

    def test_valor_acima_de_uint32(self) -> None:
        with pytest.raises(ErroDeRegistro):
            Registrador("e", 0, tipo="uint32").brutos(UINT32_MAX + 1)

    def test_faixa_de_engenharia_larga(self) -> None:
        reg = Registrador("e", 0, tipo="uint32", escala=1)
        assert reg.faixa == (0.0, float(UINT32_MAX))

    def test_faixa_de_engenharia_16(self) -> None:
        reg = Registrador("x", 0, tipo="uint16", escala=10)
        assert reg.faixa == (0.0, UINT16_MAX / 10)


@pytest.fixture
def mapa() -> MapaDeRegistros:
    """Mapa pequeno com um registrador largo no meio.

    Small map with a wide register in the middle.
    """
    m = MapaDeRegistros(nome="teste")
    m.adicionar(Registrador("tensao", 0, escala=10, unidade="V"))
    m.adicionar(Registrador("corrente", 1, escala=100, unidade="A"))
    m.adicionar(Registrador("energia", 2, tipo="uint32", unidade="kWh"))
    m.adicionar(Registrador("frequencia", 4, escala=100, unidade="Hz"))
    return m


class TestMapaDeRegistros:
    """Conjunto de registradores de um dispositivo."""

    def test_buscar_por_nome(self, mapa: MapaDeRegistros) -> None:
        assert mapa.buscar("tensao").unidade == "V"

    def test_nome_inexistente(self, mapa: MapaDeRegistros) -> None:
        assert mapa.buscar("nao_existe") is None

    def test_buscar_por_endereco(self, mapa: MapaDeRegistros) -> None:
        assert mapa.buscar_por_endereco(1).nome == "corrente"

    def test_endereco_inexistente(self, mapa: MapaDeRegistros) -> None:
        assert mapa.buscar_por_endereco(99) is None

    def test_endereco_repetido(self, mapa: MapaDeRegistros) -> None:
        with pytest.raises(ErroDeRegistro):
            mapa.adicionar(Registrador("outro", 0))

    def test_conflito_com_segunda_palavra(self, mapa: MapaDeRegistros) -> None:
        # Endereco 3 e a palavra baixa de energia, em 2.
        with pytest.raises(ErroDeRegistro):
            mapa.adicionar(Registrador("conflito", 3))

    def test_tamanho_conta_palavra_extra(self, mapa: MapaDeRegistros) -> None:
        # 4 registros, mas energia ocupa 2 e 3: o mapa vai ate o endereco 4.
        assert mapa.tamanho == 5

    def test_tamanho_do_mapa_vazio(self) -> None:
        assert MapaDeRegistros("vazio").tamanho == 0

    def test_enderecos_de_inicio(self, mapa: MapaDeRegistros) -> None:
        assert mapa.enderecos == {0, 1, 2, 4}

    def test_enderecos_ocupados_inclui_palavra_baixa(
        self, mapa: MapaDeRegistros
    ) -> None:
        assert mapa.enderecos_ocupados() == {0, 1, 2, 3, 4}

    def test_ordenar_por_endereco(self, mapa: MapaDeRegistros) -> None:
        nomes = [r.nome for r in mapa.ordenar_por_endereco()]
        assert nomes == ["tensao", "corrente", "energia", "frequencia"]

    def test_cobre_no_inicio(self, mapa: MapaDeRegistros) -> None:
        reg, pos = mapa.cobre(1)
        assert reg.nome == "corrente"
        assert pos == 0

    def test_cobre_na_palavra_baixa(self, mapa: MapaDeRegistros) -> None:
        reg, pos = mapa.cobre(3)
        assert reg.nome == "energia"
        assert pos == 1

    def test_cobre_fora_do_mapa(self, mapa: MapaDeRegistros) -> None:
        assert mapa.cobre(99) is None

    def test_bloco(self, mapa: MapaDeRegistros) -> None:
        assert [r.nome for r in mapa.bloco(0, 2)] == ["tensao", "corrente"]

    def test_bloco_passa_de_um_registrador_largo(self, mapa: MapaDeRegistros) -> None:
        assert [r.nome for r in mapa.bloco(2, 3)] == ["energia", "frequencia"]

    def test_bloco_fora_do_mapa(self, mapa: MapaDeRegistros) -> None:
        assert mapa.bloco(50, 2) == []

    def test_bloco_quantidade_zero(self, mapa: MapaDeRegistros) -> None:
        with pytest.raises(ErroDeRegistro):
            mapa.bloco(0, 0)


class TestTabela:
    """Renderizacao do mapa."""

    def test_tem_cabecalho(self, mapa: MapaDeRegistros) -> None:
        tabela = tabela_do_mapa(mapa)
        assert "Nome" in tabela
        assert "Escala" in tabela

    def test_uma_linha_por_registrador(self, mapa: MapaDeRegistros) -> None:
        linhas = tabela_do_mapa(mapa).splitlines()
        # 1 cabecalho + 1 separador + 4 registradores.
        assert len(linhas) == 6
        assert linhas[-1].lstrip().startswith("4")
        assert "frequencia" in linhas[-1]

    def test_mostra_a_largura(self, mapa: MapaDeRegistros) -> None:
        assert "uint32" in tabela_do_mapa(mapa)

    def test_mapa_vazio(self) -> None:
        assert tabela_do_mapa(MapaDeRegistros("vazio")).count("\n") == 1


class TestCarregarMapa:
    """Leitura do YAML de mapa."""

    def test_carrega_os_tres_mapas(self) -> None:
        mapa = carregar_mapa("dados/mapa-de-registros.yaml")
        assert set(mapa) == {"medidor_1pn", "medidor_3pn", "medidor_demanda"}

    def test_energia_e_uint32(self) -> None:
        mapa = carregar_mapa("dados/mapa-de-registros.yaml")
        assert mapa["medidor_1pn"].buscar("energia").palavras == 2

    def test_medidor_trifasico_tem_angulos(self) -> None:
        mapa = carregar_mapa("dados/mapa-de-registros.yaml")
        for fase in ("l1", "l2", "l3"):
            assert mapa["medidor_3pn"].buscar(f"angulo_{fase}") is not None

    def test_energia_mais_que_uint16(self) -> None:
        mapa = carregar_mapa("dados/mapa-de-registros.yaml")
        assert mapa["medidor_demanda"].buscar("energia_acumulada").faixa[1] > UINT16_MAX

    def test_topo_nao_mapeado(self, tmp_path) -> None:
        arquivo = tmp_path / "ruim.yaml"
        arquivo.write_text("- uma\n- lista\n", encoding="utf-8")
        with pytest.raises(ValueError, match="mapeamento"):
            carregar_mapa(arquivo)

    def test_registrador_sem_nome(self, tmp_path) -> None:
        arquivo = tmp_path / "m.yaml"
        arquivo.write_text("m:\n  - endereco: 0\n", encoding="utf-8")
        with pytest.raises(KeyError):
            carregar_mapa(arquivo)

    def test_tabela_do_mapa_do_arquivo(self) -> None:
        mapa = carregar_mapa("dados/mapa-de-registros.yaml")
        tabela = tabela_do_mapa(mapa["medidor_3pn"])
        assert "angulo_l2" in tabela