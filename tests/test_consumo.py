"""Testes dos calculos de consumo e de sequencia de fase.

Consumption and phase-sequence tests.

A secao de sequencia de fase e a mais importante do arquivo. Ela existe porque
a primeira implementacao do projeto decidia sequencia de fase olhando tres
magnitudes de tensao, e isso e fisicamente impossivel: as tensoes linha-a-linha
tem o mesmo valor RMS nas duas sequencias, entao o resultado era sempre "normal"
e nunca detectava o erro de campo que o projeto promete achar.
"""

from __future__ import annotations

import math

import pytest

from modbuslab.consumo import (
    SALTO_NEGATIVO,
    SALTO_POSITIVO,
    SEQUENCIA_INDETERMINADA,
    SEQUENCIA_NEGATIVA,
    SEQUENCIA_POSITIVA,
    TOLERANCIA_DESBALANCO,
    avaliar_sequencia,
    calcular,
    classificar_salto_pelo_angulo,
    desbalanco,
    fator_potencia,
    kwh_acumulado,
    potencia_aparente,
    potencia_instantanea,
)

#: Sequencia positiva ideal: L1 em 0, L2 em -120, L3 em +120.
POSITIVA = (0.0, 240.0, 120.0)

#: Sequencia negativa ideal: L2 e L3 trocados de lugar.
NEGATIVA = (0.0, 120.0, 240.0)


class TestFatorPotencia:
    """Fator de potencia a partir de ativa e reativa."""

    def test_somente_ativa(self) -> None:
        assert fator_potencia(1000.0, 0.0) == pytest.approx(1.0)

    def test_carga_resistiva(self) -> None:
        # 3-4-5: ativa 3, reativa 4, aparente 5.
        assert fator_potencia(3.0, 4.0) == pytest.approx(0.6)

    def test_nada_consumido(self) -> None:
        # Sem potencia aparente nao ha o que normalizar.
        assert fator_potencia(0.0, 0.0) == 0.0

    def test_reativa_negativa(self) -> None:
        # Carga capacitiva: fator de potencia negativo na sua convencao, e o
        # modulo do quociente e o que interessa para o consumo.
        assert fator_potencia(3.0, -4.0) == pytest.approx(0.6)

    def test_ativa_negativa(self) -> None:
        # Potencia ativa negativa e geracao passingo pelo medidor. Esta
        # calculadora devolve o modulo, que e o que a conta de consumo usa.
        assert fator_potencia(-3.0, 4.0) == pytest.approx(0.6)

    def test_ativa_negativa_pura(self) -> None:
        # Geracao sem reativa: fator 1 pelo modulo.
        assert fator_potencia(-1000.0, 0.0) == pytest.approx(1.0)

    def test_unity_limitado(self) -> None:
        assert fator_potencia(1.0, 1.0) <= 1.0

    def test_baixa_carga(self) -> None:
        assert fator_potencia(100.0, 50.0) == pytest.approx(0.8944, abs=1e-4)


class TestPotencia:
    """Potencia aparente e instantanea."""

    def test_aparente_pitagorica(self) -> None:
        assert potencia_aparente(3.0, 4.0) == pytest.approx(5.0)

    def test_aparente_zero(self) -> None:
        assert potencia_aparente(0.0, 0.0) == 0.0

    def test_instantanea_treifasica(self) -> None:
        # 220 V * 30 A * 0,9 = 5940 W
        assert potencia_instantanea(220.0, 30.0, 0.9) == pytest.approx(5940.0)

    def test_instantanea_com_fp_zero(self) -> None:
        assert potencia_instantanea(220.0, 30.0, 0.0) == 0.0


class TestKwh:
    """Energia acumulada."""

    def test_uma_hora(self) -> None:
        assert kwh_acumulado(1000.0, 1.0) == pytest.approx(1.0)

    def test_meia_hora(self) -> None:
        assert kwh_acumulado(1000.0, 0.5) == pytest.approx(0.5)

    def test_oito_horas(self) -> None:
        assert kwh_acumulado(1000.0, 8.0) == pytest.approx(8.0)

    def test_intervalo_zero(self) -> None:
        assert kwh_acumulado(1000.0, 0.0) == 0.0

    def test_intervalo_negativo(self) -> None:
        # Tempo para tras nao produz energia, e energia negativa nao tem
        # sentido fisico nesta conta.
        assert kwh_acumulado(1000.0, -2.0) == 0.0

    def test_carga_minima(self) -> None:
        assert kwh_acumulado(0.1, 24.0) == pytest.approx(0.0024)


