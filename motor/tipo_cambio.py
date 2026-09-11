# -*- coding: utf-8 -*-
"""
motor/tipo_cambio.py — Historial de tipo de cambio SUNAT.

Lee el PDF mensual "SUNAT - Tipo de Cambio" (tabla Día | Compra | Venta en 4 bloques) y
también Excel/CSV con columnas fecha, compra, venta. Los datos se acumulan en la base
(nunca se borran meses anteriores).

Regla SUNAT (IGV): para operaciones en moneda extranjera se usa el tipo de cambio promedio
ponderado VENTA publicado en la fecha de nacimiento de la obligación (fecha de emisión);
si ese día no hay publicación, el último publicado (día inmediato anterior).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

MESES = {'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4, 'MAYO': 5, 'JUNIO': 6, 'JULIO': 7,
         'AGOSTO': 8, 'SETIEMBRE': 9, 'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12}


@dataclass
class TC:
    fecha: date
    compra: float
    venta: float
    fuente: str = 'SUNAT'


def _texto_pdf(data: bytes) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return '\n'.join((p.extract_text() or '') for p in pdf.pages)
    except ImportError:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=data, filetype='pdf')
        return '\n'.join(p.get_text() for p in doc)


def leer_pdf_sunat(data: bytes) -> list[TC]:
    """Extrae (fecha, compra, venta) del PDF mensual de SUNAT."""
    texto = _texto_pdf(data)
    m = re.search(r'([A-ZÑ]+)\s*-\s*(\d{4})', texto.upper())
    if not m or m.group(1) not in MESES:
        raise ValueError('No se encontró el mes/año en el PDF (se esperaba, por ejemplo, "MAYO - 2026").')
    mes, anio = MESES[m.group(1)], int(m.group(2))
    # tripletas  "17  3.426  3.435" (puede haber 4 por línea)
    res: dict[int, TC] = {}
    for dia, compra, venta in re.findall(r'(?<!\d)(\d{1,2})\s+(\d\.\d{3})\s+(\d\.\d{3})', texto):
        d = int(dia)
        if 1 <= d <= 31 and d not in res:
            try:
                res[d] = TC(date(anio, mes, d), float(compra), float(venta), 'SUNAT PDF')
            except ValueError:
                pass
    if not res:
        raise ValueError('El PDF no contiene la tabla Día/Compra/Venta esperada.')
    return [res[k] for k in sorted(res)]


def leer_tabla(origen) -> list[TC]:
    """Excel/CSV con columnas fecha | compra | venta (cabecera opcional)."""
    import pandas as pd
    if isinstance(origen, (bytes, bytearray)):
        origen = io.BytesIO(origen)
    try:
        df = pd.read_excel(origen)
    except Exception:
        origen.seek(0) if hasattr(origen, 'seek') else None
        df = pd.read_csv(origen)
    cols = {c.lower().strip(): c for c in df.columns}
    fcol = next((cols[c] for c in cols if 'fecha' in c or 'dia' in c or 'día' in c), df.columns[0])
    ccol = next((cols[c] for c in cols if 'compra' in c), df.columns[1])
    vcol = next((cols[c] for c in cols if 'venta' in c), df.columns[2])
    out = []
    for _, r in df.iterrows():
        try:
            f = pd.to_datetime(r[fcol], dayfirst=True).date()
            out.append(TC(f, float(r[ccol]), float(r[vcol]), 'Tabla'))
        except Exception:
            continue
    return out


class HistorialTC:
    """Diccionario fecha → TC con búsqueda 'último publicado'."""

    def __init__(self, items: list[TC] | None = None):
        self._d: dict[date, TC] = {}
        for t in items or []:
            self.agregar(t)

    def agregar(self, t: TC):
        self._d[t.fecha] = t

    def __len__(self):
        return len(self._d)

    def fechas(self) -> list[date]:
        return sorted(self._d)

    def meses_cargados(self) -> list[str]:
        return sorted({f.strftime('%Y-%m') for f in self._d})

    def buscar(self, fecha: date | str, retroceso_max: int = 7) -> tuple[TC | None, bool]:
        """Devuelve (TC, exacto). Si no hay publicación ese día, retrocede hasta `retroceso_max` días."""
        if isinstance(fecha, str):
            fecha = datetime.strptime(fecha[:10], '%Y-%m-%d').date()
        if fecha in self._d:
            return self._d[fecha], True
        for i in range(1, retroceso_max + 1):
            f = fecha - timedelta(days=i)
            if f in self._d:
                return self._d[f], False
        return None, False

    def venta(self, fecha) -> float | None:
        t, _ = self.buscar(fecha)
        return t.venta if t else None
