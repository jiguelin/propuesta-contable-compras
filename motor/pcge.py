# -*- coding: utf-8 -*-
"""
motor/pcge.py — Base Contable Perú (versionada, sin Internet).

Resumen del Plan Contable General Empresarial Modificado 2019 (Res. CNC 002-2019-EF/30)
para las familias que intervienen en COMPRAS. No sustituye el plan de cuentas de cada empresa:
el PCGE dice *conceptualmente* dónde va algo; el plan de la empresa dice *qué cuenta concreta* existe.

Cada familia tiene:
  - prefijo PCGE (la cuenta de la empresa debe EMPEZAR con este prefijo)
  - nombre
  - palabras clave que activan la familia (se evalúan sobre la descripción de los ítems)
  - av: código "Clasificación de bienes y servicios" de NewContaSis (1 mercadería/MP/suministros,
        2 activo fijo, 3 otros activos, 4 gastos educación/recreación/salud/representación/viaje/
        mantenimiento de vehículo, 5 otros gastos)
"""
from __future__ import annotations

PCGE_VERSION = '2019-mod (Res. CNC 002-2019-EF/30) · base interna v1'

# Orden importa: familias más específicas primero.
FAMILIAS = [
    # ---------- 33/34 ACTIVO FIJO / INTANGIBLES ----------
    dict(prefijo='343', nombre='Programas de computadora (software)', av=2,
         kw=('SOFTWARE', 'LICENCIA PERPETUA', 'PROGRAMA DE COMPUT', 'SISTEMA CONTABLE', 'ERP ')),
    dict(prefijo='334', nombre='Unidades de transporte', av=2,
         kw=('CAMIONETA', 'AUTOMOVIL', 'AUTOMÓVIL', 'VEHICULO NUEVO', 'VEHÍCULO NUEVO', 'MOTOCICLETA', 'MOTO LINEAL', 'FURGON', 'FURGÓN')),
    dict(prefijo='335', nombre='Muebles y enseres', av=2,
         kw=('ESCRITORIO', 'SILLA GERENCIAL', 'SILLON', 'SILLÓN', 'ESTANTE', 'ANAQUEL', 'MUEBLE', 'ARCHIVADOR METAL', 'MESA DE TRABAJO', 'MOSTRADOR', 'VITRINA')),
    dict(prefijo='336', nombre='Equipos diversos (cómputo, comunicación, otros)', av=2,
         kw=('LAPTOP', 'COMPUTADORA', 'PC ', 'CPU', 'IMPRESORA', 'MONITOR', 'SERVIDOR', 'PROYECTOR', 'AIRE ACONDICIONADO', 'REFRIGERADORA', 'CONGELADORA',
             'EQUIPO DE RAYOS', 'EQUIPO DENTAL', 'UNIDAD DENTAL', 'AUTOCLAVE', 'COMPRESORA', 'MAQUINA REGISTRADORA', 'MÁQUINA REGISTRADORA', 'TELEVISOR', 'CAMARA DE SEGURIDAD', 'CÁMARA DE SEGURIDAD', 'CELULAR', 'SMARTPHONE', 'TABLET')),
    dict(prefijo='333', nombre='Maquinaria y equipo de explotación', av=2,
         kw=('MAQUINARIA', 'MAQUINA INDUSTRIAL', 'MÁQUINA INDUSTRIAL', 'TORNO', 'HORNO INDUSTRIAL', 'GENERADOR ELECTRICO', 'GENERADOR ELÉCTRICO')),

    # ---------- 60 COMPRAS (existencias) ----------
    dict(prefijo='6032', nombre='Suministros (combustibles, lubricantes, energía, otros)', av=1, pref_desc=('COMBUSTIBLE',),
         kw=('GASOHOL', 'DIESEL', 'DIÉSEL', 'DB5', 'GASOLINA', 'GLP', 'GNV', 'PETROLEO', 'PETRÓLEO', 'COMBUSTIBLE', 'LUBRICANTE', 'ACEITE DE MOTOR', 'G-PRIX', 'PREMIUM 9', 'REGULAR 9', 'PREMIUN', 'GASOHOL PREMIUM', 'GALON', 'GALÓN')),
    dict(prefijo='6033', nombre='Repuestos', av=1,
         kw=('REPUESTO', 'FILTRO DE ACEITE', 'FILTRO DE AIRE', 'FILTRO', 'BUJIA', 'BUJÍA', 'PASTILLA DE FRENO', 'NEUMATICO', 'NEUMÁTICO', 'LLANTA', 'SEAL', 'SELLO', 'KIT', 'RETAINER', 'CHUCK', 'DIAPHRAGM', 'DIAFRAGMA', 'SHANK', 'BUSHING', 'BOCINA', 'O-RING', 'ORING', 'BEARING', 'RODAMIENTO', 'HOSE', 'MANGUERA', 'VALVE', 'VALVULA', 'VÁLVULA', 'PISTON', 'PISTÓN', 'CYLINDER', 'CILINDRO', 'GASKET', 'EMPAQUETADURA', 'SPRING', 'RESORTE', 'BOLT', 'PERNO', 'NUT', 'TUERCA', 'WASHER', 'ARANDELA', 'PIN ', 'PLATE', 'GEAR', 'ENGRANAJE', 'ROD ', 'BIT ', 'BROCA', 'CUCHILLA', 'CADENA', 'FAJA', 'CORREA', 'ALTERNADOR', 'ARRANCADOR', 'RADIADOR', 'TURBO', 'INYECTOR', 'BOMBA DE', 'SENSOR')),
    dict(prefijo='6031', nombre='Materiales auxiliares', av=1,
         kw=('MATERIAL AUXILIAR', 'INSUMO', 'MATERIAL DE TRABAJO', 'MATERIAL ODONTOL', 'MATERIAL DENTAL', 'RESINA', 'GUANTES', 'MASCARILLA', 'JERINGA', 'ANESTESIA', 'ALGODON', 'ALGODÓN', 'GASA')),
    dict(prefijo='604', nombre='Envases y embalajes', av=1,
         kw=('ENVASE', 'EMBALAJE', 'BOLSA DE EMPAQUE', 'CAJA DE CARTON', 'CAJA DE CARTÓN', 'ETIQUETA', 'STRETCH FILM', 'CINTA DE EMBALAJE')),
    dict(prefijo='602', nombre='Materias primas', av=1,
         kw=('MATERIA PRIMA', 'HARINA', 'AZUCAR', 'AZÚCAR', 'MANTECA', 'TELA ', 'CUERO', 'MADERA', 'FIERRO', 'ACERO', 'CEMENTO')),
    dict(prefijo='601', nombre='Mercaderías (para reventa)', av=1,
         kw=('MERCADERIA', 'MERCADERÍA', 'PARA VENTA', 'REVENTA', 'ABARROTES', 'GASEOSA', 'CERVEZA', 'GALLETA', 'LECHE GLORIA', 'ARROZ', 'ACEITE PRIMOR', 'DETERGENTE', 'PAPEL HIGIENICO', 'PAPEL HIGIÉNICO', 'CIGARRO', 'CHOCOLATE', 'CARAMELO', 'SNACK')),

    # ---------- 63 SERVICIOS PRESTADOS POR TERCEROS ----------
    dict(prefijo='6311', nombre='Transporte de carga', av=5,
         kw=('TRANSPORTE DE CARGA', 'FLETE', 'MUDANZA', 'COURIER', 'ENVIO ', 'ENVÍO ', 'DELIVERY', 'MENSAJERIA', 'MENSAJERÍA', 'ENCOMIENDA')),
    dict(prefijo='6312', nombre='Transporte de pasajeros', av=4,
         kw=('PASAJE', 'BOLETO DE VIAJE', 'TAXI', 'MOVILIDAD', 'TRANSPORTE DE PERSONAL', 'UBER', 'VUELO', 'AEREO', 'AÉREO')),
    dict(prefijo='6313', nombre='Alojamiento', av=4,
         kw=('HOSPEDAJE', 'ALOJAMIENTO', 'HOTEL', 'HOSTAL', 'HABITACION', 'HABITACIÓN')),
    dict(prefijo='6314', nombre='Alimentación', av=4,
         kw=('MENU', 'MENÚ', 'ALMUERZO', 'CENA', 'DESAYUNO', 'CONSUMO', 'LOMO SALTADO', 'CEVICHE', 'POLLO A LA BRASA', 'HAMBURGUESA', 'PIZZA', 'CAFE ', 'CAFÉ ', 'SANDWICH', 'SÁNDWICH', 'PLATO', 'POSTRE', 'JUGO ', 'BEBIDA', 'RESTAURANT', 'CATERING', 'BUFFET', 'POR CONSUMO', 'POLLO', 'PARRILLA', 'CARNERO', 'CHICHARRON', 'CHICHARRÓN', 'PAN Y MANTEQUILLA', 'GASEOSA PERSONAL', 'INKA KOLA', 'COCA COLA', 'CHIFA', 'ARROZ CHAUFA', 'TALLARIN', 'TALLARÍN', 'SOPA', 'CALDO', 'PARRILLADA', 'ANTICUCHO', 'KIDS')),
    dict(prefijo='6315', nombre='Otros gastos de viaje', av=4,
         kw=('VIATICO', 'VIÁTICO', 'GASTOS DE VIAJE', 'PEAJE', 'ESTACIONAMIENTO', 'PARQUEO', 'APARCAMIENTO', 'COBRO TICKET', 'CAT: ', 'NORMAL L', 'LIGERO', 'PESADO')),
    dict(prefijo='6321', nombre='Asesoría administrativa', av=5,
         kw=('ASESORIA ADMINISTRATIVA', 'ASESORÍA ADMINISTRATIVA', 'GESTION ADMINISTRATIVA', 'GESTIÓN ADMINISTRATIVA', 'TRAMITE', 'TRÁMITE', 'GESTORIA', 'GESTORÍA')),
    dict(prefijo='6322', nombre='Asesoría legal y tributaria', av=5,
         kw=('LEGAL', 'ABOGADO', 'JURIDIC', 'JURÍDIC', 'NOTARIA', 'NOTARÍA', 'NOTARIAL', 'TRIBUTARI', 'ESTUDIO DE ABOGADOS', 'LAUDO', 'ARBITRAJE')),
    dict(prefijo='6323', nombre='Auditoría y contable', av=5,
         kw=('CONTABLE', 'CONTABILIDAD', 'SERIVICIO CONTABLE', 'AUDITORIA', 'AUDITORÍA', 'TENEDURIA', 'TENEDURÍA', 'DECLARACION DE IMPUESTOS', 'DECLARACIÓN DE IMPUESTOS', 'PLANILLA ELECTRONICA', 'PLANILLA ELECTRÓNICA')),
    dict(prefijo='6324', nombre='Asesoría en mercadotecnia', av=5,
         kw=('MARKETING', 'MERCADOTECNIA', 'ESTUDIO DE MERCADO', 'BRANDING', 'COMMUNITY MANAGER')),
    dict(prefijo='6325', nombre='Medioambiental', av=5,
         kw=('MEDIOAMBIENT', 'MEDIO AMBIENTE', 'RESIDUOS SOLIDOS', 'RESIDUOS SÓLIDOS', 'RESIDUOS BIOCONTAMINADOS', 'FUMIGACION', 'FUMIGACIÓN', 'DESINFECCION', 'DESINFECCIÓN')),
    dict(prefijo='6326', nombre='Investigación y desarrollo', av=5,
         kw=('INVESTIGACION', 'INVESTIGACIÓN', 'DESARROLLO DE PRODUCTO', 'PROTOTIPO')),
    dict(prefijo='6327', nombre='Producción (servicios)', av=5,
         kw=('MAQUILA', 'PRODUCCION POR ENCARGO', 'PRODUCCIÓN POR ENCARGO', 'FABRICACION POR ENCARGO', 'FABRICACIÓN POR ENCARGO', 'CONFECCION', 'CONFECCIÓN')),
    dict(prefijo='6329', nombre='Otros servicios de asesoría y consultoría', av=5,
         kw=('CONSULTORIA', 'CONSULTORÍA', 'ASESORIA', 'ASESORÍA', 'HONORARIO', 'CAPACITACION', 'CAPACITACIÓN', 'CURSO', 'TALLER', 'DIPLOMADO', 'SEMINARIO', 'SOPORTE TECNICO', 'SOPORTE TÉCNICO', 'DESARROLLO WEB', 'DISEÑO WEB', 'PROGRAMACION', 'PROGRAMACIÓN', 'IMPLEMENTACION', 'IMPLEMENTACIÓN', 'SERVICIO PROFESIONAL', 'SERVICIOS PROFESIONALES', 'RECLUTAMIENTO', 'SELECCION DE PERSONAL', 'SELECCIÓN DE PERSONAL', 'SERVICIOS DE COBRANZA', 'CENTRAL DE RIESGO', 'EQUIFAX', 'SENTINEL', 'INFOCORP')),
    dict(prefijo='6343', nombre='Mantenimiento y reparación — Propiedad, planta y equipo', av=5,
         kw=('MANTENIMIENTO', 'REPARACION', 'REPARACIÓN', 'CALIBRACION', 'CALIBRACIÓN', 'SERVICIO TECNICO', 'SERVICIO TÉCNICO', 'INSTALACION', 'INSTALACIÓN', 'GASFITERIA', 'GASFITERÍA', 'ELECTRICISTA', 'PINTADO', 'MANO DE OBRA', 'LAVADO DE VEHICULO', 'LAVADO DE VEHÍCULO', 'CAMBIO DE ACEITE')),
    dict(prefijo='6352', nombre='Alquiler — Edificaciones / locales', av=5,
         kw=('ALQUILER DE LOCAL', 'ALQUILER DE OFICINA', 'ARRENDAMIENTO DE LOCAL', 'ARRENDAMIENTO DE INMUEBLE', 'ALQUILER DE INMUEBLE', 'RENTA DE LOCAL', 'MERCED CONDUCTIVA', 'ALQUILER DE CONSULTORIO', 'ALQUILER DE ALMACEN', 'ALQUILER DE ALMACÉN', 'ALQUILER DE TIENDA')),
    dict(prefijo='6353', nombre='Alquiler — Maquinarias y equipos', av=5,
         kw=('ALQUILER DE EQUIPO', 'ALQUILER DE MAQUINA', 'ALQUILER DE MÁQUINA', 'ALQUILER DE ANDAMIO', 'ALQUILER DE GRUPO ELECTROGENO', 'ALQUILER DE GRUPO ELECTRÓGENO')),
    dict(prefijo='6354', nombre='Alquiler — Unidades de transporte', av=5,
         kw=('ALQUILER DE VEHICULO', 'ALQUILER DE VEHÍCULO', 'ALQUILER DE CAMIONETA', 'ALQUILER DE AUTO', 'RENT A CAR')),
    dict(prefijo='635', nombre='Alquileres (otros)', av=5,
         kw=('ALQUILER', 'ARRENDAMIENTO', 'ARRIENDO', 'LEASING OPERATIVO')),
    dict(prefijo='6361', nombre='Energía eléctrica', av=5,
         kw=('ENERGIA ELECTRICA', 'ENERGÍA ELÉCTRICA', 'CONSUMO DE ENERGIA', 'CONSUMO DE ENERGÍA', 'LUZ DEL SUR', 'ENEL', 'ELECTRICIDAD', 'KWH')),
    dict(prefijo='6362', nombre='Gas', av=5,
         kw=('GAS NATURAL', 'CALIDDA', 'CÁLIDDA', 'BALON DE GAS', 'BALÓN DE GAS')),
    dict(prefijo='6363', nombre='Agua', av=5,
         kw=('SERVICIO DE AGUA', 'AGUA POTABLE', 'SEDAPAL', 'ALCANTARILLADO', 'AGUA Y DESAGUE', 'AGUA Y DESAGÜE')),
    dict(prefijo='6364', nombre='Teléfono', av=5,
         kw=('TELEFON', 'TELÉFON', 'PLAN MOVIL', 'PLAN MÓVIL', 'PLAN POSTPAGO', 'LINEA MOVIL', 'LÍNEA MÓVIL', 'CELULAR PLAN', 'MOVISTAR', 'CLARO', 'ENTEL', 'BITEL')),
    dict(prefijo='6365', nombre='Internet', av=5,
         kw=('INTERNET', 'FIBRA OPTICA', 'FIBRA ÓPTICA', 'BANDA ANCHA', 'WIFI', 'HOSTING', 'DOMINIO', 'SERVIDOR CLOUD', 'NUBE')),
    dict(prefijo='6366', nombre='Radio', av=5,
         kw=('RADIO ', 'RADIOCOMUNICACION', 'RADIOCOMUNICACIÓN')),
    dict(prefijo='6367', nombre='Cable', av=5,
         kw=('CABLE TV', 'TV CABLE', 'TELEVISION POR CABLE', 'TELEVISIÓN POR CABLE', 'DIRECTV', 'MOVISTAR TV')),
    dict(prefijo='6371', nombre='Publicidad', av=5,
         kw=('PUBLICIDAD', 'ANUNCIO', 'META ADS', 'FACEBOOK ADS', 'GOOGLE ADS', 'PAUTA', 'BANNER', 'VOLANTE', 'BROCHURE', 'AFICHE', 'GIGANTOGRAFIA', 'GIGANTOGRAFÍA', 'SPOT', 'INFLUENCER', 'REDES SOCIALES', 'MERCHANDISING', 'TARJETAS DE PRESENTACION', 'TARJETAS DE PRESENTACIÓN')),
    dict(prefijo='6372', nombre='Publicaciones', av=5,
         kw=('PUBLICACION', 'PUBLICACIÓN', 'AVISO EN DIARIO', 'EDICTO', 'EL PERUANO')),
    dict(prefijo='6373', nombre='Relaciones públicas', av=4,
         kw=('RELACIONES PUBLICAS', 'RELACIONES PÚBLICAS', 'EVENTO', 'AGASAJO', 'REGALO', 'OBSEQUIO', 'CANASTA', 'CELEBRACION', 'CELEBRACIÓN', 'ANIVERSARIO', 'REPRESENTACION', 'REPRESENTACIÓN', 'ATENCION A CLIENTES', 'ATENCIÓN A CLIENTES', 'CAMPEONATO', 'TORNEO', 'COPA ', 'PARTICIPACION EN', 'PARTICIPACIÓN EN', 'INSCRIPCION AL', 'INSCRIPCIÓN AL', 'CONFRATERNIDAD', 'INTEGRACION', 'INTEGRACIÓN')),
    dict(prefijo='6381', nombre='Servicios de contratistas', av=5,
         kw=('CONTRATISTA', 'OBRA CIVIL', 'CONSTRUCCION', 'CONSTRUCCIÓN', 'REMODELACION', 'REMODELACIÓN', 'DRYWALL', 'ALBAÑIL')),
    dict(prefijo='6391', nombre='Gastos bancarios', av=5,
         kw=('COMISION BANCARIA', 'COMISIÓN BANCARIA', 'PORTES', 'MANTENIMIENTO DE CUENTA', 'ITF', 'GASTOS BANCARIOS', 'COMISION POR TRANSFERENCIA', 'COMISIÓN POR TRANSFERENCIA', 'COMISION POS', 'COMISIÓN POS', 'NIUBIZ', 'IZIPAY', 'CULQI', 'MERCADO PAGO')),
    dict(prefijo='6392', nombre='Gastos de laboratorio', av=5,
         kw=('LABORATORIO', 'ANALISIS CLINICO', 'ANÁLISIS CLÍNICO', 'ENSAYO DE LABORATORIO', 'PROTESIS', 'PRÓTESIS', 'CORONA DENTAL', 'RADIOGRAFIA', 'RADIOGRAFÍA')),
    dict(prefijo='639', nombre='Otros servicios prestados por terceros', av=5,
         kw=('SERVICIO DE LIMPIEZA', 'LIMPIEZA', 'VIGILANCIA', 'SEGURIDAD', 'GUARDIANIA', 'GUARDIANÍA', 'SERVICIO DE ', 'SERVICIOS DE ', 'IMPRESION', 'IMPRESIÓN', 'FOTOCOPIA', 'ANILLADO', 'LAVANDERIA', 'LAVANDERÍA', 'ESTERILIZACION', 'ESTERILIZACIÓN', 'COMISION', 'COMISIÓN', 'INTERMEDIACION', 'INTERMEDIACIÓN', 'TERCERIZACION', 'TERCERIZACIÓN')),

    # ---------- 65 OTROS GASTOS DE GESTIÓN ----------
    dict(prefijo='651', nombre='Seguros', av=5,
         kw=('SEGURO', 'POLIZA', 'PÓLIZA', 'SCTR', 'EPS ', 'VIDA LEY', 'PRIMA DE SEGURO', 'SOAT', 'RIMAC', 'PACIFICO SEGUROS', 'PACÍFICO SEGUROS', 'LA POSITIVA', 'MAPFRE')),
    dict(prefijo='652', nombre='Regalías', av=5,
         kw=('REGALIA', 'REGALÍA', 'ROYALTY', 'FRANQUICIA')),
    dict(prefijo='653', nombre='Suscripciones', av=5,
         kw=('SUSCRIPCION', 'SUSCRIPCIÓN', 'MEMBRESIA', 'MEMBRESÍA', 'CUOTA DE AFILIACION', 'CUOTA DE AFILIACIÓN', 'REVISTA', 'PERIODICO', 'PERIÓDICO', 'NETFLIX', 'SPOTIFY', 'CANVA', 'MICROSOFT 365', 'OFFICE 365', 'GOOGLE WORKSPACE', 'ZOOM', 'CHATGPT', 'ADOBE')),
    dict(prefijo='654', nombre='Licencias y derechos de vigencia', av=5,
         kw=('LICENCIA DE FUNCIONAMIENTO', 'LICENCIA DE SOFTWARE', 'LICENCIA ANUAL', 'LICENCIA MENSUAL', 'DERECHO DE VIGENCIA', 'RENOVACION DE LICENCIA', 'RENOVACIÓN DE LICENCIA', 'CERTIFICADO DIGITAL')),
    dict(prefijo='656', nombre='Suministros (consumo inmediato)', av=1, pref_desc=('SUMINISTROS',),
         kw=('UTILES DE OFICINA', 'ÚTILES DE OFICINA', 'UTILES DE ESCRITORIO', 'ÚTILES DE ESCRITORIO', 'PAPEL BOND', 'TONER', 'TÓNER', 'TINTA', 'LAPICERO', 'ARCHIVADOR', 'FOLDER', 'FÓLDER', 'ARTICULOS DE LIMPIEZA', 'ARTÍCULOS DE LIMPIEZA', 'JABON', 'JABÓN', 'LEJIA', 'LEJÍA', 'DESINFECTANTE', 'ESCOBA', 'TRAPEADOR', 'PAPEL TOALLA', 'AGUA DE MESA', 'BIDON', 'BIDÓN', 'CAFE INSTANTANEO', 'CAFÉ INSTANTÁNEO', 'AZUCAR ', 'FERRETERIA', 'FERRETERÍA', 'PILA', 'BATERIA', 'BATERÍA', 'FOCO', 'CABLE ', 'EXTENSION', 'EXTENSIÓN', 'TOMACORRIENTE', 'PINTURA', 'HERRAMIENTA', 'MASCARILLA', 'GUANTE', 'ALCOHOL', 'BOTIQUIN', 'BOTIQUÍN', 'MOUSE', 'TECLADO', 'USB', 'CARGADOR', 'AUDIFONO', 'AUDÍFONO', 'ACCESORIO', 'PAPEL HIGIENICO', 'PAPEL HIGIÉNICO', 'SUAVE ', 'ELITE ', 'TRAPO', 'FRANELA', 'WAYPE', 'ESCOBILLA', 'AMBIENTADOR', 'INSECTICIDA')),
    dict(prefijo='659', nombre='Otros gastos de gestión', av=5,
         kw=('DONACION', 'DONACIÓN', 'SANCION', 'SANCIÓN', 'MULTA', 'GASTOS DIVERSOS', 'OTROS GASTOS')),
]

