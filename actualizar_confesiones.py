#!/usr/bin/env python3
"""
Lee los .json de la carpeta "confesiones" (confesiones de fe), los normaliza a un formato limpio
y genera lo que necesita index.html:

  confesiones/catalogo.json        lista de confesiones disponibles
  confesiones/datos/<id>.json      cada confesión normalizada (capítulos, párrafos y textos de prueba)

Uso:
  python3 actualizar_confesiones.py                  # procesa una vez
  python3 actualizar_confesiones.py --cada 60        # vuelve a revisar cada 60 segundos
  python3 actualizar_confesiones.py --carpeta RUTA   # otra carpeta (por defecto "confesiones" junto al script)

Formatos de entrada admitidos:
  1. Formato limpio (recomendado): {"titulo": "...", "secciones": [{"titulo": "...", "parrafos": [{"n": "1.1", "t": "...", "notas": [{"n": 1, "t": "Isa. 8:20"}]}]}]}
  2. Texto extraído de un PDF/e-book y guardado como JSON fragmentado (claves = trozos de texto con valor null),
     como confesion-bautista-1689.json. Se reconstruye el texto y se detectan capítulos y párrafos "N.M".
  3. Una lista de cadenas, o una cadena de texto.
Solo usa la biblioteca estándar de Python 3.8+.
"""
import argparse, json, re, sys, time, unicodedata
from collections import Counter
from pathlib import Path

IGNORAR = {'catalogo.json'}
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def slug(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', str(s).lower()) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-') or 'confesion'


def texto_de(d):
    if isinstance(d, str):
        return d
    if isinstance(d, list) and d and all(isinstance(x, str) for x in d):
        return '\n'.join(d)
    if isinstance(d, dict) and d and all(v is None for v in d.values()):
        return ';'.join(d.keys())          # el texto original fue cortado en cada ";"
    return None


# ---------------------------------------------------------------- análisis de texto extraído
RE_PARR = re.compile(r'^(\d{1,2})\.([\dlIO]{1,2})\s+(\S.*)$')   # tolera "2.l" (OCR) en vez de "2.1"
RE_NOTA = re.compile(r'^\s*(\d{1,3})\s+(?:(?:[123]\s?)?[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{1,8}\.?\s*\d|Notas? de(?:l| los)? traductor)')
RE_PAG = re.compile(r'^\s*(?:\d{1,3}|[ivxlc]{1,6})\s*$')


def clave(ln):
    s = re.sub(r'\s+', ' ', ln.replace('\t', ' ')).strip()
    s = re.sub(r'^(?:\d+|[ivxlc]+) ', '', s)
    s = re.sub(r' (?:\d+|[ivxlc]+)$', '', s)
    return s.strip()


def cabeceras(lineas):
    c = Counter(clave(l) for l in lineas if 3 < len(l.strip()) < 90 and clave(l) != l.strip())
    return {k for k, n in c.items() if n >= 4 and k}


def indice(t):
    i = t.find('Índice de contenido')
    seg = t[i:i + 6000] if i >= 0 else t[:6000]
    caps = {}
    for m in re.finditer(r'(?<![\d.])(\d{1,2})\.\s+([^.]+?)\s*\.{3,}', seg):
        n = int(m.group(1))
        if n not in caps:
            caps[n] = re.sub(r'\s+', ' ', m.group(2)).strip()
    return caps


def _n(x):
    return re.sub(r'\s+', ' ', x).strip().lower()