class TestDesbalanco:
    """Desvio entre tensoes de fase."""

    def test_sistema_balanceado(self) -> None:
        assert desbalanco([220.0, 220.0, 220.0]) == 0.0

    def test_desbalanceado(self) -> None:
        assert desbalanco([220.0, 210.0, 220.0]) > 0.0

    def test_menos_de_duas_fases(self) -> None:
        assert desbalanco([220.0]) == 0.0

    def test_tensao_zero(self) -> None:
        assert desbalanco([0.0, 220.0, 220.0]) == 0.0


class TestClassificacaoDeSalto:
    """Traducao do salto angular em sequencia."""

    def test_salto_positivo(self) -> None:
        assert classificar_salto_pelo_angulo(*POSITIVA) == SEQUENCIA_POSITIVA

    def test_salto_negativo(self) -> None:
        assert classificar_salto_pelo_angulo(*NEGATIVA) == SEQUENCIA_NEGATIVA

    def test_salto_rotacionado(self) -> None:
        # Girar o sistema inteiro nao muda a sequencia.
        assert classificar_salto_pelo_angulo(90.0, 330.0, 210.0) == SEQUENCIA_POSITIVA
        assert classificar_salto_pelo_angulo(90.0, 210.0, 330.0) == SEQUENCIA_NEGATIVA

    def test_salto_nao_sistema(self) -> None:
        # Angulos em 90 graus: salto de 90, longe dos dois ideals.
        assert (
            classificar_salto_pelo_angulo(0.0, 90.0, 180.0)
            == SEQUENCIA_INDETERMINADA
        )

    def test_tolerancia_absorve_ruido(self) -> None:
        # Dois graus de erro de medicao nao devem virar alerta de campo.
        assert (
            classificar_salto_pelo_angulo(0.0, 238.0, 122.0) == SEQUENCIA_POSITIVA
        )

    def test_erro_grande_da_indeterminado(self) -> None:
        assert (
            classificar_salto_pelo_angulo(0.0, 200.0, 100.0)
            == SEQUENCIA_INDETERMINADA
        )

    def test_tolerancia_customizada(self) -> None:
        assert (
            classificar_salto_pelo_angulo(0.0, 215.0, 95.0, tolerancia=1.0)
            == SEQUENCIA_INDETERMINADA
        )

    def test_saltos_ideais(self) -> None:
        assert math.isclose(SALTO_POSITIVO + SALTO_NEGATIVO, 360.0)


class TestAvaliarSequencia:
    """Veredito com explicacao."""

    def test_sistema_normal(self) -> None:
        seq, alertas = avaliar_sequencia(
            *POSITIVA, 220.0, 220.0, 220.0
        )
        assert seq == SEQUENCIA_POSITIVA
        assert alertas == []

    def test_sequencia_invertida(self) -> None:
        seq, alertas = avaliar_sequencia(
            *NEGATIVA, 220.0, 220.0, 220.0
        )
        assert seq == SEQUENCIA_NEGATIVA
        assert any("invertida" in a for a in alertas)

    def test_tensao_zero(self) -> None:
        seq, alertas = avaliar_sequencia(*POSITIVA, 0.0, 220.0, 220.0)
        assert seq == SEQUENCIA_INDETERMINADA
        assert alertas

    def test_desbalanceado_da_indeterminado(self) -> None:
        # Com 40% de desvio o angulo medido nao descreve a sequencia.
        seq, alertas = avaliar_sequencia(*NEGATIVA, 220.0, 150.0, 220.0)
        assert seq == SEQUENCIA_INDETERMINADA
        assert any("desbalanceada" in a for a in alertas)

    def test_desbalanco_no_limite(self) -> None:
        seq, _ = avaliar_sequencia(*POSITIVA, 220.0, 220.0, 220.0)
        assert seq == SEQUENCIA_POSITIVA
        assert TOLERANCIA_DESBALANCO > 0

    def test_leitura_suja(self) -> None:
        # Saltos que discordam entre si: leitura inconsistente.
        seq, alertas = avaliar_sequencia(0.0, 120.0, 120.0, 220.0, 220.0, 220.0)
        assert seq == SEQUENCIA_INDETERMINADA
        assert alertas