# Palabras clave sobre el NOMBRE / nombre comercial del emisor → prefijo de familia.
# Se usan como segunda señal cuando la descripción de los ítems no dice nada ("Cat: 1", "Normal L2", "POR CONSUMO").
EMISOR_KW = [
    ('6032', ('GRIFO', 'SERVICENTRO', 'ESTACION DE SERVICIO', 'ESTACIÓN DE SERVICIO', 'PETROGAS', 'PRIMAX', 'REPSOL', 'PETROPERU', 'TERPEL', 'COMBUSTIBLE', 'GASOCENTRO', 'GNV')),
    ('6315', ('LIMA EXPRESA', 'RUTAS DE LIMA', 'DESARROLLO VIAL', 'PEAJE', 'CONCESIONARIA VIAL', 'COVI', 'AUTOPISTA', 'NORVIAL', 'ESTACIONAMIENTO', 'PARKING', 'APARCAMIENTO', 'LOS PORTALES ESTACIONAMIENTOS')),
    ('6314', ('RESTAURANT', 'RESTAURANTE', 'POLLOS', 'POLLERIA', 'POLLERÍA', 'PARRILLA', 'CHIFA', 'CEVICHERIA', 'CEVICHERÍA', 'CAFE ', 'CAFÉ ', 'CAFETERIA', 'CAFETERÍA', 'PANADERIA', 'PANADERÍA', 'PANISTERIA', 'PASTELERIA', 'PASTELERÍA', 'SANGUCHERIA', 'SANGUCHERÍA', 'PIZZERIA', 'PIZZERÍA', 'BURGER', 'KFC', 'MCDONALD', 'STARBUCKS', 'BEMBOS', 'NORKYS', 'ROKYS', 'PARDOS', 'CAMPESTRE', 'JUGUERIA', 'JUGUERÍA', 'HELADERIA', 'HELADERÍA', 'CANDY', 'DULCERIA', 'DULCERÍA', 'MARKET')),
    ('6313', ('HOTEL', 'HOSTAL', 'HOSPEDAJE', 'HOSTEL', 'LODGE')),
    ('6323', ('CONTADORES', 'CONTABLE', 'CONTADEUS', 'AUDITORES', 'OUTSOURCING CONTABLE')),
    ('6322', ('ABOGADOS', 'ESTUDIO JURIDICO', 'ESTUDIO JURÍDICO', 'NOTARIA', 'NOTARÍA')),
    ('6365', ('INTERNET', 'NETWORK', 'TELECOM', 'FIBRA', 'WIN ', 'WOW ')),
    ('6364', ('MOVISTAR', 'TELEFONICA', 'TELEFÓNICA', 'CLARO', 'ENTEL', 'BITEL')),
    ('6361', ('LUZ DEL SUR', 'ENEL', 'ELECTRO', 'HIDRANDINA', 'SEAL ', 'ELECTRONORTE', 'ELECTROCENTRO', 'PLUZ')),
    ('6363', ('SEDAPAL', 'SEDALIB', 'EPS ', 'AGUA POTABLE')),
    ('6362', ('CALIDDA', 'CÁLIDDA', 'GAS NATURAL', 'QUAVII')),
    ('651', ('SEGUROS', 'RIMAC', 'PACIFICO', 'PACÍFICO', 'MAPFRE', 'LA POSITIVA', 'INTERSEGURO', 'CRECER SEGUROS', 'PROTECTA')),
    ('6371', ('PUBLICIDAD', 'IMPRENTA', 'GRAFICA', 'GRÁFICA', 'META PLATFORMS', 'GOOGLE', 'FACEBOOK')),
    ('6033', ('REPUESTOS', 'MAQUINARIAS', 'KOMATSU', 'CATERPILLAR', 'FERREYROS', 'VOLVO', 'SCANIA', 'SANDVIK', 'EPIROC', 'ATLAS COPCO', 'HIDRAULIC', 'HIDRÁULIC')),
    ('656', ('FERRETERIA', 'FERRETERÍA', 'SODIMAC', 'PROMART', 'MAESTRO', 'LIBRERIA', 'LIBRERÍA', 'TAI LOY', 'UTILEX', 'BAZAR', 'MINIMARKET', 'BODEGA', 'TAMBO', 'OXXO', 'MASS ', 'LISTO', 'REPSHOP')),
]

