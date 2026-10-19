"""Contrato da API publica do pacote.

Public API contract of the package.

O __all__ do modbuslab e a lista que o modulo promete a quem faz
``from modbuslab import *``. Se um nome listado nao existir no modulo, o
import curinga quebra com AttributeError, e isso so aparece na hora de
importar, nao no type check nem no lint.

Estes testes existem para essa promessa continuar valendo.
"""

from __future__ import annotations

import modbuslab


def test_todo_nome_do_all_existe_no_modulo() -> None:
    """Todo nome listado no __all__ precisa estar no modulo.

    Every name in __all__ must exist on the module.
    """
    ausentes = [nome for nome in modbuslab.__all__ if not hasattr(modbuslab, nome)]

    assert ausentes == []


def test_nome_do_all_e_importavel_diretamente() -> None:
    """Todo nome do __all__ pode ser importado com ``from modbuslab import``.

    Every name in __all__ can be imported directly.
    """
    from modbuslab import (  # noqa: F401
        ClienteModbus,
        ExcecaoRemota,
        Mbap,
        QuadroInvalido,
        ScannerModbus,
        ServidorModbus,
        descricao_excecao,
        interpretar_resposta,
    )


def test_versao_e_reexportada() -> None:
    """A versao do pacote e acessivel no modulo raiz.

    The package version is reachable from the root module.
    """
    assert modbuslab.__version__