def limpiar(lineas, cab, titulos):
    tl = [(_n(t), t, n) for t, n in titulos]
    sufijos = []
    for _, t, n in tl:
        w = t.split()
        for i in range(len(w) - 1):
            sufijos.append((' '.join(w[i:]), n))
    sufijos.sort(key=lambda x: -len(x[0]))
    pat = [re.compile(r'\s*\b' + re.escape(suf) + r'\s+' + str(n) + r'\s*$') for suf, n in sufijos]

    def es_frag(ln):
        k = _n(ln)
        return len(k.split()) >= 2 and any(k in t for t, _, _ in tl)

    out = []
    for ln in lineas:
        if not ln.strip():
            continue
        if RE_PAG.match(ln) or (clave(ln) in cab and clave(ln) != ln.strip()):
            continue
        if ln.startswith('\t') and len(ln.strip()) < 45 and not RE_NOTA.match(ln):
            continue
        if '\t' in ln and not RE_NOTA.match(ln) and ln.rsplit('\t', 1)[-1].strip()[-1:].isdigit():
            ln = re.sub(r'\s*\t+\s*[^\t\n]{0,45}?\s*\d{1,3}\s*$', '', ln)
        for p in pat:
            ln = p.sub('', ln)
        if es_frag(ln) and not RE_PARR.match(ln.strip()):
            if out and re.search(r'\s\d{1,2}\s*$', out[-1]) and not RE_NOTA.match(out[-1]):
                out[-1] = re.sub(r'\s\d{1,2}\s*$', '', out[-1])     # número de capítulo pegado antes del título partido
            continue
        if ln.strip():
            out.append(ln)
    return out


def pulir(s):
    s = s.replace('¾', '—').replace('\ufeff', '')
    s = re.sub(r'(?<=[a-záéíóúñ])-\s?(?=[a-záéíóúñ])', '', s)   # guiones de fin de línea del PDF
    return re.sub(r'\s+', ' ', s).strip()


def entradas_nota(ln):
    res = {}
    for trozo in re.split(r'\s\|\s', ln.strip()):
        m = re.match(r'^(\d{1,3})\s+(.*)$', trozo.strip())
        if m:
            res[int(m.group(1))] = pulir(m.group(2))
    return res


def marcar(parrafos, notas):
    """Inserta [[k]] donde el texto trae pegado el número de la nota k (sin exigir orden: el PDF mezcla columnas)."""
    usados_total = set()
    tok = re.compile(r'(?<=[A-Za-zÁ-ÿ\.\,;:\)\]»”"\'—])(\d{1,2})(?=[\s\.\,;:\)»”\-—]|$)|(?<=[\.\,;:\)])(\d{1,2})(?=[A-Za-zÁ-ÿ¿¡])')
    for p in parrafos:
        usados = []

        def sub(m):
            k = int(m.group(1) or m.group(2))
            if k in notas and k not in usados_total:
                usados_total.add(k)
                usados.append(k)
                return '[[%d]]' % k
            return m.group(0)
        p['t'] = tok.sub(sub, p['t'])
        if usados:
            p['notas'] = [{'n': j, 't': notas[j]} for j in sorted(usados)]
    return sorted(set(notas) - usados_total)


def bloques_por_puntuacion(lineas):
    """Une líneas cortadas por saltos de página hasta que una termine en puntuación final."""
    res, buf = [], ''
    for ln in lineas:
        buf = (buf + ' ' + ln.strip()).strip()
        if re.search(r'[.!?:»”)]\s*$', buf):
            res.append(buf)
            buf = ''
    if buf:
        res.append(buf)
    return res


