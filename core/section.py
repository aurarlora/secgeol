import os, math

from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPoint,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform
)
from qgis.PyQt.QtCore import QVariant
# from .fields import fields_section_internal

class SectionManager:
    def __init__(self, gpkg_path=None):
        self.gpkg_path = gpkg_path

    def set_gpkg_path(self, gpkg_path):
        self.gpkg_path = gpkg_path

    # ---------------------------------
    #  Detecta quiebres reales en una línea y devuelve las distancias acumuladas,  donde ocurren los cambios de dirección.
    # --------------------------------- 

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

    # ---------------------------------
    #  Invierte el sentido de una geometría de línea simple.
    # --------------------------------- 

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
    
    # ---------------------------------
    #  Transforma una geometría desde source_crs hacia target_crs.
    # --------------------------------- 

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

    
    # ---------------------------------
    #  Crea una capa temporal en memoria con los campos deseados.
    # --------------------------------- 

    def _create_memory_layer(self, layer_name: str, crs_authid: str, fields: QgsFields) -> QgsVectorLayer:

        uri = f"LineString?crs={crs_authid}"
        layer = QgsVectorLayer(uri, layer_name, "memory")
        provider = layer.dataProvider()
        provider.addAttributes(fields)
        layer.updateFields()
        return layer
    
    # ---------------------------------
    #   Copia una feature conservando atributos existentes y agregando internos.
    # --------------------------------- 

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
    
    # ---------------------------------
    #   Toma una capa del usuario, conserva sus campos y agrega los internos.
    #    Devuelve una capa temporal lista para guardar.
    # --------------------------------- 


    def prepare_section_layer_from_user(
        self,
        source_layer: QgsVectorLayer,
        target_crs: QgsCoordinateReferenceSystem,
        invertida=False
    ) -> QgsVectorLayer:

        if source_layer is None or not source_layer.isValid():
            raise Exception(self.tr("La capa de sección del usuario no es válida."))

        if source_layer.geometryType() != QgsWkbTypes.LineGeometry:
            raise Exception(self.tr("La capa de sección debe ser de tipo línea."))

        if target_crs is None or not target_crs.isValid():
            raise Exception(self.tr("El CRS de destino no es válido."))

        source_crs = source_layer.crs()
        crs_authid = target_crs.authid()

        temp_layer = QgsVectorLayer(f"LineString?crs={crs_authid}", "seccion_temp", "memory")
        provider = temp_layer.dataProvider()

        features_to_add = []
        for feat in source_layer.getFeatures():
            new_feat = self._prepare_section_feature(
                feat,
                invertida=invertida,
                source_crs=source_crs,
                target_crs=target_crs
            )
            features_to_add.append(new_feat)

        provider.addFeatures(features_to_add)
        temp_layer.updateExtents()

        return temp_layer
    
    # ---------------------------------
    #  Prepara una capa de trabajo a partir de una feature dibujada por la herramienta.
    # --------------------------------- 
   
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
    

    #------- sacar la geometría efectiva de la sección------

    def obtener_geometria_seccion_efectiva(self, section_layer):
        if section_layer is None or not section_layer.isValid():
            return None

        for feat in section_layer.getFeatures():
            geom = feat.geometry()
            if geom is not None and not geom.isEmpty():
                return geom

        return None

    def obtener_geometria_seccion_efectiva(self, section_layer): 
        geo_layer = self.MapLayerGeo.currentLayer()

        if geo_layer is None:
            self.FieldClasGeo.setLayer(None)
            self.mostrar_ayuda(
                "Capa de geología",
                "Seleccione una capa geológica para cargar sus campos."
            )
            return

        # Cargar automáticamente los campos en el combo
        self.FieldClasGeo.setLayer(geo_layer)

        crs = geo_layer.crs()
        crs_authid = crs.authid()
        crs_name = crs.description()

        if crs_authid:
            crs_info = f"{crs_authid} - {crs_name}"
        else:
            crs_info = crs_name

        total_campos = len(geo_layer.fields())

        self.mostrar_ayuda(
            "Capa de geología",
            f"Capa seleccionada: {geo_layer.name()}<br>"
            f"CRS: {crs_info}<br>"
            f"Campos disponibles: {total_campos}<br>"
            f"Seleccione el campo que se utilizará para clasificar los segmentos de la sección."
            )