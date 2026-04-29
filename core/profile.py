from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsField,
    QgsVectorFileWriter,
    QgsVectorLayer
)

from qgis.PyQt.QtCore import QVariant

class ProfileManager:
    def __init__(self, gpkg_path=None):
        self.gpkg_path = gpkg_path

        
    def set_gpkg_path(self, gpkg_path):
        self.gpkg_path = gpkg_path

    #--------------------------------------lee layer
    def load_gpkg_layer(self, layer_name):     
        if not self.gpkg_path:
            raise Exception("No se ha definido la ruta del GeoPackage.")

        uri = f"{self.gpkg_path}|layername={layer_name}"
        layer = QgsVectorLayer(uri, layer_name, "ogr")

        if not layer.isValid():
            raise Exception(f"No se pudo cargar la capa '{layer_name}' desde el GPKG.")

        return layer
    #--------------------------------------lee dem
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
    #   Construye líneas verticales divisorias en el perfil para marcar quiebres.
    # --------------------------------- 
    
    def _build_break_lines(self, break_distances, base_y, top_y):
        break_lines = []
        for d in break_distances:
            geom = QgsGeometry.fromPolylineXY([
                QgsPointXY(d, base_y- 1.0),
                QgsPointXY(d, top_y)
            ])
            break_lines.append(geom)
        return break_lines

    
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
    #   Genera puntos del perfil a partir de los vértices de una línea densificada. X = distancia acumulada  
    # --------------------------------- 
    def _generate_profile_points_from_vertices(self, line_geom: QgsGeometry, dem_layer: QgsRasterLayer):
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

            perfil_geom = QgsGeometry.fromPointXY(QgsPointXY(dist_acum, elev))

            feat = QgsFeature()
            feat.setGeometry(perfil_geom)
            feat.setAttributes([
                pt_id,
                dist_acum,
                elev,
                pt.x(),
                pt.y()
            ])

            features.append(feat)
            prev_pt = pt
            pt_id += 1

        return features
    
    # --------------------------------------------------------------------------------
    #   Construye las líneas que forman el perfil y su caja:
    #- linea_perfil : polilínea real del perfil
    #    - base         : línea horizontal inferior
    #    - lim_izq      : límite vertical izquierdo
    #    - lim_der      : límite vertical derecho

    #   Parámetros
    #   features : list[QgsFeature]
    #       Lista de features generados por _generate_profile_points_from_vertices().
    #       Se espera que la geometría de cada feature esté en coordenadas de perfil:
    #       X = distancia acumulada
    # --------------------------------------------------------------------------------
    
    def _build_profile_box_lines(self, features,  extra_depth: float = 100.0):
       
        if not features:
            raise Exception("No hay puntos de perfil para construir la caja.")

        pts = []
        for feat in features:
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue

            pt = geom.asPoint()
            pts.append(QgsPointXY(pt.x(), pt.y()))

        if len(pts) < 2:
            raise Exception("Se requieren al menos dos puntos válidos para construir la caja del perfil.")

        pt_ini = pts[0]
        pt_fin = pts[-1]

        y1 = pt_ini.y()
        y2 = pt_fin.y()
        y_min_global = min(p.y() for p in pts)

        # referencia inferior: el menor entre inicio, fin y mínimo global
        y_base_ref = min(y1, y2, y_min_global)

        # la geometría ya viene con VE aplicada, así que el margen también se escala
       
        base_y = y_base_ref - extra_depth 

        linea_perfil = QgsGeometry.fromPolylineXY(pts)

        base = QgsGeometry.fromPolylineXY([
            QgsPointXY(pt_ini.x(), base_y),
            QgsPointXY(pt_fin.x(), base_y)
        ])

        lim_izq = QgsGeometry.fromPolylineXY([
            QgsPointXY(pt_ini.x(), y1),
            QgsPointXY(pt_ini.x(), base_y)
        ])

        lim_der = QgsGeometry.fromPolylineXY([
            QgsPointXY(pt_fin.x(), y2),
            QgsPointXY(pt_fin.x(), base_y)
        ])

        return {
            "linea_perfil": linea_perfil,
            "base": base,
            "lim_izq": lim_izq,
            "lim_der": lim_der,
            "y1": y1,
            "y2": y2,
            "y_min_global": y_min_global,
            "y_base_ref": y_base_ref,
            "base_y": base_y
        }
    
    # --------------------------------------------------------------------------------
    #   Genera una capa temporal de líneas con:     
    #    linea_perfil
    #    base
    #    lim_izq
    #    lim_der
    # --------------------------------------------------------------------------------


    def build_profile_box_layer(
        self,
        section_layer,
        dem_layer,
        extra_depth: float = 100.0,
        layer_name: str = "Perfil_topografico",
        break_distances=None
            ):

        if break_distances is None:
            break_distances = []

        if section_layer is None or not section_layer.isValid():
            raise Exception("La capa de sección no es válida.")

        if dem_layer is None or not dem_layer.isValid():
            raise Exception("La capa DEM no es válida.")

        if extra_depth <= 0:
            extra_depth = 100.0

        # Tomar la primera geometría válida de la sección
        line_geom = None
        for feat in section_layer.getFeatures():
            geom = feat.geometry()
            if geom is not None and not geom.isEmpty():
                line_geom = geom
                break

        if line_geom is None or line_geom.isEmpty():
            raise Exception("No se encontró una geometría válida en la capa de sección.")

        # -----------------------------
        # DENSIFICAR SEGÚN EL DEM
        # -----------------------------
        pixel_size = self._get_dem_pixel_size(dem_layer)
        print(f"Pixel size DEM: {pixel_size}")

        dense_geom = self._densify_line_geometry(line_geom, pixel_size)
        print("Línea densificada correctamente")

        # -----------------------------
        # GENERAR PUNTOS DEL PERFIL
        # -----------------------------
        profile_point_features = self._generate_profile_points_from_vertices(
            line_geom=dense_geom,
            dem_layer=dem_layer
        )

        if not profile_point_features:
            raise Exception("No fue posible generar puntos para el perfil.")

        # -----------------------------
        # CONSTRUIR PERFIL + CAJA
        # -----------------------------
        box_data = self._build_profile_box_lines(
            features=profile_point_features,
            extra_depth=extra_depth
        )

        top_y = max(p.geometry().asPoint().y() for p in profile_point_features)
        break_geoms = self._build_break_lines(break_distances, box_data["base_y"], top_y)


        # -----------------------------
        # CAPA DE SALIDA
        # -----------------------------
        crs_authid = section_layer.crs().authid()
        if not crs_authid:
            crs_authid = dem_layer.crs().authid()

        out_layer = QgsVectorLayer(f"LineString?crs={crs_authid}", layer_name, "memory")
        prov = out_layer.dataProvider()

        # id_lito = 1


        prov.addAttributes([
            QgsField("id_lito", QVariant.Int),
            QgsField("tipo", QVariant.String),
            QgsField("caja_m", QVariant.Double),
            QgsField("y_min", QVariant.Double),
            QgsField("base_y", QVariant.Double)
        ])
        out_layer.updateFields()

        feature_defs = [
            ("linea_perfil", box_data["linea_perfil"]),
            ("base", box_data["base"]),
            ("lim_izq", box_data["lim_izq"]),
            ("lim_der", box_data["lim_der"])
        ]
        
        for geom in break_geoms:
            feature_defs.append(("quiebre", geom))

        out_features = []
        for tipo, geom in feature_defs:
            feat = QgsFeature(out_layer.fields())
            feat.setGeometry(geom)
            feat.setAttributes([
                0,  # id_lito reservado para líneas base/no litológicas
                tipo,
                float(extra_depth),
                float(box_data["y_min_global"]),
                float(box_data["base_y"])
            ])
            out_features.append(feat)

        prov.addFeatures(out_features)
        out_layer.updateExtents()

        # quitar capa previa con el mismo nombre
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == layer_name:
                QgsProject.instance().removeMapLayer(lyr.id())

        QgsProject.instance().addMapLayer(out_layer)

        print(f"Puntos generados para el perfil: {len(profile_point_features)}")

        return out_layer
    

