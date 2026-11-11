import os
import json

# Directorio donde se encuentran los archivos de confesiones (ajusta si están en la raíz o en una carpeta)
# Si están en la raíz del proyecto, usa "." o especifica la carpeta correcta.
CARPETA_CONFESIONES = "."  # O cambia a "confesiones" si creaste una carpeta específica.
ARCHIVO_CATALOGO = "catalogo.json"

def actualizar_catalogo():
    catalogo = []
    
    # Listar todos los archivos JSON en el directorio
    for archivo in os.listdir(CARPETA_CONFESIONES):
        if archivo.endswith(".json") and archivo != ARCHIVO_CATALOGO and not archivo.startswith("biblias"):
            ruta_archivo = os.path.join(CARPETA_CONFESIONES, archivo)
            try:
                with open(ruta_archivo, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                    # Extraemos la información relevante para el catálogo asegurando compatibilidad
                    # Si el JSON es una lista o un diccionario con secciones, calculamos métricas básicas
                    secciones = len(data) if isinstance(data, list) else data.get("secciones", 1)
                    
                    item = {
                        "id": data.get("id", archivo.replace(".json", "")),
                        "titulo": data.get("titulo", "Confesión sin título"),
                        "idioma": data.get("idioma", "es"),
                        "file": archivo,
                        "origen": archivo,
                        "secciones": secciones,
                        "size": os.path.getsize(ruta_archivo),
                        "licencia": data.get("licencia", "Sin licencia especificada")
                    }
                    catalogo.append(item)
                    print(f"Detectado y procesado: {archivo}")
            except Exception as e:
                print(f"Error al leer el archivo {archivo}: {e}")

    # Guardar el catálogo actualizado en formato JSON legible
    with open(ARCHIVO_CATALOGO, "w", encoding="utf-8") as f:
        json.dump(catalogo, f, ensure_ascii=False, indent=2)
    
    print(f"Catálogo actualizado con éxito. Total de confesiones encontradas: {len(catalogo)}")

if __name__ == "__main__":
    actualizar_catalogo()