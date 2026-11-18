# -*- coding: utf-8 -*-
"""
motor/bd.py — Conexión a Postgres (Neon) con la misma forma de uso que sqlite3, para que `memoria.py` no cambie.

Con DATABASE_URL en los secrets de Streamlit, todo se guarda en Postgres (Neon gratis) y sobrevive a los reinicios
y actualizaciones de Streamlit Cloud. Sin ella sigue el archivo SQLite local (se borra al reiniciar en la nube).

Lo que imita de sqlite3: execute / executemany / executescript / commit, filas que se leen como r['col'], r[0]
o dict(r), y los parámetros con '?'.
  · Una sola conexión reutilizada (con candado entre sesiones de Streamlit). Neon apaga la base tras 5 minutos sin uso
    y corta la conexión: si al usarla está cortada y no hay nada a medio guardar, se reconecta y se reintenta una vez.
  · Lecturas sin transacción abierta (autocommit); las escrituras abren BEGIN y se confirman con commit(), así un
    plan de cuentas se guarda completo o nada.
  · executemany en lotes de 500 (una ida y vuelta por lote, no por fila: con la base en internet es lo que más pesa).
"""
from __future__ import annotations

import re
import threading
from urllib.parse import urlparse


class ErrorBD(RuntimeError):
    """No se pudo conectar con la base de datos (DATABASE_URL mal escrita, clave errada, sin internet…)."""


class Fila(dict):
    """Como sqlite3.Row: r['col'], r[0] y dict(r)."""
    __slots__ = ('_vals',)

    def __init__(self, cols, vals):
        super().__init__(zip(cols, vals))
        self._vals = vals

    def __getitem__(self, k):
        return self._vals[k] if isinstance(k, int) else super().__getitem__(k)


class _Resultado:
    def __init__(self, filas: list, lastrowid=None):
        self._filas = filas
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._filas[0] if self._filas else None

    def fetchall(self):
        return list(self._filas)

    def __iter__(self):
        return iter(self._filas)


_ESCRITURA = re.compile(r'^\s*(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b', re.I)


def traducir(sql: str) -> str:
    """SQL escrito para sqlite → Postgres: parámetros '?' → '%s'; tipos del esquema."""
    sql = sql.replace('%', '%%').replace('?', '%s')
    sql = re.sub(r'INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY', sql, flags=re.I)
    sql = re.sub(r'\bREAL\b', 'DOUBLE PRECISION', sql)
    return sql


class ConexionPG:
    def __init__(self, url: str):
        self.url = url.strip()
        try:
            import psycopg2  # noqa: F401
        except ImportError as ex:
            raise ErrorBD('Falta el paquete psycopg2-binary (requirements.txt).') from ex
        self._lock = threading.RLock()
        self._cx = None
        self._en_transaccion = False
        self._conectar()

    @property
    def host(self) -> str:
        return urlparse(self.url).hostname or '?'

    def _conectar(self):
        import psycopg2
        try:
            self._cx = psycopg2.connect(self.url, connect_timeout=15, keepalives=1, keepalives_idle=60)
        except Exception as ex:
            raise ErrorBD(f'No se pudo conectar a Postgres ({self.host}): {str(ex).strip().splitlines()[0]}') from ex
        self._cx.autocommit = True
        self._en_transaccion = False

    def _cortada(self, ex) -> bool:
        import psycopg2
        return isinstance(ex, (psycopg2.OperationalError, psycopg2.InterfaceError)) or bool(self._cx and self._cx.closed)

    def _correr(self, fn):
        """Corre fn(cursor) con la conexión; si estaba cortada y no había escrituras pendientes, reconecta y reintenta."""
        with self._lock:
            for intento in (1, 2):
                if self._cx is None or self._cx.closed:
                    self._conectar()
                try:
                    with self._cx.cursor() as cur:
                        return fn(cur)
                except Exception as ex:
                    if self._cortada(ex):
                        pendiente = self._en_transaccion
                        try:
                            self._cx.close()
                        except Exception:
                            pass
                        self._cx, self._en_transaccion = None, False
                        if intento == 1 and not pendiente:
                            continue
                        raise ErrorBD('Se cortó la conexión con la base de datos; vuelva a intentarlo.') from ex
                    if self._en_transaccion:          # error de datos: se descarta lo que estaba a medio guardar
                        try:
                            self._cx.rollback() if not self._cx.autocommit else self._cx.cursor().execute('ROLLBACK')
                        except Exception:
                            pass
                        self._en_transaccion = False
                    raise

    def _abrir_si_escribe(self, cur, sql: str):
        if _ESCRITURA.match(sql) and not self._en_transaccion:
            cur.execute('BEGIN')
            self._en_transaccion = True

    def execute(self, sql: str, params=()):
        q = traducir(sql)

        def fn(cur):
            self._abrir_si_escribe(cur, sql)
            cur.execute(q, tuple(params))
            if cur.description is None:
                return _Resultado([])
            cols = [d[0] for d in cur.description]
            return _Resultado([Fila(cols, v) for v in cur.fetchall()])
        return self._correr(fn)

    def executemany(self, sql: str, filas):
        from psycopg2.extras import execute_batch
        q, filas = traducir(sql), [tuple(f) for f in filas]
        if not filas:
            return _Resultado([])

        def fn(cur):
            self._abrir_si_escribe(cur, sql)
            execute_batch(cur, q, filas, page_size=500)
            return _Resultado([])
        return self._correr(fn)

    def executescript(self, script: str):
        for st in (s.strip() for s in script.split(';')):
            if st:
                self.execute(st)
        self.commit()

    def commit(self):
        with self._lock:
            if self._en_transaccion and self._cx is not None and not self._cx.closed:
                with self._cx.cursor() as cur:
                    cur.execute('COMMIT')
            self._en_transaccion = False

    def close(self):
        with self._lock:
            if self._cx is not None:
                self._cx.close()
                self._cx = None
