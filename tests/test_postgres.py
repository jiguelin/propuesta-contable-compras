# -*- coding: utf-8 -*-
"""Pruebas propias de Postgres (Neon). Solo corren con TEST_DATABASE_URL (ver conftest.py)."""
import os
import sqlite3
import threading
from datetime import date

import pytest

from motor.memoria import Memoria
from motor.reglas import Regla
from motor.tipo_cambio import TC

URL = os.environ.get('TEST_DATABASE_URL', '').strip()
pytestmark = pytest.mark.skipif(not URL, reason='sin TEST_DATABASE_URL')


def test_usa_postgres_y_guarda_entre_reinicios(tmp_path):
    m = Memoria(tmp_path / 'no-se-usa.db')
    assert m.es_postgres and m.descripcion.startswith('Postgres')
    m.guardar_empresa('20611889683', 'ALQUMIN EIRL')
    m.guardar_tc([TC(date(2026, 9, 1), 3.362, 3.367, 'SUNAT')])
    m.aprender('20611889683', '20999999999', '656', '6560094', mes='2026-10')
    m.aprender('20611889683', '20999999999', '656', '6560094', mes='2026-10')
    rid = m.guardar_regla(Regla(ruc='20611889683', nombre='prueba', palabras='X', cuenta='6560094'))
    m2 = Memoria(tmp_path / 'no-se-usa.db')                          # "reinicio" del app
    assert m2.empresa('20611889683')['nombre'] == 'ALQUMIN EIRL'
    assert m2.tc().venta(date(2026, 9, 1)) == 3.367                    # sin pérdida de decimales
    assert m2.memoria_proveedor('20611889683', '20999999999')[0]['veces'] == 2
    assert rid > 0 and any(r.id == rid for r in m2.reglas('20611889683'))
    assert not (tmp_path / 'no-se-usa.db').exists()


def test_copia_lo_que_habia_en_sqlite(tmp_path, monkeypatch):
    ruta = tmp_path / 'propuesta.db'
    monkeypatch.delenv('DATABASE_URL')
    viejo = Memoria(ruta)                                            # lo que había en Streamlit antes de Neon
    viejo.guardar_empresa('20615042456', 'SOLUCIONES RADIOLOGICAS')
    viejo.aprender('20615042456', '20100000002', '656', '6560094', mes='2026-10')
    id_viejo = viejo.guardar_regla(Regla(ruc='20615042456', nombre='vieja', palabras='Y', cuenta='6560094'))
    viejo.cx.close()
    monkeypatch.setenv('DATABASE_URL', URL)
    m = Memoria(ruta)
    assert m.copiados['empresas'] == 1 and m.copiados['reglas'] == 1
    assert m.empresa('20615042456')['nombre'] == 'SOLUCIONES RADIOLOGICAS'
    assert m.memoria_proveedor('20615042456', '20100000002')[0]['cuenta'] == '6560094'
    nuevo = m.guardar_regla(Regla(ruc='20615042456', nombre='nueva', palabras='Z', cuenta='6560094'))
    assert nuevo > id_viejo                                          # la secuencia siguió después de los copiados
    assert Memoria(ruta).copiados == {}                              # no se vuelve a copiar


def test_reconecta_si_la_base_corto_la_conexion(tmp_path):
    import psycopg2
    m = Memoria(tmp_path / 'x.db')
    m.guardar_empresa('20611889683', 'ALQUMIN EIRL')
    pid = m.cx.execute('SELECT pg_backend_pid()').fetchone()[0]
    adm = psycopg2.connect(URL)
    adm.autocommit = True
    adm.cursor().execute('SELECT pg_terminate_backend(%s)', (pid,))    # como Neon al apagarse por inactividad
    adm.close()
    assert m.empresa('20611889683')['nombre'] == 'ALQUMIN EIRL'
    assert m.cx.execute('SELECT pg_backend_pid()').fetchone()[0] != pid


def test_varias_sesiones_a_la_vez(tmp_path):
    m = Memoria(tmp_path / 'x.db')
    errores = []

    def trabajo(i):
        try:
            for j in range(15):
                m.aprender('R', f'P{i}', '656', '6560094', mes='2026-10')
                m.memoria_proveedor('R', f'P{i}')
        except Exception as ex:  # pragma: no cover
            errores.append(ex)
    hilos = [threading.Thread(target=trabajo, args=(i,)) for i in range(8)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert not errores
    assert all(m.memoria_proveedor('R', f'P{i}')[0]['veces'] == 15 for i in range(8))


def test_un_error_no_deja_la_conexion_trabada(tmp_path):
    m = Memoria(tmp_path / 'x.db')
    with pytest.raises(Exception):
        m.cx.execute('INSERT INTO empresas(ruc,nombre) VALUES(?,?)', ('X', None))   # nombre NOT NULL
    m.guardar_empresa('20611889683', 'ALQUMIN EIRL')
    assert m.empresa('20611889683')


def test_respaldo_db_se_restaura_en_postgres(tmp_path, monkeypatch):
    monkeypatch.delenv('DATABASE_URL')
    viejo = Memoria(tmp_path / 'a.db')
    viejo.guardar_empresa('20611889683', 'ALQUMIN EIRL')
    data = viejo.respaldo_sqlite()
    monkeypatch.setenv('DATABASE_URL', URL)
    m = Memoria(tmp_path / 'otro.db')                                 # el SQLite original ya no existe (reinicio)
    assert m.empresas() == []
    assert m.restaurar_respaldo(data)['empresas'] == 1
    assert m.empresa('20611889683')['nombre'] == 'ALQUMIN EIRL'
