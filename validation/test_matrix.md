# Matriz de validación de SecGeol

Este documento registra las pruebas funcionales realizadas durante la
validación manual de SecGeol en QGIS.

El objetivo es comprobar el comportamiento de las tres fases del complemento
bajo distintas configuraciones de datos de entrada, documentar las incidencias
detectadas y verificar las correcciones implementadas antes de su publicación.

## Resumen de pruebas

| Caso | DEM | Sección | Geología | Estructuras | Fase 1 | Fase 2 | Fase 3 | Resultado |
|---|---|---|---|---|---|---|---|---|
| P1 | ITRF08 / UTM 14N | EPSG:32614 | EPSG:32614 | EPSG:32614 | ❌ | ❌ | ❌ | No satisfactoria |
| R1 | ITRF08 / UTM 14N | ITRF08 / UTM 14N | ITRF08 / UTM 14N | ITRF08 / UTM 14N | ✅ | ✅ | ✅ | Satisfactoria |
| P2 | ITRF08 / UTM 14N | Sin CRS | EPSG:32614 | EPSG:32614 | ❌ | — | — | No satisfactoria |
| R2 | ITRF08 / UTM 14N |ITRF08 / UTM 14N | EPSG:32614 | EPSG:32614 | ✅ | — | — | Satisfactoria |
| R3 | ITRF08 / UTM 14N | Sin CRS y no cae → no continúa | EPSG:32614 | EPSG:32614 | ✅ | — | — | Satisfactoria |
| P4 | Fuente incompatible | Bloqueada | Bloqueada | Bloqueadas | — | — | — | No satisfactoria |
| R4 | DEM compatible ITRF08 / UTM 14N | Habilitada | Habilitada | Habilitadas | ✅ | — | — | Satisfactoria |
| P5 | ITRF08 / UTM 14N | CRS asignado incorrectamente; queda fuera del DEM | - | - | ✅ | — | — | Satisfactoria |

| Caso | Contour | Campo | Sección | Geología | Estructuras | Fase 1 | Fase 2 | Fase 3 | Resultado |
|---|---|---|---|---|---|---|---|---|---|
| Pc1 | Sin CRS | Bloqueado | Bloqueada | Bloqueada | Bloqueada | — | — | — | ✅ Satisfactoria |
| Pc2 | EPSG:6369 | Válido | Sin CRS | EPSG:32614 | EPSG:32614 | ✅ | — | — | ✅ Satisfactoria |
| Pc3 | Curvas EPSG:6369 | Campo válido | Sin CRS | Sin CRS | EPSG:32614 | ✅ | —| — | ⚠ comportamiento por corregir
|Pc4|	Curvas EPSG:6369|	Campo válido|	EPSG:32614|	EPSG:32612|	EPSG:32614|	✅|	—	|—|	✅ Satisfactoria
|Pc5|	Curvas EPSG:6369	|Campo válido|	EPSG:32614|	EPSG:32614	|Sin CRS|	✅|	—	|—|	✅ Satisfactoria
|Pc6|	Curvas EPSG:6369|	Campo válido|	EPSG:32614	|EPSG:32614|	EPSG:32612|	✅|	—	|—	|✅ Satisfactoria
|Pc7 | Curvas EPSG:6369 | Campo válido | EPSG:32614 | EPSG:32614 | `ECHADO` / `AZIMUTH_P`, incluye valores `-1` | ✅ | — | — | ✅ Satisfactoria |
| Pc8 | Curvas EPSG:6369 | Campo válido | EPSG:32614 | EPSG:32614 | EPSG:32614 | ✅ | ✅ Editada | ✅ | ✅ Satisfactoria |



---

## Prueba 1 — Flujo completo con CRS definidos diferentes al DEM

### Configuración

**Fuente de elevación**
- Tipo: MDE
- CRS: `MEXICO_ITRF_2008_UTM_Zone_14N`

**Línea de sección**
- CRS: `EPSG:32614 - WGS 84 / UTM zone 14N`

**Geología**
- CRS: `EPSG:32614 - WGS 84 / UTM zone 14N`

**Estructuras**
- CRS: `EPSG:32614 - WGS 84 / UTM zone 14N`

### Comportamiento esperado

La fuente de elevación define el CRS de trabajo de SecGeol.

Las capas vectoriales con un CRS válido distinto al de la fuente de elevación
deben ser transformadas al CRS de ésta para realizar el procesamiento.

Las capas de salida que representan geometrías espaciales deben conservar
el CRS de trabajo.

### Resultado inicial

#### Fase 1 — Sección a perfil