class TestCalcularMonofasico:
    """Leitura de medidor monofasico."""

    @pytest.fixture
    def leitura(self) -> dict[str, float]:
        return {
            "tensao": 219.4,
            "corrente": 12.35,
            "potencia_ativa": 2430.0,
            "potencia_reativa": 890.0,
            "energia": 18432.0,
            "frequencia": 60.01,
            "fator_potencia": 0.939,
        }

    def test_tensao(self, leitura: dict[str, float]) -> None:
        assert calcular(leitura).tensao_v == pytest.approx(219.4)

    def test_corrente(self, leitura: dict[str, float]) -> None:
        assert calcular(leitura).corrente_a == pytest.approx(12.35)

    def test_fator_calculado(self, leitura: dict[str, float]) -> None:
        assert calcular(leitura).fator_potencia == pytest.approx(0.939, abs=0.002)

    def test_energia_vem_do_registrador(self, leitura: dict[str, float]) -> None:
        assert calcular(leitura).energia_kwh == pytest.approx(18432.0)

    def test_frequencia(self, leitura: dict[str, float]) -> None:
        assert calcular(leitura).frequencia_hz == pytest.approx(60.01)

    def test_fases(self, leitura: dict[str, float]) -> None:
        assert calcular(leitura).fases == 1

    def test_fator_medido_e_guardado(self, leitura: dict[str, float]) -> None:
        assert calcular(leitura).fator_potencia_medido == pytest.approx(0.939)

    def test_desvio_pequeno(self, leitura: dict[str, float]) -> None:
        r = calcular(leitura)
        assert r.desvio_fator_potencia is not None
        assert r.desvio_fator_potencia < 0.05
        assert r.alertas == []

    def test_leitura_vazia(self) -> None:
        r = calcular({})
        assert r.tensao_v == 0.0
        assert r.fator_potencia == 0.0
        assert r.sequencia_fase == ""

    def test_sem_fator_medido(self) -> None:
        r = calcular({"tensao": 220.0, "potencia_ativa": 100.0})
        assert r.fator_potencia_medido is None
        assert r.desvio_fator_potencia is None


class TestCalcularMedidorDeDemanda:
    """Leitura com nomes de demanda em vez de potencia."""

    @pytest.fixture
    def leitura(self) -> dict[str, float]:
        return {
            "demanda_ativa": 9600.0,
            "demanda_reativa": 4100.0,
            "energia_acumulada": 412880.0,
            "tensao": 220.3,
            "corrente": 43.58,
            "frequencia": 60.0,
            "fator_potencia": 0.919,
        }

    def test_usa_demanda_como_potencia(self, leitura: dict[str, float]) -> None:
        assert calcular(leitura).potencia_ativa_w == pytest.approx(9600.0)

    def test_usa_energia_acumulada(self, leitura: dict[str, float]) -> None:
        assert calcular(leitura).energia_kwh == pytest.approx(412880.0)

    def test_energia_de_32_bits(self, leitura: dict[str, float]) -> None:
        # 412880 nao cabe em uint16: e o motivo do registrador largo.
        assert leitura["energia_acumulada"] > 65535


