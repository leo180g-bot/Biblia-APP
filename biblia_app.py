#!/usr/bin/env python3
"""
Biblia — aplicación de escritorio para Linux (Python + pywebview).

Abre tu index.html en una ventana propia, sirviendo esta carpeta en http://127.0.0.1:8765 (solo tu equipo).
Funciona sin internet: las Biblias, confesiones y catecismos se leen de los archivos locales.

Coloca este archivo en la MISMA carpeta que index.html, actualizar_biblias.py, actualizar_confesiones.py,
biblias-info.json, tus Biblias .json y la carpeta confesiones/.

Uso:
  python3 biblia_app.py                  # abre la ventana
  python3 biblia_app.py --navegador      # lo abre en tu navegador en vez de una ventana propia
  python3 biblia_app.py --sin-actualizar # no regenera biblias.json ni el catálogo de confesiones
  python3 biblia_app.py --probar         # comprueba que todo se sirve bien y termina (diagnóstico)

GitHub: la app puede mostrar y descargar las Biblias, confesiones y catecismos de tu repositorio (por omisión
leo180g-bot/Biblia-APP). Lo que elijas descargar se guarda en ~/.local/share/biblia-app/github y se usa sin conexión.
  python3 biblia_app.py --repo usuario/repositorio        # cambia el repositorio (se recuerda); admite usuario/repo@rama
  python3 biblia_app.py --sin-github                      # solo archivos locales, sin consultar internet
Los archivos que pongas en esta carpeta tienen prioridad sobre los de GitHub.

Al iniciar, regenera solo lo que cambió: biblias.json y confesiones/catalogo.json, así que basta con copiar
un .json nuevo a la carpeta y reiniciar la app. Instalación: bash instalar.sh
"""
import argparse, http.server, json, os, shutil, subprocess, sys, threading, time, urllib.parse, urllib.request, webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
DATOS = Path.home() / '.local' / 'share' / 'biblia-app'      # aquí se guardan tus Biblias descargadas, notas, marcadores y el estado
ESTADO = DATOS / 'estado.json'
CONFIG = DATOS / 'config.json'
CACHE = DATOS / 'github'
RAW = os.environ.get('BIBLIA_RAW_BASE', 'https://raw.githubusercontent.com')
CATALOGOS = ('biblias.json', 'biblias-info.json', 'confesiones/catalogo.json')
REPO_POR_OMISION = 'leo180g-bot/Biblia-APP'
HOOK = """
if(!window.__hookBiblia){window.__hookBiblia=1;document.addEventListener('click',function(e){
 var a=e.target.closest&&e.target.closest('a[href^="http"],a[href^="mailto:"],a[target="_blank"]');
 if(a&&window.pywebview&&window.pywebview.api){e.preventDefault();window.pywebview.api.abrir(a.href)}},true)}
"""


def leer_json(ruta):
    try:
        return json.loads(Path(ruta).read_text(encoding='utf-8-sig'))
    except Exception:
        return None


def fusionar(ruta, remoto, local):
    """Une el catálogo de GitHub con el local; lo local tiene prioridad."""
    if isinstance(remoto, dict) or isinstance(local, dict):
        return {**(remoto if isinstance(remoto, dict) else {}), **(local if isinstance(local, dict) else {})}
    clave = 'id' if ruta.endswith('catalogo.json') else 'file'
    salida = {e[clave]: e for e in (remoto or []) if isinstance(e, dict) and clave in e}
    for e in (local or []):
        if isinstance(e, dict) and clave in e:
            salida[e[clave]] = e
    return list(salida.values())


