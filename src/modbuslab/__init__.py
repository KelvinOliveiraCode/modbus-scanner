"""modbuslab - servidor Modbus TCP simulado com medidores de energia.

Modbus TCP server simulator with fictional energy meters and a bus scanner.

Tudo roda em loopback e usa apenas a biblioteca padrao mais PyYAML para os
arquivos de dados. O protocolo Modbus TCP e implementado do zero em
:mod:`modbuslab.protocolo`, e o servidor e o cliente usam o mesmo modulo, que e
o que acontece em qualquer implementacao real do protocolo.
"""

from .consumo import (
    ResultadoConsumo,
    avaliar_sequencia,
    calcular,
    classificar_salto_pelo_angulo,
    desbalanco,
    fator_potencia,
    kwh_acumulado,
    potencia_aparente,
    potencia_instantanea,
)
from .dispositivos import (
    Dispositivo,
    GerenciadorDispositivos,
    carregar_ambiente,
    carregar_dispositivos,
)
from .protocolo import (
    ExcecaoRemota,
    ErroModbus,
    Mbap,
    QuadroInvalido,
    RequisicaoLeitura,
    RespostaLeitura,
    descricao_excecao,
    interpretar_resposta,
    ler_requisicao,
    montar_excecao,
)
from .registros import (
    ErroDeRegistro,
    MapaDeRegistros,
    Registrador,
    carregar_mapa,
    tabela_do_mapa,
)
from .scanner import (
    ClienteModbus,
    DispositivoDescoberto,
    ResultadoVarredura,
    ScannerModbus,
)
from .servidor import ServidorModbus, descrever_servidor

__all__ = [
    # Protocolo
    "ErroModbus",
    "QuadroInvalido",
    "ExcecaoRemota",
    "Mbap",
    "RequisicaoLeitura",
    "RespostaLeitura",
    "interpretar_resposta",
    "ler_requisicao",
    "montar_excecao",
    "descrever_excecao",
    # Registradores
    "Registrador",
    "MapaDeRegistros",
    "ErroDeRegistro",
    "carregar_mapa",
    "tabela_do_mapa",
    # Dispositivos
    "Dispositivo",
    "GerenciadorDispositivos",
    "carregar_dispositivos",
    "carregar_ambiente",
    # Servidor e cliente
    "ServidorModbus",
    "descrever_servidor",
    "ClienteModbus",
    "ScannerModbus",
    "DispositivoDescoberto",
    "ResultadoVarredura",
    # Consumo
    "ResultadoConsumo",
    "calcular",
    "fator_potencia",
    "potencia_aparente",
    "potencia_instantanea",
    "kwh_acumulado",
    "avaliar_sequencia",
    "classificar_salto_pelo_angulo",
    "desbalanco",
]

__version__ = "1.0.0"