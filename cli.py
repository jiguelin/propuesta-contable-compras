# -*- coding: utf-8 -*-
"""Uso por línea de comandos (sin interfaz), útil para pruebas y automatización:

    python cli.py --ruc 20611889683 --nombre "ALQUMIN EIRL" --plan plan.xlsx --tc tipocambio.pdf \
                  --historial diario2025.xlsx --xml XML.zip --haber 4212 --salida ./salida
"""
import argparse
from pathlib import Path

from motor.servicio import Servicio


def main():
    ap = argparse.ArgumentParser(description='Propuesta Contable de Compras — CLI')
    ap.add_argument('--ruc', required=True)
    ap.add_argument('--nombre', default='')
    ap.add_argument('--plan', help='Excel plan de cuentas (se guarda para la empresa)')
    ap.add_argument('--tc', action='append', default=[], help='PDF SUNAT de tipo de cambio (repetible)')
    ap.add_argument('--historial', action='append', default=[], help='Diario analítico Excel (repetible, opcional)')
    ap.add_argument('--xml', action='append', required=True, help='Archivo .xml o .zip (repetible)')
    ap.add_argument('--haber', default=None, help='Cuenta del haber para el lote (defecto: la de la empresa / 4212)')
    ap.add_argument('--sin-ia', action='store_true')
    ap.add_argument('--db', default=None, help='Ruta SQLite (defecto datos/propuesta.db)')
    ap.add_argument('--salida', default='salida')
    a = ap.parse_args()

    s = Servicio(ruta_db=a.db)
    if a.nombre or a.plan:
        s.registrar_empresa(a.ruc, a.nombre or a.ruc, Path(a.plan).read_bytes() if a.plan else None)
    for f in a.tc:
        print('TC:', s.cargar_tc_pdf(Path(f).read_bytes()), 'días')
    for f in a.historial:
        h = s.cargar_historial(a.ruc, Path(f).read_bytes())
        print('Historial:', len(h.asientos), 'asientos; haber habitual', h.cuenta_haber_habitual)
    lote = s.procesar(a.ruc, [(Path(f).name, Path(f).read_bytes()) for f in a.xml], cuenta_haber=a.haber, usar_ia=not a.sin_ia)
    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)
    tag = f'{lote.ruc}_{lote.periodo}'
    (out / f'NEWCONTASIS_COMPRAS_{tag}.xlsx').write_bytes(lote.excel_importacion())
    (out / f'REVISION_{tag}.xlsx').write_bytes(lote.excel_revision())
    (out / f'REPORTE_REVISION_{tag}.txt').write_text(lote.reporte_txt(), encoding='utf-8')
    print(lote.reporte_txt())
    print('\nArchivos en', out.resolve())


if __name__ == '__main__':
    main()