def analizar(texto, nombre):
    texto = texto.replace('\r', '')
    caps = indice(texto)
    titulos = [(t, n) for n, t in caps.items()]
    m1 = re.search(r'(?m)^1\.1\s', texto)
    if not m1:
        raise ValueError('no se encontraron párrafos numerados (1.1, 1.2 …)')
    ini_cap = m1.start()
    me = re.search(r'LECTOR\s+Juicioso e Imparcial', texto)
    ini_ep = me.end() if me and me.end() < ini_cap else None
    ma = next((m for m in re.finditer(r'(?m)^[ \t]*Apéndice[ \t]*$', texto) if m.start() > ini_cap), None)
    fin_cap = ma.start() if ma else len(texto)
    lineas_todas = texto.split('\n')
    cab = cabeceras(lineas_todas)
    secciones, avisos = [], []

    # --- epístola
    if ini_ep is not None:
        lin = limpiar(texto[ini_ep:ini_cap].split('\n'), cab, titulos)
        notas, cuerpo = {}, []
        for ln in lin:
            (notas.update(entradas_nota(ln)) if RE_NOTA.match(ln) else cuerpo.append(ln))
        pars = [{'n': '', 't': pulir(b)} for b in bloques_por_puntuacion(cuerpo)]
        marcar(pars, notas)
        secciones.append({'id': 'prologo', 'tipo': 'intro', 'titulo': 'Para el lector juicioso e imparcial', 'parrafos': pars})

    # --- capítulos
    lin = limpiar(texto[ini_cap:fin_cap].split('\n'), cab, titulos)
    por_cap, notas_cap, cur, capn = {}, {}, None, 0
    for ln in lin:
        m = RE_PARR.match(ln.strip())
        if m and 1 <= int(m.group(1)) <= max(40, len(caps)) and int(m.group(1)) in (capn, capn + 1):
            capn = int(m.group(1))
            pn = m.group(2).replace('l', '1').replace('I', '1').replace('O', '0')
            cur = {'n': f'{m.group(1)}.{pn}', 't': m.group(3)}
            por_cap.setdefault(capn, []).append(cur)
            continue
        if RE_NOTA.match(ln):
            notas_cap.setdefault(capn, {}).update(entradas_nota(ln))
            continue
        if cur:
            cur['t'] += ' ' + ln.strip()
    for n in sorted(por_cap):
        pars = por_cap[n]
        for p in pars:
            p['t'] = pulir(p['t'])
        sobran = marcar(pars, notas_cap.get(n, {}))
        extra = [{'n': j, 't': notas_cap[n][j]} for j in sobran]
        nums = [int(p['n'].split('.')[1]) for p in pars]
        if nums != list(range(1, len(nums) + 1)):
            avisos.append(f'capítulo {n}: numeración de párrafos {nums}')
        if sobran:
            avisos.append(f'capítulo {n}: textos de prueba sin marca en el texto {sobran}')
        sec = {'id': f'cap{n}', 'tipo': 'capitulo', 'numero': n, 'titulo': caps.get(n, f'Capítulo {n}'), 'parrafos': pars}
        if extra:
            sec['notas_extra'] = extra
        secciones.append(sec)
    faltan = [n for n in caps if n not in por_cap]
    if faltan:
        avisos.append(f'capítulos del índice sin texto: {faltan}')

    # --- apéndice
    if ma:
        resto = texto[ma.end():]
        fin = resto.find('FINIS')
        cuerpo_t, cola = (resto[:fin], resto[fin + 5:]) if fin >= 0 else (resto, '')
        lin = limpiar(cuerpo_t.split('\n'), cab, titulos)
        notas = {}
        for ln in limpiar(cola.split('\n'), cab, titulos):
            if RE_NOTA.match(ln):
                notas.update(entradas_nota(ln))
        cuerpo = []
        for ln in lin:
            (notas.update(entradas_nota(ln)) if RE_NOTA.match(ln) else cuerpo.append(ln))
        pars = [{'n': '', 't': pulir(b)} for b in bloques_por_puntuacion(cuerpo)]
        marcar(pars, notas)
        secciones.append({'id': 'apendice', 'tipo': 'apendice', 'titulo': 'Apéndice', 'parrafos': pars})

    cab_conf = [k for k in cab if 'Confesión' in k]
    titulo = max(cab_conf, key=len) if cab_conf else nombre.replace('-', ' ').replace('_', ' ').title()
    año = re.search(r'(1[5-9]\d\d)', nombre)
    if año and año.group(1) not in titulo:
        titulo += f' ({año.group(1)})'
    lic = re.search(r'Se otorga permiso expreso[^\n]*', texto)
    return {'id': slug(nombre), 'titulo': titulo, 'idioma': 'es', 'licencia': pulir(lic.group(0)) if lic else '',
            'secciones': secciones}, avisos


