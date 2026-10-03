"""Guardia: pytest no debe arrancar contra fsm_demo ni bases no declaradas."""
from __future__ import annotations

import pytest


def test_fsm_demo_esta_prohibida_para_pytest():
    from tests.guardia_base import _PROHIBIDAS

    assert "fsm_demo" in _PROHIBIDAS
