# -*- coding: utf-8 -*-
"""
motor/plan_cuentas.py — Lector del plan de cuentas de la empresa (Excel exportado de NewContaSis
u otro formato tabular) y buscador de cuentas.

Formato observado (NewContaSis → "PLAN DE CUENTAS"):
  fila cabecera: CUENTA | (niveles en B/C/D) | DESCRIPCION | C.BAL | A.DEBE | A.HABER | TIPO | ANALISIS | CENTRO DE COSTOS
  la cuenta viene en la columna B, C o D según su nivel (2, 3, 4+ dígitos).
También acepta cualquier Excel/CSV con dos columnas: cuenta y descripción.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field, asdict
from typing import Iterable

import openpyxl


@dataclass
class Cuenta:
    codigo: str
    descripcion: str
    a_debe: str = ''       # destino automático (ej. 9411 / 20111)
    a_haber: str = ''      # contrapartida automática (ej. 7911 / 6111020)
    tipo: str = ''         # Activo / Pasivo / Gasto / Orden...
    es_hoja: bool = True   # True si no tiene sub-cuentas debajo (cuenta "imputable")

    @property
    def etiqueta(self) -> str:
        return f'{self.codigo} – {self.descripcion}'


@dataclass
class PlanCuentas:
    cuentas: list[Cuenta] = field(default_factory=list)
    empresa: str = ''
    ruc: str = ''

    # ---- índices ----
    def __post_init__(self):
        self._por_codigo = {c.codigo: c for c in self.cuentas}

    def reindex(self):
        self._por_codigo = {c.codigo: c for c in self.cuentas}
        codigos = sorted(self._por_codigo)
        for c in self.cuentas:
            c.es_hoja = not any(o != c.codigo and o.startswith(c.codigo) for o in codigos if o[: len(c.codigo)] == c.codigo)

    def get(self, codigo: str) -> Cuenta | None:
        return self._por_codigo.get((codigo or '').strip())

    def existe(self, codigo: str) -> bool:
        return self.get(codigo) is not None

    def hojas(self) -> list[Cuenta]:
        return [c for c in self.cuentas if c.es_hoja]

    def con_prefijo(self, prefijo: str, solo_hojas: bool = True) -> list[Cuenta]:
        return [c for c in self.cuentas if c.codigo.startswith(prefijo) and (c.es_hoja or not solo_hojas)]

    def buscar(self, texto: str, limite: int = 12) -> list[Cuenta]:
        """Búsqueda simple por código o palabras de la descripción (para autocompletar)."""
        t = (texto or '').strip().upper()
        if not t:
            return []
        res = []
        for c in self.cuentas:
            if c.codigo.startswith(t):
                res.append((0, c))
            elif all(p in c.descripcion.upper() for p in t.split()):
                res.append((1, c))
        res.sort(key=lambda x: (x[0], x[1].codigo))
        return [c for _, c in res[:limite]]

    def a_registros(self) -> list[dict]:
        return [asdict(c) for c in self.cuentas]

    @classmethod
    def desde_registros(cls, regs: Iterable[dict], empresa: str = '', ruc: str = '') -> 'PlanCuentas':
        p = cls([Cuenta(**{k: r.get(k, '') for k in ('codigo', 'descripcion', 'a_debe', 'a_haber', 'tipo')}) for r in regs], empresa, ruc)
        p.reindex()
        return p


def _limpio(v) -> str:
    return ' '.join(str(v).split()) if v is not None else ''


def leer_plan_excel(origen, hoja: str | None = None) -> PlanCuentas:
    """origen: ruta, bytes o file-like de un .xlsx con el plan de cuentas."""
    if isinstance(origen, (bytes, bytearray)):
        origen = io.BytesIO(origen)
    wb = openpyxl.load_workbook(origen, read_only=True, data_only=True)
    ws = wb[hoja] if hoja else wb.active
    filas = list(ws.iter_rows(values_only=True))

    empresa, ruc = '', ''
    for r in filas[:8]:
        for v in r:
            s = _limpio(v)
            m = re.search(r'R\.?U\.?C\.?\s*:?\s*(\d{11})', s)
            if m:
                ruc = m.group(1)
            elif s and not empresa and len(s) > 3 and 'PLAN' not in s.upper():
                empresa = s

    # localizar fila cabecera
    idx_cab, col_desc, cols_cta = None, None, []
    for i, r in enumerate(filas[:40]):
        vals = [_limpio(v).upper() for v in r]
        if any(v.startswith('DESCRIPCION') or v.startswith('DESCRIPCIÓN') for v in vals) and any(v == 'CUENTA' or v.startswith('CUENTA') for v in vals):
            idx_cab = i
            for j, v in enumerate(vals):
                if v.startswith('DESCRIPCION') or v.startswith('DESCRIPCIÓN'):
                    col_desc = j
            # columnas de cuenta: desde la de 'CUENTA' hasta antes de descripción
            j_cta = next(j for j, v in enumerate(vals) if v.startswith('CUENTA'))
            cols_cta = list(range(j_cta, col_desc))
            col_debe = next((j for j, v in enumerate(vals) if 'DEBE' in v), None)
            col_haber = next((j for j, v in enumerate(vals) if 'HABER' in v), None)
            col_tipo = next((j for j, v in enumerate(vals) if v == 'TIPO'), None)
            break

    cuentas: list[Cuenta] = []
    if idx_cab is not None:
        for r in filas[idx_cab + 1:]:
            codigo = ''
            for j in cols_cta:
                if j < len(r) and _limpio(r[j]):
                    codigo = _limpio(r[j])
                    break
            if not codigo or not re.fullmatch(r'\d{2,12}', codigo):
                continue
            desc = _limpio(r[col_desc]) if col_desc is not None and col_desc < len(r) else ''
            cuentas.append(Cuenta(codigo=codigo, descripcion=desc,
                                  a_debe=_limpio(r[col_debe]) if col_debe is not None and col_debe < len(r) else '',
                                  a_haber=_limpio(r[col_haber]) if col_haber is not None and col_haber < len(r) else '',
                                  tipo=_limpio(r[col_tipo]) if col_tipo is not None and col_tipo < len(r) else ''))
    else:
        # Formato genérico: primera columna numérica = cuenta, siguiente con texto = descripción
        for r in filas:
            vals = [_limpio(v) for v in r]
            codigo = next((v for v in vals if re.fullmatch(r'\d{2,12}', v)), '')
            if not codigo:
                continue
            desc = next((v for v in vals if v and v != codigo and not re.fullmatch(r'[\d.,]+', v)), '')
            cuentas.append(Cuenta(codigo=codigo, descripcion=desc))

    # quitar códigos repetidos (algunos planes traen la misma cuenta dos veces)
    vistos, unicas = set(), []
    for c in cuentas:
        if c.codigo not in vistos:
            vistos.add(c.codigo)
            unicas.append(c)
    plan = PlanCuentas(unicas, empresa=empresa, ruc=ruc)
    plan.reindex()
    return plan