class TestCalcularTrifasico:
    """Leitura de medidor trifasico, incluindo a sequencia invertida."""

    @pytest.fixture
    def leitura(self) -> dict[str, float]:
        return {
            "tensao_l1": 219.7,
            "tensao_l2": 220.1,
            "tensao_l3": 219.2,
            "corrente_l1": 18.4,
            "corrente_l2": 17.9,
            "corrente_l3": 18.6,
            "angulo_l1": 0.0,
            "angulo_l2": 120.0,
            "angulo_l3": 240.0,
            "potencia_ativa": 10980.0,
            "potencia_reativa": 3120.0,
            "energia": 91240.0,
            "frequencia": 59.98,
            "fator_potencia": 0.962,
        }

    def test_tensao_e_a_media_das_fases(self, leitura: dict[str, float]) -> None:
        r = calcular(leitura, numero_fases=3)
        assert r.tensao_v == pytest.approx((219.7 + 220.1 + 219.2) / 3)

    def test_corrente_e_a_soma_das_fases(self, leitura: dict[str, float]) -> None:
        r = calcular(leitura, numero_fases=3)
        assert r.corrente_a == pytest.approx(18.4 + 17.9 + 18.6)

    def test_fases(self, leitura: dict[str, float]) -> None:
        assert calcular(leitura, numero_fases=3).fases == 3

    def test_detecta_sequencia_invertida(self, leitura: dict[str, float]) -> None:
        r = calcular(leitura, numero_fases=3)
        assert r.sequencia_fase == SEQUENCIA_NEGATIVA
        assert r.sequencia_invertida is True

    def test_alerta_de_sequencia(self, leitura: dict[str, float]) -> None:
        r = calcular(leitura, numero_fases=3)
        assert any("invertida" in a for a in r.alertas)

    def test_sequencia_normal_nao_alerta(self) -> None:
        leitura = {
            "tensao_l1": 220.0, "tensao_l2": 220.0, "tensao_l3": 220.0,
            "angulo_l1": 0.0, "angulo_l2": 240.0, "angulo_l3": 120.0,
            "potencia_ativa": 1000.0, "potencia_reativa": 0.0,
        }
        r = calcular(leitura, numero_fases=3)
        assert r.sequencia_fase == SEQUENCIA_POSITIVA
        assert r.sequencia_invertida is False
        assert r.alertas == []

    def test_sem_angulos_nao_avalia_sequencia(self) -> None:
        leitura = {
            "tensao_l1": 220.0, "tensao_l2": 220.0, "tensao_l3": 220.0,
            "potencia_ativa": 1000.0, "potencia_reativa": 0.0,
        }
        r = calcular(leitura, numero_fases=3)
        assert r.sequencia_fase == ""

    def test_leer_fases_desligado(self, leitura: dict[str, float]) -> None:
        r = calcular(leitura, numero_fases=3, ler_fases=False)
        assert r.sequencia_fase == ""

    def test_monofasico_nao_avalia_fases(self, leitura: dict[str, float]) -> None:
        # Um medidor de uma fase nao tem sequencia de fase a avaliar.
        r = calcular(leitura, numero_fases=1)
        assert r.sequencia_fase == ""

    def test_trifasico_sem_tensao_por_fase(self) -> None:
        leitura = {
            "tensao": 220.0, "corrente": 10.0,
            "potencia_ativa": 1000.0, "potencia_reativa": 0.0,
        }
        r = calcular(leitura, numero_fases=3)
        assert r.tensao_v == pytest.approx(220.0)


class TestAlertaDeFatorDePotencia:
    """Divergencia entre o fator medido e o calculado."""

    def test_alerta_quando_discordam(self) -> None:
        r = calcular({"potencia_ativa": 1000.0, "potencia_reativa": 0.0,
                      "fator_potencia": 0.5})
        assert any("discorda" in a for a in r.alertas)

    def test_sem_alerta_quando_batem(self) -> None:
        r = calcular({"potencia_ativa": 1000.0, "potencia_reativa": 0.0,
                      "fator_potencia": 1.0})
        assert not any("discorda" in a for a in r.alertas)

    def test_tolerancia_de_cinco_por_cento(self) -> None:
        r = calcular({"potencia_ativa": 1000.0, "potencia_reativa": 0.0,
                      "fator_potencia": 0.97})
        assert not any("discorda" in a for a in r.alertas)


class TestResultadoConsumo:
    """Estrutura de resultado."""

    def test_padroes(self) -> None:
        r = calcular({})
        assert r.sequencia_invertida is False
        assert r.alertas == []
        assert r.fases == 1

    def test_potencia_aparente_preenchida(self) -> None:
        r = calcular({"potencia_ativa": 3.0, "potencia_reativa": 4.0})
        assert r.potencia_aparente_va == pytest.approx(5.0)