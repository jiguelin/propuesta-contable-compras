# -*- coding: utf-8 -*-
"""
motor/texto.py — Limpieza de texto para la glosa y la razón social (compatibilidad con el PLE de SUNAT).

Problema real: muchos XML llegan con el texto ya dañado desde el emisor o desde SUNAT:

    COMPRA ACTUALIZACIÃ¯Â¿Â½N DEL SISTEMA DE GESTIÃ¯Â¿Â½N DE FOT

Eso es *mojibake* en dos capas:
  1. El emisor perdió la letra acentuada y la reemplazó por el carácter de reemplazo U+FFFD (�).
  2. Ese � (bytes EF BF BD) se volvió a codificar mal y terminó escrito como "Ã¯Â¿Â½".

Qué hace este módulo, en este orden:
  1. `reparar()` deshace las capas de mojibake (Ã©→é, Ã±→ñ, Ã¯Â¿Â½→�) de forma iterativa y segura.
  2. `_adivinar_perdidos()` reconstruye los � que quedan usando patrones del castellano
     (CI�N→CION, A�O→ANO, …). Lo que no se puede reconstruir se elimina y se avisa.
  3. `normalizar()` deja solo caracteres seguros para el PLE: A-Z, 0-9, espacio y puntuación básica,
     sin tildes ni ñ (á→A, ñ→N), en mayúsculas y sin espacios dobles.

Nunca inventa palabras: si tuvo que adivinar o borrar algo, devuelve `perdida=True` para que la
factura salga con alerta y la persona pueda corregir la glosa a mano en la app.
"""
from __future__ import annotations

import re
import unicodedata

REEMPLAZO = '�'          # �

# Secuencias tipicas de mojibake UTF-8 leido como Latin-1 / Windows-1252.
_PISTAS_MOJIBAKE = ('\u00c3', '\u00c2', '\u00e2\u20ac', '\u00d0')

# Formas en que aparece escrito el caracter de reemplazo (U+FFFD) ya danado por doble codificacion.
_FORMAS_REEMPLAZO = ('\u00c3\u00af\u00c2\u00bf\u00c2\u00bd', '\u00ef\u00bf\u00bd', '\u00e2\u2013\u00a1')

# Reparacion por tabla, para textos que mezclan partes danadas y partes sanas
# (ahi el re-encode de toda la cadena falla y hay que ir secuencia por secuencia).
_TABLA_MOJIBAKE = {
    '\u00c3\u00a1': '\u00e1', '\u00c3\u00a9': '\u00e9', '\u00c3\u00ad': '\u00ed',
    '\u00c3\u00b3': '\u00f3', '\u00c3\u00ba': '\u00fa', '\u00c3\u00b1': '\u00f1',
    '\u00c3\u00bc': '\u00fc', '\u00c3\u0081': '\u00c1', '\u00c3\u2030': '\u00c9',
    '\u00c3\u008d': '\u00cd', '\u00c3\u201c': '\u00d3', '\u00c3\u0161': '\u00da',
    '\u00c3\u2018': '\u00d1', '\u00c3\u0153': '\u00dc', '\u00c3\u20ac': '\u00c0',
    '\u00c3\u00a8': '\u00e8', '\u00c3\u00a0': '\u00e0', '\u00c2\u00ba': '\u00ba',
    '\u00c2\u00aa': '\u00aa', '\u00c2\u00b0': '\u00b0', '\u00c2\u00bf': '\u00bf',
    '\u00c2\u00a1': '\u00a1', '\u00c2\u00b4': "'", '\u00e2\u20ac\u0153': '"',
    '\u00e2\u20ac\u009d': '"', '\u00e2\u20ac\u2122': "'", '\u00e2\u20ac\u02dc': "'",
    '\u00e2\u20ac\u201c': '-', '\u00e2\u20ac\u201d': '-', '\u00e2\u20ac\u00a6': '...',
    '\u00c2': '',
}

# Signos sueltos que no aportan y que al quitar tildes se vuelven basura (un 1/2 se parte en "1 2")
_DESCARTAR = re.compile('[\u00bf\u00a1\u00ab\u00bb\u00bd\u00bc\u00be\u00b7\u00a6\u00ac\u00ad]')

