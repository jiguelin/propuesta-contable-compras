# -*- coding: utf-8 -*-
"""
motor/ia.py — Consulta a Claude (Anthropic) SOLO para casos dudosos.

Regla fundamental: la IA elige exclusivamente entre las cuentas candidatas que le pasa el sistema
(cuentas reales del plan de la empresa). Nunca inventa una cuenta.

Usa el SDK `anthropic` si está instalado; si no, llama a la API con urllib (sin dependencias).
Variable de entorno ANTHROPIC_API_KEY (o st.secrets en Streamlit).
"""
from __future__ import annotations

import json
import os
import urllib.request

MODELO_DEFECTO = os.environ.get('PROPUESTA_MODELO_IA', 'claude-haiku-4-5-20251001')


def _llamar(prompt: str, api_key: str, modelo: str, max_tokens: int = 300) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(model=modelo, max_tokens=max_tokens, messages=[{'role': 'user', 'content': prompt}])
        return msg.content[0].text
    except ImportError:
        body = json.dumps({'model': modelo, 'max_tokens': max_tokens, 'messages': [{'role': 'user', 'content': prompt}]}).encode()
        req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=body, method='POST',
                                     headers={'x-api-key': api_key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        return ''.join(b.get('text', '') for b in data.get('content', []))


def crear_ia(api_key: str | None = None, modelo: str = MODELO_DEFECTO, max_candidatas: int = 18):
    """Devuelve una función ia(propuesta, contexto) -> (cuenta, confianza, razón) | None, o None si no hay API key."""
    api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return None

    def ia(p, ctx):
        from . import pcge, reglas as kb
        from .clasificador import candidatas_para
        c = p.c
        # candidatas: las de la familia + las más usadas por la empresa (historial) + la actual
        cands = {cu.codigo: cu for cu in p.candidatas}
        if ctx.plan:
            for cod, _ in sorted(ctx.historial_stats.items(), key=lambda x: -x[1])[:8]:
                cu = ctx.plan.get(cod)
                if cu:
                    cands.setdefault(cod, cu)
            if p.cuenta and ctx.plan.get(p.cuenta):
                cands.setdefault(p.cuenta, ctx.plan.get(p.cuenta))
            # si la familia dominante no está clara, añadir cuentas hoja de familias de gasto frecuentes
            if len(cands) < 6:
                for pref in ('656', '638', '6329', '6343', '6371', '601', '336'):
                    for cu in candidatas_para(pref, ctx)[:2]:
                        cands.setdefault(cu.codigo, cu)
        cands = {k: v for k, v in cands.items() if not kb.cuenta_bloqueada(k, getattr(ctx, 'reglas', []))}
        if not cands:
            return None
        lista = list(cands.values())[:max_candidatas]
        items = '\n'.join(f'- {l.cantidad} {l.unidad} {l.descripcion[:90]} → {c.simbolo} {l.valor_venta}' for l in c.lineas[:25])
        cuentas_txt = '\n'.join(f'{cu.codigo} | {cu.descripcion[:80]}' + (f' | usada {ctx.historial_stats[cu.codigo]}x por la empresa' if ctx.historial_stats.get(cu.codigo) else '') for cu in lista)
        prompt = f"""Eres un contador peruano experto en el PCGE 2019 y en registrar compras.
Debes elegir UNA cuenta contable para el gasto/compra de esta factura, ÚNICAMENTE entre las cuentas candidatas listadas (son las que existen en el plan de cuentas de la empresa). Está PROHIBIDO proponer una cuenta que no esté en la lista.

Empresa: {ctx.plan.empresa if ctx.plan else ''} (giro deducible del plan/historial).
Proveedor: {c.nombre_emisor} (RUC {c.ruc_emisor}). Comprobante {c.tipo_nombre} {c.serie_numero} del {c.fecha_emision}. Total {c.simbolo} {c.importe_total}.
{'Con detracción.' if c.tiene_detraccion else ''}
Ítems:
{items or '(sin detalle)'}

Propuesta preliminar por reglas: {p.cuenta or '(ninguna)'} — {p.explicacion}

Cuentas candidatas (código | descripción):
{cuentas_txt}

Referencia PCGE: {pcge.NATURALEZA_PCGE.get(p.familia[:2], '')}

Está PROHIBIDO proponer cualquier cuenta fuera de esa lista.

Responde SOLO un JSON: {{"cuenta": "<código exacto de la lista>", "confianza": <0-100>, "razon": "<una línea, máx 120 caracteres>"}}"""
        raw = _llamar(prompt, api_key, modelo)
        s, e = raw.find('{'), raw.rfind('}') + 1
        data = json.loads(raw[s:e])
        cuenta = str(data.get('cuenta', '')).strip()
        if cuenta not in cands:
            return None
        return cuenta, int(data.get('confianza', 80)), str(data.get('razon', ''))[:160]

    return ia
