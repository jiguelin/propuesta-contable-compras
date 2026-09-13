# -*- coding: utf-8 -*-
"""
motor/servicio.py — Orquestador: lo que la app (y la línea de comandos) llaman.

    from motor.servicio import Servicio
    s = Servicio()                                   # abre/crea la base de datos
    s.registrar_empresa('20611889683', 'ALQUMIN EIRL', plan_xlsx=bytes)
    s.cargar_tc_pdf(bytes)                           # cada mes
    lote = s.procesar('20611889683', archivos=[(nombre, bytes), ...], cuenta_haber='4212')
    lote.excel_importacion(), lote.excel_revision(), lote.reporte_txt()
    s.aplicar_correccion(lote, id_propuesta, '6343094')   # aprende
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime

from . import pcge, reglas as kb
from .clasificador import Contexto, Propuesta, procesar_lote, resumen
from .detracciones import Constancia, cruzar, leer_constancias
from .excel_newcontasis import generar_excel_importacion, generar_excel_revision
from .historial import ResumenHistorial, leer_historial_excel
from .ia import crear_ia
from .memoria import Memoria
from .plan_cuentas import PlanCuentas, leer_plan_excel
from .reporte import generar_reporte_txt
from .tipo_cambio import leer_pdf_sunat, leer_tabla
from .xml_parser import Comprobante, parse_xml_bytes


def extraer_xml(archivos: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """Acepta .xml sueltos y .zip (con carpetas); devuelve [(nombre, bytes)] solo de XML."""
    out = []
    for nombre, data in archivos:
        low = nombre.lower()
        if low.endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for n in z.namelist():
                    if n.lower().endswith('.xml') and not n.startswith('__MACOSX'):
                        out.append((n.split('/')[-1], z.read(n)))
        elif low.endswith('.xml'):
            out.append((nombre, data))
    return out


@dataclass
class Lote:
    ruc: str
    empresa: str
    periodo: str
    cuenta_haber: str
    propuestas: list[Propuesta]
    alerta_monto: float
    tc_meses: list[str] = field(default_factory=list)
    generado: datetime = field(default_factory=datetime.now)
    usd_en_soles: bool = True
    constancias_sin_factura: list = field(default_factory=list)
    n_constancias: int = 0

    @property
    def resumen(self) -> dict:
        return resumen(self.propuestas)

    def por_id(self, pid: str) -> Propuesta | None:
        return next((p for p in self.propuestas if p.id == pid), None)

    def excel_importacion(self, con_cabecera: bool = False) -> bytes:
        return generar_excel_importacion(self.propuestas, self.cuenta_haber, con_cabecera=con_cabecera, usd_en_soles=self.usd_en_soles)

    def excel_revision(self) -> bytes:
        return generar_excel_revision(self.propuestas, self.cuenta_haber, self.empresa, self.periodo, usd_en_soles=self.usd_en_soles)

    def reporte_txt(self) -> str:
        return generar_reporte_txt(self.propuestas, self.empresa, self.ruc, self.periodo, self.cuenta_haber, self.alerta_monto, self.tc_meses, self.constancias_sin_factura, self.n_constancias)

    def zip_todo(self) -> bytes:
        buf = io.BytesIO()
        tag = f'{self.ruc}_{self.periodo}'.replace('/', '-').replace(' ', '_')
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr(f'NEWCONTASIS_COMPRAS_{tag}.xlsx', self.excel_importacion())
            z.writestr(f'REVISION_{tag}.xlsx', self.excel_revision())
            z.writestr(f'REPORTE_REVISION_{tag}.txt', self.reporte_txt())
        return buf.getvalue()


class Servicio:
    def __init__(self, ruta_db: str | None = None, api_key: str | None = None):
        self.db = Memoria(ruta_db)
        self.api_key = api_key

    # ---------- empresas ----------
    def empresas(self) -> list[dict]:
        return self.db.empresas()

    def registrar_empresa(self, ruc: str, nombre: str, plan_xlsx: bytes | None = None, cuenta_haber: str = '4212', alerta_monto: float = 20000) -> PlanCuentas | None:
        self.db.guardar_empresa(ruc, nombre, cuenta_haber, alerta_monto)
        if plan_xlsx:
            return self.actualizar_plan(ruc, plan_xlsx)
        return None

    def actualizar_plan(self, ruc: str, plan_xlsx: bytes) -> PlanCuentas:
        plan = leer_plan_excel(plan_xlsx)
        if not plan.cuentas:
            raise ValueError('No encontré cuentas en el archivo. Se espera el Excel "Plan de cuentas" exportado de NewContaSis (columnas CUENTA / DESCRIPCION).')
        self.db.guardar_plan(ruc, plan)
        return plan

    def plan(self, ruc: str) -> PlanCuentas | None:
        return self.db.plan(ruc)

    # ---------- tipo de cambio ----------
    def cargar_tc_pdf(self, data: bytes) -> int:
        return self.db.guardar_tc(leer_pdf_sunat(data))

    def cargar_tc_varios(self, archivos: list[tuple[str, bytes]]) -> tuple[int, list[str]]:
        """Varios PDF/Excel de golpe. Devuelve (días agregados, errores)."""
        n, errores = 0, []
        for nombre, data in archivos:
            try:
                n += self.cargar_tc_pdf(data) if nombre.lower().endswith('.pdf') else self.cargar_tc_tabla(data)
            except Exception as ex:
                errores.append(f'{nombre}: {ex}')
        return n, errores

    def cargar_tc_tabla(self, data: bytes) -> int:
        return self.db.guardar_tc(leer_tabla(data))

    def tc_meses(self) -> list[str]:
        return self.db.tc().meses_cargados()

    # ---------- historial opcional ----------
    def cargar_historial(self, ruc: str, data: bytes) -> ResumenHistorial:
        h = leer_historial_excel(data)
        self.db.guardar_historial_stats(ruc, dict(h.frecuencia_cuentas), h.descripciones)
        bloqueadas = set()
        for ruc_prov, cnt in h.por_proveedor.items():
            for cuenta, n in cnt.items():
                if kb.cuenta_bloqueada(cuenta, self.db.reglas(ruc)):
                    bloqueadas.add(cuenta)
                    continue
                fam = pcge.familia_por_prefijo(cuenta)
                self.db.aprender(ruc, ruc_prov, fam['prefijo'] if fam else cuenta[:3], cuenta, origen='historial', veces=n)
        h.cuentas_bloqueadas = sorted(bloqueadas)
        if h.cuenta_haber_habitual:
            e = self.db.empresa(ruc)
            if e and e['cuenta_haber'] == '4212' and h.cuenta_haber_habitual != '4212':
                pass  # no cambiamos la preferencia automáticamente; la app la muestra como sugerencia
        return h

    # ---------- base de conocimiento (reglas) ----------
    def reglas(self, ruc: str | None = None) -> list:
        return self.db.reglas(ruc)

    def guardar_regla(self, regla) -> int:
        problema = kb.validar(regla)
        if problema:
            raise ValueError(problema)
        return self.db.guardar_regla(regla)

    def eliminar_regla(self, id_regla: int):
        self.db.eliminar_regla(id_regla)

    # ---------- procesamiento ----------
    @staticmethod
    def meses_en_archivos(archivos: list[tuple[str, bytes]]) -> dict[str, int]:
        """'YYYY-MM' → cantidad de comprobantes, para elegir el mes a trabajar antes de procesar."""
        from collections import Counter
        cnt = Counter()
        for n, b in extraer_xml(archivos):
            c = parse_xml_bytes(b, n)
            if not c.error and c.fecha_emision:
                cnt[c.fecha_emision[:7]] += 1
        return dict(sorted(cnt.items()))

    def procesar(self, ruc: str, archivos: list[tuple[str, bytes]], cuenta_haber: str | None = None, periodo: str = '',
                 usar_ia: bool = True, excluir_bancos: bool = True, alerta_monto: float | None = None, umbral_ia: int = 90,
                 constancias: list[tuple[str, bytes]] | None = None, usd_en_soles: bool = True, umbral_activo: float = 1800,
                 excluir_detraccion_sin_constancia: bool = True, glosa_ascii: bool = True) -> Lote:
        e = self.db.empresa(ruc) or {'nombre': ruc, 'cuenta_haber': '4212', 'alerta_monto': 20000}
        cuenta_haber = (cuenta_haber or e['cuenta_haber'] or '4212').strip()
        alerta_monto = alerta_monto if alerta_monto is not None else e['alerta_monto']
        plan = self.db.plan(ruc)
        ctx = Contexto(plan=plan, tc=self.db.tc(), memoria_proveedor=lambda rp: self.db.memoria_proveedor(ruc, rp),
                       historial_stats=self.db.historial_stats(ruc), cuenta_haber=cuenta_haber, alerta_monto=alerta_monto,
                       excluir_bancos=excluir_bancos, ia=crear_ia(self.api_key) if usar_ia else None, umbral_ia=umbral_ia,
                       reglas=self.db.reglas(ruc), glosa_ascii=glosa_ascii)
        comps = [parse_xml_bytes(b, n) for n, b in extraer_xml(archivos)]
        comps.sort(key=lambda c: (c.fecha_emision, c.serie_numero))
        if not periodo:   # mes con más comprobantes
            from collections import Counter
            cnt = Counter(c.fecha_emision[:7] for c in comps if c.fecha_emision)
            periodo = cnt.most_common(1)[0][0] if cnt else datetime.now().strftime('%Y-%m')
        ctx.periodo = periodo
        ctx.umbral_activo = umbral_activo
        props = procesar_lote(comps, ctx)
        lote = Lote(ruc=ruc, empresa=e['nombre'], periodo=periodo, cuenta_haber=cuenta_haber, propuestas=props,
                    alerta_monto=alerta_monto, tc_meses=ctx.tc.meses_cargados() if ctx.tc else [], usd_en_soles=usd_en_soles)
        if constancias:
            lista = leer_constancias(constancias)
            lote.n_constancias, lote.constancias_sin_factura = cruzar(props, lista)
        if excluir_detraccion_sin_constancia:
            # Regla tributaria: sin el depósito de la detracción no se puede usar el crédito fiscal → no entra al Excel.
            for p in props:
                if p.estado in ('ok', 'revisar') and p.c.tiene_detraccion and not p.det_constancia:
                    p.estado = 'excluido'
                    p.motivo = (f'Detracción {p.c.detraccion_porcentaje}% (S/ {p.c.detraccion_monto}) sin constancia de depósito: no se puede usar el IGV todavía. '
                                'Cuando tenga la constancia, vuelva a generar incluyéndola (o regístrela en el mes en que se pagó).')
                    p.alertas = [a for a in p.alertas if 'constancia' not in a.lower()]
        r = lote.resumen
        self.db.registrar_lote(ruc, periodo, r['total'], r['ok'], r['excluidos'], r['revisar'], r)
        return lote

    def aplicar_correccion(self, lote: Lote, pid: str, cuenta: str, aprender: bool = True) -> Propuesta | None:
        """Cambio manual de cuenta hecho por la persona. Queda en la memoria proveedor + concepto."""
        p = lote.por_id(pid)
        if not p:
            return None
        cuenta = (cuenta or '').strip()
        p.cuenta, p.fuente, p.confianza = cuenta, 'manual', 100
        plan = self.db.plan(lote.ruc)
        cu = plan.get(cuenta) if plan else None
        p.cuenta_desc = cu.descripcion if cu else ''
        p.av = pcge.av_por_cuenta(cuenta)
        if p.estado == 'revisar' and cuenta:
            p.estado = 'ok'
        bloqueo = kb.cuenta_bloqueada(cuenta, self.db.reglas(lote.ruc))
        if bloqueo:
            p.alertas = [a for a in p.alertas if 'bloqueada' not in a] + [
                f'ATENCIÓN: {cuenta} está bloqueada ({bloqueo.nombre}). {bloqueo.nota[:160]} '
                f'Se registró porque usted la escribió, pero no se guardará en la memoria.']
            aprender = False
        if aprender and cuenta and p.c.ruc_emisor:
            self.db.aprender(lote.ruc, p.c.ruc_emisor, p.concepto or (pcge.familia_por_prefijo(cuenta) or {}).get('prefijo', cuenta[:3]), cuenta, origen='correccion')
        return p

    def corregir_glosa(self, lote: Lote, pid: str, glosa: str, ascii_estricto: bool = True):
        """La persona editó la glosa en la tabla: se limpia igual que las automáticas y se da por buena."""
        from .texto import normalizar
        p = lote.por_id(pid)
        if not p:
            return None
        p.glosa, perdida = normalizar(glosa, ascii_estricto, 60)
        if not perdida:
            p.glosa_revisar = False
            p.alertas = [a for a in p.alertas if 'glosa' not in a.lower()]
        return p

    def confirmar_lote(self, lote: Lote):
        """Al descargar: todo lo aceptado sin cambios también refuerza la memoria (proveedor+concepto)."""
        for p in lote.propuestas:
            if p.estado == 'ok' and p.cuenta and p.c.ruc_emisor and p.fuente not in ('manual', 'regla') \
                    and not kb.cuenta_bloqueada(p.cuenta, self.db.reglas(lote.ruc)):
                self.db.aprender(lote.ruc, p.c.ruc_emisor, p.concepto, p.cuenta, origen='confirmado')