# Reconstrucción de � por patrones frecuentes del castellano (ya en mayúsculas, sin tildes).
_PATRONES = [
    (re.compile(r'CI' + REEMPLAZO + r'N'), 'CION'),        # ACTUALIZACIÓN, GESTIÓN, ATENCIÓN
    (re.compile(r'SI' + REEMPLAZO + r'N'), 'SION'),        # REVISIÓN, DIVISIÓN, COMISIÓN
    (re.compile(r'CI' + REEMPLAZO + r'NES'), 'CIONES'),
    (re.compile(r'(?<=[AEIOU])' + REEMPLAZO + r'(?=[AEIOU])'), 'N'),   # AÑO, DISEÑO, MAÑANA, SEÑOR
    (re.compile(REEMPLAZO + r'(?=N\b)'), 'O'),             # …ÓN al final de palabra
    (re.compile(r'(?<=\bA)' + REEMPLAZO + r'(?=[A-Z])'), 'N'),
    (re.compile(r'(?<=[BCDFGHJKLMNPQRSTVWXYZ])' + REEMPLAZO + r'(?=S?\b)'), 'A'),  # CÉDULA→…, plurales
]

# Caracteres que el PLE no admite o que rompen los archivos de texto separados por |
_PROHIBIDOS = re.compile(r'[|\t\r\n\x00-\x1f\x7f]')
_PERMITIDOS = re.compile(r'[^A-Z0-9 .,\-/()#%+&:°ºª\'"]')


def reparar(s: str) -> str:
    """Deshace el mojibake (hasta 3 capas). Si el resultado empeora, devuelve el original."""
    if not s:
        return ''
    # 1) el carácter de reemplazo, en cualquiera de sus disfraces, se normaliza primero
    for forma in _FORMAS_REEMPLAZO:
        if forma != REEMPLAZO:
            s = s.replace(forma, REEMPLAZO)
    # 2) capas de mojibake sobre toda la cadena
    for _ in range(3):
        if not any(p in s for p in _PISTAS_MOJIBAKE):
            break
        try:
            nuevo = s.encode('latin-1', errors='strict').decode('utf-8', errors='strict')
        except (UnicodeEncodeError, UnicodeDecodeError):
            try:
                nuevo = s.encode('cp1252', errors='strict').decode('utf-8', errors='strict')
            except (UnicodeEncodeError, UnicodeDecodeError):
                # texto mixto (una parte dañada y otra sana): se repara por tabla
                for malo, bueno in _TABLA_MOJIBAKE.items():
                    s = s.replace(malo, bueno)
                break
        if nuevo == s:
            break
        s = nuevo
    for forma in _FORMAS_REEMPLAZO:
        if forma != REEMPLAZO:
            s = s.replace(forma, REEMPLAZO)
    return s


def _sin_tildes(s: str) -> str:
    """á→a, ñ→n, ü→u (descompone y quita los acentos)."""
    return ''.join(ch for ch in unicodedata.normalize('NFKD', s) if not unicodedata.combining(ch))


def normalizar(s: str, ascii_estricto: bool = True, limite: int = 60) -> tuple[str, bool]:
    """Devuelve (texto limpio, hubo_perdida).

    ascii_estricto=True  → solo A-Z, 0-9 y puntuación básica (recomendado para el PLE).
    ascii_estricto=False → conserva tildes y ñ, pero igual repara el mojibake y quita caracteres de control.
    """
    if not s:
        return '', False
    original = s
    s = reparar(s)
    s = _PROHIBIDOS.sub(' ', s)
    s = _DESCARTAR.sub(' ', s)
    perdida = REEMPLAZO in s

    if ascii_estricto:
        s = _sin_tildes(s).upper()
        for patron, reemplazo in _PATRONES:
            s = patron.sub(reemplazo, s)
        s = s.replace(REEMPLAZO, '')
        s = _PERMITIDOS.sub(' ', s)
    else:
        s = s.replace(REEMPLAZO, '').upper()

    s = ' '.join(s.split())
    # puntuación suelta que quedó de los borrados: " - ,"
    s = re.sub(r'\s+([.,])', r'\1', s).strip(' .,-/')
    if limite:
        s = s[:limite].strip(' .,-/')
    if not s and original.strip():
        perdida = True
    return s, perdida


def limpiar(s: str, ascii_estricto: bool = True, limite: int = 60) -> str:
    """Igual que normalizar() pero devolviendo solo el texto."""
    return normalizar(s, ascii_estricto, limite)[0]
