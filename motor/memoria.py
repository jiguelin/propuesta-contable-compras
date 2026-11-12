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
from .reglas import REGLAS_SISTEMA, Regla
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
CREATE TABLE IF NOT EXISTS aprendizaje_mes (
    ruc TEXT, ruc_proveedor TEXT, concepto TEXT, cuenta TEXT, mes TEXT, origen TEXT, veces REAL DEFAULT 1,
    PRIMARY KEY (ruc, ruc_proveedor, concepto, cuenta, mes, origen));
CREATE TABLE IF NOT EXISTS historial_stats (
    ruc TEXT, cuenta TEXT, veces INTEGER, descripcion TEXT, PRIMARY KEY (ruc, cuenta));
CREATE TABLE IF NOT EXISTS reglas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ruc TEXT DEFAULT '*', tipo TEXT DEFAULT 'cuenta', nombre TEXT,
    palabras TEXT, ruc_proveedor TEXT, cuenta TEXT, alternativas TEXT, nota TEXT,
    prioridad INTEGER DEFAULT 100, activa INTEGER DEFAULT 1, creado TEXT);
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
        self._migrar_aprendizaje_mes()

    def _migrar_aprendizaje_mes(self):
        """v0.3.5: la memoria pasa a guardarse por mes (para que lo reciente pese más). Lo aprendido antes se lleva
        al mes de su último uso."""
        if self.cx.execute('SELECT COUNT(*) FROM aprendizaje_mes').fetchone()[0]:
            return
        self.cx.execute("""INSERT OR IGNORE INTO aprendizaje_mes(ruc,ruc_proveedor,concepto,cuenta,mes,origen,veces)
                           SELECT ruc,ruc_proveedor,concepto,cuenta,substr(COALESCE(ultima,''),1,7),COALESCE(origen,''),veces
                           FROM aprendizaje""")
        self.cx.commit()

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
        for t in ('plan_cuentas', 'aprendizaje', 'aprendizaje_mes', 'historial_stats', 'lotes', 'empresas'):
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
    # Cada uso se guarda con su MES. Al consultar, lo reciente pesa más: el mes más reciente de la empresa vale 1,
    # el anterior 0.6, el otro 0.36… (PESO_MES ** meses atrás), como en el app de Ralumin. Así, si un proveedor se
    # registró mal mucho tiempo y en los últimos meses se corrigió, gana lo corregido. Las reglas contables siguen
    # mandando sobre la memoria (eso lo decide el clasificador).
    PESO_MES = 0.6
    PESO_SIN_FECHA = 0.1

    def aprender(self, ruc: str, ruc_proveedor: str, concepto: str, cuenta: str, origen: str = 'correccion', veces: float = 1,
                 mes: str | None = None):
        now = datetime.now().isoformat(timespec='seconds')
        mes = (mes if mes is not None else now[:7])[:7]
        self.cx.execute("""INSERT INTO aprendizaje(ruc,ruc_proveedor,concepto,cuenta,veces,origen,ultima) VALUES(?,?,?,?,?,?,?)
                           ON CONFLICT(ruc,ruc_proveedor,concepto,cuenta) DO UPDATE SET veces=veces+excluded.veces, ultima=excluded.ultima, origen=excluded.origen""",
                        (ruc, ruc_proveedor, concepto, cuenta, int(round(veces)) or 1, origen, now))
        self.cx.execute("""INSERT INTO aprendizaje_mes(ruc,ruc_proveedor,concepto,cuenta,mes,origen,veces) VALUES(?,?,?,?,?,?,?)
                           ON CONFLICT(ruc,ruc_proveedor,concepto,cuenta,mes,origen) DO UPDATE SET veces=veces+excluded.veces""",
                        (ruc, ruc_proveedor, concepto, cuenta, mes, origen, veces))
        self.cx.commit()

    def reemplazar_historial(self, ruc: str, filas: list[tuple], meses: set[str]):
        """Carga del Diario: [(ruc_proveedor, concepto, cuenta, mes, veces)]. Reemplaza lo que había del historial en
        esos meses, así volver a subir el mismo Diario (o uno corregido) no duplica."""
        for mes in meses:
            self.cx.execute("DELETE FROM aprendizaje_mes WHERE ruc=? AND origen='historial' AND mes=?", (ruc, mes))
        self.cx.executemany("""INSERT INTO aprendizaje_mes(ruc,ruc_proveedor,concepto,cuenta,mes,origen,veces) VALUES(?,?,?,?,?,'historial',?)
                               ON CONFLICT(ruc,ruc_proveedor,concepto,cuenta,mes,origen) DO UPDATE SET veces=veces+excluded.veces""",
                            [(ruc, rp, co, cu, me, n) for rp, co, cu, me, n in filas])
        now = datetime.now().isoformat(timespec='seconds')
        self.cx.executemany("""INSERT INTO aprendizaje(ruc,ruc_proveedor,concepto,cuenta,veces,origen,ultima) VALUES(?,?,?,?,?,'historial',?)
                               ON CONFLICT(ruc,ruc_proveedor,concepto,cuenta) DO UPDATE SET ultima=excluded.ultima""",
                            [(ruc, rp, co, cu, int(n), now) for rp, co, cu, me, n in filas])
        self.cx.commit()

    def mes_referencia(self, ruc: str) -> str:
        r = self.cx.execute("SELECT MAX(mes) FROM aprendizaje_mes WHERE ruc=? AND mes<>''", (ruc,)).fetchone()
        return r[0] or ''

    @classmethod
    def peso(cls, mes: str, mes_ref: str) -> float:
        if not mes or not mes_ref:
            return cls.PESO_SIN_FECHA if mes_ref else 1.0
        try:
            atras = (int(mes_ref[:4]) * 12 + int(mes_ref[5:7])) - (int(mes[:4]) * 12 + int(mes[5:7]))
        except ValueError:
            return cls.PESO_SIN_FECHA
        return cls.PESO_MES ** max(atras, 0)

    def _agregado(self, ruc: str, ruc_proveedor: str | None = None) -> list[dict]:
        mes_ref = self.mes_referencia(ruc)
        q = 'SELECT ruc_proveedor,concepto,cuenta,mes,origen,veces FROM aprendizaje_mes WHERE ruc=?'
        args = [ruc]
        if ruc_proveedor is not None:
            q += ' AND ruc_proveedor=?'
            args.append(ruc_proveedor)
        acc: dict = {}
        for r in self.cx.execute(q, args):
            k = (r['ruc_proveedor'], r['concepto'], r['cuenta'])
            a = acc.setdefault(k, {'ruc_proveedor': k[0], 'concepto': k[1], 'cuenta': k[2], 'veces': 0.0, 'peso': 0.0,
                                   'ultima': '', 'origen': ''})
            a['veces'] += r['veces']
            a['peso'] += r['veces'] * self.peso(r['mes'], mes_ref)
            if r['mes'] >= a['ultima']:
                a['ultima'], a['origen'] = r['mes'], r['origen']
        out = []
        for a in acc.values():
            a['veces'] = int(round(a['veces'])) or 1
            a['peso'] = round(a['peso'], 3)
            out.append(a)
        return out

    def memoria_proveedor(self, ruc: str, ruc_proveedor: str) -> list[dict]:
        """[{concepto, cuenta, veces, peso, ultima (mes), origen}] ordenado por PESO (lo reciente primero), luego veces."""
        return sorted(self._agregado(ruc, ruc_proveedor), key=lambda a: (-a['peso'], -a['veces'], a['cuenta']))

    def memoria_completa(self, ruc: str) -> list[dict]:
        return sorted(self._agregado(ruc), key=lambda a: (a['ruc_proveedor'], -a['peso'], -a['veces']))

    def olvidar(self, ruc: str, ruc_proveedor: str | None = None):
        for t in ('aprendizaje', 'aprendizaje_mes'):
            if ruc_proveedor:
                self.cx.execute(f'DELETE FROM {t} WHERE ruc=? AND ruc_proveedor=?', (ruc, ruc_proveedor))
            else:
                self.cx.execute(f'DELETE FROM {t} WHERE ruc=?', (ruc,))
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

    # ---------------- reglas (base de conocimiento contable) ----------------
    def reglas(self, ruc: str | None = None, incluir_sistema: bool = True) -> list[Regla]:
        """Reglas de sistema + globales ('*') + las de esta empresa, ordenadas por prioridad."""
        q = "SELECT * FROM reglas WHERE ruc='*'" + (' OR ruc=?' if ruc else '')
        filas = [dict(r) for r in self.cx.execute(q, (ruc,) if ruc else ())]
        propias = [Regla(**{k: v for k, v in f.items() if k != 'creado'}) for f in filas]
        todas = (list(REGLAS_SISTEMA) if incluir_sistema else []) + propias
        return sorted(todas, key=lambda r: (r.prioridad, r.id))

    def guardar_regla(self, r: Regla) -> int:
        if r.id and r.id > 0:
            self.cx.execute('''UPDATE reglas SET ruc=?, tipo=?, nombre=?, palabras=?, ruc_proveedor=?, cuenta=?,
                               alternativas=?, nota=?, prioridad=?, activa=? WHERE id=?''',
                            (r.ruc, r.tipo, r.nombre, r.palabras, r.ruc_proveedor, r.cuenta,
                             r.alternativas, r.nota, r.prioridad, r.activa, r.id))
            self.cx.commit()
            return r.id
        cur = self.cx.execute('''INSERT INTO reglas(ruc,tipo,nombre,palabras,ruc_proveedor,cuenta,alternativas,nota,prioridad,activa,creado)
                                 VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                              (r.ruc, r.tipo, r.nombre, r.palabras, r.ruc_proveedor, r.cuenta,
                               r.alternativas, r.nota, r.prioridad, r.activa, datetime.now().isoformat(timespec='seconds')))
        self.cx.commit()
        return cur.lastrowid

    def eliminar_regla(self, id_regla: int):
        self.cx.execute('DELETE FROM reglas WHERE id=?', (id_regla,))
        self.cx.commit()

    # ---------------- lotes ----------------
    def registrar_lote(self, ruc: str, periodo: str, n_xml: int, n_ok: int, n_excluidos: int, n_revisar: int, resumen: dict | None = None):
        self.cx.execute('INSERT INTO lotes(ruc,periodo,fecha,n_xml,n_ok,n_excluidos,n_revisar,resumen) VALUES(?,?,?,?,?,?,?,?)',
                        (ruc, periodo, datetime.now().isoformat(timespec='seconds'), n_xml, n_ok, n_excluidos, n_revisar, json.dumps(resumen or {}, ensure_ascii=False)))
        self.cx.commit()

    def lotes(self, ruc: str | None = None) -> list[dict]:
        q = 'SELECT * FROM lotes' + (' WHERE ruc=?' if ruc else '') + ' ORDER BY id DESC LIMIT 50'
        return [dict(r) for r in self.cx.execute(q, (ruc,) if ruc else ())]
