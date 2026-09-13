# -*- coding: utf-8 -*-
"""
motor/xml_parser.py — Lector UBL 2.1 de comprobantes SUNAT.
Copia del parser probado del "Clasificador v2" (xml_facturas.py), sin la parte de PDF.
NO modificar el clasificador original: este módulo vive de forma independiente.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Optional

from lxml import etree

# ============================================================
# NAMESPACES UBL / SUNAT
# ============================================================
NS = {
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'sac': 'urn:sunat:names:specification:ubl:peru:schema:xsd:SunatAggregateComponents-1',
    'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
}
# Algunos emisores generan xmlns:schemaLocation inválidos; recover=True los tolera.
_PARSER = etree.XMLParser(recover=True, huge_tree=True, remove_blank_text=True)

# ============================================================
# CATÁLOGOS SUNAT
# ============================================================
TIPOS_DOC = {          # Catálogo 01
    '01': ('factura', 'FACTURA ELECTRÓNICA'),
    '03': ('boleta', 'BOLETA DE VENTA ELECTRÓNICA'),
    '07': ('nota_credito', 'NOTA DE CRÉDITO ELECTRÓNICA'),
    '08': ('nota_debito', 'NOTA DE DÉBITO ELECTRÓNICA'),
    '30': ('codigo_30', 'COMPROBANTE DE OPERACIONES - LEY 29972 / SERVICIOS FINANCIEROS'),
    '09': ('guia_remision', 'GUÍA DE REMISIÓN ELECTRÓNICA'),
}
MONEDAS = {'PEN': ('soles', 'S/'), 'USD': ('dolares', 'US$'), 'EUR': ('euros', '€')}
UNIDADES = {          # Catálogo 03 (las más comunes)
    'NIU': 'UNIDAD', 'ZZ': 'SERVICIO', 'BX': 'CAJA', 'PK': 'PAQUETE', 'CS': 'CAJA', 'EA': 'UNIDAD',
    'ST': 'HOJA', 'KGM': 'KILOGRAMO', 'GRM': 'GRAMO', 'LTR': 'LITRO', 'MTR': 'METRO', 'MTK': 'M2',
    'MTQ': 'M3', 'GLL': 'GALÓN', 'DZN': 'DOCENA', 'SET': 'JUEGO', 'BG': 'BOLSA', 'BO': 'BOTELLA',
    'CT': 'CARTÓN', 'PR': 'PAR', 'RO': 'ROLLO', 'TNE': 'TONELADA', 'HUR': 'HORA', 'DAY': 'DÍA',
    'MON': 'MES', 'ANN': 'AÑO', 'NMP': 'PACK', 'MIL': 'MILLAR', 'GLI': 'GALÓN UK',
}
LEYENDAS = {          # Catálogo 52
    '1000': None,   # monto en letras (se muestra aparte)
    '1002': 'TRANSFERENCIA GRATUITA DE UN BIEN Y/O SERVICIO PRESTADO GRATUITAMENTE',
    '2000': 'COMPROBANTE DE PERCEPCIÓN',
    '2001': 'BIENES TRANSFERIDOS EN LA AMAZONÍA REGIÓN SELVA PARA SER CONSUMIDOS EN LA MISMA',
    '2002': 'SERVICIOS PRESTADOS EN LA AMAZONÍA REGIÓN SELVA PARA SER CONSUMIDOS EN LA MISMA',
    '2003': 'CONTRATOS DE CONSTRUCCIÓN EJECUTADOS EN LA AMAZONÍA REGIÓN SELVA',
    '2004': 'AGENCIA DE VIAJE - PAQUETE TURÍSTICO',
    '2005': 'VENTA REALIZADA POR EMISOR ITINERANTE',
    '2006': 'OPERACIÓN SUJETA AL SISTEMA DE PAGO DE OBLIGACIONES TRIBUTARIAS CON EL GOBIERNO CENTRAL',
    '2007': 'OPERACIÓN SUJETA AL IVAP',
    '2008': 'VENTA EXONERADA DEL IGV-ISC-IPM. PROHIBIDA LA VENTA FUERA DE LA ZONA COMERCIAL DE TACNA',
}
BIENES_SERVICIOS_DETRACCION = {   # Catálogo 54 (resumen)
    '001': 'Azúcar y melaza de caña', '003': 'Alcohol etílico', '004': 'Recursos hidrobiológicos',
    '005': 'Maíz amarillo duro', '007': 'Caña de azúcar', '008': 'Madera', '009': 'Arena y piedra',
    '010': 'Residuos, subproductos, desechos', '011': 'Bienes gravados con IGV por renuncia a exoneración',
    '012': 'Intermediación laboral y tercerización', '013': 'Animales vivos', '014': 'Carnes y despojos',
    '015': 'Abonos, cueros y pieles', '016': 'Aceite de pescado', '017': 'Harina de pescado',
    '019': 'Arrendamiento de bienes', '020': 'Mantenimiento y reparación de bienes muebles',
    '021': 'Movimiento de carga', '022': 'Otros servicios empresariales', '023': 'Leche',
    '024': 'Comisión mercantil', '025': 'Fabricación de bienes por encargo', '026': 'Servicio de transporte de personas',
    '027': 'Servicio de transporte de carga', '028': 'Transporte de pasajeros', '030': 'Contratos de construcción',
    '031': 'Oro gravado con IGV', '034': 'Minerales metálicos no auríferos', '035': 'Bienes exonerados del IGV',
    '036': 'Oro y demás minerales metálicos exonerados', '037': 'Demás servicios gravados con IGV',
    '039': 'Minerales no metálicos', '040': 'Bien inmueble gravado con IGV', '041': 'Plomo',
}
MEDIOS_PAGO_DETRACCION = {'001': 'Depósito en cuenta', '002': 'Giro', '003': 'Transferencia de fondos', '004': 'Orden de pago', '005': 'Tarjeta de débito', '006': 'Tarjeta de crédito', '008': 'Efectivo', '011': 'Tarjeta de crédito no bancaria', '999': 'Otros'}

# ============================================================
# LISTAS DE RUCs CONOCIDOS  ←  ÚNICO LUGAR DONDE SE AGREGAN RUCs
# app.py importa estas listas, así que sirven para imágenes, PDF y XML.
# Para agregar uno: copia una línea y cambia RUC y nombre, ej.
#     '20601234567': 'La Lucha Sangucheria',
# ============================================================
RUCS_BANCOS = {
    '20100047218': 'BCP', '20100130204': 'BBVA', '20354766437': 'Interbank', '20100053455': 'Interbank',
    '20522108720': 'Scotiabank', '20258702832': 'BanBif', '20451844326': 'Pichincha', '20100105862': 'Banco de la Nacion',
    '20100043140': 'Scotiabank',
}
RUCS_COMBUSTIBLE = {
    '20258092133': 'Repsol', '20100128056': 'Primax', '20330291017': 'Petroperu', '20543298922': 'Petrogas', '20511995028': 'Terpel Peru',
}
RUCS_RESTAURANTES = {
    '20509828235': 'KFC', '20268571286': 'McDonalds', '20505101688': 'Starbucks', '20388829452': 'Pizza Hut',
    '20424024268': 'Bembos', '20613563700': 'Pardos Chicken', '20563571498': 'Norkys', '20607085600': 'Popeyes',
    '20602122779': 'Little Caesars Pizza', '20600193342': 'EHJ Inversiones (Consumo)', '20100315751': 'Haiti Miraflores',
    '20386489263': 'Inversiones Reixa - Delicass', '20603010524': 'Tere Stabile', '10078403816': 'Zavaleta Zavaleta Rosa Cerolinda (Restaurante)',
    '20127765279': 'Coesti S.A. (Tienda Conveniencia Primax)', '20521370042': 'Eterno Retorno SAC', '20537230399': 'Inversiones SAP - Don Tito',
    '20553689962': 'Taller 109 SRL (Heladeria)',
}
RUCS_SEGUROS = {'20504262242': 'Rimac', '20552083401': 'Pacifico Seguros', '20608644467': 'La Positiva', '20100036773': 'Mapfre'}
RUCS_SERVICIOS_PUBLICOS = {'20331898008': 'Luz del Sur', '20467534026': 'Claro', '20106253251': 'Movistar', '20602235914': 'Entel', '20100167628': 'Sedapal'}
RUCS_BIENES = {'20512002090': 'Mifarma', '20100579228': 'Pareja Lecaros', '20602457029': 'Rigodent / Medical Dental', '20601096022': 'Fresh Life'}
RUCS_SERVICIOS = {'20544547756': 'Despegar.com Peru'}

# Palabras clave para categoría por reglas (se evalúan sobre las descripciones de ítems)
_KW_COMBUSTIBLE = ('GASOHOL', 'DIESEL', 'GASOLINA', 'GLP', 'GNV', 'PETROLEO', 'COMBUSTIBLE', 'PEAJE', 'PREMIUM 9', 'REGULAR 9')
_KW_SEGURO = ('SEGURO', 'POLIZA', 'PÓLIZA', 'SCTR', 'EPS ', 'VIDA LEY', 'PRIMA ')
_KW_RESTAURANTE = ('MENU', 'MENÚ', 'ALMUERZO', 'CENA', 'DESAYUNO', 'LOMO SALTADO', 'CEVICHE', 'POLLO A LA BRASA', 'HAMBURGUESA', 'PIZZA',
                   'CHILCANO', 'PISCO SOUR', 'CAFE ', 'CAFÉ ', 'CAPPUCCINO', 'LATTE', 'SANDWICH', 'SÁNDWICH', 'CONSUMO', 'PLATO', 'ENTRADA', 'POSTRE', 'JUGO ')
_KW_SERVICIO = ('SERVICIO', 'ALQUILER', 'ARRENDAMIENTO', 'MANTENIMIENTO', 'CONSULTORIA', 'CONSULTORÍA', 'ASESORIA', 'ASESORÍA', 'HONORARIO',
                'TRANSPORTE', 'FLETE', 'INTERNET', 'PUBLICIDAD', 'LICENCIA', 'SUSCRIPCION', 'SUSCRIPCIÓN', 'HOSPEDAJE', 'ALOJAMIENTO', 'PASAJE',
                'COMISION', 'COMISIÓN', 'INSTALACION', 'INSTALACIÓN', 'REPARACION', 'REPARACIÓN', 'CAPACITACION', 'CAPACITACIÓN', 'SOPORTE',
                'HOSTING', 'DOMINIO', 'LIMPIEZA', 'SEGURIDAD', 'VIGILANCIA', 'CONTABLE', 'LABORAL', 'LEGAL', 'AUDITORIA', 'AUDITORÍA', 'MEMBRESIA',
                'MEMBRESÍA', 'CUOTA', 'ENVIO', 'ENVÍO', 'COURIER', 'DELIVERY', 'ESTACIONAMIENTO', 'PARQUEO', 'PLAN ', 'TASA')

NO_COMPROBANTE = {'guia_remision', 'nota_pedido', 'recibo_servicio', 'documento_autorizado', 'codigo_30', 'otro', 'recibo_honorarios'}


# ============================================================
# MODELO DE DATOS
# ============================================================
@dataclass
class Linea:
    nro: str = ''
    cantidad: Decimal = Decimal(0)
    unidad: str = ''
    codigo: str = ''
    descripcion: str = ''
    valor_unitario: Decimal = Decimal(0)   # sin IGV
    precio_unitario: Decimal = Decimal(0)  # con IGV (PricingReference 01)
    descuento: Decimal = Decimal(0)
    igv: Decimal = Decimal(0)
    isc: Decimal = Decimal(0)
    valor_venta: Decimal = Decimal(0)      # LineExtensionAmount
    afectacion: str = ''                   # Catálogo 07: 10 gravado, 20 exonerado, 30 inafecto...


@dataclass
class Comprobante:
    archivo: str = ''
    tipo_codigo: str = ''
    tipo_documento: str = 'otro'
    tipo_nombre: str = 'DOCUMENTO'
    tipo_operacion: str = ''
    serie_numero: str = ''
    fecha_emision: str = ''
    fecha_vencimiento: str = ''
    periodo: str = ''
    moneda_codigo: str = 'PEN'
    moneda: str = 'soles'
    simbolo: str = 'S/'
    # emisor
    ruc_emisor: str = ''
    nombre_emisor: str = ''
    nombre_comercial: str = ''
    direccion_emisor: str = ''
    # cliente
    tipo_doc_cliente: str = ''
    doc_cliente: str = ''
    nombre_cliente: str = ''
    direccion_cliente: str = ''
    # referencias
    orden_compra: str = ''
    doc_referencia: str = ''      # NC/ND: comprobante afectado
    motivo_referencia: str = ''
    guias: List[str] = field(default_factory=list)
    observaciones: List[str] = field(default_factory=list)
    # pago
    forma_pago: str = ''
    cuotas: List[dict] = field(default_factory=list)
    # totales
    gravadas: Decimal = Decimal(0)
    exoneradas: Decimal = Decimal(0)
    inafectas: Decimal = Decimal(0)
    gratuitas: Decimal = Decimal(0)
    exportacion: Decimal = Decimal(0)
    descuentos: Decimal = Decimal(0)
    otros_cargos: Decimal = Decimal(0)
    anticipos: Decimal = Decimal(0)
    igv: Decimal = Decimal(0)
    isc: Decimal = Decimal(0)
    icbper: Decimal = Decimal(0)
    otros_tributos: Decimal = Decimal(0)
    redondeo: Decimal = Decimal(0)
    valor_venta: Decimal = Decimal(0)
    importe_total: Decimal = Decimal(0)
    monto_letras: str = ''
    leyendas: List[str] = field(default_factory=list)
    # detracción / percepción / retención
    tiene_detraccion: bool = False
    detraccion_codigo: str = ''
    detraccion_porcentaje: Decimal = Decimal(0)
    detraccion_monto: Decimal = Decimal(0)
    detraccion_cuenta: str = ''
    detraccion_medio: str = ''
    tiene_percepcion: bool = False
    percepcion_monto: Decimal = Decimal(0)
    percepcion_porcentaje: Decimal = Decimal(0)
    percepcion_total: Decimal = Decimal(0)   # total incluida percepción
    tiene_retencion: bool = False
    retencion_monto: Decimal = Decimal(0)
    # ítems
    lineas: List[Linea] = field(default_factory=list)
    # clasificación
    categoria: Optional[str] = None
    razon: str = ''
    tiene_igv: bool = False
    # errores de parseo
    error: str = ''


# ============================================================
# HELPERS DE LECTURA
# ============================================================
def _d(v, default='0') -> Decimal:
    try:
        return Decimal(str(v).strip()) if v not in (None, '') else Decimal(default)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _txt(node, xp, default='') -> str:
    if node is None:
        return default
    r = node.xpath(xp, namespaces=NS)
    if not r:
        return default
    v = r[0] if isinstance(r[0], str) else (r[0].text or '')
    return ' '.join(v.split()) if v else default


def _all(node, xp):
    return node.xpath(xp, namespaces=NS) if node is not None else []


def _direccion(party):
    """Arma dirección legible desde cac:RegistrationAddress."""
    addr = _all(party, './/cac:RegistrationAddress')
    if not addr:
        return ''
    a = addr[0]
    partes = [_txt(a, './cac:AddressLine/cbc:Line'), _txt(a, './cbc:StreetName')]
    ubigeo = ' - '.join(p for p in (_txt(a, './cbc:District'), _txt(a, './cbc:CityName'), _txt(a, './cbc:CountrySubentity')) if p)
    partes.append(ubigeo)
    return ' '.join(p for p in partes if p).strip()


def fmt(v: Decimal, dec=2) -> str:
    try:
        q = Decimal(10) ** -dec
        return f"{Decimal(v).quantize(q):,.{dec}f}"
    except Exception:
        return str(v)


def fmt_qty(v: Decimal) -> str:
    """Cantidad: sin decimales innecesarios (30.000 → 30 ; 0.03333 → 0.03333)."""
    try:
        v = Decimal(v).normalize()
        s = f"{v:f}"
        return s if s != '-0' else '0'
    except Exception:
        return str(v)


# ============================================================
# 1. PARSEO UBL
# ============================================================
def parse_xml(path: Path) -> Comprobante:
    c = Comprobante(archivo=Path(path).name)
    try:
        root = etree.parse(str(path), _PARSER).getroot()
    except Exception as ex:
        c.error = f'XML ilegible: {ex}'
        return c
    if root is None:
        c.error = 'XML vacío o ilegible'
        return c

    raiz = etree.QName(root).localname
    if raiz not in ('Invoice', 'CreditNote', 'DebitNote'):
        c.error = f'No es un comprobante UBL (raíz {raiz}). Puede ser CDR, Retención, Percepción o Guía.'
        return c

    # --- Tipo / serie / fechas / moneda ---
    if raiz == 'Invoice':
        c.tipo_codigo = _txt(root, './cbc:InvoiceTypeCode', '01')
        c.tipo_operacion = _txt(root, './cbc:InvoiceTypeCode/@listID')
    elif raiz == 'CreditNote':
        c.tipo_codigo = '07'
    else:
        c.tipo_codigo = '08'
    c.tipo_documento, c.tipo_nombre = TIPOS_DOC.get(c.tipo_codigo, ('otro', f'DOCUMENTO TIPO {c.tipo_codigo}'))
    c.serie_numero = _txt(root, './cbc:ID')
    c.fecha_emision = _txt(root, './cbc:IssueDate')
    c.fecha_vencimiento = _txt(root, './cbc:DueDate')
    ini, fin = _txt(root, './cac:InvoicePeriod/cbc:StartDate'), _txt(root, './cac:InvoicePeriod/cbc:EndDate')
    if ini or fin:
        c.periodo = f'{_fecha(ini)} al {_fecha(fin)}'
    c.moneda_codigo = _txt(root, './cbc:DocumentCurrencyCode', 'PEN').upper()
    c.moneda, c.simbolo = MONEDAS.get(c.moneda_codigo, ('desconocido', c.moneda_codigo + ' '))

    # --- Emisor ---
    sup = _all(root, './cac:AccountingSupplierParty')
    sup = sup[0] if sup else None
    c.ruc_emisor = _txt(sup, './cac:Party/cac:PartyIdentification/cbc:ID') or _txt(sup, './cbc:CustomerAssignedAccountID')
    c.nombre_emisor = _txt(sup, './cac:Party/cac:PartyLegalEntity/cbc:RegistrationName') or _txt(sup, './cac:Party/cac:PartyName/cbc:Name')
    c.nombre_comercial = _txt(sup, './cac:Party/cac:PartyName/cbc:Name')
    if c.nombre_comercial.upper() == c.nombre_emisor.upper():
        c.nombre_comercial = ''
    c.direccion_emisor = _direccion(sup)

    # --- Cliente ---
    cus = _all(root, './cac:AccountingCustomerParty')
    cus = cus[0] if cus else None
    c.doc_cliente = _txt(cus, './cac:Party/cac:PartyIdentification/cbc:ID') or _txt(cus, './cbc:CustomerAssignedAccountID')
    c.tipo_doc_cliente = {'6': 'RUC', '1': 'DNI', '4': 'C.E.', '7': 'PASAPORTE', '0': 'DOC.'}.get(
        _txt(cus, './cac:Party/cac:PartyIdentification/cbc:ID/@schemeID'), 'RUC' if len(c.doc_cliente) == 11 else 'DOC.')
    c.nombre_cliente = _txt(cus, './cac:Party/cac:PartyLegalEntity/cbc:RegistrationName') or _txt(cus, './cac:Party/cac:PartyName/cbc:Name')
    c.direccion_cliente = _direccion(cus)

    # --- Referencias ---
    c.orden_compra = _txt(root, './cac:OrderReference/cbc:ID')
    for g in _all(root, './cac:DespatchDocumentReference/cbc:ID'):
        if g.text:
            c.guias.append(g.text.strip())
    if raiz in ('CreditNote', 'DebitNote'):
        c.doc_referencia = _txt(root, './cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID')
        c.motivo_referencia = _txt(root, './cac:DiscrepancyResponse/cbc:Description')
        if not c.tipo_operacion:
            c.tipo_operacion = _txt(root, './cac:DiscrepancyResponse/cbc:ResponseCode')

    # --- Notas / leyendas ---
    for n in _all(root, './cbc:Note'):
        code = n.get('languageLocaleID')
        text = ' '.join((n.text or '').split())
        if not text:
            continue
        if code == '1000':
            c.monto_letras = text
        elif code in LEYENDAS and code != '1000':
            c.leyendas.append(text)
        elif code:
            c.leyendas.append(text)
        else:
            c.observaciones.append(text)
    if not c.monto_letras and c.tipo_codigo == '01':
        pass  # algunos emisores no la incluyen; el PDF la omite

    # --- Forma de pago / cuotas / detracción / percepción ---
    for pt in _all(root, './cac:PaymentTerms'):
        pid = _txt(pt, './cbc:ID').upper()
        means = _txt(pt, './cbc:PaymentMeansID')
        if pid == 'FORMAPAGO':
            if means.upper().startswith('CUOTA'):
                c.cuotas.append({'cuota': means, 'monto': _d(_txt(pt, './cbc:Amount')), 'vence': _txt(pt, './cbc:PaymentDueDate')})
            elif means:
                c.forma_pago = means
        elif pid == 'DETRACCION':
            c.tiene_detraccion = True
            c.detraccion_codigo = means
            c.detraccion_porcentaje = _d(_txt(pt, './cbc:PaymentPercent'))
            if 0 < c.detraccion_porcentaje < 1:      # algunos emisores ponen 0.12 en vez de 12
                c.detraccion_porcentaje = c.detraccion_porcentaje * 100
            c.detraccion_monto = _d(_txt(pt, './cbc:Amount'))
        elif pid == 'PERCEPCION':
            c.tiene_percepcion = True
            c.percepcion_total = _d(_txt(pt, './cbc:Amount'))
        elif pid == 'RETENCION':
            c.tiene_retencion = True
            c.retencion_monto = _d(_txt(pt, './cbc:Amount'))
    for pm in _all(root, './cac:PaymentMeans'):
        cuenta = _txt(pm, './cac:PayeeFinancialAccount/cbc:ID')
        if cuenta:
            c.detraccion_cuenta = cuenta
            c.detraccion_medio = _txt(pm, './cbc:PaymentMeansCode')
    # Percepción / retención declaradas como cargo global (código 51/52/53 percepción, 62 retención)
    for ac in _all(root, './cac:AllowanceCharge'):
        es_cargo = _txt(ac, './cbc:ChargeIndicator').lower() == 'true'
        code = _txt(ac, './cbc:AllowanceChargeReasonCode')
        monto = _d(_txt(ac, './cbc:Amount'))
        factor = _d(_txt(ac, './cbc:MultiplierFactorNumeric'))
        if es_cargo and code in ('51', '52', '53'):
            c.tiene_percepcion = True
            c.percepcion_monto = monto
            c.percepcion_porcentaje = factor * 100 if factor < 1 else factor
        elif not es_cargo and code == '62':
            c.tiene_retencion = True
            c.retencion_monto = monto
        elif es_cargo and code in ('45', '46', '47', '48', '49', '50'):
            c.otros_cargos += monto
        elif not es_cargo and code in ('02', '03', '04', '05', '06'):
            c.descuentos += monto
    if c.tiene_percepcion and not c.percepcion_monto and c.percepcion_total:
        pass  # se calcula abajo cuando conozcamos el total
    # Leyenda 2006 → detracción aunque no haya PaymentTerms
    if any('OBLIGACIONES TRIBUTARIAS' in l.upper() or 'DETRACC' in l.upper() for l in c.leyendas):
        c.tiene_detraccion = True
    if any('PERCEPCI' in l.upper() for l in c.leyendas) or c.tipo_operacion == '2001':
        c.tiene_percepcion = True

    # --- Tributos globales ---
    for ts in _all(root, './cac:TaxTotal/cac:TaxSubtotal'):
        nombre = _txt(ts, './cac:TaxCategory/cac:TaxScheme/cbc:Name').upper()
        tid = _txt(ts, './cac:TaxCategory/cac:TaxScheme/cbc:ID')
        monto = _d(_txt(ts, './cbc:TaxAmount'))
        base = _d(_txt(ts, './cbc:TaxableAmount'))
        if nombre == 'IGV' or tid == '1000':
            c.igv += monto
            if not c.gravadas:
                c.gravadas = base
        elif nombre == 'ISC' or tid == '2000':
            c.isc += monto
        elif nombre in ('ICBPER',) or tid == '7152':
            c.icbper += monto
        elif nombre == 'EXO' or tid == '9997':
            c.exoneradas += base
        elif nombre == 'INA' or tid == '9998':
            c.inafectas += base
        elif nombre == 'GRA' or tid == '9996':
            c.gratuitas += base
        elif nombre == 'EXP' or tid == '9995':
            c.exportacion += base
        elif nombre == 'IVAP' or tid == '1016':
            c.otros_tributos += monto
        else:
            c.otros_tributos += monto

    # --- Totales ---
    lmt = _all(root, './cac:LegalMonetaryTotal') or _all(root, './cac:RequestedMonetaryTotal')
    lmt = lmt[0] if lmt else None
    c.valor_venta = _d(_txt(lmt, './cbc:LineExtensionAmount')) or _d(_txt(lmt, './cbc:TaxExclusiveAmount'))
    c.importe_total = _d(_txt(lmt, './cbc:PayableAmount')) or _d(_txt(lmt, './cbc:TaxInclusiveAmount'))
    c.anticipos = _d(_txt(lmt, './cbc:PrepaidAmount'))
    c.redondeo = _d(_txt(lmt, './cbc:PayableRoundingAmount'))
    if not c.descuentos:
        c.descuentos = _d(_txt(lmt, './cbc:AllowanceTotalAmount'))
    if not c.otros_cargos:
        c.otros_cargos = _d(_txt(lmt, './cbc:ChargeTotalAmount'))
    if c.tiene_percepcion:
        if not c.percepcion_total and c.percepcion_monto:
            c.percepcion_total = c.importe_total + c.percepcion_monto
        if not c.percepcion_monto and c.percepcion_total:
            c.percepcion_monto = c.percepcion_total - c.importe_total
    c.tiene_igv = c.igv > 0

    # --- Líneas (InvoiceLine / CreditNoteLine / DebitNoteLine) ---
    line_tag = {'Invoice': 'cac:InvoiceLine', 'CreditNote': 'cac:CreditNoteLine', 'DebitNote': 'cac:DebitNoteLine'}[raiz]
    qty_tag = {'Invoice': 'cbc:InvoicedQuantity', 'CreditNote': 'cbc:CreditedQuantity', 'DebitNote': 'cbc:DebitedQuantity'}[raiz]
    for ln in _all(root, f'./{line_tag}'):
        sub = _all(ln, './cac:SubInvoiceLine')
        if sub:   # Tipo 30 (bancos): las sublíneas son el detalle real
            for s in sub:
                L = Linea(nro=_txt(s, './cbc:ID'), cantidad=Decimal(1), unidad='',
                          codigo=_txt(s, './cac:Item/cac:SellersItemIdentification/cbc:ID'),
                          descripcion=_txt(s, './cac:Item/cbc:Description') or _txt(s, './cac:OriginatorParty/cac:PartyLegalEntity/cbc:RegistrationName'),
                          valor_venta=_d(_txt(s, './cbc:LineExtensionAmount')),
                          igv=_d(_txt(s, './cac:TaxTotal/cbc:TaxAmount')))
                L.valor_unitario = L.valor_venta
                L.precio_unitario = _d(_txt(s, './cac:ItemPriceExtension/cbc:Amount')) or L.valor_venta
                c.lineas.append(L)
            continue
        L = Linea(nro=_txt(ln, './cbc:ID'))
        L.cantidad = _d(_txt(ln, f'./{qty_tag}'), '1')
        uc = _txt(ln, f'./{qty_tag}/@unitCode')
        L.unidad = UNIDADES.get(uc, uc)
        L.codigo = _txt(ln, './cac:Item/cac:SellersItemIdentification/cbc:ID')
        descs = [' '.join((d.text or '').split()) for d in _all(ln, './cac:Item/cbc:Description')]
        L.descripcion = ' / '.join(d for d in descs if d)
        # Algunos emisores meten metadatos con @@ en la descripción (ej. "PRODUCTO@@UND@@0.00@@57.21" o "PRODUCTO@#@ 12- @#@29.36")
        L.descripcion = re.split(r'@#@|@@', L.descripcion)[0].strip()
        L.valor_venta = _d(_txt(ln, './cbc:LineExtensionAmount'))
        L.valor_unitario = _d(_txt(ln, './cac:Price/cbc:PriceAmount'))
        for acp in _all(ln, './cac:PricingReference/cac:AlternativeConditionPrice'):
            if _txt(acp, './cbc:PriceTypeCode') == '01':
                L.precio_unitario = _d(_txt(acp, './cbc:PriceAmount'))
        for ac in _all(ln, './cac:AllowanceCharge'):
            if _txt(ac, './cbc:ChargeIndicator').lower() == 'false':
                L.descuento += _d(_txt(ac, './cbc:Amount'))
        for ts in _all(ln, './cac:TaxTotal/cac:TaxSubtotal'):
            nombre = _txt(ts, './cac:TaxCategory/cac:TaxScheme/cbc:Name').upper()
            tid = _txt(ts, './cac:TaxCategory/cac:TaxScheme/cbc:ID')
            monto = _d(_txt(ts, './cbc:TaxAmount'))
            if nombre == 'IGV' or tid == '1000':
                L.igv += monto
                L.afectacion = _txt(ts, './cac:TaxCategory/cbc:TaxExemptionReasonCode')
            elif nombre == 'ISC' or tid == '2000':
                L.isc += monto
            elif not L.afectacion:
                L.afectacion = _txt(ts, './cac:TaxCategory/cbc:TaxExemptionReasonCode')
        if not L.precio_unitario and L.cantidad:
            L.precio_unitario = ((L.valor_venta + L.igv + L.isc) / L.cantidad) if L.cantidad else Decimal(0)
        c.lineas.append(L)

    if not c.gravadas and c.igv:
        c.gravadas = c.valor_venta
    return c



def _fecha(iso: str) -> str:
    """'2026-05-17' → '17/05/2026' (tolerante)."""
    try:
        return datetime.strptime(iso[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception:
        return iso or ''


def parse_xml_bytes(data: bytes, nombre: str = 'archivo.xml') -> Comprobante:
    """Igual que parse_xml pero desde bytes (subidas en Streamlit, ZIPs)."""
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as tmp:
        tmp.write(data)
        ruta = tmp.name
    try:
        c = parse_xml(Path(ruta))
    finally:
        try:
            os.unlink(ruta)
        except OSError:
            pass
    c.archivo = nombre
    return c


def texto_items(c: Comprobante) -> str:
    """Descripciones de todos los ítems, en mayúsculas, separadas por ' | '."""
    return ' | '.join(l.descripcion for l in c.lineas).upper()
