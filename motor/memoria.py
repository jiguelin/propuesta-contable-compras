# -*- coding: utf-8 -*-
"""
motor/memoria.py — Persistencia: empresas, planes de cuentas, tipo de cambio, aprendizaje.

v1: SQLite (archivo local `datos/propuesta.db`). Todas las consultas pasan por esta clase, de modo
que migrar a Postgres (Supabase/Neon) para 100+ empresas es cambiar solo este módulo.
Variable de entorno PROPUESTA_DB → ruta del archivo SQLite.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

from .plan_cuentas import PlanCuentas
from .tipo_cambio import TC, HistorialTC

SCHEMA = """
CREATE TABLE IF NOT EXISTS empresas (
    ruc TEXT PRIMARY KEY, nombre TEXT NOT NULL, cuenta_haber TEXT DEFAULT '4212',
    alerta_monto REAL DEFAULT 20000, creado TEXT, actualizado TEXT);
CREATE TABLE IF NOT EXISTS plan_cuentas (
    ruc TEXT, codigo TEXT, descripcion TEXT, a_debe TEXT, a_haber TEXT, tipo TEXT,
    PRIMARY KEY (ruc, codigo));
CREATE TABLE IF NOT EXISTS tipo_cambio (
    fecha TEXT PRIMARY KEY, compra REAL, venta REAL, fuente TEXT, cargado TEXT);
CREATE TABLE IF NOT EXISTS aprendizaje (
    ruc TEXT, ruc_proveedor TEXT, concepto TEXT, cuenta TEXT, veces INTEGER DEFAULT 1,
    origen TEXT, ultima TEXT, PRIMARY KEY (ruc, ruc_proveedor, concepto, cuenta));
CREATE TABLE IF NOT EXISTS historial_stats (
    ruc TEXT, cuenta TEXT, veces INTEGER, descripcion TEXT, PRIMARY KEY (ruc, cuenta));
CREATE TABLE IF NOT EXISTS lotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ruc TEXT, periodo TEXT, fecha TEXT, n_xml INTEGER,
    n_ok INTEGER, n_excluidos INTEGER, n_revisar INTEGER, resumen TEXT);
