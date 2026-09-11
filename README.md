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