class GitHub:
    """Lee catálogos y descarga archivos de un repositorio de GitHub (raw.githubusercontent.com), con caché local."""

    def __init__(self, repo, rama='main'):
        self.repo, self.rama = repo, rama
        self.tam = {}                 # ruta -> tamaño esperado, según los catálogos remotos
        self.bloqueos, self.cerrojo = {}, threading.Lock()
        self.sin_red_hasta = 0

    def url(self, ruta):
        return f'{RAW}/{self.repo}/{self.rama}/' + '/'.join(urllib.parse.quote(p) for p in ruta.split('/'))

    def leer(self, ruta, timeout):
        req = urllib.request.Request(self.url(ruta), headers={'User-Agent': 'biblia-app'})
        return urllib.request.urlopen(req, timeout=timeout)

    def hay_red(self):
        return time.time() >= self.sin_red_hasta

    def fallo_red(self):
        self.sin_red_hasta = time.time() + 60      # tras un fallo, no insiste durante un minuto (usa la caché)

    def registrar(self, ruta, d):
        if not isinstance(d, list):
            return
        for e in d:
            if not isinstance(e, dict):
                continue
            if ruta == 'biblias.json' and e.get('file'):
                self.tam[e['file']] = e.get('size')
            elif ruta.endswith('catalogo.json') and e.get('file'):
                self.tam['confesiones/' + e['file']] = e.get('size')

    def catalogo(self, ruta):
        copia = CACHE / ruta
        datos = None
        if self.hay_red():
            try:
                with self.leer(ruta, 8) as r:
                    datos = r.read()
                json.loads(datos)
                copia.parent.mkdir(parents=True, exist_ok=True)
                copia.write_bytes(datos)
            except Exception:
                datos = None
                self.fallo_red()
        if datos is None and copia.exists():
            datos = copia.read_bytes()
        if datos is None:
            return None
        d = json.loads(datos)
        self.registrar(ruta, d)
        return d

    def cargar_catalogos(self):
        for r in CATALOGOS[::2]:
            self.catalogo(r)

    def conocido(self, ruta):
        return ruta in self.tam

    def archivo(self, ruta):
        """Devuelve la copia local del archivo; lo descarga de GitHub si falta o si cambió de tamaño."""
        destino, esperado = CACHE / ruta, self.tam.get(ruta)
        with self.cerrojo:
            cerrojo = self.bloqueos.setdefault(ruta, threading.Lock())
        with cerrojo:
            if destino.exists() and (not esperado or destino.stat().st_size == esperado):
                return destino
            if not self.hay_red():
                return destino if destino.exists() else None
            tmp = destino.with_name(destino.name + '.part')
            destino.parent.mkdir(parents=True, exist_ok=True)
            try:
                with self.leer(ruta, 60) as r, open(tmp, 'wb') as f:
                    shutil.copyfileobj(r, f)
                tmp.replace(destino)
                return destino
            except Exception as e:
                print(f'No se pudo descargar {ruta}: {e}')
                tmp.unlink(missing_ok=True)
                self.fallo_red()
                return destino if destino.exists() else None


class Handler(http.server.SimpleHTTPRequestHandler):
    github = None

    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(BASE), **k)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def log_message(self, *a):
        pass

    def enviar(self, tipo, tam, escribir):
        try:
            self.send_response(200)
            self.send_header('Content-Type', tipo)
            self.send_header('Content-Length', str(tam))
            self.end_headers()
            escribir(self.wfile)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        ruta = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path).lstrip('/')
        gh = Handler.github
        if gh and '..' not in ruta.split('/'):
            if ruta in CATALOGOS:
                remoto = gh.catalogo(ruta)
                if remoto is not None:
                    datos = json.dumps(fusionar(ruta, remoto, leer_json(BASE / ruta)), ensure_ascii=False).encode('utf-8')
                    return self.enviar('application/json; charset=utf-8', len(datos), lambda w: w.write(datos))
            elif ruta.endswith('.json') and not (BASE / ruta).exists():
                if not gh.conocido(ruta):
                    gh.cargar_catalogos()
                if gh.conocido(ruta):
                    f = gh.archivo(ruta)
                    if f:
                        with open(f, 'rb') as fh:
                            return self.enviar('application/json; charset=utf-8', f.stat().st_size, lambda w: shutil.copyfileobj(fh, w))
        return super().do_GET()


class Api:
    """Funciones de Python que llama la página (window.pywebview.api)."""

    def abrir(self, url):
        if str(url).startswith(('http://', 'https://', 'mailto:')):
            webbrowser.open(url)
            return True
        return False

    def copiar(self, texto):
        for cmd in (['wl-copy'], ['xclip', '-selection', 'clipboard'], ['xsel', '-ib']):
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(cmd, input=str(texto).encode('utf-8'), check=True, timeout=5)
                    return True
                except Exception:
                    pass
        return False            # sin herramienta de portapapeles: la página usa su método alternativo


def estado():
    try:
        return json.loads(ESTADO.read_text(encoding='utf-8'))
    except Exception:
        return {}


def guardar_estado(clave, valor):
    e = estado()
    e[clave] = valor
    try:
        DATOS.mkdir(parents=True, exist_ok=True)
        ESTADO.write_text(json.dumps(e), encoding='utf-8')
    except OSError:
        pass


