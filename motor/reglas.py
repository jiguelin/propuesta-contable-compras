# -*- coding: utf-8 -*-
"""
motor/reglas.py — Base de conocimiento contable: reglas que mandan sobre todo lo demás.

Dos tipos de regla:

  · `cuenta`  → "cuando aparezca X, usa la cuenta Y". Se evalúa ANTES que la memoria de la empresa
                y antes del plan/IA, porque una decisión contable razonada pesa más que la costumbre.
  · `bloqueo` → "nunca propongas una cuenta que empiece con Z" (aunque exista en el plan de la empresa).

Las reglas se guardan en la base (tabla `reglas`) y se administran desde la app. Pueden ser
globales (ruc = '*', valen para todas las empresas) o de una empresa concreta.

Reglas de sistema (siempre activas, no se pueden borrar): ver REGLAS_SISTEMA abajo. La primera es
el bloqueo de la 6399, porque el PCGE 2019 solo reconoce 6391 (gastos bancarios) y 6392 (gastos de
laboratorio) dentro de la subcuenta 639, y SUNAT rechaza cualquier otra divisionaria de 639 en el
balance de comprobación.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Regla:
    id: int = 0
    ruc: str = '*'                 # '*' = todas las empresas
    tipo: str = 'cuenta'           # 'cuenta' | 'bloqueo'
    nombre: str = ''
    palabras: str = ''             # separadas por coma; basta que aparezca UNA en el texto
    ruc_proveedor: str = ''        # opcional: además debe ser este proveedor
    cuenta: str = ''               # cuenta exacta, o prefijo si termina en '*' (p. ej. '638*')
    alternativas: str = ''         # solo en bloqueos: prefijos sugeridos en su lugar, separados por coma
    nota: str = ''                 # fundamento, para que la persona entienda por qué
    prioridad: int = 100           # menor = se evalúa primero
    activa: int = 1
    sistema: int = 0               # 1 = regla de sistema (no editable)

    @property
    def lista_palabras(self) -> list[str]:
        return [p.strip().upper() for p in (self.palabras or '').split(',') if p.strip()]

    @property
    def lista_alternativas(self) -> list[str]:
        return [p.strip() for p in (self.alternativas or '').split(',') if p.strip()]

    @property
    def es_prefijo(self) -> bool:
        return self.cuenta.endswith('*')

    @property
    def cuenta_limpia(self) -> str:
        return self.cuenta.rstrip('*').strip()

    def coincide(self, texto: str, ruc_proveedor: str) -> bool:
        if not self.activa:
            return False
        if self.ruc_proveedor and self.ruc_proveedor != ruc_proveedor:
            return False
        palabras = self.lista_palabras
        if not palabras:
            return bool(self.ruc_proveedor)     # regla solo por proveedor
        t = ' ' + (texto or '').upper() + ' '
        return any(p in t for p in palabras)


# ----------------------------------------------------------------------------- reglas de sistema
REGLAS_SISTEMA = [
    Regla(id=-1, ruc='*', tipo='bloqueo', nombre='No usar 6399 (SUNAT la rechaza)',
          cuenta='6399', alternativas='638,633,6329,60919',
          nota='El PCGE 2019 solo reconoce 6391 (gastos bancarios) y 6392 (gastos de laboratorio) dentro de la '
               'subcuenta 639. SUNAT rechaza cualquier otra divisionaria de 639 en el balance de comprobación. '
               'Alternativas: 638 servicios de contratistas, 633 producción encargada a terceros, '
               '6329 otros servicios de asesoría y consultoría, o 60919 otros costos vinculados a las compras (NIC 2).',
          prioridad=1, sistema=1),
]


# ----------------------------------------------------------------------------- evaluación
def bloqueos(reglas: list[Regla]) -> list[Regla]:
    return [r for r in reglas if r.tipo == 'bloqueo' and r.activa]


def cuenta_bloqueada(codigo: str, reglas: list[Regla]) -> Regla | None:
    """Devuelve la regla que impide usar esa cuenta, o None."""
    codigo = (codigo or '').strip()
    if not codigo:
        return None
    for r in bloqueos(reglas):
        pref = r.cuenta_limpia
        if pref and codigo.startswith(pref):
            return r
    return None


def filtrar_cuentas(codigos, reglas: list[Regla]):
    """Quita de una lista de cuentas (str u objetos con .codigo) las que estén bloqueadas."""
    def cod(x):
        return x if isinstance(x, str) else getattr(x, 'codigo', '')
    return [c for c in codigos if not cuenta_bloqueada(cod(c), reglas)]


def aplicar(texto: str, ruc_proveedor: str, reglas: list[Regla]) -> Regla | None:
    """Primera regla de tipo 'cuenta' que coincide (por prioridad)."""
    candidatas = sorted([r for r in reglas if r.tipo == 'cuenta' and r.activa], key=lambda r: (r.prioridad, r.id))
    for r in candidatas:
        if r.coincide(texto, ruc_proveedor):
            return r
    return None


def validar(regla: Regla) -> str:
    """Devuelve '' si la regla es usable, o el motivo del rechazo."""
    if regla.tipo not in ('cuenta', 'bloqueo'):
        return 'Tipo de regla no válido.'
    if not regla.cuenta.strip():
        return 'Indique la cuenta (o el prefijo a bloquear).'
    if not re.fullmatch(r'\d{2,12}\*?', regla.cuenta.strip()):
        return 'La cuenta debe ser numérica (2 a 12 dígitos), opcionalmente terminada en * para indicar un prefijo.'
    if regla.tipo == 'cuenta' and not (regla.lista_palabras or regla.ruc_proveedor):
        return 'Una regla de cuenta necesita palabras clave o un RUC de proveedor.'
    if regla.ruc_proveedor and not re.fullmatch(r'\d{8,11}', regla.ruc_proveedor):
        return 'El RUC del proveedor debe tener 8 u 11 dígitos.'
    return ''
