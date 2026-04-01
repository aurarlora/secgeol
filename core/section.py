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
"'"

"'"

class SectionManager:
    def __init__(self, gpkg_path=None):
        self.gpkg_path = gpkg_path

    def set_gpkg_path(self, gpkg_path):
        self.gpkg_path = gpkg_path

    def _internal_field_names(self):
        return [field.name() for field in fields_section_internal()]
    
    # ---------------------------------
    #   Conserva los campos del usuario y agrega los internos si no existen.
    # --------------------------------- 

    def _merge_fields_with_internal(self, source_fields: QgsFields) -> QgsFields:

        merged = QgsFields()

        existing_names = set()

        for field in source_fields:
            merged.append(field)
            existing_names.add(field.name().lower())

        for field in fields_section_internal():
            if field.name().lower() not in existing_names:
                merged.append(field)

        return merged
    
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

    def _copy_feature_with_fields(
        self,
        source_feature: QgsFeature,
        target_fields: QgsFields,
        invertida=False,
        origen="usuario",
        source_crs: QgsCoordinateReferenceSystem = None,
        target_crs: QgsCoordinateReferenceSystem = None
    ) -> QgsFeature:

        new_feature = QgsFeature(target_fields)

        source_geom = source_feature.geometry()

        if invertida:
            source_geom = self._reverse_linestring_geometry(source_geom)

        if source_crs is not None and target_crs is not None:
            source_geom = self._transform_geometry_to_crs(source_geom, source_crs, target_crs)

        new_feature.setGeometry(source_geom)

        source_attr_map = {}
        for idx, field in enumerate(source_feature.fields()):
            source_attr_map[field.name()] = source_feature.attribute(idx)

        attrs = []
        for field in target_fields:
            name = field.name()

            if name in source_attr_map:
                attrs.append(source_attr_map[name])
            elif name == "sec_id":
                attrs.append(source_feature.id())
            elif name == "origen":
                attrs.append(origen)
            elif name == "invertida":
                attrs.append(1 if invertida else 0)
            else:
                attrs.append(None)

        new_feature.setAttributes(attrs)
        return new_feature
    
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

        source_fields = source_layer.fields()
        merged_fields = self._merge_fields_with_internal(source_fields)

        source_crs = source_layer.crs()
        crs_authid = target_crs.authid()

        temp_layer = self._create_memory_layer("seccion_temp", crs_authid, merged_fields)
        provider = temp_layer.dataProvider()

        features_to_add = []
        for feat in source_layer.getFeatures():
            new_feat = self._copy_feature_with_fields(
                feat,
                merged_fields,
                invertida=invertida,
                origen="usuario",
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

        new_feat = self._copy_feature_with_fields(
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

   