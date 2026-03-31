
    

## C:\Users\auraramos\AppData\Roaming\QGIS\QGIS4\profiles\default\python\plugins\secgeol

# De profile



from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsVectorFileWriter,
    QgsVectorLayer
)


class ProfileManager:
    def __init__(self, gpkg_path=None):
        self.gpkg_path = gpkg_path

    def set_gpkg_path(self, gpkg_path):
        self.gpkg_path = gpkg_path

    def load_gpkg_layer(self, layer_name):
        if not self.gpkg_path:
            raise Exception("No se ha definido la ruta del GeoPackage.")

        uri = f"{self.gpkg_path}|layername={layer_name}"
        layer = QgsVectorLayer(uri, layer_name, "ogr")

        if not layer.isValid():
            raise Exception(f"No se pudo cargar la capa '{layer_name}' desde el GPKG.")

        return layer

    def _sample_raster_value(self, raster_layer: QgsRasterLayer, x: float, y: float):
        """
        Devuelve el valor del raster en la coordenada x, y.
        """
        provider = raster_layer.dataProvider()
        result = provider.sample(QgsPointXY(x, y), 1)

        if isinstance(result, tuple):
            value = result[0]
            ok = result[1] if len(result) > 1 else True
            if not ok:
                return None
            return value

        return result
    

    # ---------------------------------
    #  Genera features de puntos a lo largo de la línea con distancia acumulada y elevación.
    # --------------------------------- 

    def _generate_profile_points(self, line_geom: QgsGeometry, dem_layer: QgsRasterLayer, step: float):       

        if line_geom is None or line_geom.isEmpty():
            raise Exception("La geometría de la sección está vacía.")

        length = line_geom.length()
        if length <= 0:
            raise Exception("La longitud de la sección es inválida.")

        features = []
        dist = 0.0
        pt_id = 1
        last_dist = None

        while dist <= length:
            point_geom = line_geom.interpolate(dist)
            point = point_geom.asPoint()

            elev = self._sample_raster_value(dem_layer, point.x(), point.y())

            feat = QgsFeature()
            feat.setGeometry(point_geom)
            feat.setAttributes([
                pt_id,         # pt_id
                dist,          # dist_m
                elev,          # elev
                point.x(),     # x
                point.y()      # y
            ])

            features.append(feat)

            last_dist = dist
            pt_id += 1
            dist += step

        # asegurar último punto exacto al final
        if length > 0 and (last_dist is None or last_dist < length):
            point_geom = line_geom.interpolate(length)
            point = point_geom.asPoint()
            elev = self._sample_raster_value(dem_layer, point.x(), point.y())

            feat = QgsFeature()
            feat.setGeometry(point_geom)
            feat.setAttributes([
                pt_id,
                length,
                elev,
                point.x(),
                point.y()
            ])
            features.append(feat)

        return features

    def save_points_to_gpkg(self, points_layer, layer_name="sec_points_profile"):
        """
        Guarda la capa de puntos en el GeoPackage.
        """
        if not self.gpkg_path:
            raise Exception("No se ha definido la ruta del GeoPackage.")

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer_name
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer

        writer_result = QgsVectorFileWriter.writeAsVectorFormatV3(
            points_layer,
            self.gpkg_path,
            QgsProject.instance().transformContext(),
            options
        )

        print(f"Resultado al guardar {layer_name}: {writer_result}")

        result = writer_result[0]
        error_message = writer_result[1] if len(writer_result) > 1 else ""

        if result != QgsVectorFileWriter.NoError:
            raise Exception(f"Error al guardar '{layer_name}' en el GPKG: {error_message}")

    def build_profile_points_layer(self, section_layer: QgsVectorLayer, dem_layer: QgsRasterLayer, step: float):
        """
        Construye una capa temporal de puntos del perfil.
        """
        if section_layer is None or not section_layer.isValid():
            raise Exception("La capa de sección no es válida.")

        if dem_layer is None or not dem_layer.isValid():
            raise Exception("La capa DEM no es válida.")

        features = list(section_layer.getFeatures())
        if not features:
            raise Exception("La capa de sección no contiene entidades.")

        # por ahora trabajamos con la primera línea
        line_feature = features[0]
        line_geom = line_feature.geometry()

        crs_authid = section_layer.crs().authid()
        uri = f"Point?crs={crs_authid}&field=pt_id:integer&field=dist_m:double&field=elev:double&field=x:double&field=y:double"
        points_layer = QgsVectorLayer(uri, "sec_points_profile", "memory")

        provider = points_layer.dataProvider()
        profile_features = self._generate_profile_points(line_geom, dem_layer, step)
        provider.addFeatures(profile_features)
        points_layer.updateExtents()

        return points_layer
    