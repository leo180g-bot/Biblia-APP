#!/usr/bin/env python3
"""
Genera biblias.json: la lista (catálogo) de Biblias .json de la carpeta y TODAS sus subcarpetas
(excepto la carpeta "confesiones" y los archivos cuyo nombre contenga catalogo, confesion, catecismo o credo,
que usa actualizar_confesiones.py).
index.html lee esa lista y deja que cada usuario elija cuáles descargar.

Uso:
  python3 actualizar_biblias.py                 # revisa una vez y termina
  python3 actualizar_biblias.py --cada 60       # vuelve a revisar cada 60 segundos
  python3 actualizar_biblias.py --sin-validar   # incluye cualquier .json, aunque no lo reconozca como Biblia
  python3 actualizar_biblias.py --carpeta RUTA --salida RUTA/biblias.json

Opcional: biblias-info.json, para poner a mano el título, el idioma o el nombre de una Biblia:
  {"RVSBT18.json": {"title": "Biblia Reina Valera SBT 2018", "lang": "Español"}}

Solo usa la biblioteca estándar de Python 3.8+. Muestra qué archivos incluye y cuáles omite (y por qué).
"""
import argparse, json, re, sys, time, unicodedata
from pathlib import Path

IGNORAR = {'biblias.json', 'biblias-info.json', 'package.json', 'package-lock.json', 'manifest.json', 'composer.json', 'tsconfig.json'}
NO_BIBLIA = re.compile(r'catalogo|confesion|catecism|credo', re.I)     # catálogos y textos de fe: los maneja actualizar_confesiones.py
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


IDIOMAS = {'español': 'Español', 'espanol': 'Español', 'spanish': 'Español', 'es': 'Español', 'castellano': 'Español',
           'inglés': 'Inglés', 'ingles': 'Inglés', 'english': 'Inglés', 'en': 'Inglés', 'portugués': 'Portugués', 'portugues': 'Portugués',
           'portuguese': 'Portugués', 'pt': 'Portugués', 'francés': 'Francés', 'frances': 'Francés', 'french': 'Francés', 'fr': 'Francés',
           'alemán': 'Alemán', 'aleman': 'Alemán', 'german': 'Alemán', 'de': 'Alemán', 'italiano': 'Italiano', 'italian': 'Italiano', 'it': 'Italiano',
           'latín': 'Latín', 'latin': 'Latín', 'la': 'Latín'}
PALABRAS = {
    'Español': 'de la que el en y los las del se por un con una su para es al lo como más pero sus le ya fue este porque esta entre cuando muy sin sobre también dios señor',
    'Inglés': 'the and of to in that is was he for it with as his on be at by this had not are but from or have they which you were her all she there would their we him been has when who will',
    'Portugués': 'de a o que e do da em um para é com não uma os no se na por mais as dos como mas foi ao ele das tem seu sua ou ser quando muito há nos já está também deus senhor',
    'Francés': 'de la le et les des en un du une que est pour qui dans par au sur il se ne pas plus son sa ce avec dieu seigneur',
    'Alemán': 'der die und in den von zu das mit sich des auf für ist im dem nicht ein eine als auch es an werden aus er hat dass sie nach wird bei einer um am sind noch wie einem über einen so zum war haben nur oder aber vor zur bis mehr durch man sein wurde sprach herr gott',
    'Italiano': 'di e il la che in un per è con non una sono le da si ma lo dei al come più del anche io suo dio signore',
    'Latín': 'et in est non ad cum ut qui quae quod sed per ex de dominus deus'}
PALABRAS = {k: set(v.split()) for k, v in PALABRAS.items()}


def detectar_idioma(d, limite=40000):
    """Cuenta palabras funcionales en una muestra del texto para adivinar el idioma ('' si no hay certeza)."""
    pila, muestra, n = [d], [], 0
    while pila and n < limite:
        x = pila.pop()
        if isinstance(x, str):
            muestra.append(x); n += len(x)
        elif isinstance(x, dict):
            pila.extend(reversed(list(x.values())))
        elif isinstance(x, list):
            pila.extend(reversed(x))
    palabras = re.findall(r'[^\W\d_]+', ' '.join(muestra).lower())
    if len(palabras) < 200:
        return ''
    pt = {k: sum(1 for w in palabras if w in v) for k, v in PALABRAS.items()}
    mejor = sorted(pt.items(), key=lambda t: -t[1])
    return mejor[0][0] if mejor[0][1] > 1.2 * max(mejor[1][1], 1) and mejor[0][1] > 0.05 * len(palabras) else ''


def archivos(carpeta):
    for p in sorted(carpeta.rglob('*.json'), key=lambda p: str(p).lower()):
        rel = p.relative_to(carpeta)
        if any(x.startswith('.') or x in ('node_modules', 'confesiones') for x in rel.parts[:-1]):
            continue
        if p.name.lower() in IGNORAR or NO_BIBLIA.search(p.stem):
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
    if not lang and '/' in rel:                              # carpeta con nombre de idioma: Español/RVR1960.json
        lang = IDIOMAS.get(unicodedata.normalize('NFC', rel.split('/')[0].lower()), '')
    if not lang:
        lang = detectar_idioma(d)
    return {'file': rel, 'name': nombre, 'title': '' if titulo == nombre else titulo,
            'lang': str(lang), 'size': ruta.stat().st_size, 'copy': copia}


def cargar_info(carpeta):
    """biblias-info.json (opcional, lo editas tú): {"RVSBT18.json": {"title": "Biblia Reina Valera SBT 2018", "lang": "Español"}}"""
    ruta = carpeta / 'biblias-info.json'
    try:
        d = json.loads(ruta.read_text(encoding='utf-8-sig')) if ruta.exists() else {}
        return d if isinstance(d, dict) else {}
    except Exception as e:
        print(f'  ! biblias-info.json no es válido ({e}); se ignora')
        return {}


def generar(carpeta, validar=True):
    lista, usados, total = [], set(), 0
    info = cargar_info(carpeta)
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
        e.update({k: str(v) for k, v in (info.get(rel) or info.get(ruta.name) or {}).items() if k in ('name', 'title', 'lang', 'copy')})
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
    extra = [carpeta / 'biblias-info.json']
    return tuple((rel, p.stat().st_size, p.stat().st_mtime_ns) for p, rel in archivos(carpeta)) + tuple((x.name, x.stat().st_mtime_ns) for x in extra if x.exists())


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
