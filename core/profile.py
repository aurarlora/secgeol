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
    #  Obtiene un tamaño promedio de pixel del DEM.
    # --------------------------------- 
    def _get_dem_pixel_size(self, dem_layer: QgsRasterLayer):
        extent = dem_layer.extent()
        width = dem_layer.width()
        height = dem_layer.height()

        if width == 0 or height == 0:
            raise Exception("El DEM no tiene dimensiones válidas.")

        pixel_size_x = extent.width() / width
        pixel_size_y = extent.height() / height

        return (abs(pixel_size_x) + abs(pixel_size_y)) / 2.0
    
    # ---------------------------------
    #   Densifica la línea usando una distancia fija entre vértices.
    # --------------------------------- 
    def _densify_line_geometry(self, line_geom: QgsGeometry, distance: float) -> QgsGeometry:
        if line_geom is None or line_geom.isEmpty():
            raise Exception("La geometría de la sección está vacía.")

        if distance <= 0:
            raise Exception("La distancia de densificación debe ser mayor que cero.")

        return line_geom.densifyByDistance(distance)
     
    # ---------------------------------
    #   Genera puntos del perfil a partir de los vértices de una línea densificada. X = distancia acumulada  Y = elevación * ve
    # --------------------------------- 
    def _generate_profile_points_from_vertices(self, line_geom: QgsGeometry, dem_layer: QgsRasterLayer, ve: float):
        if line_geom is None or line_geom.isEmpty():
            raise Exception("La geometría de la sección está vacía.")

        vertices = list(line_geom.vertices())
        if len(vertices) < 2:
            raise Exception("La línea densificada no tiene suficientes vértices.")

        features = []
        dist_acum = 0.0
        pt_id = 1
        prev_pt = None

        for pt in vertices:
            if prev_pt is not None:
                dx = pt.x() - prev_pt.x()
                dy = pt.y() - prev_pt.y()
                dist_acum += (dx**2 + dy**2) ** 0.5

            elev = self._sample_raster_value(dem_layer, pt.x(), pt.y())
            if elev is None:
                elev = 0.0

            perfil_geom = QgsGeometry.fromPointXY(QgsPointXY(dist_acum, elev * ve))

            feat = QgsFeature()
            feat.setGeometry(perfil_geom)
            feat.setAttributes([
                pt_id,       # pt_id
                dist_acum,   # dist_m
                elev,        # elev
                pt.x(),      # map_x
                pt.y()       # map_y
            ])

            features.append(feat)
            prev_pt = pt
            pt_id += 1

        return features
    
    # ---------------------------------
    #   Construye una capa temporal de puntos del perfil a partir de una línea densificada.
    # --------------------------------- 

    def build_profile_points_layer(self, section_layer: QgsVectorLayer, dem_layer: QgsRasterLayer, ve: float = 1.0):

        if section_layer is None or not section_layer.isValid():
            raise Exception("La capa de sección no es válida.")

        if dem_layer is None or not dem_layer.isValid():
            raise Exception("La capa DEM no es válida.")

        features = list(section_layer.getFeatures())
        if not features:
            raise Exception("La capa de sección no contiene entidades.")

        line_feature = features[0]
        line_geom = line_feature.geometry()

        pixel_size = self._get_dem_pixel_size(dem_layer)
        print(f"Pixel size DEM: {pixel_size}")

        dense_geom = self._densify_line_geometry(line_geom, pixel_size)
        print("Línea densificada correctamente")

        crs_authid = section_layer.crs().authid()
        uri = (
            f"Point?crs={crs_authid}"
            f"&field=pt_id:integer"
            f"&field=dist_m:double"
            f"&field=elev:double"
            f"&field=map_x:double"
            f"&field=map_y:double"
        )

        points_layer = QgsVectorLayer(uri, "sec_points_profile", "memory")
        provider = points_layer.dataProvider()

        profile_features = self._generate_profile_points_from_vertices(dense_geom, dem_layer, ve)
        provider.addFeatures(profile_features)
        points_layer.updateExtents()

        print(f"Puntos generados: {len(profile_features)}")

        return points_layer
    
    # ---------------------------------
    #   Guarda la capa de puntos en el GeoPackage.
    # --------------------------------- 

    
    def save_points_to_gpkg(self, points_layer, layer_name="sec_points_profile"):
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

