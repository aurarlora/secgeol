# Matriz de validación de SecGeol

Este documento registra las pruebas funcionales realizadas durante la
validación manual de SecGeol en QGIS.

El objetivo es comprobar el comportamiento de las tres fases del complemento
bajo distintas configuraciones de datos de entrada y documentar cualquier
incidencia detectada antes de su publicación.

## Resumen de pruebas

| Prueba | DEM | Sección | Geología | Estructuras | Fase 1 | Fase 2 | Fase 3 | Resultado |
|---|---|---|---|---|---|---|---|---|
| 1 | ITRF08 / UTM 14N | EPSG:32614 | EPSG:32614 | EPSG:32614 | ❌ | ❌ | ❌ | No satisfactoria |

---

## Prueba 1 — Flujo completo con CRS definidos

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

Las capas vectoriales cuyo CRS sea diferente al de la fuente de elevación
deben ser reproyectadas al CRS de ésta. Si una capa ya utiliza el mismo CRS,
no requiere reproyección.

Las salidas que representan geometrías espaciales deben conservar el CRS
de trabajo correspondiente.

### Resultado observado

#### Fase 1 — Sección a perfil

La fase genera las capas de salida y transfiere correctamente la información
geológica y estructural.

Sin embargo:

- el perfil topográfico se genera sin CRS;
- la sección guía (`_guia`) se genera sin CRS.

**Resultado de la fase:** ❌ No satisfactoria.

#### Fase 2 — Líneas a polígonos

La fase genera las entidades y la tabla de atributos. También se genera
correctamente la capa de ejes (`_ejes`).

Sin embargo:

- el perfil poligonal aparece identificado como `EPSG:4326`;
- las geometrías no se visualizan correctamente en el lienzo debido a que
  las coordenadas del perfil corresponden a distancia–elevación y no a
  longitud–latitud;
- la capa `_ejes` se genera sin CRS.

**Resultado de la fase:** ❌ No satisfactoria.

#### Fase 3 — Reconstrucción 3D

La reconstrucción geométrica se realiza y se genera el perfil 3D.

La geometría reconstruida coincide espacialmente con la sección y el MDE
al visualizarla en un entorno 3D.

Sin embargo:

- la capa 3D resultante se genera sin CRS.
**Resultado de la fase:** ❌ No satisfactoria.

### Incidencias detectadas y correcciones

Durante la ejecución inicial de la prueba se detectaron inconsistencias en la
asignación y propagación del sistema de referencia espacial. Aunque las tres
fases completaban sus procesos principales y la reconstrucción geométrica final
era correcta, algunas capas de salida no conservaban adecuadamente el CRS de
trabajo.

La revisión del código mostró que SecGeol utilizaba `authid()` para obtener y
propagar el CRS. Se comprobó que la fuente de elevación utilizada en esta prueba
posee un CRS válido (`MEXICO_ITRF_2008_UTM_Zone_14N`), pero sin un identificador
`authid()` disponible. Esto provocaba la pérdida del CRS en algunas salidas y,
en la fase 2, la asignación incorrecta de `EPSG:4326`.

Se modificó el manejo del CRS para utilizar directamente el objeto
`QgsCoordinateReferenceSystem` y asignarlo a las capas de salida mediante
`setCrs()`.

Después de aplicar las correcciones se repitió el flujo completo con los mismos
datos de entrada.

### Validación posterior a la corrección

La repetición de la prueba produjo correctamente:

- perfil topográfico con `MEXICO_ITRF_2008_UTM_Zone_14N`;
- sección guía con `MEXICO_ITRF_2008_UTM_Zone_14N`;
- polígonos geológicos 2D con `MEXICO_ITRF_2008_UTM_Zone_14N`;
- capa de ejes con `MEXICO_ITRF_2008_UTM_Zone_14N`;
- reconstrucción geológica 3D con `MEXICO_ITRF_2008_UTM_Zone_14N`.

Adicionalmente, la reconstrucción 3D se verificó de forma independiente en
ArcScene. La línea original de la sección fue configurada para obtener su
elevación directamente del DEM y se observó coincidencia con el borde superior
del perfil reconstruido por SecGeol.

![Validación de la reconstrucción 3D en ArcScene](../img/sec_lin.png)

La comparación confirma la correspondencia espacial de la reconstrucción y la
consistencia de las elevaciones obtenidas a partir del DEM.

### Resultado general

**✅ SATISFACTORIA**

La prueba permitió detectar y corregir una deficiencia en la propagación del CRS.
Después de la corrección, las tres fases del flujo se ejecutaron correctamente,
las capas de salida conservaron el sistema de referencia espacial esperado y la
reconstrucción tridimensional fue consistente con la elevación derivada
independientemente del DEM.