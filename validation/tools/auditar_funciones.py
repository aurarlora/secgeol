from pathlib import Path
import ast
import re

repo = Path(".")

archivos = [
    p for p in repo.rglob("*.py")
    if ".git" not in p.parts
]

funciones = []

# Detectar funciones y métodos definidos
for archivo in archivos:
    texto = archivo.read_text(
        encoding="utf-8",
        errors="ignore"
    )

    try:
        arbol = ast.parse(texto)
    except SyntaxError:
        continue

    for nodo in ast.walk(arbol):
        if isinstance(
            nodo,
            (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            funciones.append({
                "nombre": nodo.name,
                "archivo": str(archivo),
                "linea": nodo.lineno
            })

# Buscar referencias textuales
resultados = []

for funcion in funciones:
    nombre = funcion["nombre"]
    patron = re.compile(
        rf"\b{re.escape(nombre)}\b"
    )

    apariciones = []

    for archivo in archivos:
        texto = archivo.read_text(
            encoding="utf-8",
            errors="ignore"
        )

        for numero, linea in enumerate(
            texto.splitlines(),
            start=1
        ):
            if patron.search(linea):
                apariciones.append(
                    (
                        str(archivo),
                        numero,
                        linea.strip()
                    )
                )

    resultados.append({
        **funcion,
        "apariciones": apariciones
    })


print("\n=== POSIBLES FUNCIONES SIN USO ===\n")

for r in resultados:
    if len(r["apariciones"]) == 1:
        print(
            f"{r['archivo']}:{r['linea']} "
            f"{r['nombre']}()"
        )


print("\n=== FUNCIONES CON SOLO DOS APARICIONES ===\n")

for r in resultados:
    if len(r["apariciones"]) == 2:
        print(
            f"{r['archivo']}:{r['linea']} "
            f"{r['nombre']}()"
        )