# Emisores cuya factura NO es una compra/gasto normal (se marcan para revisión, no se contabilizan a ciegas)
EMISOR_NO_GASTO = (
    ('CAMBISTA', 'Casa de cambio: la factura documenta compra/venta de moneda, no un gasto. Registrar como operación de cambio (10x), no como compra.'),
    ('CASA DE CAMBIO', 'Casa de cambio: la factura documenta compra/venta de moneda, no un gasto.'),
    ('COMPRA DE DOLARES', 'Compra de moneda extranjera: no es un gasto deducible; revisar tratamiento.'),
    ('COMPRA DE DÓLARES', 'Compra de moneda extranjera: no es un gasto deducible; revisar tratamiento.'),
    ('VENTA DE DOLARES', 'Operación de cambio de moneda: no es un gasto.'),
    ('VENTA DE DÓLARES', 'Operación de cambio de moneda: no es un gasto.'),
)


def familia_por_emisor(nombre: str) -> dict | None:
    t = ' ' + (nombre or '').upper() + ' '
    for prefijo, kws in EMISOR_KW:
        if any(k in t for k in kws):
            return next(f for f in FAMILIAS if f['prefijo'] == prefijo)
    return None


def motivo_no_gasto(nombre_emisor: str, texto_items: str) -> str | None:
    t = ((nombre_emisor or '') + ' ' + (texto_items or '')).upper()
    for k, msg in EMISOR_NO_GASTO:
        if k in t:
            return msg
    return None