"""


class Memoria:
    def __init__(self, ruta: str | os.PathLike | None = None):
        ruta = ruta or os.environ.get('PROPUESTA_DB') or Path(__file__).resolve().parent.parent / 'datos' / 'propuesta.db'
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        self.ruta = str(ruta)
        self.cx = sqlite3.connect(self.ruta, check_same_thread=False)
        self.cx.row_factory = sqlite3.Row
        self.cx.executescript(SCHEMA)

    # ---------------- empresas ----------------
    def empresas(self) -> list[dict]:
        return [dict(r) for r in self.cx.execute('SELECT * FROM empresas ORDER BY nombre')]

    def empresa(self, ruc: str) -> dict | None:
        r = self.cx.execute('SELECT * FROM empresas WHERE ruc=?', (ruc,)).fetchone()
        return dict(r) if r else None

    def guardar_empresa(self, ruc: str, nombre: str, cuenta_haber: str = '4212', alerta_monto: float = 20000):
        now = datetime.now().isoformat(timespec='seconds')
        self.cx.execute("""INSERT INTO empresas(ruc,nombre,cuenta_haber,alerta_monto,creado,actualizado) VALUES(?,?,?,?,?,?)
                           ON CONFLICT(ruc) DO UPDATE SET nombre=excluded.nombre, cuenta_haber=excluded.cuenta_haber,
                           alerta_monto=excluded.alerta_monto, actualizado=excluded.actualizado""",
                        (ruc, nombre, cuenta_haber, alerta_monto, now, now))
        self.cx.commit()

    def eliminar_empresa(self, ruc: str):
        for t in ('plan_cuentas', 'aprendizaje', 'historial_stats', 'lotes', 'empresas'):
            self.cx.execute(f'DELETE FROM {t} WHERE ruc=?', (ruc,))
        self.cx.commit()

    # ---------------- plan de cuentas ----------------
    def guardar_plan(self, ruc: str, plan: PlanCuentas):
        self.cx.execute('DELETE FROM plan_cuentas WHERE ruc=?', (ruc,))
        self.cx.executemany('INSERT OR REPLACE INTO plan_cuentas VALUES(?,?,?,?,?,?)',
                            [(ruc, c.codigo, c.descripcion, c.a_debe, c.a_haber, c.tipo) for c in plan.cuentas])
        self.cx.execute('UPDATE empresas SET actualizado=? WHERE ruc=?', (datetime.now().isoformat(timespec='seconds'), ruc))
        self.cx.commit()

    def plan(self, ruc: str) -> PlanCuentas | None:
        regs = [dict(r) for r in self.cx.execute('SELECT codigo,descripcion,a_debe,a_haber,tipo FROM plan_cuentas WHERE ruc=? ORDER BY codigo', (ruc,))]
        if not regs:
            return None
        e = self.empresa(ruc) or {}
        return PlanCuentas.desde_registros(regs, empresa=e.get('nombre', ''), ruc=ruc)

    def plan_resumen(self, ruc: str) -> int:
        return self.cx.execute('SELECT COUNT(*) FROM plan_cuentas WHERE ruc=?', (ruc,)).fetchone()[0]

    # ---------------- tipo de cambio ----------------
    def guardar_tc(self, items: list[TC]) -> int:
        now = datetime.now().isoformat(timespec='seconds')
        self.cx.executemany("""INSERT INTO tipo_cambio(fecha,compra,venta,fuente,cargado) VALUES(?,?,?,?,?)
                               ON CONFLICT(fecha) DO UPDATE SET compra=excluded.compra, venta=excluded.venta, fuente=excluded.fuente, cargado=excluded.cargado""",
                            [(t.fecha.isoformat(), t.compra, t.venta, t.fuente, now) for t in items])
        self.cx.commit()
        return len(items)

    def tc(self) -> HistorialTC:
        return HistorialTC([TC(date.fromisoformat(r['fecha']), r['compra'], r['venta'], r['fuente'])
                            for r in self.cx.execute('SELECT * FROM tipo_cambio')])

    # ---------------- aprendizaje (memoria proveedor + concepto) ----------------
    def aprender(self, ruc: str, ruc_proveedor: str, concepto: str, cuenta: str, origen: str = 'correccion', veces: int = 1):
        now = datetime.now().isoformat(timespec='seconds')
        self.cx.execute("""INSERT INTO aprendizaje(ruc,ruc_proveedor,concepto,cuenta,veces,origen,ultima) VALUES(?,?,?,?,?,?,?)
                           ON CONFLICT(ruc,ruc_proveedor,concepto,cuenta) DO UPDATE SET veces=veces+excluded.veces, ultima=excluded.ultima, origen=excluded.origen""",
                        (ruc, ruc_proveedor, concepto, cuenta, veces, origen, now))
        self.cx.commit()

    def memoria_proveedor(self, ruc: str, ruc_proveedor: str) -> list[dict]:
        """[{concepto, cuenta, veces, origen}] ordenado por veces desc."""
        return [dict(r) for r in self.cx.execute(
            'SELECT concepto,cuenta,veces,origen,ultima FROM aprendizaje WHERE ruc=? AND ruc_proveedor=? ORDER BY veces DESC', (ruc, ruc_proveedor))]

    def memoria_completa(self, ruc: str) -> list[dict]:
        return [dict(r) for r in self.cx.execute('SELECT * FROM aprendizaje WHERE ruc=? ORDER BY ruc_proveedor, veces DESC', (ruc,))]

    def olvidar(self, ruc: str, ruc_proveedor: str | None = None):
        if ruc_proveedor:
            self.cx.execute('DELETE FROM aprendizaje WHERE ruc=? AND ruc_proveedor=?', (ruc, ruc_proveedor))
        else:
            self.cx.execute('DELETE FROM aprendizaje WHERE ruc=?', (ruc,))
        self.cx.commit()

    # ---------------- historial (estadísticas de cuentas usadas) ----------------
    def guardar_historial_stats(self, ruc: str, frecuencia: dict, descripciones: dict, acumular: bool = True):
        for cuenta, n in frecuencia.items():
            if acumular:
                self.cx.execute("""INSERT INTO historial_stats(ruc,cuenta,veces,descripcion) VALUES(?,?,?,?)
                                   ON CONFLICT(ruc,cuenta) DO UPDATE SET veces=veces+excluded.veces""",
                                (ruc, cuenta, n, descripciones.get(cuenta, '')))
            else:
                self.cx.execute('INSERT OR REPLACE INTO historial_stats VALUES(?,?,?,?)', (ruc, cuenta, n, descripciones.get(cuenta, '')))
        self.cx.commit()

    def historial_stats(self, ruc: str) -> dict[str, int]:
        return {r['cuenta']: r['veces'] for r in self.cx.execute('SELECT cuenta,veces FROM historial_stats WHERE ruc=?', (ruc,))}

    # ---------------- lotes ----------------
    def registrar_lote(self, ruc: str, periodo: str, n_xml: int, n_ok: int, n_excluidos: int, n_revisar: int, resumen: dict | None = None):
        self.cx.execute('INSERT INTO lotes(ruc,periodo,fecha,n_xml,n_ok,n_excluidos,n_revisar,resumen) VALUES(?,?,?,?,?,?,?,?)',
                        (ruc, periodo, datetime.now().isoformat(timespec='seconds'), n_xml, n_ok, n_excluidos, n_revisar, json.dumps(resumen or {}, ensure_ascii=False)))
        self.cx.commit()

    def lotes(self, ruc: str | None = None) -> list[dict]:
        q = 'SELECT * FROM lotes' + (' WHERE ruc=?' if ruc else '') + ' ORDER BY id DESC LIMIT 50'
        return [dict(r) for r in self.cx.execute(q, (ruc,) if ruc else ())]
