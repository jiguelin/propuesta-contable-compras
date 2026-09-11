# -*- coding: utf-8 -*-
"""
motor/clasificador.py — Motor de contabilización de compras.

Capas (en este orden, la IA al final y solo si hay duda):
  1. Exclusiones: bancos (RUC conocido o tipo 30), documentos que no son comprobantes de compra, duplicados.
  2. Concepto de la factura: familia PCGE dominante por IMPORTE de los ítems (no por número de líneas).
  3. Memoria de la empresa: proveedor + concepto → cuenta aprendida (correcciones anteriores / historial).
  4. Plan de cuentas de la empresa: cuentas candidatas reales bajo la familia PCGE (preferimos las que
     el historial muestra que la empresa usa).
  5. IA (opcional): solo elige entre las candidatas existentes. Nunca inventa una cuenta.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from . import pcge
from .plan_cuentas import Cuenta, PlanCuentas
from .tipo_cambio import HistorialTC
from .xml_parser import (Comprobante, RUCS_BANCOS, RUCS_COMBUSTIBLE, RUCS_RESTAURANTES, RUCS_SEGUROS,
                         RUCS_SERVICIOS_PUBLICOS, texto_items)

TIPOS_COMPRA = {'01', '03', '07', '08'}      # factura, boleta, NC, ND

VERDE, AMARILLO, ROJO = 95, 75, 0


@dataclass
class Propuesta:
    c: Comprobante
    estado: str = 'ok'              # ok | revisar | excluido | error | duplicado
    motivo: str = ''
    cuenta: str = ''
    cuenta_desc: str = ''
    confianza: int = 0
    fuente: str = ''                # memoria | historial | reglas | ia | manual | defecto
    familia: str = ''               # prefijo PCGE
    familia_nombre: str = ''
    concepto: str = ''              # clave de aprendizaje (= familia)
    av: int = 5
    candidatas: list[Cuenta] = field(default_factory=list)
    mezcla: list[tuple[str, float]] = field(default_factory=list)   # [(familia, %)] cuando es mixta
    tc: float | None = None
    tc_exacto: bool = True
    alertas: list[str] = field(default_factory=list)
    glosa: str = ''
    explicacion: str = ''
    posible_activo: bool = False
    det_constancia: str = ''
    det_fecha: object = None
    det_monto: float = 0.0          # monto depositado según la constancia (si se cruzó)

    @property
    def semaforo(self) -> str:
        if self.estado in ('excluido', 'error', 'duplicado'):
            return '⚪'
        return '🟢' if self.confianza >= VERDE else ('🟡' if self.confianza >= AMARILLO else '🔴')

    @property
    def id(self) -> str:
        return f'{self.c.ruc_emisor}|{self.c.tipo_codigo}|{self.c.serie_numero}'


@dataclass
class Contexto:
    plan: PlanCuentas | None
    tc: HistorialTC | None
    memoria_proveedor: callable = None         # (ruc_proveedor) -> [{concepto, cuenta, veces}]
    historial_stats: dict = field(default_factory=dict)   # cuenta → veces (del Diario)
    cuenta_haber: str = '4212'
    alerta_monto: float = 20000
    excluir_bancos: bool = True
    ia: callable = None                        # (Propuesta, Contexto) -> (cuenta, confianza, razon) | None
    umbral_ia: int = 90                        # si confianza < umbral y hay IA, se consulta
    umbral_activo: float = 1800                # sospecha de activo fijo desde este importe (incl. IGV)
    periodo: str = ''                          # 'YYYY-MM'; si se indica, lo que no sea de ese mes se excluye


# --------------------------------------------------------------------------------------
# 2. Concepto dominante por importe
# --------------------------------------------------------------------------------------
def _familia_por_ruc(c: Comprobante) -> dict | None:
    if c.ruc_emisor in RUCS_COMBUSTIBLE:
        return next(f for f in pcge.FAMILIAS if f['prefijo'] == '6032')
    if c.ruc_emisor in RUCS_RESTAURANTES:
        return next(f for f in pcge.FAMILIAS if f['prefijo'] == '6314')
    if c.ruc_emisor in RUCS_SEGUROS:
        return next(f for f in pcge.FAMILIAS if f['prefijo'] == '651')
    if c.ruc_emisor in RUCS_SERVICIOS_PUBLICOS:
        nombre = RUCS_SERVICIOS_PUBLICOS[c.ruc_emisor].upper()
        pref = '6361' if 'LUZ' in nombre or 'ENEL' in nombre else ('6363' if 'SEDAPAL' in nombre else '6364')
        return next(f for f in pcge.FAMILIAS if f['prefijo'] == pref)
    return None


def _familia_defecto(c: Comprobante, ctx: Contexto) -> tuple[dict, str]:
    """Sin pista en la descripción: decidir entre 'bien' y 'servicio' y usar la familia que la
    empresa más usa según su historial (p.ej. minimarket → 601; consultorio → 656)."""
    unidades = {l.unidad for l in c.lineas}
    es_servicio = bool(c.lineas) and unidades <= {'SERVICIO', ''} or c.tiene_detraccion
    if es_servicio:
        pref = '639'
        txt = 'ítems con unidad SERVICIO (ZZ)' + (' y detracción' if c.tiene_detraccion else '')
    else:
        pref = '656'
        # ¿la empresa compra mercadería (601) más que suministros (656)?
        n601 = sum(v for k, v in ctx.historial_stats.items() if k.startswith('601'))
        n656 = sum(v for k, v in ctx.historial_stats.items() if k.startswith('656'))
        if n601 > n656:
            pref = '601'
        txt = f'productos sin palabra clave; la empresa usa habitualmente {pref} según su historial' if ctx.historial_stats else 'productos sin palabra clave'
    fam = next(f for f in pcge.FAMILIAS if f['prefijo'] == pref)
    return fam, txt


def determinar_concepto(c: Comprobante, ctx: Contexto) -> tuple[dict, list[tuple[str, float]], str, int]:
    """Devuelve (familia dominante, mezcla [(prefijo, %)], explicación, fuerza 0-3)."""
    pesos: dict[str, Decimal] = defaultdict(Decimal)
    nombres = {}
    total = Decimal(0)
    for l in c.lineas:
        imp = abs(l.valor_venta) if l.valor_venta else Decimal(0)
        total += imp
        hits = pcge.familias_por_texto(l.descripcion)
        if hits:
            fam = hits[0][0]
            pesos[fam['prefijo']] += imp if imp else Decimal('0.01')
            nombres[fam['prefijo']] = fam
    if pesos:
        orden = sorted(pesos.items(), key=lambda x: -x[1])
        base = total if total else sum(pesos.values())
        mezcla = [(p, float(v / base * 100) if base else 0.0) for p, v in orden]
        fam = nombres[orden[0][0]]
        cubierto = float(sum(pesos.values()) / base * 100) if base else 100
        fuerza = 3 if cubierto >= 80 else (2 if cubierto >= 50 else 1)
        return fam, mezcla, f'descripción de ítems → {fam["nombre"]} ({cubierto:.0f}% del importe con palabra clave)', fuerza

    # sin coincidencia por ítems: probar texto completo (leyendas/observaciones) y RUC conocido
    hits = pcge.familias_por_texto(' '.join(c.leyendas + c.observaciones))
    fr = _familia_por_ruc(c)
    if fr:
        return fr, [(fr['prefijo'], 100.0)], f'RUC conocido ({c.nombre_emisor[:30]}) → {fr["nombre"]}', 2
    fe = pcge.familia_por_emisor(c.nombre_emisor + ' ' + c.nombre_comercial)
    if fe:
        return fe, [(fe['prefijo'], 100.0)], f'nombre del emisor ({c.nombre_emisor[:30]}) → {fe["nombre"]}', 2
    if hits:
        return hits[0][0], [(hits[0][0]['prefijo'], 100.0)], f'texto del comprobante → {hits[0][0]["nombre"]}', 1
    fam, txt = _familia_defecto(c, ctx)
    return fam, [(fam['prefijo'], 100.0)], txt, 0


# --------------------------------------------------------------------------------------
# 4. Candidatas del plan de la empresa
# --------------------------------------------------------------------------------------
def candidatas_para(prefijo: str, ctx: Contexto) -> list[Cuenta]:
    if not ctx.plan:
        return []
    p = prefijo
    while len(p) >= 2:
        cand = ctx.plan.con_prefijo(p)
        if cand:
            return cand
        p = p[:-1]
    return []


def _puntaje_candidata(cu: Cuenta, ctx: Contexto, fam: dict | None = None, texto: str = '') -> tuple:
    usos = ctx.historial_stats.get(cu.codigo, 0)
    d = cu.descripcion.upper()
    # 1) palabras preferidas de la familia en la descripción de la cuenta (ej. 6032 → "COMBUSTIBLE")
    pref = sum(1 for k in (fam or {}).get('pref_desc', ()) if k in d)
    # 2) palabras de los ítems que aparecen en la descripción de la cuenta
    palabras = {w for w in texto.upper().replace('/', ' ').split() if len(w) > 3}
    coincid = sum(1 for w in palabras if w in d)
    # 3) preferimos ADM (094 / "- ADM") como destino genérico si no hay historial
    pref_adm = 1 if ('ADM' in d or cu.codigo.endswith('094') or cu.codigo.endswith('4')) else 0
    return (-usos, -pref, -coincid, -pref_adm, len(cu.codigo), cu.codigo)


def elegir_candidata(cands: list[Cuenta], ctx: Contexto, fam: dict | None = None, texto: str = '') -> tuple[Cuenta | None, str]:
    if not cands:
        return None, ''
    orden = sorted(cands, key=lambda cu: _puntaje_candidata(cu, ctx, fam, texto))
    top = orden[0]
    usos = ctx.historial_stats.get(top.codigo, 0)
    if usos:
        return top, f'la empresa la usó {usos} veces en su historial'
    if len(orden) == 1:
        return top, 'única cuenta de esa familia en el plan'
    return top, f'{len(orden)} cuentas posibles en la familia; se propone la de administración/genérica'


# --------------------------------------------------------------------------------------
# Motor principal
# --------------------------------------------------------------------------------------
def _glosa(c: Comprobante) -> str:
    dom = max(c.lineas, key=lambda l: l.valor_venta).descripcion if c.lineas else ''
    pref = {'07': 'NOTA DE CRÉDITO', '08': 'NOTA DE DÉBITO'}.get(c.tipo_codigo, 'COMPRA')
    g = f'{pref} {dom}'.strip()
    return ' '.join(g.split())[:60].upper()


def procesar_lote(comprobantes: list[Comprobante], ctx: Contexto) -> list[Propuesta]:
    vistos: set[str] = set()
    props: list[Propuesta] = []
    for c in comprobantes:
        p = Propuesta(c=c)
        props.append(p)
        if c.error:
            p.estado = 'excluido' if 'No es un comprobante UBL' in c.error else 'error'
            p.motivo = c.error
            continue
        # ---- 1. exclusiones ----
        if c.ruc_emisor in RUCS_BANCOS or c.tipo_codigo == '30':
            p.estado = 'excluido'
            p.motivo = f'Banco / entidad financiera ({RUCS_BANCOS.get(c.ruc_emisor, "documento tipo 30")})'
            if ctx.excluir_bancos:
                continue
            p.estado = 'ok'
        if c.tipo_codigo not in TIPOS_COMPRA:
            p.estado, p.motivo = 'excluido', f'No es comprobante de compra ({c.tipo_nombre})'
            continue
        if ctx.periodo and c.fecha_emision[:7] != ctx.periodo:
            p.estado, p.motivo = 'excluido', f'Fuera del periodo {ctx.periodo} (emitida el {c.fecha_emision})'
            continue
        if p.id in vistos:
            p.estado, p.motivo = 'duplicado', 'Mismo RUC + serie-número ya procesado en este lote'
            continue
        vistos.add(p.id)

        p.glosa = _glosa(c)
        no_gasto = pcge.motivo_no_gasto(c.nombre_emisor, texto_items(c))
        if no_gasto:
            p.estado, p.confianza = 'revisar', 0
            p.alertas.append(no_gasto)
            p.explicacion = 'No parece una compra de bienes/servicios. Cuenta en blanco a propósito.'
            continue

        # ---- 2. concepto ----
        fam, mezcla, expl, fuerza = determinar_concepto(c, ctx)
        p.familia, p.familia_nombre, p.concepto, p.mezcla = fam['prefijo'], fam['nombre'], fam['prefijo'], mezcla
        p.explicacion = expl
        if len(mezcla) > 1 and mezcla[1][1] >= 20:
            det = ' / '.join(f'{pcge.familia_por_prefijo(pr)["nombre"] if pcge.familia_por_prefijo(pr) else pr} {pc:.0f}%' for pr, pc in mezcla[:3])
            p.alertas.append(f'Factura mixta: {det}. Se usa una sola cuenta (la de mayor importe).')

        # ---- 3. memoria proveedor + concepto ----
        memo = ctx.memoria_proveedor(c.ruc_emisor) if ctx.memoria_proveedor else []
        memo_ok = [m for m in memo if m['concepto'] == p.concepto and (not ctx.plan or ctx.plan.existe(m['cuenta']))]
        memo_otro = [m for m in memo if m['concepto'] != p.concepto and (not ctx.plan or ctx.plan.existe(m['cuenta']))]

        if memo_ok:
            m = memo_ok[0]
            p.cuenta, p.fuente = m['cuenta'], 'memoria'
            p.confianza = min(99, 92 + min(m['veces'], 7))
            p.explicacion = f'Proveedor + concepto "{p.familia_nombre}" ya contabilizado {m["veces"]} vez/veces en {m["cuenta"]}. {expl}.'
        elif memo_otro and fuerza <= 1:
            # la descripción no dio pista fuerte: manda lo que se hizo antes con este proveedor
            m = memo_otro[0]
            p.cuenta, p.fuente = m['cuenta'], 'memoria'
            p.confianza = 82 if fuerza == 0 else 78
            p.explicacion = f'Sin palabra clave clara; este proveedor se contabilizó {m["veces"]} vez/veces en {m["cuenta"]} (otro concepto). {expl}.'
            f2 = pcge.familia_por_prefijo(m['cuenta'])
            if f2:
                p.familia, p.familia_nombre, p.concepto = f2['prefijo'], f2['nombre'], f2['prefijo']
        else:
            # ---- 4. plan de cuentas ----
            p.candidatas = candidatas_para(p.familia, ctx)
            cu, razon = elegir_candidata(p.candidatas, ctx, pcge.familia_por_prefijo(p.familia), texto_items(c))
            # La práctica de la empresa manda sobre la teoría: si a este proveedor ya se le contabilizó varias veces
            # en una cuenta que la empresa sí usa, y la cuenta "de manual" nunca la ha usado, preferimos la memoria.
            if memo_otro and cu and not ctx.historial_stats.get(cu.codigo) and memo_otro[0]['veces'] >= 2:
                m = memo_otro[0]
                p.cuenta, p.fuente = m['cuenta'], 'memoria'
                p.confianza = min(96, 88 + min(m['veces'], 8))
                p.explicacion = f'{expl}; pero este proveedor ya fue contabilizado {m["veces"]} veces en {m["cuenta"]} y la empresa nunca usa {cu.codigo}.'
                f2 = pcge.familia_por_prefijo(m['cuenta'])
                if f2:
                    p.familia, p.familia_nombre, p.concepto = f2['prefijo'], f2['nombre'], f2['prefijo']
                cu = None
            if p.cuenta and p.fuente == 'memoria':
                pass
            elif cu:
                p.cuenta, p.fuente = cu.codigo, 'historial' if ctx.historial_stats.get(cu.codigo) else 'reglas'
                base = {3: 88, 2: 84, 1: 72, 0: 55}[fuerza]
                if fuerza == 3 and len(mezcla) == 1:
                    base = 90
                if ctx.historial_stats.get(cu.codigo):
                    base += 6
                if len(p.candidatas) == 1:
                    base += 3
                if memo_otro:
                    base -= 8
                    p.alertas.append(f'Este proveedor antes se contabilizó en {memo_otro[0]["cuenta"]} ({memo_otro[0]["veces"]}x); hoy la descripción sugiere otra familia.')
                p.confianza = max(30, min(94, base))
                p.explicacion = f'{expl}; {razon}.'
            elif ctx.plan:
                p.estado = 'revisar'
                p.confianza = 0
                p.explicacion = f'{expl}, pero el plan de cuentas no tiene ninguna cuenta bajo {p.familia}.'
                p.alertas.append(f'Sin cuenta en el plan para la familia {p.familia} ({p.familia_nombre}). Asignar manualmente.')
            else:
                p.cuenta, p.fuente, p.confianza = p.familia, 'defecto', 40
                p.explicacion = f'{expl}. Sin plan de cuentas cargado: se propone la familia PCGE {p.familia}.'

        # ---- 5. IA solo si hay duda ----
        if ctx.ia and p.confianza < ctx.umbral_ia and p.estado != 'revisar':
            try:
                res = ctx.ia(p, ctx)
            except Exception as ex:   # la IA nunca rompe el flujo
                res = None
                p.alertas.append(f'IA no disponible: {str(ex)[:80]}')
            if res:
                cuenta_ia, conf_ia, razon_ia = res
                if cuenta_ia and (not ctx.plan or ctx.plan.existe(cuenta_ia)):
                    if cuenta_ia != p.cuenta:
                        p.explicacion += f' IA: {razon_ia} (reglas proponían {p.cuenta}).'
                    else:
                        p.explicacion += f' IA confirma: {razon_ia}.'
                    p.cuenta, p.fuente = cuenta_ia, 'ia'
                    p.confianza = max(p.confianza, min(int(conf_ia), 96))
                    f2 = pcge.familia_por_prefijo(cuenta_ia)
                    if f2:
                        p.familia, p.familia_nombre, p.concepto = f2['prefijo'], f2['nombre'], f2['prefijo']

        if ctx.plan and p.cuenta:
            cu = ctx.plan.get(p.cuenta)
            p.cuenta_desc = cu.descripcion if cu else ''
        p.av = pcge.av_por_cuenta(p.cuenta) if p.cuenta else fam['av']

        # ---- tipo de cambio (para TODAS las operaciones, soles y dólares) ----
        t, exacto = ctx.tc.buscar(c.fecha_emision) if (ctx.tc and c.fecha_emision) else (None, False)
        if t:
            p.tc, p.tc_exacto = t.venta, exacto
            if not exacto and c.moneda_codigo != 'PEN':
                p.alertas.append(f'TC del {t.fecha:%d/%m/%Y} (último publicado antes del {c.fecha_emision[8:10]}/{c.fecha_emision[5:7]}).')
        elif c.moneda_codigo != 'PEN':
            p.alertas.append(f'Sin tipo de cambio para {c.fecha_emision}: cargue el PDF SUNAT del mes.')
            p.estado = 'revisar'
        else:
            p.alertas.append(f'Sin tipo de cambio para {c.fecha_emision} (columna W quedará en blanco). Cargue el PDF SUNAT del mes.')

        # ---- sospecha de activo fijo ----
        tc_val = p.tc or 1.0
        for l in c.lineas:
            imp_linea = float(l.valor_venta + l.igv) * (tc_val if c.moneda_codigo != 'PEN' else 1.0)
            d = ' ' + l.descripcion.upper() + ' '
            if imp_linea >= ctx.umbral_activo and any(k in d for k in pcge.KW_ACTIVO_FIJO):
                p.posible_activo = True
                p.alertas.append(f'Posible ACTIVO FIJO: "{l.descripcion[:50]}" S/ {imp_linea:,.2f} (≥ S/ {ctx.umbral_activo:,.0f}). Validar cuenta {p.cuenta or ""} y registrar en el módulo de activos.')
                break
        if not p.posible_activo and p.cuenta.startswith(('33', '34')):
            p.posible_activo = True
            p.alertas.append('Cuenta de activo fijo propuesta: registrar también en el módulo de activos.')

        # ---- alertas de negocio ----
        total_pen = float(c.importe_total) * (p.tc or 1.0)
        if total_pen >= ctx.alerta_monto:
            p.alertas.append(f'Importe mayor a S/ {ctx.alerta_monto:,.0f} (S/ {total_pen:,.2f}).')
        if c.tiene_detraccion:
            p.alertas.append(f'Sujeta a detracción {c.detraccion_porcentaje}% (S/ {c.detraccion_monto}). Falta N° y fecha de constancia de depósito (no viene en el XML).')
        if c.tiene_percepcion:
            p.alertas.append(f'Con percepción S/ {c.percepcion_monto}.')
        if c.tipo_codigo in ('07', '08'):
            p.alertas.append(f'{c.tipo_nombre.title()} que modifica {c.doc_referencia or "(sin referencia)"}: {c.motivo_referencia or ""}'.strip())
        if not c.igv and (c.exoneradas or c.inafectas):
            p.alertas.append('Operación exonerada/inafecta (sin IGV).')
        if not c.lineas:
            p.alertas.append('El XML no trae detalle de ítems.')
        if c.doc_cliente and ctx.plan and ctx.plan.ruc and c.doc_cliente != ctx.plan.ruc:
            p.alertas.append(f'El comprobante está emitido a RUC {c.doc_cliente}, distinto al de la empresa.')

        if p.estado == 'ok' and p.confianza < AMARILLO:
            p.estado = 'revisar'
    return props


def resumen(props: list[Propuesta]) -> dict:
    r = dict(total=len(props), ok=0, revisar=0, excluidos=0, duplicados=0, errores=0, verde=0, amarillo=0, rojo=0, con_alertas=0)
    for p in props:
        k = {'ok': 'ok', 'revisar': 'revisar', 'excluido': 'excluidos', 'duplicado': 'duplicados', 'error': 'errores'}[p.estado]
        r[k] += 1
        if p.estado in ('ok', 'revisar'):
            r[{'🟢': 'verde', '🟡': 'amarillo', '🔴': 'rojo'}[p.semaforo]] += 1
            if p.alertas:
                r['con_alertas'] += 1
    return r
