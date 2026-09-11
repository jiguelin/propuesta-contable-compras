# -*- coding: utf-8 -*-
"""motor/reporte.py — REPORTE_REVISION.txt: resumen del lote, observaciones, excluidos."""
from __future__ import annotations

from datetime import datetime

from .clasificador import Propuesta, resumen


def generar_reporte_txt(props: list[Propuesta], empresa: str, ruc: str, periodo: str, cuenta_haber: str, alerta_monto: float, tc_meses: list[str]) -> str:
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
    L.append('  · Las constancias de depósito de detracción no vienen en el XML: completar U/V y AN-AP en NewContaSis o en el Excel.')
    L.append('  · Las facturas mixtas usan una sola cuenta (la del mayor importe); cámbiela si corresponde.')
    L.append('  · Cada corrección de cuenta que haga en la app queda en la memoria de la empresa para el próximo mes.')
    return '\n'.join(L)