# Familias con IGV que NO da derecho a crédito fiscal (referencia; no bloquea)
FAMILIAS_ACTIVO = ('33', '34')
FAMILIAS_EXISTENCIAS = ('60',)
FAMILIAS_GASTO = ('63', '65')

# Descripción general de la naturaleza (para prompts de IA y explicaciones)
NATURALEZA_PCGE = {
    '60': 'Compras de existencias: mercaderías (601), materias primas (602), materiales auxiliares/suministros/repuestos (603), envases y embalajes (604). Se destinan a inventario (20/21/25/26) vía 61.',
    '63': 'Gastos de servicios prestados por terceros: transporte/viajes (631), asesoría y consultoría (632), producción encargada (633), mantenimiento y reparaciones (634), alquileres (635), servicios básicos (636), publicidad/publicaciones/RRPP (637), contratistas (638), otros (639).',
    '65': 'Otros gastos de gestión: seguros (651), regalías (652), suscripciones (653), licencias (654), suministros de consumo inmediato (656), otros (659).',
    '33': 'Propiedad, planta y equipo: terrenos (331), edificaciones (332), maquinaria (333), unidades de transporte (334), muebles y enseres (335), equipos diversos (336).',
    '34': 'Intangibles: concesiones/licencias (341), patentes (342), programas de computadora/software (343).',
}

