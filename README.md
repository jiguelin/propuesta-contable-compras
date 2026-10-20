# Propuesta Contable de Compras

Sube los **XML de compras** del mes → obtienes el **Excel listo para importar en NewContaSis** (Registro de Compras,
con la cuenta contable propuesta por factura y la cuenta del haber que elijas) + un **reporte de observaciones**.

Una pantalla. Sin pasos intermedios. Cada corrección que haces, el sistema la recuerda para el próximo mes.

```
XML (o ZIP) ─▶ lector UBL ─▶ ¿banco? excluir ─▶ concepto por importe ─▶ memoria proveedor+concepto
            ─▶ plan de cuentas de la empresa ─▶ (IA solo si hay duda, elige entre cuentas reales)
            ─▶ Excel NewContaSis + Excel de revisión + REPORTE_REVISION.txt
```

## Cómo se usa

1. **Empresa** (una sola vez): RUC, razón social y el Excel del plan de cuentas exportado de NewContaSis. Queda guardado.
2. **Tipo de cambio** (una vez al mes): subir el PDF "SUNAT – Tipo de Cambio" del mes. El historial se acumula, nunca se borra.
3. **Historial contable** (opcional): Diario Analítico de NewContaSis (MES/FECHA/CUENTA/DEBE/HABER). Enseña qué cuentas usa realmente la empresa.
4. **Cuenta del haber** para el lote: escribe cualquier cuenta (4212, 1011, 104101…). Se valida contra el plan.
5. **Subir XML** (sueltos o ZIP) → **GENERAR PROPUESTA**.
6. Revisar la tabla (🟢 ≥95 % · 🟡 75–94 % · 🔴 <75 %), corregir cuentas en la misma tabla y **descargar**.

## Qué produce

| Archivo | Contenido |
|---|---|
| `NEWCONTASIS_COMPRAS_<ruc>_<periodo>.xlsx` | Solo filas de datos, 50 columnas A–AX según la plantilla oficial (se importa directo). |
| `REVISION_<ruc>_<periodo>.xlsx` | Hojas PROPUESTA (semáforo, explicación), REVISAR, EXCLUIDOS y NEWCONTASIS (ref) con cabeceras. |
| `REPORTE_REVISION_<ruc>_<periodo>.txt` | Resumen, observaciones (importes altos, mixtas, detracción sin constancia, sin TC, fuera de periodo, casas de cambio…), excluidos. |

## Reglas de negocio implementadas

- **Bancos** (RUC conocido o comprobante tipo 30) → excluidos y listados aparte.
- **Una sola cuenta por factura**, la del mayor **importe** (no la de más líneas). Facturas mixtas se marcan.
- **Memoria = proveedor + concepto**, no solo proveedor: "Sodimac + limpieza" ≠ "Sodimac + aire acondicionado".
- **La IA nunca inventa cuentas**: recibe las candidatas reales del plan y solo puede elegir una de ellas. Se consulta únicamente cuando la confianza por reglas es < 90 %.
- **Detracción**: código, %, monto y cuenta BN salen del XML. El N° y fecha de constancia **no** vienen en el XML → se dejan en blanco y se avisa.
- **Tipo de cambio**: TC venta SUNAT de la fecha de emisión; si no hay publicación, el último publicado (y se avisa).
- **Alerta configurable** de importes (S/ 20 000 por defecto).
- **PCGE 2019** incorporado en `motor/pcge.py` (familias 33/34/60/63/65 con palabras clave), versionado, sin Internet.

## Estructura

```
app.py                  ← interfaz Streamlit (solo dibuja)
cli.py                  ← mismo motor por línea de comandos
motor/
  xml_parser.py         ← lector UBL 2.1 (copia del clasificador v2, sin PDF)
  pcge.py               ← base contable Perú: familias, palabras clave, emisores conocidos
  plan_cuentas.py       ← lee el plan de la empresa, busca cuentas, hojas/prefijos
  historial.py          ← lee el Diario Analítico (opcional)
  tipo_cambio.py        ← PDF SUNAT → historial de TC con "último publicado"
  memoria.py            ← SQLite: empresas, planes, TC, aprendizaje, lotes
  clasificador.py       ← el motor de decisión (capas + confianza)
  ia.py                 ← Claude, solo entre candidatas
  excel_newcontasis.py  ← Excel de importación (A–AX) y Excel de revisión
  reporte.py            ← REPORTE_REVISION.txt
  servicio.py           ← orquestador que usan app.py y cli.py
plantillas/             ← plantilla oficial NewContaSis de referencia
tests/                  ← pruebas del motor (python -m pytest)
```

