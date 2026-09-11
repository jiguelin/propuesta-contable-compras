# -*- coding: utf-8 -*-
"""motor/reporte.py — REPORTE_REVISION.txt: resumen del lote, observaciones, excluidos."""
from __future__ import annotations

from datetime import datetime

from .clasificador import Propuesta, resumen


def generar_reporte_txt(props: list[Propuesta], empresa: str, ruc: str, periodo: str, cuenta_haber: str, alerta_monto: float, tc_meses: list[str],
                        constancias_sin_factura: list | None = None, n_constancias: int = 0) -> str:
    r = resumen(props)
    L = []
    L.append('PROPUESTA CONTABLE DE COMPRAS')
    L.append(f'Empresa : {empresa}  (RUC {ruc})')
    L.append(f'Periodo : {periodo}')
    L.append(f'Generado: {datetime.now():%d/%m/%Y %H:%M}')
    L.append(f'Cuenta del haber aplicada al lote: {cuenta_haber}')
    L.append(f'Tipo de cambio cargado: {", ".join(tc_meses) if tc_meses else "ninguno"}')
    L.append('')
    L.append('RESUMEN')
    L.append(f'  XML recibidos        : {r["total"]}')
    L.append(f'  Contabilizados       : {r["ok"] + r["revisar"]}   (🟢 {r["verde"]}  🟡 {r["amarillo"]}  🔴 {r["rojo"]})')
    L.append(f'  Requieren revisión   : {r["revisar"]}')
    L.append(f'  Con observaciones    : {r["con_alertas"]}')
    L.append(f'  Bancos / excluidos   : {r["excluidos"]}')
    L.append(f'  Duplicados           : {r["duplicados"]}')
    L.append(f'  XML ilegibles        : {r["errores"]}')
    det = [p for p in props if p.c.tiene_detraccion and (p.estado in ('ok', 'revisar') or 'constancia' in (p.motivo or '').lower())]
    act = [p for p in props if p.estado in ('ok', 'revisar') and p.posible_activo]
    L.append(f'  Con detracción       : {len(det)}   (con constancia: {sum(1 for p in det if p.det_constancia)})')
    L.append(f'  Posible activo fijo  : {len(act)}')
    L.append('')
    if det:
        L.append('DETRACCIONES')
        for p in det:
            L.append(f'  - {p.c.serie_numero}  {p.c.nombre_emisor[:35]}  {p.c.detraccion_porcentaje}% S/ {float(p.c.detraccion_monto):,.2f}  → '
                     + (f'constancia {p.det_constancia} ({p.det_fecha:%d/%m/%Y})' if p.det_constancia else ('SIN CONSTANCIA → EXCLUIDA DEL EXCEL (pendiente para cuando se pague la detracción)' if p.estado == 'excluido' else 'SIN CONSTANCIA')))
        if constancias_sin_factura:
            L.append('  Constancias cargadas que no corresponden a ninguna factura del lote:')
            for ct in constancias_sin_factura:
                L.append(f'    · {ct.numero}  RUC {ct.ruc_proveedor}  {ct.serie}-{ct.numero_doc}  S/ {ct.monto:,.2f}  {ct.fecha:%d/%m/%Y}' if ct.fecha else f'    · {ct.numero}  RUC {ct.ruc_proveedor}  {ct.serie}-{ct.numero_doc}')
        L.append('')
    if act:
        L.append('POSIBLES ACTIVOS FIJOS (validar cuenta y registrar en el módulo de activos)')
        for p in act:
            L.append(f'  - {p.c.serie_numero}  {p.c.nombre_emisor[:35]}  {p.c.simbolo} {float(p.c.importe_total):,.2f}  cuenta {p.cuenta}')
        L.append('')

    obs = [p for p in props if p.estado in ('ok', 'revisar') and (p.alertas or p.estado == 'revisar' or p.confianza < 85)]
    L.append(f'OBSERVACIONES ({len(obs)})')
    if not obs:
        L.append('  Sin observaciones.')
    for i, p in enumerate(sorted(obs, key=lambda x: (x.estado != 'revisar', x.confianza)), start=1):
        c = p.c
        L.append(f'{i:>3}. {p.semaforo} {c.serie_numero}  {c.nombre_emisor[:40]}  {c.simbolo} {float(c.importe_total):,.2f}  ({c.fecha_emision})')
        L.append(f'      Cuenta sugerida: {p.cuenta or "(ninguna)"} {p.cuenta_desc[:50]}   Confianza: {p.confianza}%   Fuente: {p.fuente or "-"}')
        if p.explicacion:
            L.append(f'      Por qué: {p.explicacion}')
        for a in p.alertas:
            L.append(f'      ⚠ {a}')
        L.append('')

    exc = [p for p in props if p.estado in ('excluido', 'duplicado', 'error')]
    L.append(f'EXCLUIDOS DEL EXCEL ({len(exc)})')
    for p in exc:
        L.append(f'  - [{p.estado}] {p.c.serie_numero or p.c.archivo}  {p.c.nombre_emisor[:40]}  {p.c.simbolo} {float(p.c.importe_total):,.2f}  → {p.motivo}')
    L.append('')
    L.append('NOTAS')
    L.append(f'  · Alerta configurada para importes ≥ S/ {alerta_monto:,.0f}.')
    L.append('  · Detracciones sin constancia: suba el TXT/CSV/Excel de constancias de SUNAT (o los PDF) y vuelva a generar; o complete U/V en NewContaSis.')
    L.append('  · Las facturas mixtas usan una sola cuenta (la del mayor importe); cámbiela si corresponde.')
    L.append('  · Cada corrección de cuenta que haga en la app queda en la memoria de la empresa para el próximo mes.')
    return '\n'.join(L)
