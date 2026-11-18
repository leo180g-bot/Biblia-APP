#!/usr/bin/env bash
# Instala las dependencias de la app Biblia en un entorno virtual y crea el lanzador del menú de aplicaciones.
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"
for f in index.html biblia_app.py actualizar_biblias.py actualizar_confesiones.py; do
  [ -f "$f" ] || { echo "Falta $f en esta carpeta."; exit 1; }
done
python3 -m venv .venv || { echo "Instala python3-venv (por ejemplo: sudo apt install python3-venv) y vuelve a ejecutar."; exit 1; }
.venv/bin/pip install --upgrade pip
.venv/bin/pip install "pywebview[qt]" pdfplumber
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/biblia-app.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Biblia
Comment=Biblia, confesiones de fe y catecismos
Exec=$DIR/.venv/bin/python $DIR/biblia_app.py
Path=$DIR
Icon=accessories-dictionary
Terminal=false
Categories=Education;Utility;
DESK
chmod +x biblia_app.py
echo
echo "Listo. Busca «Biblia» en tu menú de aplicaciones, o ejecuta:  $DIR/.venv/bin/python $DIR/biblia_app.py"
