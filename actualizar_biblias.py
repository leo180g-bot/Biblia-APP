import os
import json

CARPETA_CONFESIONES = "confesiones"
ARCHIVO_SALIDA = "confesiones.json"

def generar_catalogo_confesiones():
    catalogo = []
    
    if not os.path.exists(CARPETA_CONFESIONES):
        print(f"La carpeta '{CARPETA_CONFESIONES}' no existe.")
        return

    # Recorrer todos los archivos de la carpeta
    for archivo in os.listdir(CARPETA_CONFESIONES):
        if archivo.endswith(".json"):
            ruta_archivo = os.path.join(CARPETA_CONFESIONES, archivo)
            try:
                with open(ruta_archivo, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Extraemos metadatos básicos para el catálogo o guardamos la referencia
                    catalogo.endswith # (puedes ajustar según lo que requiera tu app)
                    catalogo.append({
                        "archivo": archivo,
                        "titulo": data.get("titulo", archivo.replace(".json", "")),
                        "descripcion": data.get("descripcion", "")
                    })
            except Exception as e:
                print(f"Error leyendo {archivo}: {e}")

    # Guardar el índice consolidado
    with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as f:
        json.dump(catalogo, f, ensure_ascii=False, indent=2)
    
    print(f"Catálogo generado con éxito: {len(catalogo)} confesiones detectadas.")

if __name__ == "__main__":
    generar_catalogo_confesiones()