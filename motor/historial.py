# -*- coding: utf-8 -*-
"""
motor/historial.py — Lector OPCIONAL del historial contable de la empresa.

Formato 1 (Diario Analítico NewContaSis, "LIBRO DIARIO ... SUBDIARIO 01"):
   MES | FECHA | CUENTA | DESCRIPCION | DEBE | HABER | GLOSA, asientos separados por
   "Sub diario 01 asiento No: N" y "TOTAL ASIENTO". No trae RUC ni número de comprobante.
   → Sirve para saber qué cuentas usa realmente la empresa, con qué frecuencia, cuál es su
     cuenta del haber habitual (4212 / 1011 / 104101...) y para cruzar por fecha+importe con XML.

Formato 2 (cualquier Excel con columnas RUC/proveedor + cuenta): memoria directa por proveedor.
"""
from __future__ import annotations

import io
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

import openpyxl


@dataclass
class Asiento:
    fecha: date | None
    lineas: list[dict]          # {cuenta, descripcion, debe, haber, glosa}

    @property
    def cuenta_gasto(self) -> str | None:
        """Primera cuenta del debe que es de gasto/compra/activo (6x, 33, 34)."""
        for l in self.lineas:
            c = l['cuenta']
            if l['debe'] and c.startswith(('60', '62', '63', '65', '33', '34')):
                return c
        return None

    @property
    def base(self) -> float:
        return sum(l['debe'] for l in self.lineas if l['cuenta'].startswith(('60', '62', '63', '65', '33', '34')))

    @property
    def total(self) -> float:
        return sum(l['haber'] for l in self.lineas if l['cuenta'].startswith(('42', '10', '46')))

    @property
    def cuenta_haber(self) -> str | None:
        for l in self.lineas:
            if l['haber'] and l['cuenta'].startswith(('42', '10', '46')):
                return l['cuenta']
        return None


@dataclass
class ResumenHistorial:
    empresa: str = ''
    ruc: str = ''
    periodo: str = ''
    asientos: list[Asiento] = field(default_factory=list)
    frecuencia_cuentas: Counter = field(default_factory=Counter)      # cuenta gasto → veces
    frecuencia_haber: Counter = field(default_factory=Counter)        # 4212/1011 → veces
    descripciones: dict = field(default_factory=dict)                 # cuenta → descripción
    por_proveedor: dict = field(default_factory=dict)                 # ruc → Counter(cuenta) (solo formato 2)

    @property
    def cuenta_haber_habitual(self) -> str | None:
        return self.frecuencia_haber.most_common(1)[0][0] if self.frecuencia_haber else None

    def cuentas_usadas(self) -> list[str]:
        return [c for c, _ in self.frecuencia_cuentas.most_common()]

    def buscar_por_importe(self, fecha: date, base: float, total: float, tolerancia: float = 0.02, dias: int = 3) -> Asiento | None:
        """Cruce Diario ↔ XML: mismo total (±tol) en fecha cercana. Devuelve el asiento o None."""
        mejores = []
        for a in self.asientos:
            if not a.fecha:
                continue
            if abs((a.fecha - fecha).days) <= dias and (abs(a.total - total) <= tolerancia or abs(a.base - base) <= tolerancia):
                mejores.append((abs((a.fecha - fecha).days), a))
        if len(mejores) == 1 or (mejores and mejores[0][0] == 0 and sum(1 for m in mejores if m[0] == 0) == 1):
            mejores.sort(key=lambda x: x[0])
            return mejores[0][1]
        return None