# ---------------------------------------------------------------- generación
def normalizar(d, nombre):
    if isinstance(d, dict) and isinstance(d.get('secciones'), list):
        doc = {'id': slug(d.get('id') or nombre), 'titulo': d.get('titulo') or nombre, 'idioma': d.get('idioma', 'es'),
               'licencia': d.get('licencia', ''), 'secciones': d['secciones']}
        return doc, []
    t = texto_de(d)
    if t is None:
        raise ValueError('formato no reconocido')
    return analizar(t, nombre)


def archivos(carpeta):
    for p in sorted(carpeta.rglob('*.json'), key=lambda p: str(p).lower()):
        rel = p.relative_to(carpeta)
        if rel.parts[0] == 'datos' or p.name.lower() in IGNORAR or any(x.startswith('.') for x in rel.parts):
            continue
        yield p, rel


def escribir(ruta, texto):
    if not ruta.exists() or ruta.read_text(encoding='utf-8') != texto:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto, encoding='utf-8')
        return True
    return False


def actualizar(carpeta):
    print(f'[{time.strftime("%H:%M:%S")}] Buscando confesiones en {carpeta} ...')
    catalogo, ids, cambios = [], set(), 0
    for ruta, rel in archivos(carpeta):
        try:
            d = json.loads(ruta.read_text(encoding='utf-8-sig'))
            doc, avisos = normalizar(d, ruta.stem)
        except Exception as e:
            print(f'  - {rel}: se omite ({e})')
            continue
        if doc['id'] in ids:
            doc['id'] = slug(str(rel)[:-5])
        ids.add(doc['id'])
        pars = sum(len(s['parrafos']) for s in doc['secciones'])
        notas = sum(len(p.get('notas', [])) for s in doc['secciones'] for p in s['parrafos'])
        txt = json.dumps(doc, ensure_ascii=False, separators=(',', ':'))
        cambios += escribir(carpeta / 'datos' / f'{doc["id"]}.json', txt)
        catalogo.append({'id': doc['id'], 'titulo': doc['titulo'], 'idioma': doc['idioma'], 'file': f'datos/{doc["id"]}.json',
                         'origen': rel.as_posix(), 'secciones': len(doc['secciones']), 'parrafos': pars,
                         'size': len(txt.encode('utf-8')), 'licencia': doc['licencia']})
        print(f'  + {rel}: "{doc["titulo"]}" — {len(doc["secciones"])} secciones, {pars} párrafos, {notas} textos de prueba')
        for a in avisos:
            print(f'      aviso: {a}')
    cambios += escribir(carpeta / 'catalogo.json', json.dumps(catalogo, ensure_ascii=False, indent=2) + '\n')
    print('Archivos actualizados.' if cambios else 'Sin cambios.')


def firma(carpeta):
    return tuple((str(r), p.stat().st_size, p.stat().st_mtime_ns) for p, r in archivos(carpeta))


def main():
    base = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description='Normaliza las confesiones de fe .json y genera catalogo.json.')
    ap.add_argument('--carpeta', type=Path, default=base / 'confesiones')
    ap.add_argument('--cada', type=int, default=0, metavar='SEG')
    a = ap.parse_args()
    carpeta = a.carpeta.resolve()
    if not carpeta.is_dir():
        sys.exit(f'No existe la carpeta {carpeta}. Créala y pon dentro los .json de las confesiones.')
    actualizar(carpeta)
    if a.cada > 0:
        print(f'Vigilando la carpeta cada {a.cada} s. Ctrl+C para salir.')
        ultima = firma(carpeta)
        try:
            while True:
                time.sleep(a.cada)
                f = firma(carpeta)
                if f != ultima:
                    ultima = f
                    actualizar(carpeta)
        except KeyboardInterrupt:
            print('\nDetenido.')


if __name__ == '__main__':
    main()
