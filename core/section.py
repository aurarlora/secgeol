import os

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
from .fields import fields_section_internal

class SectionManager:
    def __init__(self, gpkg_path=None):
        self.gpkg_path = gpkg_path

    def set_gpkg_path(self, gpkg_path):
        self.gpkg_path = gpkg_path

    # ---------------------------------
    #  Invierte el sentido de una geometría de línea simple.
    # --------------------------------- 

    def _reverse_linestring_geometry(self, geom: QgsGeometry) -> QgsGeometry:

        if geom is None or geom.isEmpty():
            return geom

        if QgsWkbTypes.isMultipart(geom.wkbType()):
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
            raise Exception("El CRS de origen no es válido.")

        if not target_crs.isValid():
            raise Exception("El CRS de destino no es válido.")

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
            raise Exception("La capa de sección del usuario no es válida.")

        if source_layer.geometryType() != QgsWkbTypes.LineGeometry:
            raise Exception("La capa de sección debe ser de tipo línea.")

        if target_crs is None or not target_crs.isValid():
            raise Exception("El CRS de destino no es válido.")

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
        crs_authid: str,
        invertida=False
        ) -> QgsVectorLayer:

        if source_feature is None:
            raise Exception("No se proporcionó una sección dibujada.")

        merged_fields = fields_section_internal()

        temp_layer = self._create_memory_layer("seccion_temp", crs_authid, merged_fields)
        provider = temp_layer.dataProvider()

        new_feat = self._prepare_section_feature(
            source_feature,
            merged_fields,
            invertida=invertida,
            origen="digitalizada",
            source_crs=None,
            target_crs=None
        )

        provider.addFeatures([new_feat])
        temp_layer.updateExtents()

        return temp_layer

   