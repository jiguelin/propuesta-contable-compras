# -*- coding: utf-8 -*-
"""
motor/excel_entrada.py — Comprobantes de compra desde un Excel, para cuando el descargador no trae todos los XML.

Formato: el mismo orden de columnas que la plantilla de importación de NewContaSis (A–AX), con las cuentas vacías
(es el `resultado_*.xlsx` del descargador; hoja "Comprobantes", datos desde la fila 4, pero se acepta cualquier hoja/fila):
    A emisión · B/AD vencimiento · C tipo · D serie · F número · G tipo doc. proveedor · H RUC · I razón social
    J base gravada · K IGV · L–O gravadas mixtas/no gravadas · P no gravadas · Q ISC · R otros tributos · S total  ← en SOLES
    U/V constancia de detracción · W tipo de cambio · X–AA documento de referencia (NC/ND) · AC importe en US$
Reglas de lectura (las mismas del app de Ralumin):
  · Se toma toda fila con fecha en A y tipo (1–2 dígitos) en C; sin número de comprobante se omite con aviso.
  · Si AC tiene un valor, el comprobante es en DÓLARES y W trae su tipo de cambio. En soles AC viene vacío y W = 1.
  · Las notas de crédito vienen en negativo: se leen en positivo (tipo 07), igual que en el XML.
  · El Excel no trae ítems, glosa ni forma de pago: la cuenta sale de la memoria del proveedor (historial) y de su nombre;
    vencimiento posterior a la emisión → crédito.

Cada fila se convierte en un `Comprobante` como el de un XML (origen='excel'), así el resto del motor no cambia.
Los importes originales en soles y el TC del Excel se guardan en `c.excel` para exportarlos tal cual.
Si el mismo comprobante llega también por XML, MANDA EL XML (trae ítems, referencia de la NC, detracción, percepción).
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

import openpyxl

from .xml_parser import TIPOS_DOC, Comprobante

COLS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z',
        'AA', 'AB', 'AC', 'AD', 'AE', 'AF', 'AG', 'AH', 'AI', 'AJ', 'AK', 'AL', 'AM', 'AN', 'AO', 'AP', 'AQ', 'AR', 'AS', 'AT', 'AU', 'AV',
        'AW', 'AX']
COL = {k: i for i, k in enumerate(COLS)}
IMPORTES = 'JKLMNOPQRS'
_C = Decimal('0.01')


def _txt(v) -> str:
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return ' '.join(str(v).split())


def _num(v) -> float:
    if v is None or v == '':
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(',', '').strip() or 0)
    except ValueError:
        return 0.0


def _fecha(v) -> str:
    """→ 'YYYY-MM-DD' o ''."""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = _txt(v)
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(s[:10], fmt).date().isoformat()
        except ValueError:
            pass
    return ''


def es_excel(nombre: str) -> bool:
    return nombre.lower().endswith(('.xlsx', '.xlsm'))


def leer_excel_compras(data: bytes, nombre: str = 'Excel') -> tuple[list[dict], list[str]]:
    """Devuelve (filas, avisos). Cada fila es un dict con las columnas útiles (importes en positivo)."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as ex:
        return [], [f'{nombre}: no se pudo abrir como Excel ({ex}).']
    filas, avisos = [], []
    for ws in wb.worksheets:
        for n, r in enumerate(ws.iter_rows(values_only=True), start=1):
            r = list(r) + [None] * (50 - len(r))
            fe, tipo = _fecha(r[COL['A']]), _txt(r[COL['C']])
            if not fe or not re.fullmatch(r'\d{1,2}', tipo):
                continue
            serie, numero = _txt(r[COL['D']]).upper(), _txt(r[COL['F']])
            if not numero:
                avisos.append(f'{nombre} · {ws.title} fila {n}: sin número de comprobante; se omitió.')
                continue
            ac = r[COL['AC']]
            f = {'archivo': nombre, 'hoja': ws.title, 'fila': n, 'emision': fe,
                 'vencimiento': _fecha(r[COL['AD']]) or _fecha(r[COL['B']]),
                 'tipo': tipo.zfill(2), 'serie': serie, 'numero': numero,
                 'tipo_doc_prov': _txt(r[COL['G']]), 'ruc': _txt(r[COL['H']]), 'nombre': _txt(r[COL['I']]),
                 'det_constancia': _txt(r[COL['U']]), 'det_fecha': _fecha(r[COL['V']]), 'tc': _num(r[COL['W']]),
                 'ref_fecha': _fecha(r[COL['X']]), 'ref_tipo': _txt(r[COL['Y']]).zfill(2) if _txt(r[COL['Y']]) else '',
                 'ref_serie': _txt(r[COL['Z']]).upper(), 'ref_numero': _txt(r[COL['AA']]),
                 'usd': _txt(ac) != '' and abs(_num(ac)) > 0, 'AC': abs(_num(ac))}
            for col in IMPORTES:           # NC en negativo → positivo (como el XML)
                f[col] = abs(_num(r[COL[col]]))
            filas.append(f)
    return filas, avisos