def regenerar_biblias():
    try:
        import actualizar_biblias as ab
        f = repr(ab.firma(BASE))
        if f == estado().get('biblias') and (BASE / 'biblias.json').exists():
            return
        ab.actualizar(BASE, BASE / 'biblias.json', True)
        guardar_estado('biblias', f)
    except Exception as e:
        print('Aviso (Biblias):', e)


def regenerar_confesiones(al_cambiar=None):
    d = BASE / 'confesiones'
    if not d.is_dir():
        return
    try:
        import actualizar_confesiones as ac
        f = repr(ac.firma(d))
        if f == estado().get('confesiones') and (d / 'catalogo.json').exists():
            return
        ac.actualizar(d)
        guardar_estado('confesiones', f)
        if al_cambiar:
            al_cambiar()
    except Exception as e:
        print('Aviso (confesiones):', e)


def configurar_github(a):
    cfg = leer_json(CONFIG) or {}
    if a.repo:
        repo, _, rama = a.repo.partition('@')
        cfg.update(repo=repo.strip().strip('/'), rama=rama or 'main')
    cfg.setdefault('repo', REPO_POR_OMISION)
    cfg.setdefault('rama', 'main')
    try:
        DATOS.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False), encoding='utf-8')
    except OSError:
        pass
    if a.sin_github:
        return None
    print(f'GitHub: {cfg["repo"]} (rama {cfg["rama"]}). Lo que descargues se guarda en {CACHE}')
    return GitHub(cfg['repo'], cfg['rama'])


def iniciar_servidor(puerto):
    for p in range(puerto, puerto + 20):
        try:
            srv = http.server.ThreadingHTTPServer(('127.0.0.1', p), Handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            return srv, p
        except OSError:
            continue
    sys.exit('No hay puertos libres para iniciar la aplicación.')


def probar(puerto):
    ok = True
    for ruta in ('/index.html', '/biblias.json', '/confesiones/catalogo.json'):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{puerto}{ruta}', timeout=5) as r:
                cuerpo = r.read()
            extra = ''
            if ruta.endswith('.json'):
                extra = f' ({len(json.loads(cuerpo))} elementos)'
            print(f'  OK   {ruta}  {len(cuerpo)/1e3:.0f} KB{extra}')
        except Exception as e:
            ok = False
            print(f'  FALTA {ruta}  ({e})')
    return ok


def main():
    ap = argparse.ArgumentParser(description='Biblia: aplicación de escritorio.')
    ap.add_argument('--puerto', type=int, default=8765)
    ap.add_argument('--navegador', action='store_true')
    ap.add_argument('--sin-actualizar', action='store_true')
    ap.add_argument('--probar', action='store_true')
    ap.add_argument('--repo', help='repositorio de GitHub: usuario/repositorio o usuario/repositorio@rama (se recuerda)')
    ap.add_argument('--sin-github', action='store_true', help='no consultar GitHub; solo archivos locales')
    a = ap.parse_args()
    if not (BASE / 'index.html').exists():
        sys.exit('No encuentro index.html junto a biblia_app.py.')
    if not a.sin_actualizar:
        regenerar_biblias()
    Handler.github = configurar_github(a)
    srv, puerto = iniciar_servidor(a.puerto)
    url = f'http://127.0.0.1:{puerto}/index.html'
    if a.probar:
        if not a.sin_actualizar:
            regenerar_confesiones()
        sys.exit(0 if probar(puerto) else 1)
    try:
        import webview
    except ImportError:
        webview = None
    if a.navegador or webview is None:
        if webview is None and not a.navegador:
            print('pywebview no está instalado; abro el navegador. Para tener ventana propia:  pip install "pywebview[qt]"')
        if not a.sin_actualizar:
            threading.Thread(target=regenerar_confesiones, daemon=True).start()
        webbrowser.open(url)
        print(f'Biblia en {url}  (Ctrl+C para salir)')
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return
    win = webview.create_window('Biblia', url, width=1200, height=820, min_size=(420, 520), js_api=Api())
    win.events.loaded += lambda: win.evaluate_js(HOOK)

    def arrancar():
        if not a.sin_actualizar:
            regenerar_confesiones(lambda: win.evaluate_js('location.reload()'))

    DATOS.mkdir(parents=True, exist_ok=True)
    try:
        webview.start(arrancar, private_mode=False, storage_path=str(DATOS))
    except TypeError:
        webview.start(arrancar)


if __name__ == '__main__':
    main()
