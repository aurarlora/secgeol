import os, math

from qgis.core import (
    QgsFeature,
    Qgis,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform
)


class SectionManager:
    def __init__(self, gpkg_path=None):
        self.gpkg_path = gpkg_path

    def set_gpkg_path(self, gpkg_path):
        self.gpkg_path = gpkg_path

    #  Detecta quiebres reales en una línea y devuelve las distancias acumuladas,  donde ocurren los cambios de dirección.
    
    def detect_section_break_distances(self, geom: QgsGeometry, angle_tolerance_deg: float = 5.0):

        if geom is None or geom.isEmpty():
            return []

        pts = list(geom.vertices())
        if len(pts) < 3:
            return []

        cumulative_dist = [0.0]
        for i in range(1, len(pts)):
            seg_len = math.hypot(pts[i].x() - pts[i-1].x(), pts[i].y() - pts[i-1].y())
            cumulative_dist.append(cumulative_dist[-1] + seg_len)

        break_distances = []

        for i in range(1, len(pts) - 1):
            p0 = pts[i - 1]
            p1 = pts[i]
            p2 = pts[i + 1]

            v1x = p1.x() - p0.x()
            v1y = p1.y() - p0.y()
            v2x = p2.x() - p1.x()
            v2y = p2.y() - p1.y()

            norm1 = math.hypot(v1x, v1y)
            norm2 = math.hypot(v2x, v2y)

            if norm1 == 0 or norm2 == 0:
                continue

            dot = (v1x * v2x + v1y * v2y) / (norm1 * norm2)
            dot = max(-1.0, min(1.0, dot))

            angle_deg = math.degrees(math.acos(dot))

            if angle_deg > angle_tolerance_deg:
                break_distances.append(cumulative_dist[i])

        return break_distances

    
    def recortar_seccion_por_distancia(self, geom, dist_inicio, dist_fin):
        if geom is None or geom.isEmpty():
            raise Exception("La geometría de la sección está vacía.")

        if dist_inicio > dist_fin:
            dist_inicio, dist_fin = dist_fin, dist_inicio

        longitud_total = geom.length()

        if dist_inicio < 0 or dist_fin > longitud_total:
            raise Exception(
                "Las distancias de recorte están fuera de la longitud de la sección."
            )

        vertices = list(geom.vertices())

        if len(vertices) < 2:
            raise Exception(
                "La sección debe contener al menos dos vértices."
            )

        puntos_salida = []
        acumulada = 0.0

        for i in range(len(vertices) - 1):
            p1 = QgsPointXY(vertices[i])
            p2 = QgsPointXY(vertices[i + 1])

            longitud_segmento = p1.distance(p2)

            if longitud_segmento == 0:
                continue

            inicio_segmento = acumulada
            fin_segmento = acumulada + longitud_segmento

            # El segmento queda completamente antes del intervalo útil
            if fin_segmento < dist_inicio:
                acumulada = fin_segmento
                continue

            # Ya rebasamos el final del intervalo
            if inicio_segmento > dist_fin:
                break

            # Punto exacto de inicio del recorte
            if inicio_segmento <= dist_inicio <= fin_segmento:
                ratio = (
                    (dist_inicio - inicio_segmento)
                    / longitud_segmento
                )

                x = p1.x() + ratio * (p2.x() - p1.x())
                y = p1.y() + ratio * (p2.y() - p1.y())

                punto_inicio = QgsPointXY(x, y)

                if not puntos_salida or puntos_salida[-1] != punto_inicio:
                    puntos_salida.append(punto_inicio)

            # Añadir el vértice final del segmento si cae dentro del intervalo
            if dist_inicio <= fin_segmento <= dist_fin:
                if not puntos_salida or puntos_salida[-1] != p2:
                    puntos_salida.append(p2)

            # Punto exacto de fin del recorte
            if inicio_segmento <= dist_fin <= fin_segmento:
                ratio = (
                    (dist_fin - inicio_segmento)
                    / longitud_segmento
                )

                x = p1.x() + ratio * (p2.x() - p1.x())
                y = p1.y() + ratio * (p2.y() - p1.y())

                punto_fin = QgsPointXY(x, y)

                if not puntos_salida or puntos_salida[-1] != punto_fin:
                    puntos_salida.append(punto_fin)

                break

            acumulada = fin_segmento

        if len(puntos_salida) < 2:
            raise Exception(
                "No fue posible recortar la sección entre las distancias indicadas."
            )

        return QgsGeometry.fromPolylineXY(puntos_salida)

    #  Invierte el sentido de una geometría de línea simple.  Verificar que las partes tambien se cambien

    def _reverse_linestring_geometry(self, geom: QgsGeometry) -> QgsGeometry:
        if geom is None or geom.isEmpty():
            return geom

        if geom.isMultipart():
            parts = geom.asMultiPolyline()
            if not parts:
                return geom

            reversed_parts = []
            for part in parts:
                reversed_parts.append(list(reversed(part)))

            return QgsGeometry.fromMultiPolylineXY(reversed_parts)

        line = geom.asPolyline()
        if not line:
            return geom

        reversed_line = list(reversed(line))
        return QgsGeometry.fromPolylineXY(reversed_line)
    
    
    #  Transforma una geometría desde source_crs hacia target_crs.
    
    def _transform_geometry_to_crs(
        self,
        geom: QgsGeometry,
        source_crs: QgsCoordinateReferenceSystem,
        target_crs: QgsCoordinateReferenceSystem
    ) -> QgsGeometry:
        if geom is None or geom.isEmpty():
            return geom

        if not source_crs.isValid():
            raise Exception(self.tr("El CRS de origen no es válido."))

        if not target_crs.isValid():
            raise Exception(self.tr("El CRS de destino no es válido."))

        if source_crs == target_crs:
            return QgsGeometry(geom)

        new_geom = QgsGeometry(geom)
        transform = QgsCoordinateTransform(
            source_crs,
            target_crs,
            QgsProject.instance()
        )
        new_geom.transform(transform)
        return new_geom

    #   Copia una feature conservando atributos existentes y agregando internos.
   
    def _prepare_section_feature(
        self,
        source_feature: QgsFeature,
        invertida=False,
        source_crs=None,
        target_crs=None
    ) -> QgsFeature:

        geom = source_feature.geometry()

        # Transformar CRS si es necesario
        if source_crs and target_crs and source_crs != target_crs:
            geom = self._transform_geometry_to_crs(geom, source_crs, target_crs)

        # Invertir si aplica
        if invertida:
            geom = self._reverse_linestring_geometry(geom)

        new_feat = QgsFeature()
        new_feat.setGeometry(geom)

        return new_feat
    
    #  Prepara una capa de trabajo a partir de una feature dibujada por la herramienta.
   
    def prepare_section_layer_from_feature(
        self,
        source_feature: QgsFeature,
        source_crs,
        target_crs,
        invertida=False
    ) -> QgsVectorLayer:

        if source_feature is None:
            raise Exception(self.tr("No se proporcionó una sección válida."))

        if target_crs is None or not target_crs.isValid():
            raise Exception(self.tr("El CRS de destino no es válido."))

        crs_authid = target_crs.authid()

        temp_layer = QgsVectorLayer(f"LineString?crs={crs_authid}", "seccion_temp", "memory")
        provider = temp_layer.dataProvider()

        new_feat = self._prepare_section_feature(
            source_feature,
            invertida=invertida,
            source_crs=source_crs,
            target_crs=target_crs
        )

        provider.addFeatures([new_feat])
        temp_layer.updateExtents()

        return temp_layer
    

    # Obtener la geometría efectiva de la sección

    def obtener_geometria_seccion_efectiva(self, section_layer):
        if section_layer is None or not section_layer.isValid():
            return None

        for feat in section_layer.getFeatures():
            geom = feat.geometry()
            if geom is not None and not geom.isEmpty():
                return geom

        return None
    
    # Intersectar con  geologia
    
    def intersectar_seccion_con_geologia(self, section_geom, section_crs, geo_layer, campo_geo=None):
        segmentos = []
        id_lito = 1

        if section_geom is None or section_geom.isEmpty():
            return segmentos

        if geo_layer is None:
            return segmentos

        transform = None
        if geo_layer.crs() != section_crs:
            transform = QgsCoordinateTransform(
                geo_layer.crs(),
                section_crs,
                QgsProject.instance()
            )

        for feat_geo in geo_layer.getFeatures():
            geom_geo = QgsGeometry(feat_geo.geometry())

            if geom_geo is None or geom_geo.isEmpty():
                continue

            if transform is not None:
                geom_geo.transform(transform)

            if not section_geom.intersects(geom_geo):
                continue

            inter = section_geom.intersection(geom_geo)

            if inter is None or inter.isEmpty():
                continue

            # Calcular distancia inicial y final sobre la sección
            vertices = list(inter.vertices())

            if len(vertices) < 2:
                continue

            p_ini = vertices[0]
            p_fin = vertices[-1]

            dist_ini = section_geom.lineLocatePoint(QgsGeometry.fromPointXY(QgsPointXY(p_ini)))
            dist_fin = section_geom.lineLocatePoint(QgsGeometry.fromPointXY(QgsPointXY(p_fin)))

            if dist_ini > dist_fin:
                dist_ini, dist_fin = dist_fin, dist_ini

                        
            valor_campo = None

            if campo_geo and campo_geo in feat_geo.fields().names():
                valor_campo = feat_geo[campo_geo]
            else:
                valor_campo = None

            segmentos.append({
                "id_lito": id_lito,
                "campo_geo": campo_geo,
                "valor_geo": valor_campo,
                "dist_ini": dist_ini,
                "dist_fin": dist_fin,
                "geometry": inter
            })
            id_lito += 1

        return segmentos
    

    def intersectar_seccion_con_estructuras(
        self,
        section_geom,
        section_crs,
        est_layer,
        campo_dip,
        campo_azimuth
    ):

        estructuras = []

        if section_geom is None or section_geom.isEmpty():
            return estructuras

        if est_layer is None:
            return estructuras
        

        # Reproyección si es necesario
        
        est_crs = est_layer.crs()

        transform = None

        if est_crs != section_crs:
            transform = QgsCoordinateTransform(
                est_crs,
                section_crs,
                QgsProject.instance()
            )

        # Recorrer estructuras
        
        for feat in est_layer.getFeatures():

            geom_est = QgsGeometry(feat.geometry())

            if geom_est is None or geom_est.isEmpty():
                continue

            # reproyectar geometría
            if transform is not None:
                geom_est.transform(transform)

            # atributos
            dip = feat[campo_dip]
            azimuth = feat[campo_azimuth]


            # Validaciones

            try:
                dip = float(dip)
                azimuth = float(azimuth)
            except (TypeError, ValueError):
                continue

            # -1 o valores sin dato
            if dip == -1 or azimuth == -1:
                continue

            # rangos válidos
            if dip <= 0 or dip > 90:
                continue

            if azimuth < 0 or azimuth > 360:
                continue


            # Intersección

            inter = geom_est.intersection(section_geom)

            if inter.isEmpty():
                continue

            # Obtenemos un punto
            if inter.type() != Qgis.GeometryType.Point:
                continue

            pt = inter.asPoint()

            punto_geom = QgsGeometry.fromPointXY(pt)

            dist = section_geom.lineLocatePoint(punto_geom)
            azimuth_seccion = self.calcular_azimuth_local_seccion(section_geom, dist)

            if azimuth_seccion is None:
                continue

            delta = (azimuth - azimuth_seccion) % 360

            if 0 <= delta <= 180:
                lado = "derecha"
            else:
                lado = "izquierda"
                
            estructuras.append({
                "dist": dist,
                "echado": dip,
                "azimuth": azimuth, 
                "azimuth_seccion": azimuth_seccion,
                "lado": lado
            })

        return estructuras
    
    #    Calcula el azimuth local de la sección en la distancia dada.
    #    Azimuth en grados: 0=N, 90=E, 180=S, 270=W.
    
    def calcular_azimuth_local_seccion(self, section_geom, dist_objetivo):

        vertices = list(section_geom.vertices())

        if len(vertices) < 2:
            return None

        distancia_acum = 0.0

        for i in range(len(vertices) - 1):
            p1 = vertices[i]
            p2 = vertices[i + 1]

            seg_len = p1.distance(p2)
            seg_ini = distancia_acum
            seg_fin = distancia_acum + seg_len

            if seg_ini <= dist_objetivo <= seg_fin:
                dx = p2.x() - p1.x()
                dy = p2.y() - p1.y()

                azimuth = math.degrees(math.atan2(dx, dy)) % 360
                return azimuth

            distancia_acum = seg_fin

        return None
    