import math
from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsField,
    QgsMessageLog,
    QgsVectorLayer,

)

from qgis.PyQt.QtCore import QVariant

class ProfileManager:
    #Lee un valor del DEM
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
    
    #   Construye líneas verticales divisorias en el perfil para marcar quiebres.
    
    def _build_break_lines(self, break_distances, base_y, top_y):
        break_lines = []
        for d in break_distances:
            geom = QgsGeometry.fromPolylineXY([
                QgsPointXY(d, base_y- 1.0),
                QgsPointXY(d, top_y)
            ])
            break_lines.append(geom)
        return break_lines

    
    #  Obtiene un tamaño promedio de pixel del DEM.
    
    def _get_dem_pixel_size(self, dem_layer: QgsRasterLayer):
        extent = dem_layer.extent()
        width = dem_layer.width()
        height = dem_layer.height()

        if width == 0 or height == 0:
            raise Exception("El DEM no tiene dimensiones válidas.")

        pixel_size_x = extent.width() / width
        pixel_size_y = extent.height() / height

        return (abs(pixel_size_x) + abs(pixel_size_y)) / 2.0
    
    
    #   Densifica la línea usando una distancia fija entre vértices.  
    
    def _densify_line_geometry(self, line_geom: QgsGeometry, distance: float) -> QgsGeometry:
        if line_geom is None or line_geom.isEmpty():
            raise Exception("La geometría de la sección está vacía.")

        if distance <= 0:
            raise Exception("La distancia de densificación debe ser mayor que cero.")

        return line_geom.densifyByDistance(distance)
     
    
    #   Genera puntos del perfil a partir de los vértices de una línea densificada. X = distancia acumulada  
    
    def _generate_profile_points_from_vertices(
        self,
        line_geom: QgsGeometry,
        dem_layer: QgsRasterLayer
        ):
        if line_geom is None or line_geom.isEmpty():
            raise Exception("La geometría de la sección está vacía.")

        vertices = list(line_geom.vertices())

        if len(vertices) < 2:
            raise Exception(
                "La línea densificada no tiene suficientes vértices."
            )

        features = []
        dist_acum = 0.0
        pt_id = 1
        prev_pt = None

        # Última elevación válida obtenida del DEM
        last_valid_elev = None

        for pt in vertices:
            if prev_pt is not None:
                dx = pt.x() - prev_pt.x()
                dy = pt.y() - prev_pt.y()
                dist_acum += (dx**2 + dy**2) ** 0.5

            elev = self._sample_raster_value(
                dem_layer,
                pt.x(),
                pt.y()
            )

            if elev is None:
                if last_valid_elev is None:
                    raise Exception(
                        "No fue posible obtener una elevación válida "
                        f"para el primer punto del perfil: "
                        f"X={pt.x():.3f}, Y={pt.y():.3f}."
                    )

                elev = last_valid_elev

                print(
                    "Elevación no disponible. "
                    f"Se utilizó el valor anterior en el punto {pt_id}: "
                    f"{elev:.3f} m"
                )
            else:
                last_valid_elev = elev

            perfil_geom = QgsGeometry.fromPointXY(
                QgsPointXY(dist_acum, elev)
            )

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
    
        
        # Recorta una línea usando distancias acumuladas sobre la geometría.
        # Conserva los vértices intermedios para seguir la forma real del perfil.
        

    def recortar_linea_por_distancia(self, linea_geom, dist_ini, dist_fin):

        if linea_geom is None or linea_geom.isEmpty():
            return None

        if dist_ini > dist_fin:
            dist_ini, dist_fin = dist_fin, dist_ini

        vertices = list(linea_geom.vertices())

        if len(vertices) < 2:
            return None

        puntos_salida = []

        for i in range(len(vertices) - 1):
            p1 = vertices[i]
            p2 = vertices[i + 1]

            x1, y1 = p1.x(), p1.y()
            x2, y2 = p2.x(), p2.y()

            # segmento fuera del rango
            if max(x1, x2) < dist_ini:
                continue

            if min(x1, x2) > dist_fin:
                break

            # punto inicial       # no recuerdo si funciona cuando cambie de sentido la línea, verificar
            if x1 <= dist_ini <= x2:
                ratio = (dist_ini - x1) / (x2 - x1) if x2 != x1 else 0
                y_ini = y1 + ratio * (y2 - y1)
                puntos_salida.append(QgsPointXY(dist_ini, y_ini))

            # vértice intermedio
            if dist_ini <= x1 <= dist_fin:
                puntos_salida.append(QgsPointXY(x1, y1))

            # punto final
            if x1 <= dist_fin <= x2:
                ratio = (dist_fin - x1) / (x2 - x1) if x2 != x1 else 0
                y_fin = y1 + ratio * (y2 - y1)
                puntos_salida.append(QgsPointXY(dist_fin, y_fin))
                break

        # limpiar duplicados consecutivos
        puntos_limpios = []
        for p in puntos_salida:
            if not puntos_limpios or p != puntos_limpios[-1]:
                puntos_limpios.append(p)

        if len(puntos_limpios) < 2:
            return None

        return QgsGeometry.fromPolylineXY(puntos_limpios)

    
    #   Construye las líneas que forman el perfil y su caja:linea_perfil, base, lim_izq, lim_der
    #   Se espera que la geometría de cada feature esté en coordenadas de perfil: X = distancia acumulada
    
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
    
    
    # Mapa de líneas de Estrcuturas
    
    def construir_linea_estructura(
            self,
            dist,
            z,
            base_y,
            echado,
            lado,
            x_min,
            x_max,
            margen=10.0
        ):
        """
        Construye una línea estructural desde ligeramente arriba del perfil
        hasta ligeramente debajo de la base.
        """

        import math

        y_sup = z + margen
        y_inf = base_y - margen

        delta_y = y_sup - y_inf

        ang_rad = math.radians(echado)

        if abs(math.tan(ang_rad)) < 1e-9:
            return None

        dx = delta_y / math.tan(ang_rad)

        if lado == "derecha":
            x_sup = dist
            x_inf = dist + dx
        else:
            x_sup = dist
            x_inf = dist - dx

        # Recortar contra límites laterales conservando el ángulo
        if x_inf < x_min:
            ratio = (x_min - x_sup) / (x_inf - x_sup)
            y_inf = y_sup + ratio * (y_inf - y_sup)
            x_inf = x_min - margen

        elif x_inf > x_max:
            ratio = (x_max - x_sup) / (x_inf - x_sup)
            y_inf = y_sup + ratio * (y_inf - y_sup)
            x_inf = x_max + margen

        return QgsGeometry.fromPolylineXY([
            QgsPointXY(x_sup, y_sup),
            QgsPointXY(x_inf, y_inf)
        ])

    
    # Obtiene la elevación Y del perfil para una coordenada X dada.
    # En el perfil, X representa la distancia acumulada sobre la sección.
    

    def obtener_y_en_x(self, linea_geom, x_objetivo):
        

        vertices = list(linea_geom.vertices())

        if len(vertices) < 2:
            return None

        for i in range(len(vertices) - 1):
            p1 = vertices[i]
            p2 = vertices[i + 1]

            x1, y1 = p1.x(), p1.y()
            x2, y2 = p2.x(), p2.y()

            if min(x1, x2) <= x_objetivo <= max(x1, x2):
                if x2 == x1:
                    return y1

                ratio = (x_objetivo - x1) / (x2 - x1)
                return y1 + ratio * (y2 - y1)

        return None
    
    #   Genera una capa temporal de líneas con:    linea_perfil, base, lim_izq, lim_der

    def build_profile_box_layer(
        self,
        section_layer,
        dem_layer,
        extra_depth: float = 100.0,
        layer_name: str = "Perfil_topografico",
        break_distances=None,
        segmentos_geo=None,
        estructuras=None
            ):

        if break_distances is None:
            break_distances = []

        if segmentos_geo is None:
            segmentos_geo = []

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


        # DENSIFICAR SEGÚN EL DEM

        pixel_size = self._get_dem_pixel_size(dem_layer)
        print(f"Pixel size DEM: {pixel_size}")

        dense_geom = self._densify_line_geometry(line_geom, pixel_size)
        print("Línea densificada correctamente")


        # GENERAR PUNTOS DEL PERFIL

        profile_point_features = self._generate_profile_points_from_vertices(
            line_geom=dense_geom,
            dem_layer=dem_layer
        )

        if not profile_point_features:
            raise Exception("No fue posible generar puntos para el perfil.")

        
        # CONSTRUIR PERFIL + CAJA
        
        box_data = self._build_profile_box_lines(
            features=profile_point_features,
            extra_depth=extra_depth
        )

        linea_perfil = box_data["linea_perfil"]

        lineas_estructura = []

        vertices_perfil = list(linea_perfil.vertices())
        max_x_perfil = max(v.x() for v in vertices_perfil)

        QgsMessageLog.logMessage(
            f"Distancia máxima X perfil: {max_x_perfil}",
            "SecGeol",
            Qgis.Info
        )

        if segmentos_geo:
            max_dist_fin = max(seg["dist_fin"] for seg in segmentos_geo)
            QgsMessageLog.logMessage(
                f"Máximo dist_fin geología: {max_dist_fin}",
                "SecGeol",
                Qgis.Info
            )

        top_y = max(p.geometry().asPoint().y() for p in profile_point_features)
        break_geoms = self._build_break_lines(break_distances, box_data["base_y"], top_y)


        segmentos_linea = []

        for seg in segmentos_geo:
            d_ini = seg["dist_ini"]
            d_fin = seg["dist_fin"]

            sub_geom = self.recortar_linea_por_distancia(
                linea_perfil,
                d_ini,
                d_fin
            )

            if sub_geom is None or sub_geom.isEmpty():
                continue

            segmentos_linea.append({
                "id_lito": seg["id_lito"],
                "valor_geo": seg["valor_geo"],
                "geometry": sub_geom
            })


        # FORZAR CIERRE EXACTO EN EXTREMOS

        if segmentos_linea:

            vertices_perfil = list(linea_perfil.vertices())

            p_ini_perfil = vertices_perfil[0]
            p_fin_perfil = vertices_perfil[-1]

            geom_ini = segmentos_linea[0]["geometry"]
            pts_ini = list(geom_ini.vertices())

            if len(pts_ini) >= 2:
                pts_ini[0] = p_ini_perfil

                segmentos_linea[0]["geometry"] = QgsGeometry.fromPolylineXY([
                    QgsPointXY(p.x(), p.y()) for p in pts_ini
                ])

            geom_fin = segmentos_linea[-1]["geometry"]
            pts_fin = list(geom_fin.vertices())

            if len(pts_fin) >= 2:
                pts_fin[-1] = p_fin_perfil

                segmentos_linea[-1]["geometry"] = QgsGeometry.fromPolylineXY([
                    QgsPointXY(p.x(), p.y()) for p in pts_fin
                ])



        QgsMessageLog.logMessage(
            f"Segmentos recibidos en profile.py: {len(segmentos_geo)}",
            "SecGeol",
            Qgis.Info
        )

        QgsMessageLog.logMessage(
            f"Segmentos de perfil generados: {len(segmentos_linea)}",
            "SecGeol",
            Qgis.Info
        )

        QgsMessageLog.logMessage(
            f"Estructuras recibidas en profile.py: {len(estructuras)}",
            "SecGeol",
            Qgis.Info
        )

        
        # CAPA DE SALIDA
        
        crs_authid = section_layer.crs().authid()
        if not crs_authid:
            crs_authid = dem_layer.crs().authid()

        out_layer = QgsVectorLayer(f"LineString?crs={crs_authid}", layer_name, "memory")
        prov = out_layer.dataProvider()

        prov.addAttributes([
            QgsField("id_lito", QVariant.Int),
            QgsField("tipo", QVariant.String),
            QgsField("valor_geo", QVariant.String),
            QgsField("caja_m", QVariant.Double),
            QgsField("y_min", QVariant.Double),
            QgsField("base_y", QVariant.Double)
        ])
        out_layer.updateFields()

        feature_defs = []

        if not segmentos_geo:
            feature_defs.append(("linea_perfil", box_data["linea_perfil"]))

        feature_defs.extend([
            ("base", box_data["base"]),
            ("lim_izq", box_data["lim_izq"]),
            ("lim_der", box_data["lim_der"])
        ])
        
        for geom in break_geoms:
            feature_defs.append(("quiebre", geom))

        out_features = []

        for tipo, geom in feature_defs:
            feat = QgsFeature(out_layer.fields())
            feat.setGeometry(geom)
            feat.setAttributes([
                0,  # id_lito reservado para líneas base/no litológicas
                tipo,
                None,
                float(extra_depth),
                float(box_data["y_min_global"]),
                float(box_data["base_y"])
            ])
            out_features.append(feat)

        for seg in segmentos_linea:
            feat = QgsFeature(out_layer.fields())
            feat.setGeometry(seg["geometry"])
            feat.setAttributes([
                seg["id_lito"],
                "geologia",
                seg["valor_geo"],
                float(extra_depth),
                float(box_data["y_min_global"]),
                float(box_data["base_y"])
            ])

            out_features.append(feat)

        for est in estructuras:
            dist = est["dist"]
            echado = est["echado"]
            lado = est["lado"]
            vertices_perfil = list(linea_perfil.vertices())
            x_min = min(v.x() for v in vertices_perfil)
            x_max = max(v.x() for v in vertices_perfil)

            z = self.obtener_y_en_x(linea_perfil, dist)

            if z is None:
                continue

            geom_est = self.construir_linea_estructura(
                dist=dist,
                z=z,
                base_y=float(box_data["base_y"]),
                echado=echado,
                lado=lado,
                x_min=x_min,
                x_max=x_max,
                margen=10.0
            )

            lineas_estructura.append({
                "geometry": geom_est,
                "echado": echado,
                "azimuth": est["azimuth"],
                "lado": lado
            })

            QgsMessageLog.logMessage(
                f"Línea estructura creada: dist={dist}, lado={lado}",
                "SecGeol",
                Qgis.Info
            )


        for est in lineas_estructura:
            feat = QgsFeature(out_layer.fields())
            feat.setGeometry(est["geometry"])
            feat.setAttributes([
                99,
                "estructura",
                None,
                float(extra_depth),
                float(box_data["y_min_global"]),
                float(box_data["base_y"])
            ])

            out_features.append(feat)

        prov.addFeatures(out_features)
        out_layer.updateExtents()

        # Quitar capa previa con el mismo nombre
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == layer_name:
                QgsProject.instance().removeMapLayer(lyr.id())

        QgsProject.instance().addMapLayer(out_layer)

        print(f"Puntos generados para el perfil: {len(profile_point_features)}")
        print("Segmentos recibidos en profile:", len(segmentos_geo))
        return out_layer


        # Crea una capa temporal de polígonos para el perfil geológico.
        
    def build_geological_polygon_layer(self, line_layer, layer_name="perfil_geologico"):

        if line_layer is None or not line_layer.isValid():
            raise Exception("La capa de líneas del perfil no es válida.")

        crs_authid = line_layer.crs().authid()
        if not crs_authid:
            crs_authid = "EPSG:4326"

        out_layer = QgsVectorLayer(
            f"Polygon?crs={crs_authid}",
            layer_name,
            "memory"
        )

        prov = out_layer.dataProvider()

        prov.addAttributes([
            QgsField("id_lito", QVariant.Int),
            QgsField("tipo", QVariant.String),
            QgsField("valor_geo", QVariant.String)
        ])
        out_layer.updateFields()

        line_geoms = []
        geologia_lineas = []

        for feat in line_layer.getFeatures():

            geom = feat.geometry()

            if geom is None or geom.isEmpty():
                continue

            if geom.type() != Qgis.GeometryType.Line:
                continue

            tipo = feat["tipo"] if "tipo" in feat.fields().names() else None

            if tipo == "geologia":
                id_lito = feat["id_lito"] if "id_lito" in feat.fields().names() else None
                valor_geo = feat["valor_geo"] if "valor_geo" in feat.fields().names() else None

                geologia_lineas.append({
                    "id_lito": id_lito,
                    "valor_geo": valor_geo,
                    "geometry": geom
                })

            line_geoms.append(geom)

        merged = QgsGeometry.unaryUnion(line_geoms)
        polygon_geoms = QgsGeometry.polygonize([merged])


        if polygon_geoms is None or polygon_geoms.isEmpty():

            QgsMessageLog.logMessage(
                "Polygonize no generó polígonos.",
                "SecGeol",
                Qgis.Warning
            )

            QgsProject.instance().addMapLayer(out_layer)

            return out_layer
        
        multi = polygon_geoms.asGeometryCollection()

        out_features = []

        for poly_geom in multi:

            feat = QgsFeature(out_layer.fields())

            feat.setGeometry(poly_geom)

            id_lito_poly = 0
            valor_geo_poly = None

            for geo in geologia_lineas:
                geom_geo = geo["geometry"]

                if poly_geom.buffer(0.01, 1).intersects(geom_geo):

                    id_lito_poly = geo["id_lito"]
                    valor_geo_poly = geo["valor_geo"]

                    break


            feat.setAttributes([
                id_lito_poly,
                "poligono",
                valor_geo_poly
            ])

            out_features.append(feat)

        prov.addFeatures(out_features)

        out_layer.updateExtents()

        QgsProject.instance().addMapLayer(out_layer)

        QgsMessageLog.logMessage(
            f"Capa temporal creada: {layer_name}",
            "SecGeol",
            Qgis.Info
        )

        return out_layer
    
    #------ Para agregar los tics -----
    def build_axes_layer(
            self,
            line_layer,
            layer_name="ejes"
        ):

        if line_layer is None or not line_layer.isValid():
            raise Exception("La capa de líneas no es válida.")

        crs_authid = line_layer.crs().authid()

        out_layer = QgsVectorLayer(
            f"LineString?crs={crs_authid}",
            layer_name,
            "memory"
        )

        prov = out_layer.dataProvider()

        prov.addAttributes([
            QgsField("tipo", QVariant.String),
            QgsField("ejes", QVariant.String)
        ])

        out_layer.updateFields()
        
        # Obtener extensión de las líneas del perfil
        extent = line_layer.extent()

        x_min = extent.xMinimum()
        x_max = extent.xMaximum()

        y_min = extent.yMinimum()
        y_max = extent.yMaximum()

        longitud_x = x_max - x_min
        altura_y = y_max - y_min

        # Número adaptable de divisiones
        ticks_deseados_x = max(5, min(20, int(longitud_x / 500)))
        ticks_deseados_y = max(4, min(12, int(altura_y / 100)))

        # Pasos agradables
        paso_x = self.nice_number(longitud_x / ticks_deseados_x)
        paso_y = self.nice_number(altura_y / ticks_deseados_y)

        QgsMessageLog.logMessage(
            f"Ejes: X={longitud_x:.2f}, pasoX={paso_x} | "
            f"Y={altura_y:.2f}, pasoY={paso_y}",
            "SecGeol",
            Qgis.Info
        )
        
        out_features = []

        # separación respecto a la caja
        offset = altura_y * 0.10

        offset_x = offset
        offset_y = offset

        # longitud proporcional de los ticks
        tick_len = max(5, min(40, altura_y * 0.04))


        # EJE X


        y_eje = y_min - offset_y

        geom_x = QgsGeometry.fromPolylineXY([
            QgsPointXY(x_min, y_eje),
            QgsPointXY(x_max, y_eje)
        ])

        feat = QgsFeature(out_layer.fields())
        feat.setGeometry(geom_x)

        feat.setAttributes([
            "eje_x",
            None
        ])

        out_features.append(feat)

        
        # TICKS EJE X
        
        x_tick = 0

        while x_tick <= x_max:

            geom_tick = QgsGeometry.fromPolylineXY([
                QgsPointXY(x_tick, y_eje - tick_len/2),
                QgsPointXY(x_tick, y_eje + tick_len/2)
            ])

            feat = QgsFeature(out_layer.fields())
            feat.setGeometry(geom_tick)

            feat.setAttributes([
                "tick_x",
                f"{int(x_tick)}"
            ])

            out_features.append(feat)

            x_tick += paso_x

            QgsMessageLog.logMessage(
                f"Tick X creado en: {x_tick}",
                "SecGeol",
                Qgis.Info
            )


        
        # EJE Y
        
        x_eje = x_min - offset_x

        geom_y = QgsGeometry.fromPolylineXY([
            QgsPointXY(x_eje, y_min),
            QgsPointXY(x_eje, y_max)
        ])

        feat = QgsFeature(out_layer.fields())
        feat.setGeometry(geom_y)

        feat.setAttributes([
            "eje_y",
            None
        ])

        out_features.append(feat)

        
        # TICKS EJE Y
        

        y_tick = math.ceil(y_min / paso_y) * paso_y

        while y_tick <= y_max:

            geom_tick = QgsGeometry.fromPolylineXY([
                QgsPointXY(x_eje - tick_len/2, y_tick),
                QgsPointXY(x_eje + tick_len/2, y_tick)
            ])

            feat = QgsFeature(out_layer.fields())
            feat.setGeometry(geom_tick)

            feat.setAttributes([
                "tick_y",
                f"{int(round(y_tick))}"
            ])

            out_features.append(feat)

            y_tick += paso_y

        prov.addFeatures(out_features)
        out_layer.updateExtents()

        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == layer_name:
                QgsProject.instance().removeMapLayer(lyr.id())

        QgsProject.instance().addMapLayer(out_layer)

        return out_layer
    

    def nice_number(self, value):
        import math

        if value <= 0:
            return 1

        exp = math.floor(math.log10(value))
        fraction = value / (10 ** exp)

        if fraction < 1.5:
            nice = 1
        elif fraction < 3:
            nice = 2
        elif fraction < 7:
            nice = 5
        else:
            nice = 10

        return nice * (10 ** exp)