## Instalación local

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # opcional: API key de Anthropic
streamlit run app.py
```

Sin API key la app funciona igual (solo reglas + plan + memoria).

## Publicar en GitHub + Streamlit Community Cloud

1. Crear un repositorio en GitHub y subir esta carpeta (`git init && git add . && git commit -m "v0.1" && git push`).
2. En https://share.streamlit.io → *New app* → elegir el repo, rama `main`, archivo `app.py`.
3. En *Advanced settings → Secrets* pegar `ANTHROPIC_API_KEY = "sk-ant-..."`.
4. Listo: la app queda en `https://<tu-app>.streamlit.app`.

> **Importante para producción / 100+ empresas:** el disco de Streamlit Cloud es efímero: la base SQLite
> (`datos/propuesta.db`) se pierde al reiniciar la app. Para el piloto está bien; para producción hay que
> apuntar `PROPUESTA_DB` a un volumen persistente o migrar `motor/memoria.py` a Postgres (Supabase/Neon, plan gratuito).
> Todo el acceso a datos está aislado en ese módulo justamente para que ese cambio no toque nada más.

## Novedades v0.2.0

- **Dólares**: las columnas J–S del Excel van en **soles** (importe × TC venta SUNAT de la fecha de emisión), W = TC y AC = importe original en USD. Así NewContaSis muestra el mismo importe en dólares que la factura.
- **TC en todas las filas** (soles y dólares), según la fecha de emisión. Se pueden subir varios PDF de meses distintos a la vez; el historial se acumula.
- **Mes a trabajar**: al subir los XML se elige el mes; todo comprobante de otro mes se excluye del Excel (queda en EXCLUIDOS y en el reporte).
- **Constancias de detracción (opcional)**: TXT/CSV/Excel de SUNAT o PDF individuales (o ZIP). Se cruzan por RUC + serie + número y llenan U/V y AO/AP solo en las facturas afectas. Lo que no cruza se informa. Filtro "Con detracción" en la tabla.
- **Posible activo fijo**: compras de equipos/muebles/vehículos/software con importe ≥ S/ 1,800 (configurable) se marcan, aparecen en el filtro "Posibles activos fijos" y en el reporte.
- Columna AV: la familia 6315 (peajes, estacionamiento, viáticos) sale con **5**.

## Novedades v0.2.1

- **Detracción sin constancia → fuera del Excel** (regla tributaria: sin depósito no hay crédito fiscal). Queda en EXCLUIDOS, en el filtro "Con detracción" y en el reporte como pendiente; al pagar la detracción se vuelve a generar con la constancia. Desactivable con una casilla.
- Constancias: varios archivos y varios meses a la vez (TXT/CSV/Excel/PDF/ZIP mezclados).
- Columna W: si no hay TC cargado para la fecha, queda en blanco (antes ponía 1.0000 en soles) y la app avisa en rojo si falta el TC del mes elegido.

## Novedades v0.3.0

- **Glosa compatible con el PLE** (`motor/texto.py`). Repara el texto dañado que llega en muchos XML
  (`GESTIÃ¯Â¿Â½N` → `GESTION`), reconstruye los caracteres perdidos con patrones del castellano
  (`CI�N`→`CION`, `A�O`→`ANO`), quita tildes y ñ y deja solo A-Z, números y puntuación básica.
  Lo que tuvo que adivinar se marca: filtro "Glosa reparada" y **la glosa es editable en la tabla**.
  La razón social (columna I) recibe el mismo tratamiento.
- **Base de conocimiento contable** (`motor/reglas.py`), editable desde la app y con prioridad **sobre**
  el historial de la empresa. Dos tipos de regla: *usar esta cuenta* cuando aparezcan ciertas palabras
  (o cierto proveedor), y *bloquear esta cuenta*. Las reglas se guardan por empresa o para todas.