# Mapa de sufijos "destino" habituales en planes NewContaSis (observado): 093 CDS, 094 ADM, 095 VTAS
SUFIJOS_DESTINO = {'093': 'Costo del servicio (CDS)', '094': 'Administración (ADM)', '095': 'Ventas (VTAS)',
                   '3': 'Costo del servicio', '4': 'Administración', '5': 'Ventas'}


def familias_por_texto(texto: str) -> list[tuple[dict, int]]:
    """Devuelve [(familia, puntaje)] ordenadas por puntaje (cantidad de palabras clave que aparecen)."""
    t = ' ' + (texto or '').upper() + ' '
    hits = []
    for fam in FAMILIAS:
        n = sum(1 for k in fam['kw'] if k in t)
        if n:
            hits.append((fam, n))
    hits.sort(key=lambda x: -x[1])
    return hits


def familia_por_prefijo(cuenta: str) -> dict | None:
    """Familia PCGE más específica cuyo prefijo coincide con la cuenta dada."""
    cuenta = (cuenta or '').strip()
    mejor = None
    for fam in FAMILIAS:
        if cuenta.startswith(fam['prefijo']) and (mejor is None or len(fam['prefijo']) > len(mejor['prefijo'])):
            mejor = fam
    return mejor


def av_por_cuenta(cuenta: str) -> int:
    """Clasificación NewContaSis (AV) a partir de la cuenta: 1 existencias, 2 activo fijo, 4/5 gastos."""
    fam = familia_por_prefijo(cuenta)
    if fam:
        return fam['av']
    c = (cuenta or '').strip()
    if c.startswith(('60', '20', '21', '25', '26', '656')):
        return 1
    if c.startswith(('33', '34')):
        return 2
    if c.startswith(('631', '6373')):
        return 4
    return 5