La fase genera las capas de salida y transfiere correctamente la información
geológica y estructural.

Sin embargo:

- el perfil topográfico se genera sin CRS;
- la sección guía (`_guia`) se genera sin CRS.

**Resultado:** ❌ No satisfactoria.

#### Fase 2 — Líneas a polígonos

La fase genera las entidades y la tabla de atributos. También se genera
correctamente la capa de ejes (`_ejes`).

Sin embargo:

- el perfil poligonal aparece identificado como `EPSG:4326`;
- las geometrías no se visualizan correctamente en el lienzo, ya que las
  coordenadas del perfil corresponden a distancia–elevación y no a
  longitud–latitud;
- la capa `_ejes` se genera sin CRS.

**Resultado:** ❌ No satisfactoria.

#### Fase 3 — Reconstrucción 3D

La reconstrucción geométrica se realiza y se genera el perfil 3D.

La geometría reconstruida coincide espacialmente con la sección y el MDE
al visualizarla en un entorno 3D.

Sin embargo:

- la capa 3D resultante se genera sin CRS.

**Resultado:** ❌ No satisfactoria.

### Incidencias detectadas

La revisión del código mostró que SecGeol utilizaba `authid()` para obtener
y propagar el CRS.

La fuente de elevación utilizada en esta prueba posee un CRS válido
(`MEXICO_ITRF_2008_UTM_Zone_14N`), pero sin un identificador `authid()`
disponible. Esto provocaba la pérdida del CRS en algunas salidas y, en la
fase 2, la asignación incorrecta de `EPSG:4326`.

### Corrección implementada

Se modificó el manejo del CRS para utilizar directamente el objeto
`QgsCoordinateReferenceSystem` y asignarlo a las capas de salida mediante
`setCrs()`.

### Repetición de la prueba — R1

Después de aplicar la corrección se repitió el flujo completo con los mismos
datos de entrada.

Se obtuvo correctamente:

- perfil topográfico con `MEXICO_ITRF_2008_UTM_Zone_14N`;
- sección guía con `MEXICO_ITRF_2008_UTM_Zone_14N`;
- polígonos geológicos 2D con `MEXICO_ITRF_2008_UTM_Zone_14N`;
- capa de ejes con `MEXICO_ITRF_2008_UTM_Zone_14N`;
- reconstrucción geológica 3D con `MEXICO_ITRF_2008_UTM_Zone_14N`.

Adicionalmente, la reconstrucción 3D se verificó de forma independiente en
ArcScene. La línea original de la sección fue configurada para obtener su
elevación directamente del DEM y se observó coincidencia con el borde superior
del perfil reconstruido por SecGeol.

![Validación de la reconstrucción 3D en ArcScene](/validation/img/sec_lin.png)

La comparación confirma la correspondencia espacial de la reconstrucción y
la consistencia de las elevaciones obtenidas a partir del DEM.

### Resultado general

**✅ SATISFACTORIA**

La prueba permitió detectar y corregir una deficiencia en la propagación del CRS.

Después de la corrección, las tres fases del flujo se ejecutaron correctamente,
las capas de salida conservaron el sistema de referencia espacial esperado y
la reconstrucción tridimensional fue consistente con la elevación derivada
independientemente del DEM.

---

## Prueba 2 — Línea de sección sin CRS definido

### Configuración

**Fuente de elevación**
- Tipo: MDE
- CRS: `MEXICO_ITRF_2008_UTM_Zone_14N`

**Línea de sección**
- CRS: Sin definir

**Geología**
- CRS: `EPSG:32614 - WGS 84 / UTM zone 14N`

**Estructuras**
- CRS: `EPSG:32614 - WGS 84 / UTM zone 14N`

### Comportamiento esperado

SecGeol no debe asumir ni asignar automáticamente un CRS a una capa cuya
referencia espacial no esté definida.

El proceso debe detenerse antes de ejecutar la Fase 1 y mostrar un mensaje
claro indicando que la línea de sección debe tener un CRS válido.

### Resultado observado

Al intentar ejecutar la Fase 1 con la sección sin CRS se genera un error
de Python.

La herramienta:

- no muestra una validación preventiva;
- no informa al usuario que la sección carece de CRS;
- no documenta este requisito en la ayuda HTML;
- obliga a cancelar el proceso.

**Resultado:** ❌ No satisfactoria.

### Corrección requerida

Agregar una validación previa del CRS de la línea de sección.

Si la capa no tiene un CRS válido, SecGeol debe detener el proceso y mostrar
un mensaje indicando que el usuario debe asignar el sistema de referencia
correspondiente antes de continuar.

También debe añadirse este requisito a la ayuda HTML.


