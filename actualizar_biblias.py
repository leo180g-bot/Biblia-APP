#!/usr/bin/env python3
"""
Actualiza index.html con las Biblias (.json) que haya en la misma carpeta.

Uso:
  python3 actualizar_biblias.py                 # revisa una vez y termina
  python3 actualizar_biblias.py --cada 60       # vuelve a revisar cada 60 segundos
  python3 actualizar_biblias.py --carpeta RUTA --html RUTA/index.html

Solo usa la biblioteca estándar de Python 3.8+. Los JSON que no sean una Biblia
(o que estén dañados) se omiten con un aviso. index.html solo se reescribe si
algo cambió, y las Biblias cuyo .json se borre desaparecen del index.html.
"""
import argparse, base64, gzip, html, json, re, sys, time
from pathlib import Path

INI, FIN = '<!--BIBLIAS_INICIO-->', '<!--BIBLIAS_FIN-->'
IGNORAR = {'biblias.json', 'package.json', 'package-lock.json', 'manifest.json', 'composer.json', 'tsconfig.json'}

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def es_biblia(d):
    libros = d.get('books') if isinstance(d, dict) else d
    if isinstance(d, dict) and isinstance(d.get('verses'), list):
        return True
    if isinstance(libros, dict) and len(libros) >= 60:
        return True
    if isinstance(libros, list) and libros:
        p = libros[0]
        if isinstance(p, dict):
            return 'chapters' in p or any(k in p for k in ('verse', 'text', 'verse_text'))
        return isinstance(p, list)
    return isinstance(d, dict) and len(d) >= 60 and all(isinstance(v, (dict, list)) for v in d.values())


def podar(d):
    """Si el JSON usa libros -> capítulos -> items, descarta campos que el lector no necesita."""
    libros = d.get('books') if isinstance(d, dict) else d
    try:
        if isinstance(libros, list) and 'items' in libros[0]['chapters'][0]:
            def cap(c):
                o = {'usfm': c['usfm']} if c.get('usfm') else {'human': c.get('human')}
                o['items'] = [{'type': i.get('type'), 'verse_numbers': i.get('verse_numbers'), 'lines': i.get('lines')}
                              for i in c.get('items', [])]
                return o
            return {'books': [{'human': b.get('human') or b.get('name'), 'usfm': b.get('usfm'),
                               'chapters': [cap(c) for c in b['chapters']]} for b in libros]}
    except (KeyError, IndexError, TypeError, AttributeError):
        pass
    return d


def metadatos(d, ruta):
    m = d if isinstance(d, dict) else {}
    nombre = str(m.get('local_abbreviation') or m.get('abbreviation') or ruta.stem)
    titulo = str(m.get('local_title') or m.get('title') or m.get('translation') or m.get('name') or '')
    cp = m.get('copyright')
    copia = cp.get('text', '') if isinstance(cp, dict) else (cp if isinstance(cp, str) else '')
    return nombre, ('' if titulo == nombre else titulo), copia


def generar(carpeta):
    bloques, usados = [], set()
    for ruta in sorted(carpeta.glob('*.json'), key=lambda p: p.name.lower()):
        if ruta.name.lower() in IGNORAR:
            continue
        try:
            d = json.loads(ruta.read_text(encoding='utf-8-sig'))
        except Exception as e:
            print(f'  - {ruta.name}: JSON no válido ({e}); se omite')
            continue
        if not es_biblia(d):
            print(f'  - {ruta.name}: no parece una Biblia; se omite')
            continue
        nombre, titulo, copia = metadatos(d, ruta)
        if nombre in usados:
            nombre = ruta.stem
        usados.add(nombre)
        raw = json.dumps(podar(d), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        z = base64.b64encode(gzip.compress(raw, 9, mtime=0)).decode()
        a = lambda s: html.escape(s, quote=True)
        bloques.append(f'<script type="text/plain" class="bib" data-file="{a(ruta.name)}" data-name="{a(nombre)}" '
                       f'data-title="{a(titulo)}" data-copy="{a(copia)}">{z}</script>')
        print(f'  + {ruta.name}: "{nombre}" ({len(raw)/1e6:.1f} MB -> {len(z)/1e6:.1f} MB)')
    return bloques


def actualizar(carpeta, destino):
    txt = destino.read_text(encoding='utf-8')
    if INI not in txt or FIN not in txt:
        sys.exit(f'Error: {destino.name} no contiene las marcas {INI} y {FIN}.')
    print(f'[{time.strftime("%H:%M:%S")}] Buscando Biblias en {carpeta} ...')
    bloques = generar(carpeta)
    nuevo = re.sub(re.escape(INI) + '.*?' + re.escape(FIN),
                   lambda m: INI + '\n' + '\n'.join(bloques) + '\n' + FIN, txt, flags=re.S)
    if nuevo != txt:
        destino.write_text(nuevo, encoding='utf-8')
        print(f'{destino.name} actualizado con {len(bloques)} Biblia(s).')
    else:
        print('Sin cambios.')


def firma(carpeta):
    return tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(carpeta.glob('*.json')))


def main():
    base = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description='Inserta en index.html las Biblias .json de la carpeta.')
    ap.add_argument('--carpeta', type=Path, default=base)
    ap.add_argument('--html', type=Path, default=None)
    ap.add_argument('--cada', type=int, default=0, metavar='SEG', help='repetir la revisión cada SEG segundos')
    a = ap.parse_args()
    carpeta = a.carpeta.resolve()
    destino = (a.html or carpeta / 'index.html').resolve()
    actualizar(carpeta, destino)
    if a.cada > 0:
        print(f'Vigilando la carpeta cada {a.cada} s. Ctrl+C para salir.')
        ultima = firma(carpeta)
        try:
            while True:
                time.sleep(a.cada)
                f = firma(carpeta)
                if f != ultima:
                    ultima = f
                    actualizar(carpeta, destino)
        except KeyboardInterrupt:
            print('\nDetenido.')


if __name__ == '__main__':
    main()
