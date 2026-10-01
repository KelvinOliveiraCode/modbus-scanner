"""Calculos de consumo: potencia, energia, fator de potencia e sequencia de fase.

Consumption maths: power, energy, power factor and phase sequence.

## Sobre sequencia de fase

Sequencia de fase e uma propriedade **angular**. Num sistema trifasico balanceado,
as tres tensesoes linha-a-linha tem o mesmo valor RMS, exatamente nas duas
sequencias: em sequencia positiva (L1-L2-L3) e em sequencia negativa
(L1-L3-L2), com 220 V em qualquer das tres, o valor RMS e identico. So o
sentido de rotacao difere.

Por isso nenhuma heuristica sobre magnitudes consegue detectar sequencia
invertida. Uma implementacao que ordena tres numeros e compara o menor com o
maior esta inventando um criterio que nao corresponde a nada na fisica, e ainda
funciona: os tres numeros sao iguais, a diferenca da some, e o resultado e
sempre "normal".

A deteccao aqui usa o que de fato distingue as duas sequencias, que e o angulo
de fase. Num sistema ideal, com L1 como referencia em 0 graus:

    sequencia positiva:  L1 =   0 graus   L2 = -120   L3 = +120
    sequencia negativa:  L1 =   0 graus   L2 = +120   L3 = -120

Logo o salto de angulo de L1 para L2, medido no sentido positivo, vale 240 graus
na sequencia positiva e 120 graus na negativa. E sobre esse salto que a funcao
decide, com uma tolerancia para ruido de medicao.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

#: Deslocamento angular ideal entre fases, em graus.
DESLOCAMENTO_FASE = 120.0

#: Salto L1->L2 na sequencia positiva, em graus.
SALTO_POSITIVO = 240.0

#: Salto L1->L2 na sequencia negativa, em graus.
SALTO_NEGATIVO = 120.0

#: Tolerancia angular, em graus, para absorver ruido de medicao.
TOLERANCIA_GRAUS = 20.0

#: Desbalanco maximo de tensao entre fases, em fracao, para considerar que
#: a leitura de angulo e confiavel. Acima disso o sistema ta tao desbalanceado
#: que o angulo medido nao descreve a sequencia com seguranca.
TOLERANCIA_DESBALANCO = 0.10

#: Sequencias reconhecidas.
SEQUENCIA_POSITIVA = "positiva"
SEQUENCIA_NEGATIVA = "negativa"
SEQUENCIA_INDETERMINADA = "indeterminada"


@dataclass
class ResultadoConsumo:
    """Metricas calculadas a partir de uma leitura de registradores.

    Metrics computed from one register read.
    """

    tensao_v: float = 0.0
    corrente_a: float = 0.0
    potencia_ativa_w: float = 0.0
    potencia_reativa_var: float = 0.0
    potencia_aparente_va: float = 0.0
    fator_potencia: float = 0.0
    fator_potencia_medido: float | None = None
    energia_kwh: float = 0.0
    frequencia_hz: float = 0.0
    fases: int = 1
    sequencia_fase: str = ""
    sequencia_invertida: bool = False
    alertas: list[str] = field(default_factory=list)

    @property
    def desvio_fator_potencia(self) -> float | None:
        """Diferenca entre o fator medido e o calculado.

        Gap between the meter's own power factor and the one computed from
        active and reactive power. ``None`` quando o medidor nao expoe o fator.
        """
        if self.fator_potencia_medido is None:
            return None
        return abs(self.fator_potencia_medido - self.fator_potencia)


def _salto(a: float, b: float) -> float:
    """Diferenca angular de a para b, no sentido positivo.

    Angular step from a to b, measured in the positive direction.

    Args:
        a: Angulo de partida, em graus.
        b: Angulo de chegada, em graus.

    Returns:
        O salto em ``[0, 360)``.
    """
    return (b - a) % 360.0


def classificar_salto_pelo_angulo(
    angulo_l1: float,
    angulo_l2: float,
    angulo_l3: float,
    tolerancia: float = TOLERANCIA_GRAUS,
) -> str:
    """Classifica a sequencia de fase pelos angulos medidos.

    Classify the phase sequence from the measured angles.

    Usa dois saltos independentes, L1->L2 e L2->L3. Se os dois discordarem, o
    resultado e indeterminado em vez de uma escolha arbitraria: discordancia
    significa leitura suja, nao fase invertida.

    Args:
        angulo_l1: Angulo da fase L1, em graus.
        angulo_l2: Angulo da fase L2, em graus.
        angulo_l3: Angulo da fase L3, em graus.
        tolerancia: Folga angular em graus.

    Returns:
        A sequencia classificada, ou :data:`SEQUENCIA_INDETERMINADA`.
    """
    salto_12 = _salto(angulo_l1, angulo_l2)
    salto_23 = _salto(angulo_l2, angulo_l3)

    proximo_12 = abs(salto_12 - SALTO_POSITIVO)
    proximo_23 = abs(salto_23 - SALTO_POSITIVO)
    veredito_12 = (
        SEQUENCIA_POSITIVA if proximo_12 <= tolerancia
        else SEQUENCIA_NEGATIVA if abs(salto_12 - SALTO_NEGATIVO) <= tolerancia
        else SEQUENCIA_INDETERMINADA
    )
    veredito_23 = (
        SEQUENCIA_POSITIVA if proximo_23 <= tolerancia
        else SEQUENCIA_NEGATIVA if abs(salto_23 - SALTO_NEGATIVO) <= tolerancia
        else SEQUENCIA_INDETERMINADA
    )

    if veredito_12 == SEQUENCIA_INDETERMINADA:
        return SEQUENCIA_INDETERMINADA
    if veredito_23 != SEQUENCIA_INDETERMINADA and veredito_23 != veredito_12:
        # Os dois saltos apontam para sequencias diferentes: leitura suja.
        return SEQUENCIA_INDETERMINADA
    if veredito_23 == SEQUENCIA_INDETERMINADA:
        # Um salto legivel e outro nao: nao ha base para afirmar sequencia.
        return SEQUENCIA_INDETERMINADA
    return veredito_12


def desbalanco(tensoes: list[float]) -> float:
    """Maior desvio relativo entre as tensoes de fase.

    Largest relative spread between phase voltages.

    Args:
        tensoes: Tensoes por fase, em volts.

    Returns:
        Fracao entre zero e um. Zero quando todas sao iguais.
    """
    if len(tensoes) < 2 or any(t <= 0 for t in tensoes):
        return 0.0
    menor, maior = min(tensoes), max(tensoes)
    media = sum(tensoes) / len(tensoes)
    if media <= 0:
        return 0.0
    return (maior - menor) / media


def avaliar_sequencia(
    angulo_l1: float,
    angulo_l2: float,
    angulo_l3: float,
    tensao_l1: float,
    tensao_l2: float,
    tensao_l3: float,
    tolerancia_angulo: float = TOLERANCIA_GRAUS,
) -> tuple[str, list[str]]:
    """Avalia a sequencia de fase e explica o veredito.

    Assess the phase sequence and explain the verdict.

    Args:
        angulo_l1: Angulo da fase L1, em graus.
        angulo_l2: Angulo da fase L2, em graus.
        angulo_l3: Angulo da fase L3, em graus.
        tensao_l1: Tensao da fase L1, em volts.
        tensao_l2: Tensao da fase L2, em volts.
        tensao_l3: Tensao da fase L3, em volts.
        tolerancia_angulo: Folga angular em graus.

    Returns:
        Par com a sequencia e a lista de alertas.
    """
    alertas: list[str] = []

    if any(t <= 0 for t in (tensao_l1, tensao_l2, tensao_l3)):
        return SEQUENCIA_INDETERMINADA, [
            "sequencia de fase exige leitura trifasica com tensao valida"
        ]

    desequilibrio = desbalanco([tensao_l1, tensao_l2, tensao_l3])
    if desequilibrio > TOLERANCIA_DESBALANCO:
        alertas.append(
            f"tensao desbalanceada ({desequilibrio:.1%} de spread): "
            "leitura de angulo pouco confiavel"
        )
        return SEQUENCIA_INDETERMINADA, alertas

    sequencia = classificar_salto_pelo_angulo(
        angulo_l1, angulo_l2, angulo_l3, tolerancia_angulo
    )

    if sequencia == SEQUENCIA_NEGATIVA:
        alertas.append(
            "sequencia de fase invertida: ordem L1-L3-L2 em vez de L1-L2-L3"
        )
    elif sequencia == SEQUENCIA_INDETERMINADA:
        alertas.append(
            "angulos de fase fora do esperado para um sistema ideal; "
            "verifique a ligacao dos sensores de angulo"
        )
    return sequencia, alertas


def fator_potencia(ativa_w: float, reativa_var: float) -> float:
    """Fator de potencia a partir das potencias ativa e reativa.

    Power factor from active and reactive power.

    Devolve o **modulo** do fator, em ``[0, 1]``. Um medidor de consumo
    faturado pelo fator usa o modulo, entao esse e o numero que interessa. O
    sinal fica de fora de proposito: potencia ativa negativa e o caso de
    geracao passingo pelo medidor, que nao se enquadra nesta conta, e devolver
    um numero negativo num relatorio de consumo confunde mais do que ajuda.

    Args:
        ativa_w: Potencia ativa, em watts.
        reativa_var: Potencia reativa, em var.

    Returns:
        Fator de potencia em ``[0, 1]``. Zero quando as duas sao zero, porque
        nao ha potencia aparente para normalizar.
    """
    aparente = math.sqrt(ativa_w * ativa_w + reativa_var * reativa_var)
    if aparente == 0:
        return 0.0
    return max(0.0, min(1.0, abs(ativa_w) / aparente))


def potencia_aparente(ativa_w: float, reativa_var: float) -> float:
    """Potencia aparente, em volt-ampere.

    Apparent power, in volt-amperes.
    """
    return math.sqrt(ativa_w * ativa_w + reativa_var * reativa_var)


def potencia_instantanea(tensao_v: float, corrente_a: float, fp: float) -> float:
    """Potencia ativa instantanea, em watts.

    Instantaneous active power, in watts.

    Args:
        tensao_v: Tensao, em volts.
        corrente_a: Corrente, em amperes.
        fp: Fator de potencia.

    Returns:
        Potencia ativa em watts.
    """
    return tensao_v * corrente_a * fp


def kwh_acumulado(potencia_w: float, horas: float) -> float:
    """Energia acumulada em quilowatt-hora.

    Accumulated energy in kilowatt-hours.

    Args:
        potencia_w: Potencia media no intervalo, em watts.
        horas: Duracao do intervalo, em horas.

    Returns:
        Energia em kWh. Intervalo nao positivo devolve zero, porque energia
        negativa nao tem sentido fisico aqui.
    """
    if horas <= 0:
        return 0.0
    return potencia_w * horas / 1000.0


def calcular(
    dados: dict[str, float],
    numero_fases: int = 1,
    ler_fases: bool = True,
) -> ResultadoConsumo:
    """Calcula todas as metricas de uma leitura.

    Compute every metric from one reading.

    Os nomes de chave sao os do mapa de registradores. Para o medidor trifasico,
    a tensao e a media das tres fases, que e o que a literature chama de tensao
    de linha; a corrente e a soma das correntes de fase.

    Args:
        dados: Mapa de nome de registrador para valor de engenharia.
        numero_fases: 1 para monofasico, 3 para trifasico.
        ler_fases: Se deve avaliar sequencia de fase. So faz sentido em
            trifasico com leitura de angulo.

    Returns:
        As metricas calculadas, com alertas preenchidos quando algo esta fora
        do esperado.
    """
    ativa = float(dados.get("potencia_ativa", dados.get("demanda_ativa", 0.0)))
    reativa = float(
        dados.get("potencia_reativa", dados.get("demanda_reativa", 0.0))
    )
    fp = fator_potencia(ativa, reativa)

    if numero_fases >= 3:
        tensoes = [
            float(dados.get(f"tensao_{f}", 0.0)) for f in ("l1", "l2", "l3")
        ]
        tensao = sum(tensoes) / 3.0 if any(tensoes) else float(
            dados.get("tensao", 0.0)
        )
        corrente = sum(
            float(dados.get(f"corrente_{f}", 0.0)) for f in ("l1", "l2", "l3")
        ) or float(dados.get("corrente", 0.0))
    else:
        tensao = float(dados.get("tensao", 0.0))
        corrente = float(dados.get("corrente", 0.0))

    resultado = ResultadoConsumo(
        tensao_v=tensao,
        corrente_a=corrente,
        potencia_ativa_w=ativa,
        potencia_reativa_var=reativa,
        potencia_aparente_va=potencia_aparente(ativa, reativa),
        fator_potencia=fp,
        energia_kwh=float(dados.get("energia", dados.get("energia_acumulada", 0.0))),
        frequencia_hz=float(dados.get("frequencia", 0.0)),
        fases=numero_fases,
    )

    if "fator_potencia" in dados:
        resultado.fator_potencia_medido = float(dados["fator_potencia"])

    if ler_fases and numero_fases >= 3:
        angulos = [float(dados.get(f"angulo_{f}", 0.0)) for f in ("l1", "l2", "l3")]
        tensoes = [float(dados.get(f"tensao_{f}", 0.0)) for f in ("l1", "l2", "l3")]
        if any(a > 0 for a in angulos):
            sequencia, alertas = avaliar_sequencia(
                angulos[0], angulos[1], angulos[2],
                tensoes[0], tensoes[1], tensoes[2],
            )
            resultado.sequencia_fase = sequencia
            resultado.sequencia_invertida = sequencia == SEQUENCIA_NEGATIVA
            resultado.alertas.extend(alertas)

    desvio = resultado.desvio_fator_potencia
    if desvio is not None and desvio > 0.05:
        resultado.alertas.append(
            f"fator de potencia medido ({resultado.fator_potencia_medido:.3f}) "
            f"discorda do calculado ({resultado.fator_potencia:.3f})"
        )

    return resultado