- **La 6399 nunca se propone** (regla de sistema). El PCGE 2019 solo reconoce 6391 (gastos bancarios) y
  6392 (gastos de laboratorio) dentro de 639, y SUNAT rechaza el resto en el balance de comprobación.
  Si el plan de la empresa la tiene, el motor la ignora y usa una alternativa (638, 633, 6329 o 60919);
  si usted la escribe a mano se respeta, pero con alerta y sin guardarla en la memoria.
  El reparto de familias se corrigió en consecuencia: 638 servicios de contratistas, 6329 intermediación/comisiones.
- Las palabras clave ahora puntúan por especificidad: "COMISION POR TRANSFERENCIA" (6391) le gana a "COMISION" (6329).

## Novedades v0.3.2

- **Facturas de bancos por intereses fuera del Excel**: además de la lista de RUC de bancos (se agregó Mibanco),
  se excluye todo comprobante con tipo de operación 2100–2106 del catálogo SUNAT, códigos que solo usa el sistema
  financiero (créditos a empresas, consumo, etc.). Así queda fuera cualquier banco, caja o financiera aunque su RUC
  no esté en la lista. Quedan visibles en la hoja EXCLUIDOS con el motivo.

## Novedades v0.3.3

- **Percepción en el mismo comprobante → cuenta 40113 en el asiento**: la plantilla de NewContaSis no tiene una columna
  para la cuenta de percepción. La única línea de cuenta adicional que acepta es "otros tributos" (R + cuenta AG). Por eso,
  en las facturas con percepción, R lleva la percepción, AG la cuenta (40113 por defecto, editable en Opciones; vacía = no
  se agrega) y S el total pagado. El asiento sale completo: compras / 401111 / 40113 al Debe y el Haber por el total pagado.
- **Corrección manual obligatoria en Contasis**: la percepción NO va en el Registro de Compras. Después de importar, en la
  línea 401111 de cada una se pone Otros T y C = 0 y Total = importe del comprobante. La hoja **PERCEPCIONES** del Excel
  de revisión lista los comprobantes y los montos; también sale como alerta en cada factura.
- Validado con una importación real (CBC MARKET F3T1-435534, 20/10/2026).

## Novedades v0.3.4

- **IGV distinto del 18 %** (MYPE de restaurantes y hoteles, Ley 31556 y modificatorias: 10 % en 2025, 10.5 % en 2026,
  15 % en 2027). La app lee la tasa del XML (de la cabecera o de los ítems; si no viene, IGV ÷ base) y la pone en la
  columna **AR (% IGV)**, que antes iba fija en 18.00. Con AR = 10.50, Contasis marca sola la casilla "IGV 10.5%" de la
  línea 401111, necesaria para enviar bien el SIRE (validado el 20/10/2026 con GASTRONOMIA F V FA01-398).
- Además: alerta por factura, filtro "IGV ≠ 18%", columna "IGV %" en la tabla y hoja **IGV DISTINTO 18%** en el Excel de
  revisión. Si una factura mezcla tasas en sus ítems, se avisa para revisarla a mano.

## Hoja de ruta

- **v0.1 (esta)**: flujo completo XML → Excel + reporte, memoria por proveedor+concepto, TC, detracción, IA opcional.
- **v0.2**: Postgres + login por usuario (varios contadores, 100+ empresas), constancias de detracción (subir y cruzar), NC/ND con referencia completa.
- **v0.3**: cruce automático "XML antiguos + Diario" para construir memoria histórica por proveedor, centros de costo, panel de métricas por empresa.

## Supuestos a confirmar con la primera importación real en NewContaSis

Estos campos se llenaron según la plantilla y su documentación interna, pero **nunca se ha importado un mes real todavía**:

- Importes (J–S) en **soles** (USD convertidos con el TC venta de la fecha), W = tipo de cambio, AC = total en USD cuando la moneda es D. Si se comprueba que NewContaSis los espera en dólares, basta `usd_en_soles=False` en `Servicio.procesar`.
- Columnas L/M/N/O (gravadas mixtas / destinadas a no gravadas) en 0: todas las compras se tratan como destinadas a operaciones gravadas.
- B y AD (vencimiento) = fecha de vencimiento del XML o, si no trae, la de emisión.
- AG (cuenta otros tributos) = misma cuenta del gasto cuando hay otros cargos.
- AX (cuenta ICBPER) se deja en blanco; configurar si NewContaSis la exige.
