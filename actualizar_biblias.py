#!/usr/bin/env python3
"""
Genera biblias.json: la lista (catálogo) de Biblias .json de la carpeta y TODAS sus subcarpetas.
index.html lee esa lista y deja que cada usuario elija cuáles descargar.

Uso:
  python3 actualizar_biblias.py                 # revisa una vez y termina
  python3 actualizar_biblias.py --cada 60       # vuelve a revisar cada 60 segundos
  python3 actualizar_biblias.py --sin-validar   # incluye cualquier .json, aunque no lo reconozca como Biblia
  python3 actualizar_biblias.py --carpeta RUTA --salida RUTA/biblias.json

Solo usa la biblioteca estándar de Python 3.8+. Muestra qué archivos incluye y cuáles omite (y por qué).
"""
import argparse, json, re, sys, time, unicodedata
from pathlib import Path

IGNORAR = {'biblias.json', 'package.json', 'package-lock.json', 'manifest.json', 'composer.json', 'tsconfig.json'}
NOMBRES = {'genesis', 'exodo', 'levitico', 'numeros', 'mateo', 'marcos', 'lucas', 'juan', 'matthew', 'mark',
           'luke', 'john', 'gn', 'gen', 'mt', 'mat'}

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def norm(s):
    s = unicodedata.normalize('NFD', str(s).lower())
    return re.sub(r'[^a-z0-9]', '', ''.join(c for c in s if not unicodedata.combining(c)))


def es_biblia(d, prof=0):
    if isinstance(d, dict):
        for k in ('books', 'bible', 'Bible', 'data', 'content', 'testaments', 'verses'):
            v = d.get(k)
            if isinstance(v, (list, dict)) and prof < 3 and es_biblia(v, prof + 1):
                return True
        ks = list(d)[:300]
        if any(norm(k) in NOMBRES for k in ks):
            return True
        if ks and re.match(r'^.+\s+\d+:\d+$', str(ks[0])):
            return True
        return len(d) >= 60 and all(isinstance(v, (dict, list)) for v in d.values())
    if isinstance(d, list) and d:
        p = d[0]
        if isinstance(p, dict):
            return any(k in p for k in ('chapters', 'verses', 'items', 'verse', 'text', 'verse_text', 'chapter'))
        return isinstance(p, list)
    return False


def archivos(carpeta):
    for p in sorted(carpeta.rglob('*.json'), key=lambda p: str(p).lower()):
        rel = p.relative_to(carpeta)
        if any(x.startswith('.') or x == 'node_modules' for x in rel.parts[:-1]):
            continue
        if p.name.lower() in IGNORAR:
            continue
        yield p, rel.as_posix()


def entrada(d, ruta, rel):
    m = d if isinstance(d, dict) else {}
    nombre = str(m.get('local_abbreviation') or m.get('abbreviation') or ruta.stem)
    titulo = str(m.get('local_title') or m.get('title') or m.get('translation') or m.get('name') or '')
    cp = m.get('copyright')
    copia = cp.get('text', '') if isinstance(cp, dict) else (cp if isinstance(cp, str) else '')
    lg = m.get('language')
    lang = lg.get('local_name', '') if isinstance(lg, dict) else (lg if isinstance(lg, str) else '')
    return {'file': rel, 'name': nombre, 'title': '' if titulo == nombre else titulo,
            'lang': str(lang), 'size': ruta.stat().st_size, 'copy': copia}


def generar(carpeta, validar=True):
    lista, usados, total = [], set(), 0
    for ruta, rel in archivos(carpeta):
        total += 1
        try:
            d = json.loads(ruta.read_text(encoding='utf-8-sig'))
        except Exception as e:
            print(f'  - {rel}: JSON no válido ({e}); se omite')
            continue
        if validar and not es_biblia(d):
            print(f'  - {rel}: no se reconoce como Biblia; se omite (usa --sin-validar para incluirlo)')
            continue
        e = entrada(d, ruta, rel)
        if e['name'] in usados:
            e['name'] = rel[:-5].replace('/', ' - ')
        usados.add(e['name'])
        lista.append(e)
        print(f'  + {rel}: "{e["name"]}" ({e["size"]/1e6:.1f} MB)')
    print(f'{total} archivo(s) .json encontrados, {len(lista)} incluidos.')
    return lista


def actualizar(carpeta, salida, validar):
    print(f'[{time.strftime("%H:%M:%S")}] Buscando Biblias en {carpeta} (incluye subcarpetas) ...')
    nuevo = json.dumps(generar(carpeta, validar), ensure_ascii=False, indent=2) + '\n'
    viejo = salida.read_text(encoding='utf-8') if salida.exists() else None
    if nuevo != viejo:
        salida.write_text(nuevo, encoding='utf-8')
        print(f'{salida.name} actualizado.')
    else:
        print('Sin cambios.')


def firma(carpeta):
    return tuple((rel, p.stat().st_size, p.stat().st_mtime_ns) for p, rel in archivos(carpeta))


def main():
    base = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description='Genera biblias.json con las Biblias .json de la carpeta y subcarpetas.')
    ap.add_argument('--carpeta', type=Path, default=base)
    ap.add_argument('--salida', type=Path, default=None)
    ap.add_argument('--cada', type=int, default=0, metavar='SEG', help='repetir la revisión cada SEG segundos')
    ap.add_argument('--sin-validar', action='store_true', help='incluir cualquier .json')
    a = ap.parse_args()
    carpeta = a.carpeta.resolve()
    salida = (a.salida or carpeta / 'biblias.json').resolve()
    validar = not a.sin_validar
    actualizar(carpeta, salida, validar)
    if a.cada > 0:
        print(f'Vigilando la carpeta cada {a.cada} s. Ctrl+C para salir.')
        ultima = firma(carpeta)
        try:
            while True:
                time.sleep(a.cada)
                f = firma(carpeta)
                if f != ultima:
                    ultima = f
                    actualizar(carpeta, salida, validar)
        except KeyboardInterrupt:
            print('\nDetenido.')


if __name__ == '__main__':
    main()
