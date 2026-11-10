#!/usr/bin/env python3
"""
Genera biblias.json: la lista (catálogo) de Biblias .json que hay en la carpeta.
index.html lee esa lista y deja que cada usuario elija cuáles descargar.

Uso:
  python3 actualizar_biblias.py                 # revisa una vez y termina
  python3 actualizar_biblias.py --cada 60       # vuelve a revisar cada 60 segundos
  python3 actualizar_biblias.py --carpeta RUTA --salida RUTA/biblias.json

Solo usa la biblioteca estándar de Python 3.8+. Los JSON que no sean una Biblia
(o que estén dañados) se omiten con un aviso. biblias.json solo se reescribe si
algo cambió. Los archivos de las Biblias no se modifican.
"""
import argparse, json, sys, time
from pathlib import Path

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


def entrada(d, ruta):
    m = d if isinstance(d, dict) else {}
    nombre = str(m.get('local_abbreviation') or m.get('abbreviation') or ruta.stem)
    titulo = str(m.get('local_title') or m.get('title') or m.get('translation') or m.get('name') or '')
    cp = m.get('copyright')
    copia = cp.get('text', '') if isinstance(cp, dict) else (cp if isinstance(cp, str) else '')
    lg = m.get('language')
    lang = lg.get('local_name', '') if isinstance(lg, dict) else (lg if isinstance(lg, str) else '')
    return {'file': ruta.name, 'name': nombre, 'title': '' if titulo == nombre else titulo,
            'lang': str(lang), 'size': ruta.stat().st_size, 'copy': copia}


def generar(carpeta):
    lista, usados = [], set()
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
        e = entrada(d, ruta)
        if e['name'] in usados:
            e['name'] = ruta.stem
        usados.add(e['name'])
        lista.append(e)
        print(f'  + {ruta.name}: "{e["name"]}" ({e["size"]/1e6:.1f} MB)')
    return lista


def actualizar(carpeta, salida):
    print(f'[{time.strftime("%H:%M:%S")}] Buscando Biblias en {carpeta} ...')
    nuevo = json.dumps(generar(carpeta), ensure_ascii=False, indent=2) + '\n'
    viejo = salida.read_text(encoding='utf-8') if salida.exists() else None
    if nuevo != viejo:
        salida.write_text(nuevo, encoding='utf-8')
        print(f'{salida.name} actualizado.')
    else:
        print('Sin cambios.')


def firma(carpeta):
    return tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(carpeta.glob('*.json'))
                 if p.name.lower() != 'biblias.json')


def main():
    base = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description='Genera biblias.json con las Biblias .json de la carpeta.')
    ap.add_argument('--carpeta', type=Path, default=base)
    ap.add_argument('--salida', type=Path, default=None)
    ap.add_argument('--cada', type=int, default=0, metavar='SEG', help='repetir la revisión cada SEG segundos')
    a = ap.parse_args()
    carpeta = a.carpeta.resolve()
    salida = (a.salida or carpeta / 'biblias.json').resolve()
    actualizar(carpeta, salida)
    if a.cada > 0:
        print(f'Vigilando la carpeta cada {a.cada} s. Ctrl+C para salir.')
        ultima = firma(carpeta)
        try:
            while True:
                time.sleep(a.cada)
                f = firma(carpeta)
                if f != ultima:
                    ultima = f
                    actualizar(carpeta, salida)
        except KeyboardInterrupt:
            print('\nDetenido.')


if __name__ == '__main__':
    main()
