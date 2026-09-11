# -*- coding: utf-8 -*-
"""
Propuesta Contable de Compras — interfaz Streamlit (una sola pantalla).

    streamlit run app.py

Toda la lógica vive en `motor/`; este archivo solo dibuja la pantalla.
"""
from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import streamlit as st

from motor import __version__
from motor.servicio import Servicio

st.set_page_config(page_title='Propuesta Contable de Compras', page_icon='📊', layout='wide')

# ----------------------------------------------------------------------------- estilo
st.markdown("""
<style>
  .block-container {padding-top: 1.6rem; max-width: 1400px;}
  h1 {font-weight: 700; letter-spacing: -0.02em;}
  .stMetric {background: #f7f7f9; border-radius: 12px; padding: 10px 14px;}
  div[data-testid="stFileUploader"] {border-radius: 12px;}
  .paso {font-size: 0.8rem; color: #6b7280; text-transform: uppercase; letter-spacing: .08em; margin-top: .8rem;}
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------- servicio
def api_key() -> str | None:
    try:
        return st.secrets.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')
    except Exception:
        return os.environ.get('ANTHROPIC_API_KEY')


@st.cache_resource
def servicio() -> Servicio:
    ruta = None
    try:
        ruta = st.secrets.get('PROPUESTA_DB')
    except Exception:
        pass
    return Servicio(ruta_db=ruta or os.environ.get('PROPUESTA_DB'), api_key=api_key())


S = servicio()
ss = st.session_state
ss.setdefault('lote', None)
ss.setdefault('ruc', None)

# ----------------------------------------------------------------------------- barra lateral: empresa y datos maestros
with st.sidebar:
    st.markdown('### 🏢 Empresa')
    empresas = S.empresas()
    opciones = {f"{e['nombre']} · {e['ruc']}": e['ruc'] for e in empresas}
    etiquetas = ['➕ Nueva empresa'] + list(opciones)
    idx = 0
    if ss.ruc and ss.ruc in opciones.values():
        idx = 1 + list(opciones.values()).index(ss.ruc)
    sel = st.selectbox('Seleccione', etiquetas, index=idx, label_visibility='collapsed')

    if sel == '➕ Nueva empresa':
        with st.form('nueva'):
            ruc_n = st.text_input('RUC (11 dígitos)', max_chars=11)
            nom_n = st.text_input('Razón social')
            plan_n = st.file_uploader('Plan de cuentas (Excel de NewContaSis)', type=['xlsx', 'xls'])
            if st.form_submit_button('Crear empresa', type='primary'):
                if len(ruc_n.strip()) != 11 or not ruc_n.strip().isdigit():
                    st.error('El RUC debe tener 11 dígitos.')
                elif not nom_n.strip():
                    st.error('Indique la razón social.')
                else:
                    try:
                        plan = S.registrar_empresa(ruc_n.strip(), nom_n.strip().upper(), plan_n.read() if plan_n else None)
                        ss.ruc = ruc_n.strip()
                        ss.lote = None
                        st.success(f'Empresa creada' + (f' · plan con {len(plan.cuentas)} cuentas' if plan else ''))
                        st.rerun()
                    except Exception as ex:
                        st.error(f'No se pudo leer el plan: {ex}')
        ruc = None
    else:
        ruc = opciones[sel]
        if ss.ruc != ruc:
            ss.ruc, ss.lote = ruc, None
        emp = S.db.empresa(ruc)
        n_plan = S.db.plan_resumen(ruc)
        stats = S.db.historial_stats(ruc)
        memoria = S.db.memoria_completa(ruc)

        st.markdown('<div class="paso">Plan de cuentas</div>', unsafe_allow_html=True)
        if n_plan:
            st.success(f'✓ {n_plan} cuentas cargadas', icon=None)
        else:
            st.warning('Sin plan de cuentas: se propondrán familias PCGE genéricas.')
        with st.expander('Actualizar plan'):
            f = st.file_uploader('Excel del plan de cuentas', type=['xlsx', 'xls'], key='plan_up')
            if f and st.button('Guardar plan'):
                try:
                    plan = S.actualizar_plan(ruc, f.read())
                    st.success(f'Plan actualizado: {len(plan.cuentas)} cuentas.')
                    st.rerun()
                except Exception as ex:
                    st.error(str(ex))

        st.markdown('<div class="paso">Historial contable (opcional)</div>', unsafe_allow_html=True)
        if stats:
            st.success(f'✓ {sum(stats.values())} asientos · {len(stats)} cuentas distintas')
        else:
            st.caption('Sin historial. Funciona igual; con historial la primera propuesta es más precisa.')
        with st.expander('Agregar historial'):
            f = st.file_uploader('Diario analítico (Excel de NewContaSis) o tabla RUC + cuenta', type=['xlsx', 'xls'], key='hist_up')
            if f and st.button('Cargar historial'):
                try:
                    h = S.cargar_historial(ruc, f.read())
                    st.success(f'{len(h.asientos)} asientos leídos. Cuenta del haber habitual: {h.cuenta_haber_habitual or "-"}.')
                    st.rerun()
                except Exception as ex:
                    st.error(str(ex))

        st.markdown('<div class="paso">Memoria aprendida</div>', unsafe_allow_html=True)
        st.caption(f'{len(memoria)} reglas proveedor + concepto → cuenta')
        if memoria and st.button('Ver / limpiar memoria'):
            ss.ver_memoria = True

    st.markdown('<div class="paso">Tipo de cambio SUNAT</div>', unsafe_allow_html=True)
    meses = S.tc_meses()
    st.caption('Meses cargados: ' + (', '.join(meses[-6:]) if meses else 'ninguno'))
    f = st.file_uploader('PDF mensual de SUNAT (o Excel fecha/compra/venta)', type=['pdf', 'xlsx', 'csv'], key='tc_up')
    if f and st.button('Agregar al historial de TC'):
        try:
            n = S.cargar_tc_pdf(f.read()) if f.name.lower().endswith('.pdf') else S.cargar_tc_tabla(f.read())
            st.success(f'{n} días agregados.')
            st.rerun()
        except Exception as ex:
            st.error(str(ex))

    st.markdown('---')
    st.caption(f'v{__version__} · IA: {"Claude activo" if api_key() else "sin API key (solo reglas)"}')

# ----------------------------------------------------------------------------- pantalla principal
st.title('Propuesta Contable de Compras')
st.caption('Suba los XML de compras del mes y obtenga el Excel listo para importar en NewContaSis, con el asiento propuesto y un reporte de observaciones.')

if not ruc:
    st.info('Cree o seleccione una empresa en la barra lateral para comenzar.')
    st.stop()

emp = S.db.empresa(ruc)
plan = S.plan(ruc)

if ss.get('ver_memoria'):
    with st.expander('Memoria de la empresa (proveedor + concepto → cuenta)', expanded=True):
        dfm = pd.DataFrame(S.db.memoria_completa(ruc))
        if not dfm.empty:
            st.dataframe(dfm[['ruc_proveedor', 'concepto', 'cuenta', 'veces', 'origen', 'ultima']], use_container_width=True, hide_index=True)
        c1, c2 = st.columns(2)
        if c1.button('Cerrar'):
            ss.ver_memoria = False
            st.rerun()
        if c2.button('Borrar toda la memoria de esta empresa', type='secondary'):
            S.db.olvidar(ruc)
            ss.ver_memoria = False
            st.rerun()

# --- parámetros del lote
c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    st.markdown('<div class="paso">Cuenta del haber (contrapartida) para todo el lote</div>', unsafe_allow_html=True)
    cuenta_haber = st.text_input('Cuenta del haber', value=emp['cuenta_haber'] or '4212', label_visibility='collapsed',
                                 help='Escriba cualquier cuenta. Sugerencias: 4212 Facturas por pagar · 1011 Caja · 104101 Banco cta. cte.').strip()
    sugeridas = ['4212', '1011', '104101', '1041']
    if plan:
        cu = plan.get(cuenta_haber)
        if cu:
            st.caption(f'✓ {cu.etiqueta}')
        elif cuenta_haber:
            st.warning(f'⚠ La cuenta {cuenta_haber} no existe en el plan de la empresa. Puede continuar bajo su responsabilidad.')
            for c in plan.buscar(cuenta_haber, 5):
                st.caption(f'   ¿Quiso decir {c.etiqueta}?')
    else:
        st.caption('Sugeridas: ' + ' · '.join(sugeridas))
with c2:
    st.markdown('<div class="paso">Alertar importes desde</div>', unsafe_allow_html=True)
    alerta_monto = st.number_input('S/', min_value=0.0, value=float(emp['alerta_monto'] or 20000), step=1000.0, label_visibility='collapsed')
with c3:
    st.markdown('<div class="paso">Opciones</div>', unsafe_allow_html=True)
    excluir_bancos = st.checkbox('Excluir comprobantes bancarios', value=True)
    usar_ia = st.checkbox('Usar IA en casos dudosos', value=bool(api_key()), disabled=not api_key())

if (cuenta_haber != emp['cuenta_haber'] or alerta_monto != emp['alerta_monto']) and cuenta_haber:
    S.db.guardar_empresa(ruc, emp['nombre'], cuenta_haber, alerta_monto)

st.markdown('<div class="paso">XML del mes</div>', unsafe_allow_html=True)
archivos = st.file_uploader('Arrastre los XML o un ZIP', type=['xml', 'zip'], accept_multiple_files=True, label_visibility='collapsed')

if st.button('GENERAR PROPUESTA', type='primary', disabled=not archivos, use_container_width=True):
    with st.spinner('Leyendo XML y proponiendo cuentas…'):
        try:
            ss.lote = S.procesar(ruc, [(f.name, f.getvalue()) for f in archivos], cuenta_haber=cuenta_haber,
                                 usar_ia=usar_ia, excluir_bancos=excluir_bancos, alerta_monto=alerta_monto)
            ss.confirmado = False
        except Exception as ex:
            st.error(f'No se pudo procesar: {ex}')

lote = ss.lote
if not lote:
    st.stop()

# ----------------------------------------------------------------------------- resultados
r = lote.resumen
st.markdown('---')
st.subheader(f'{lote.empresa} · periodo {lote.periodo}')
m = st.columns(6)
m[0].metric('XML recibidos', r['total'])
m[1].metric('Contabilizados', r['ok'] + r['revisar'])
m[2].metric('🟢 Alta confianza', r['verde'])
m[3].metric('🟡 Revisar rápido', r['amarillo'])
m[4].metric('🔴 Revisión obligatoria', r['rojo'])
m[5].metric('Excluidos / dup.', r['excluidos'] + r['duplicados'] + r['errores'])

st.markdown('<div class="paso">Revise y corrija la cuenta directamente en la tabla (doble clic en la celda "Cuenta")</div>', unsafe_allow_html=True)

filtro = st.radio('Mostrar', ['Todos', 'Solo con observaciones', 'Solo 🔴/🟡', 'Excluidos'], horizontal=True, label_visibility='collapsed')


def _fila(p):
    c = p.c
    return {'id': p.id, '': p.semaforo, 'Conf.': p.confianza if p.estado in ('ok', 'revisar') else None, 'Fecha': c.fecha_emision,
            'Comprobante': c.serie_numero, 'Proveedor': c.nombre_emisor[:45], 'Mon.': c.moneda_codigo, 'Total': float(c.importe_total),
            'Descripción': (c.lineas[0].descripcion[:60] + (' …' if len(c.lineas) > 1 else '')) if c.lineas else '',
            'Cuenta': p.cuenta, 'Cuenta (descripción)': p.cuenta_desc[:45], 'Fuente': p.fuente,
            'Alertas': ' | '.join(p.alertas) if p.alertas else (p.motivo if p.estado in ('excluido', 'duplicado', 'error') else ''),
            'Por qué': p.explicacion}


props = lote.propuestas
if filtro == 'Solo con observaciones':
    props = [p for p in props if p.alertas or p.estado == 'revisar']
elif filtro == 'Solo 🔴/🟡':
    props = [p for p in props if p.semaforo in ('🔴', '🟡')]
elif filtro == 'Excluidos':
    props = [p for p in props if p.estado in ('excluido', 'duplicado', 'error')]

df = pd.DataFrame([_fila(p) for p in props])
if df.empty:
    st.info('Nada que mostrar con este filtro.')
else:
    editado = st.data_editor(
        df, hide_index=True, use_container_width=True, height=min(600, 60 + 35 * len(df)),
        column_config={
            'id': None,
            '': st.column_config.TextColumn('', width='small'),
            'Conf.': st.column_config.NumberColumn('Conf. %', width='small'),
            'Total': st.column_config.NumberColumn('Total', format='%.2f'),
            'Cuenta': st.column_config.TextColumn('Cuenta ✏️', help='Escriba la cuenta correcta; el sistema la recordará para este proveedor.'),
            'Alertas': st.column_config.TextColumn('Alertas', width='large'),
            'Por qué': st.column_config.TextColumn('Por qué', width='large'),
        },
        disabled=[c for c in df.columns if c != 'Cuenta'], key=f'editor_{filtro}_{lote.generado.timestamp()}')

    cambios = 0
    for _, row in editado.iterrows():
        p = lote.por_id(row['id'])
        nueva = str(row['Cuenta'] or '').strip()
        if p and nueva != (p.cuenta or ''):
            if plan and nueva and not plan.existe(nueva):
                st.warning(f'{p.c.serie_numero}: la cuenta {nueva} no existe en el plan. Se aplica igual, revise.')
            S.aplicar_correccion(lote, row['id'], nueva)
            cambios += 1
    if cambios:
        st.success(f'{cambios} cuenta(s) corregida(s) y aprendida(s) para la próxima vez.')
        st.rerun()

    # ayuda para buscar cuentas del plan
    if plan:
        with st.expander('🔎 Buscar cuenta en el plan de la empresa'):
            q = st.text_input('Código o palabras de la descripción', placeholder='ej. combustible, 6371, mantenimiento')
            if q:
                for c in plan.buscar(q, 15):
                    st.write(f'`{c.codigo}` {c.descripcion}')

# ----------------------------------------------------------------------------- descargas
st.markdown('<div class="paso">Descargar</div>', unsafe_allow_html=True)
if not ss.get('confirmado'):
    S.confirmar_lote(lote)
    ss.confirmado = True
tag = f'{lote.ruc}_{lote.periodo}'
d1, d2, d3, d4 = st.columns(4)
d1.download_button('📥 Excel NewContaSis (importar)', lote.excel_importacion(), f'NEWCONTASIS_COMPRAS_{tag}.xlsx',
                   'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True, type='primary')
d2.download_button('📋 Excel de revisión', lote.excel_revision(), f'REVISION_{tag}.xlsx',
                   'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)
d3.download_button('📝 Reporte de observaciones (.txt)', lote.reporte_txt(), f'REPORTE_REVISION_{tag}.txt', 'text/plain', use_container_width=True)
d4.download_button('🗜 Todo en ZIP', lote.zip_todo(), f'PROPUESTA_{tag}.zip', 'application/zip', use_container_width=True)

with st.expander('Ver reporte de observaciones'):
    st.code(lote.reporte_txt(), language=None)