def _limpio(v) -> str:
    return ' '.join(str(v).split()) if v is not None else ''


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def leer_historial_excel(origen) -> ResumenHistorial:
    if isinstance(origen, (bytes, bytearray)):
        origen = io.BytesIO(origen)
    wb = openpyxl.load_workbook(origen, read_only=True, data_only=True)
    ws = wb.active
    filas = list(ws.iter_rows(values_only=True))
    res = ResumenHistorial()

    for r in filas[:8]:
        for v in r:
            s = _limpio(v)
            m = re.search(r'R\.?U\.?C\.?\s*:?\s*(\d{11})', s)
            if m:
                res.ruc = m.group(1)
            elif s and not res.empresa and len(s) > 3 and 'LIBRO' not in s.upper():
                res.empresa = s
            if 'LIBRO DIARIO' in s.upper():
                res.periodo = s

    # cabecera
    idx = None
    for i, r in enumerate(filas[:40]):
        vals = [_limpio(v).upper() for v in r]
        if 'CUENTA' in vals and 'DEBE' in vals and 'HABER' in vals:
            idx = i
            ci = {v: j for j, v in enumerate(vals)}
            break

    if idx is not None:   # ---- Formato 1: Diario Analítico ----
        c_fecha, c_cta, c_desc, c_debe, c_haber = ci['CUENTA'] - 1, ci['CUENTA'], ci.get('DESCRIPCION', ci.get('DESCRIPCIÓN', ci['CUENTA'] + 1)), ci['DEBE'], ci['HABER']
        c_glosa = ci.get('GLOSA')
        c_ruc = next((ci[k] for k in ci if 'RUC' in k), None)
        actual: list[dict] = []
        fecha_actual = None

        def cerrar():
            nonlocal actual, fecha_actual
            if actual:
                res.asientos.append(Asiento(fecha_actual, actual))
            actual, fecha_actual = [], None

        for r in filas[idx + 1:]:
            vals = list(r) + [None] * 12
            desc = _limpio(vals[c_desc]).upper()
            cta = _limpio(vals[c_cta])
            if desc.startswith('TOTAL ASIENTO') or 'ASIENTO NO' in desc:
                cerrar()
                continue
            if not re.fullmatch(r'\d{2,12}', cta):
                continue
            f = vals[c_fecha]
            if isinstance(f, datetime):
                fecha_actual = f.date()
            elif isinstance(f, date):
                fecha_actual = f
            elif isinstance(f, str):
                for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
                    try:
                        fecha_actual = datetime.strptime(f[:10], fmt).date()
                        break
                    except ValueError:
                        pass
            linea = dict(cuenta=cta, descripcion=_limpio(vals[c_desc]), debe=_num(vals[c_debe]), haber=_num(vals[c_haber]),
                         glosa=_limpio(vals[c_glosa]) if c_glosa is not None else '')
            if c_ruc is not None and re.fullmatch(r'\d{11}', _limpio(vals[c_ruc])):
                linea['ruc'] = _limpio(vals[c_ruc])
            actual.append(linea)
            res.descripciones.setdefault(cta, linea['descripcion'])
        cerrar()

        for a in res.asientos:
            g = a.cuenta_gasto
            if g:
                res.frecuencia_cuentas[g] += 1
            h = a.cuenta_haber
            if h:
                res.frecuencia_haber[h] += 1
            rucs = {l.get('ruc') for l in a.lineas if l.get('ruc')}
            if g and rucs:
                for ruc in rucs:
                    res.por_proveedor.setdefault(ruc, Counter())[g] += 1
    else:   # ---- Formato 2: tabla plana RUC + cuenta ----
        import pandas as pd
        origen.seek(0) if hasattr(origen, 'seek') else None
        df = pd.read_excel(origen)
        cols = {str(c).strip().upper(): c for c in df.columns}
        c_ruc = next((cols[k] for k in cols if 'RUC' in k), None)
        c_cta = next((cols[k] for k in cols if 'CUENTA' in k), None)
        if c_ruc is None or c_cta is None:
            raise ValueError('No reconozco el formato: se esperaba un Diario Analítico (MES/FECHA/CUENTA/DEBE/HABER) o una tabla con columnas RUC y CUENTA.')
        for _, r in df.iterrows():
            ruc, cta = _limpio(r[c_ruc]), _limpio(r[c_cta]).split('.')[0]
            if re.fullmatch(r'\d{11}', ruc) and re.fullmatch(r'\d{2,12}', cta):
                res.por_proveedor.setdefault(ruc, Counter())[cta] += 1
                res.frecuencia_cuentas[cta] += 1
    return res
