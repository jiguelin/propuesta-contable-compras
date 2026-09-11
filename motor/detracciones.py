# -*- coding: utf-8 -*-
"""
motor/detracciones.py — Constancias de depósito de detracción (SUNAT) y su cruce con las facturas.

Formatos aceptados (todos los que SUNAT permite descargar):
  · TXT / CSV "Consulta de constancias" (una fila por constancia, separadas por | o ,):
      Tipo de Cuenta | Numero de Cuenta | Numero Constancia | Periodo Tributario | RUC Proveedor | ... |
      Fecha Pago | Monto Deposito | Tipo Bien | Tipo Operacion | Tipo de Comprobante | Serie de Comprobante | Numero de Comprobante | ...
  · Excel con las mismas columnas.
  · PDF "CONSTANCIA DE DEPÓSITO" individual (uno por factura) — se leen los campos por texto.
  · ZIP con cualquier mezcla de los anteriores.

Cruce: RUC del proveedor + serie + número (sin ceros a la izquierda). Si no cruza, se informa; nunca se inventa.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class Constancia:
    numero: str
    fecha: date | None
    ruc_proveedor: str
    serie: str
    numero_comprobante: str
    monto: float = 0.0
    periodo: str = ''
    origen: str = ''

    @property
    def clave(self) -> tuple:
        return (self.ruc_proveedor, self.serie.upper(), self.numero_comprobante.lstrip('0') or '0')

    @property
    def numero_doc(self) -> str:
        return self.numero_comprobante

    @property
    def comprobante(self) -> str:
        return f'{self.serie}-{self.numero_comprobante}'


def _fecha(s: str) -> date | None:
    s = (s or '').strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            pass
    return None


def _num(s) -> float:
    try:
        return float(str(s).replace('S/', '').replace(',', '').strip() or 0)
    except ValueError:
        return 0.0


# ------------------------------------------------------------------ PDF individual
def leer_constancia_pdf(data: bytes, nombre: str = '') -> Constancia | None:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            texto = '\n'.join((p.extract_text() or '') for p in pdf.pages)
    except ImportError:
        import fitz
        texto = '\n'.join(p.get_text() for p in fitz.open(stream=data, filetype='pdf'))
    if 'CONSTANCIA' not in texto.upper() or 'DETRACCI' not in texto.upper() and 'D.LEG' not in texto.upper():
        return None

    def campo(etiqueta: str) -> str:
        m = re.search(etiqueta + r'\s*[:\-]?\s*(.+)', texto, re.IGNORECASE)
        return m.group(1).strip() if m else ''

    numero = re.sub(r'\D', '', campo(r'N[úu]mero de constancia'))
    ruc = re.sub(r'\D', '', campo(r'Ruc del Proveedor'))[:11]
    comp = campo(r'N[úu]mero de Comprobante')
    m = re.match(r'([A-Z0-9]{1,6})\s*-\s*(\d+)', comp.upper())
    serie, num = (m.group(1), m.group(2)) if m else ('', re.sub(r'\D', '', comp))
    fecha = _fecha(campo(r'Fecha y hora de pago'))
    if not numero or not ruc:
        return None
    return Constancia(numero, fecha, ruc, serie, num, _num(campo(r'Monto del dep[óo]sito')), re.sub(r'\D', '', campo(r'Periodo Tributario'))[:6], nombre or 'PDF')


# ------------------------------------------------------------------ TXT / CSV / Excel de SUNAT
def _de_tabla(filas: list[list[str]], origen: str) -> list[Constancia]:
    if not filas:
        return []
    cab = [str(c or '').strip().upper() for c in filas[0]]

    def col(*claves):
        for i, c in enumerate(cab):
            if all(k in c for k in claves):
                return i
        return None

    i_num, i_ruc, i_fecha = col('CONSTANCIA'), col('RUC', 'PROVEEDOR'), col('FECHA', 'PAGO')
    i_serie, i_ncomp = col('SERIE', 'COMPROBANTE'), col('NUMERO', 'COMPROBANTE')
    i_monto, i_per = col('MONTO'), col('PERIODO')
    if i_num is None or i_ruc is None:
        return []
    out = []
    for f in filas[1:]:
        f = [str(x or '').strip() for x in f] + [''] * 20
        if not re.fullmatch(r'\d{11}', f[i_ruc]) or not f[i_num]:
            continue
        num_c = re.sub(r'\D', '', f[i_ncomp]) if i_ncomp is not None else ''
        # a veces viene "E001-00000002" en una sola columna
        serie = f[i_serie] if i_serie is not None else ''
        if not serie and '-' in f[i_ncomp or 0]:
            serie, num_c = f[i_ncomp].split('-', 1)
            num_c = re.sub(r'\D', '', num_c)
        out.append(Constancia(re.sub(r'\D', '', f[i_num]), _fecha(f[i_fecha]) if i_fecha is not None else None, f[i_ruc],
                              serie.upper(), num_c, _num(f[i_monto]) if i_monto is not None else 0.0,
                              re.sub(r'\D', '', f[i_per])[:6] if i_per is not None else '', origen))
    return out


def leer_constancias(archivos) -> list[Constancia]:
    """archivos: [(nombre, bytes)] o (nombre, bytes). Acepta pdf / txt / csv / xlsx / zip."""
    if isinstance(archivos, tuple):
        archivos = [archivos]
    out = []
    for nombre, data in archivos:
        out += _leer_uno(nombre, data)
    return out


def _leer_uno(nombre: str, data: bytes) -> list[Constancia]:
    low = nombre.lower()
    if low.endswith('.zip'):
        out = []
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for n in z.namelist():
                if n.startswith('__MACOSX') or n.endswith('/'):
                    continue
                out += _leer_uno(n.split('/')[-1], z.read(n))
        return out
    if low.endswith('.pdf'):
        c = leer_constancia_pdf(data, nombre)
        return [c] if c else []
    if low.endswith(('.xlsx', '.xls')):
        import openpyxl
        ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        return _de_tabla([list(r) for r in ws.iter_rows(values_only=True)], nombre)
    if low.endswith(('.txt', '.csv')):
        texto = data.decode('utf-8-sig', errors='replace')
        sep = '|' if texto.count('|') > texto.count(',') else ','
        return _de_tabla(list(csv.reader(io.StringIO(texto), delimiter=sep)), nombre)
    return []


# ------------------------------------------------------------------ cruce con las propuestas
def cruzar(propuestas, constancias: list[Constancia]) -> tuple[int, list[Constancia]]:
    """Asigna p.constancia / p.constancia_fecha a las facturas con detracción. Devuelve (n_cruzadas, no_cruzadas)."""
    indice: dict[tuple, Constancia] = {}
    for c in constancias:
        indice.setdefault(c.clave, c)          # si SUNAT lista dos veces la misma, nos quedamos con la primera
    usadas: set[tuple] = set()
    n = 0
    for p in propuestas:
        if p.estado not in ('ok', 'revisar'):
            continue
        sn = p.c.serie_numero.upper()
        serie, num = (sn.split('-', 1) + [''])[:2]
        clave = (p.c.ruc_emisor, serie, num.lstrip('0') or '0')
        c = indice.get(clave)
        if c:
            p.det_constancia, p.det_fecha, p.det_monto = c.numero, c.fecha, c.monto
            if c.monto and p.c.detraccion_monto and abs(float(p.c.detraccion_monto) - c.monto) > 1.0:
                p.alertas.append(f'El depósito de la constancia (S/ {c.monto:,.2f}) difiere del monto de detracción del XML (S/ {float(p.c.detraccion_monto):,.2f}).')
            usadas.add(clave)
            n += 1
            p.alertas = [a for a in p.alertas if 'constancia' not in a.lower()]
            if not p.c.tiene_detraccion:
                p.alertas.append(f'Hay constancia de detracción {c.numero} pero el XML no declara detracción: revisar.')
    return n, [c for k, c in indice.items() if k not in usadas]