def clave(ruc: str, tipo: str, serie_numero: str) -> tuple:
    """Clave para no duplicar XML ↔ Excel: RUC + tipo + serie + número sin ceros a la izquierda."""
    serie, _, numero = (serie_numero or '').upper().replace(' ', '').rpartition('-')
    numero = numero.lstrip('0') or '0'
    return (ruc or '', (tipo or '').zfill(2), serie, numero)


def _d(x: float) -> Decimal:
    return Decimal(str(x)).quantize(_C, ROUND_HALF_UP)


def comprobante_desde_fila(f: dict) -> Comprobante:
    tipo = f['tipo']
    c = Comprobante(archivo=f'{f["archivo"]} · fila {f["fila"]}')
    c.tipo_codigo = tipo
    c.tipo_documento, c.tipo_nombre = TIPOS_DOC.get(tipo) or ('otro', f'DOCUMENTO TIPO {tipo}')
    c.serie_numero = f'{f["serie"]}-{f["numero"]}'
    c.fecha_emision = f['emision']
    c.fecha_vencimiento = f['vencimiento'] if f['vencimiento'] and f['vencimiento'] > f['emision'] else ''
    c.ruc_emisor = f['ruc'] if f['ruc'] not in ('0', '') else ''
    c.nombre_emisor = f['nombre'] or (f'PROVEEDOR {c.ruc_emisor}' if c.ruc_emisor else 'PROVEEDOR SIN RUC')
    usd = bool(f['usd'])
    c.moneda_codigo, c.moneda, c.simbolo = ('USD', 'dolares', 'US$') if usd else ('PEN', 'soles', 'S/')

    # importes: el Excel los trae en soles; un comprobante en dólares se lleva a dólares con AC / S (o 1 / TC)
    S = f['S']
    k = ((f['AC'] / S) if S else (1 / f['tc'] if f['tc'] else 1.0)) if usd else 1.0
    base = f['J'] + f['L'] + f['N']
    igv_sol = f['K'] + f['M'] + f['O']
    c.gravadas = _d(base * k)
    c.inafectas = _d(f['P'] * k)
    c.isc = _d(f['Q'] * k)
    c.otros_cargos = _d(f['R'] * k)
    c.importe_total = _d(f['AC']) if usd and S else _d(S * k)
    c.igv = (c.importe_total - c.gravadas - c.inafectas - c.isc - c.otros_cargos) if igv_sol else Decimal(0)
    c.valor_venta = c.gravadas + c.inafectas
    c.tiene_igv = c.igv > 0
    if base > 0 and igv_sol:
        tasa = igv_sol / base * 100
        for conocida in (18, 10.5, 10, 15, 8):
            if abs(tasa - conocida) <= 0.3:
                tasa = conocida
                break
        c.igv_tasa = Decimal(str(round(tasa, 2))).quantize(_C)

    if c.fecha_vencimiento:                       # vence después de la emisión → crédito
        c.forma_pago = 'Credito'
        c.cuotas = [{'cuota': 'Cuota001', 'monto': c.importe_total, 'vence': c.fecha_vencimiento}]
    if f['ref_serie'] or f['ref_numero']:         # NC / ND: documento de referencia
        c.doc_referencia = f'{f["ref_serie"]}-{f["ref_numero"]}'
    if f['det_constancia']:                       # detracción solo si el Excel trae la constancia
        c.tiene_detraccion = True

    c.origen = 'excel'
    c.excel = f
    return c


def es_de_excel(c) -> bool:
    return getattr(c, 'origen', 'xml') == 'excel'