## Prueba 3 — Línea de sección sin CRS y fuera de la fuente de elevación

La línea de sección no tiene un CRS definido y no se encuentra completamente contenida dentro del DEM. Se corrigió el comportamiento para que SecGeol no continúe con el procesamiento y muestre una advertencia al usuario indicando que la sección debe estar completamente contenida dentro de la fuente de elevación.

**Resultado: ✅ SATISFACTORIA**

## Prueba 4 — Fuente de elevación incompatible

Cuando el DEM seleccionado no es compatible con SecGeol, la herramienta deshabilita los controles correspondientes a Sección y Geología/Estructuras, impidiendo continuar con el flujo de trabajo. Al seleccionar un DEM compatible, los controles se habilitan automáticamente.

**Resultado: ✅ SATISFACTORIA**


## Prueba 5 — CRS asignado incorrectamente; queda fuera del DEM 

En este caso, la sección tiene un CRS válido, pero asignado incorrectamente, por lo que no queda contenida dentro del DEM. SecGeol valida la ubicación espacial de la sección y detiene el proceso, indicando que la sección no se encuentra completamente contenida dentro de la fuente de elevación.

**Resultado: ✅ SATISFACTORIA**

## Prueba 6 — Curvas de nivel compatibles como fuente de elevación

Se seleccionó una capa de curvas de nivel con CRS EPSG:6369 - Mexico ITRF2008 / UTM zone 14N y un campo numérico de elevación. SecGeol habilitó correctamente los controles de Sección y Geología/Estructuras y generó el perfil topográfico.
La línea de sección de trabajo y la capa _guía conservaron el CRS de la fuente de elevación.

**Resultado: ✅ SATISFACTORIA**

## Prueba 7 — Validación de valores estructurales

**Objetivo:** verificar que SecGeol procese únicamente estructuras con valores
válidos de echado y azimut de buzamiento, descartando registros con valores
inválidos sin interrumpir la generación del perfil.

**Configuración de prueba:**

- Fuente de elevación: curvas de nivel.
- CRS de trabajo: EPSG:6369.
- Campo de echado: `ECHADO`.
- Campo de azimut de buzamiento: `AZIMUTH_P`.
- La capa estructural contiene valores válidos y registros con `-1`,
  utilizado en los datos de prueba como valor sin información.

**Criterios de validación:**

- Los campos seleccionables para echado y azimut deben ser de tipo numérico.
- Los valores de echado deben cumplir `0 < echado <= 90`.
- Los valores de azimut de buzamiento deben cumplir `0 <= azimut <= 360`.
- Los valores fuera de estos intervalos deben ser ignorados.
- Los registros con valor `-1` deben ser ignorados.
- Los registros inválidos no deben interrumpir la ejecución.
- Las estructuras con valores válidos deben representarse correctamente
  en el perfil.

**Resultado observado:**

SecGeol restringe la selección de los campos de echado y azimut a campos
numéricos. Durante el procesamiento, los registros con valores fuera de los
intervalos admitidos son descartados y no se incorporan al perfil. Los
registros con valores válidos se procesan normalmente.

La presencia de valores `-1` en los datos de prueba no interrumpió la
ejecución.

**Resultado general:**

**✅ SATISFACTORIA**

## Prueba 8 — Reconstrucción 3D de polígonos editados

![Reconstrucción 3D de polígonos editados](/validation/img/seccion_mod.png)

**Objetivo:** verificar que SecGeol conserve las modificaciones realizadas
manualmente sobre los polígonos geológicos generados en la fase 2 al realizar
su reconstrucción espacial en la fase 3.

**Procedimiento:**

1. Se generó el perfil topográfico mediante la fase 1.
2. Se generaron los polígonos geológicos mediante la fase 2.
3. Se modificó manualmente la geometría de la parte inferior de varios
   polígonos del perfil.
4. Se guardaron las modificaciones realizadas sobre la capa.
5. La capa de polígonos editada se utilizó como entrada para la fase 3.
6. Se verificó visualmente la geometría obtenida en la reconstrucción 3D.

**Resultado observado:**

La fase 3 procesó correctamente la capa modificada y conservó las ediciones
realizadas sobre los polígonos geológicos. Las modificaciones introducidas
manualmente en la parte inferior de los polígonos fueron reproducidas en la
reconstrucción 3D sin errores.

Esto confirma que la reconstrucción 3D utiliza la geometría existente en la
capa de entrada y permite incorporar modificaciones realizadas por el usuario
después de la generación automática de los polígonos en la fase 2.

**Resultado general:**

**✅ SATISFACTORIA**
