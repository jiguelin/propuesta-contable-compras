# -*- coding: utf-8 -*-
"""Con TEST_DATABASE_URL (un Postgres de pruebas, NUNCA el de producción) todas las pruebas corren contra Postgres:
cada prueba empieza con la base vacía.   TEST_DATABASE_URL=postgresql://... python -m pytest -q"""
import os

import pytest


@pytest.fixture(autouse=True)
def _postgres_de_prueba(monkeypatch):
    url = os.environ.get('TEST_DATABASE_URL', '').strip()
    if not url:
        monkeypatch.delenv('DATABASE_URL', raising=False)
        yield
        return
    import psycopg2
    cx = psycopg2.connect(url)
    cx.autocommit = True
    with cx.cursor() as cur:
        cur.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public;')
    cx.close()
    monkeypatch.setenv('DATABASE_URL', url)
    yield
