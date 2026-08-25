import os, re, unicodedata
from .secgeol_dialog import SecGeolDialog
from qgis.PyQt.QtCore import QCoreApplication, QSettings, QTranslator
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import ( 
                        QgsWkbTypes,QgsVectorLayer,
                        QgsProject,QgsVectorFileWriter,
                        Qgis, QgsGeometry,
                       )

class SecGeol:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dlg = None

        # Traducción
        self.translator = None

        locale = QSettings().value(
            "locale/userLocale",
            ""
        )

        locale = locale[0:2] if locale else ""

        locale_path = os.path.join(
            self.plugin_dir,
            "i18n",
            f"secgeol_{locale}.qm"
        )

        if os.path.exists(locale_path):
            self.translator = QTranslator()

            if self.translator.load(locale_path):
                QCoreApplication.installTranslator(
                    self.translator
                )

        self.menu = self.tr("SecGeol")


    def tr(self, message):
        return QCoreApplication.translate("SecGeol", message)

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")

        self.action = QAction(
            QIcon(icon_path) if os.path.exists(icon_path) else QIcon(),
            self.tr("SecGeol"),
            self.iface.mainWindow()
        )

        self.action.triggered.connect(self.run)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.menu, self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu(self.menu, self.action)
            self.iface.removeToolBarIcon(self.action)

    def run(self):
        if self.dlg is None:
            self.dlg = SecGeolDialog(self.iface)
            self.dlg.MapLayerDEM.layerChanged.connect(self.dlg.actualizar_info_dem)
            self.dlg.MapLayerSec.layerChanged.connect(self.dlg.actualizar_info_seccion)
            self.dlg.checkInvSec.toggled.connect(self.dlg.actualizar_info_seccion)

            # Botones Aceptar y cerrar
            self.dlg.buttonBox.accepted.connect(self.ejecutar)
            self.dlg.buttonBox.rejected.connect(self.dlg.close)

            # Botón de dibujo
            self.dlg.btnDrawSec.clicked.connect(self.draw_section)

        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    # DIBUJAR SECCIÓN (placeholder)

    def draw_section(self):
        self.iface.messageBar().pushInfo(
            self.tr("SecGeol"),
            self.tr("Dibuja la sección sobre el mapa: haz clic para iniciar y clic derecho para finalizar.")
        )


    # Devuelve una única feature válida de la sección del layer.
    # Si no cumple la regla, muestra ayuda y regresa None.

    def _set_help(self, texto):
        if self.dlg and hasattr(self.dlg, "textBrowserHelp"):
            self.dlg.textBrowserHelp.setPlainText(texto)


    def obtener_feature_seccion(self, sec_layer, has_drawn=False):

        if has_drawn:
            return None  # La sección dibujada se resolverá aparte

        if sec_layer is None:
            self._set_help("Seleccione una capa de sección o dibuje una.")
            return None

        if QgsWkbTypes.geometryType(sec_layer.wkbType()) != QgsWkbTypes.LineGeometry:
            self._set_help("La capa de sección debe ser de tipo línea.")
            return None

        total = sec_layer.featureCount()
        seleccionadas = sec_layer.selectedFeatureCount()

        if total == 0:
            self._set_help("La capa de sección no contiene registros.")
            return None

        if seleccionadas > 1:
            self._set_help(
                "Hay más de una sección seleccionada. "
                "Deje seleccionada solo una línea."
            )
            return None

        feat = None

        if seleccionadas == 1:
            feat = next(sec_layer.getSelectedFeatures(), None)
            if feat is None:
                self._set_help("No fue posible recuperar la sección seleccionada.")
                return None

        elif total == 1:
            feat = next(sec_layer.getFeatures(), None)
            if feat is None:
                self._set_help("No fue posible recuperar la sección.")
                return None

        else:
            self._set_help(
                "La capa contiene más de una sección. "
                "Seleccione una sola línea para continuar."
            )
            return None

        
        # Validación geométrica del registro
        
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            self._set_help("La geometría de la sección está vacía.")
            return None

        if geom.isMultipart():
            partes = geom.asMultiPolyline()

            if not partes:
                self._set_help("No fue posible interpretar la geometría de la sección.")
                return None

            if len(partes) > 1:
                self._set_help(
                    "La sección contiene líneas separadas dentro de un mismo registro. "
                    "SecGeol solo acepta una sola línea por sección."
                )
                return None

        return feat


    # Devuelve la geometría base de la sección: dibujada por el usuario, o tomada del layer/selección

    def obtener_geometria_seccion_base(self, sec_layer, has_drawn=False):
        # Caso 1: sección dibujada
        if has_drawn:
            feat = self.dlg.drawn_section_feature
            if feat is None:
                self._set_help("No fue posible recuperar la sección dibujada.")
                return None

            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                self._set_help("La sección dibujada no contiene una geometría válida.")
                return None

            return geom

        # Caso 2: sección desde layer
        feat = self.obtener_feature_seccion(sec_layer, has_drawn=False)
        if feat is None:
            return None

        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            self._set_help("No fue posible recuperar la geometría de la sección.")
            return None

        return geom



    # Guarda el perfil y la sección guía como dos Shapefiles relacionados

    def guardar_capas_salida(self, perfil_layer, guia_layer, salida):
        """
        Retorna:
            dict: rutas de los archivos guardados.
        """

        # 1. Validaciones
        
        if not salida:
            raise ValueError(
                self.tr("You must specify an output file.")
            )

        if perfil_layer is None or not perfil_layer.isValid():
            raise ValueError(
                self.tr("The profile layer is not valid.")
            )

        if guia_layer is None or not guia_layer.isValid():
            raise ValueError(
                self.tr("The guide section layer is not valid.")
            )

        
        # 2. Obtener carpeta y nombre base
        
        carpeta = os.path.dirname(salida)

        if not carpeta:
            raise ValueError(
                self.tr("The output folder is not valid.")
            )

        if not os.path.isdir(carpeta):
            os.makedirs(carpeta, exist_ok=True)

        nombre_archivo = os.path.basename(salida)
        nombre_base, _ = os.path.splitext(nombre_archivo)

        
        # 3. Normalizar el nombre
        
        nombre_base = unicodedata.normalize("NFKD", nombre_base)
        nombre_base = nombre_base.encode("ascii", "ignore").decode("ascii")

        nombre_base = nombre_base.lower().strip()
        nombre_base = re.sub(r"\s+", "_", nombre_base)
        nombre_base = re.sub(r"[^a-z0-9_-]", "", nombre_base)
        nombre_base = re.sub(r"_+", "_", nombre_base)
        nombre_base = nombre_base.strip("_-")

        if not nombre_base:
            nombre_base = "perfil"

        # Máximo acordado para el nombre base
        nombre_base = nombre_base[:30].rstrip("_-")

       
        # 4. Buscar un nombre disponible para ambas capas
       
        extensiones_shapefile = (
            ".shp",
            ".shx",
            ".dbf",
            ".prj",
            ".cpg",
            ".qpj"
        )

        def conjunto_existe(ruta_sin_extension):
            return any(
                os.path.exists(ruta_sin_extension + extension)
                for extension in extensiones_shapefile
            )

        contador = 0

        while True:
            if contador == 0:
                nombre_disponible = nombre_base
            else:
                nombre_disponible = f"{nombre_base}_{contador}"

            base_perfil = os.path.join(
                carpeta,
                nombre_disponible
            )

            base_guia = os.path.join(
                carpeta,
                f"{nombre_disponible}_guia"
            )

            if (
                not conjunto_existe(base_perfil)
                and not conjunto_existe(base_guia)
            ):
                break

            contador += 1

        ruta_perfil = base_perfil + ".shp"
        ruta_guia = base_guia + ".shp"

        
        # 5. Configuración de escritura
        
        opciones = QgsVectorFileWriter.SaveVectorOptions()
        opciones.driverName = "ESRI Shapefile"
        opciones.fileEncoding = "UTF-8"
        opciones.actionOnExistingFile = (
            QgsVectorFileWriter.CreateOrOverwriteFile
        )

        contexto_transformacion = (
            QgsProject.instance().transformContext()
        )

       
        # 6. Guardar el perfil
       
        resultado_perfil = QgsVectorFileWriter.writeAsVectorFormatV3(
            perfil_layer,
            ruta_perfil,
            contexto_transformacion,
            opciones
        )

        error_perfil = resultado_perfil[0]
        mensaje_perfil = resultado_perfil[1]

        if error_perfil != QgsVectorFileWriter.NoError:
            raise RuntimeError(
                self.tr("The profile could not be saved: ")
                + str(mensaje_perfil)
            )

        
        # 7. Guardar la sección guía
        
        resultado_guia = QgsVectorFileWriter.writeAsVectorFormatV3(
            guia_layer,
            ruta_guia,
            contexto_transformacion,
            opciones
        )

        error_guia = resultado_guia[0]
        mensaje_guia = resultado_guia[1]

        if error_guia != QgsVectorFileWriter.NoError:
            raise RuntimeError(
                self.tr("The guide section could not be saved: ")
                + str(mensaje_guia)
            )



        # 8. Cargar las capas guardadas al proyecto

        perfil_guardado = QgsVectorLayer(
            ruta_perfil,
            nombre_disponible,
            "ogr"
        )

        guia_guardada = QgsVectorLayer(
            ruta_guia,
            f"{nombre_disponible}_guia",
            "ogr"
        )

        if not perfil_guardado.isValid():
            raise RuntimeError(
                self.tr("The saved profile layer could not be loaded.")
            )

        if not guia_guardada.isValid():
            raise RuntimeError(
                self.tr("The saved guide section layer could not be loaded.")
            )

        QgsProject.instance().addMapLayer(perfil_guardado)
        QgsProject.instance().addMapLayer(guia_guardada)

        # 9. Eliminar las capas temporales
        
        if perfil_layer.id() in QgsProject.instance().mapLayers():
            QgsProject.instance().removeMapLayer(perfil_layer.id())

        if guia_layer.id() in QgsProject.instance().mapLayers():
            QgsProject.instance().removeMapLayer(guia_layer.id())

        
        # 10. Devolver resultados
        
        return {
            "perfil": ruta_perfil,
            "guia": ruta_guia,
            "perfil_layer": perfil_guardado,
            "guia_layer": guia_guardada
        }
    

    # EJECUTAR, aceptar Tab_1
    
    def ejecutar(self):
        
        # Sección
        sec_layer = self.dlg.MapLayerSec.currentLayer()
        has_drawn = self.dlg.drawn_section_feature is not None
        inv_sec = self.dlg.checkInvSec.isChecked()

        # Geología
        
        geo_layer = None
        if self.dlg.checkGeo.isChecked():
            geo_layer = self.dlg.MapLayerGeo.currentLayer()

        campo_geo = None
        if self.dlg.checkGeo.isChecked():
            campo_geo = self.dlg.FieldClasGeo.currentField()

        # Estructuras
        est_layer = None
        if self.dlg.checkEst.isChecked():
            est_layer = self.dlg.MapLayerEst.currentLayer()

        # Caja                            ***revisar
        caja_m = self.dlg.doubleSpinBox.value()

        # Ejes                            ***revisar
        crear_ejes = self.dlg.checkEjes.isChecked()

        # Salida
        salida = self.dlg.fileWidgetPerfil.filePath().strip()


        # VALIDACIONES DE LA FUENTE DE ELEVACIÓN

        dem_layer = self.dlg.MapLayerDEM.currentLayer()
        curvas_layer = self.dlg.MapLayerCurvas.currentLayer()

        # Debe existir al menos una fuente de elevación
        if dem_layer is None and curvas_layer is None:
            self.iface.messageBar().pushWarning(
                self.tr("SecGeol"),
                self.tr(
                    "Seleccione una fuente de elevación: "
                    "un DEM o una capa de curvas de nivel."
                )
            )
            return


        # VALIDACIONES ESPECÍFICAS DEL DEM
        if dem_layer is not None:

            if dem_layer.type() != dem_layer.RasterLayer:
                self.iface.messageBar().pushWarning(
                    self.tr("SecGeol"),
                    self.tr("La capa DEM seleccionada no es raster.")
                )
                return

            dem_crs = dem_layer.crs()

            if not dem_crs.isValid():
                self.iface.messageBar().pushWarning(
                    self.tr("SecGeol"),
                    self.tr("El CRS del DEM no es válido.")
                )
                self._set_help(
                    "El sistema de referencia del DEM no es válido."
                )
                return

            if dem_crs.mapUnits() != Qgis.DistanceUnit.Meters:
                self.iface.messageBar().pushWarning(
                    self.tr("SecGeol"),
                    self.tr("El DEM debe utilizar unidades métricas.")
                )
                self._set_help(
                    "El modelo digital de elevación debe estar en un sistema "
                    "de referencia proyectado con unidades en metros."
                )
                return

            if dem_layer.bandCount() != 1:
                self.iface.messageBar().pushWarning(
                    self.tr("SecGeol"),
                    self.tr("El DEM debe contener una sola banda.")
                )
                self._set_help(
                    "El raster seleccionado no parece corresponder a un modelo "
                    "digital de elevación. Es posible que la capa sea una imagen "
                    "y no contenga elevación del terreno."
                )
                return

            provider = dem_layer.dataProvider()
            band_type = provider.dataType(1)

            tipos_validos = {
                Qgis.DataType.Int16,
                Qgis.DataType.UInt16,
                Qgis.DataType.Int32,
                Qgis.DataType.UInt32,
                Qgis.DataType.Float32,
                Qgis.DataType.Float64,
            }

            tipo_nombres = {
                Qgis.DataType.Int16: "Int16",
                Qgis.DataType.UInt16: "UInt16",
                Qgis.DataType.Int32: "Int32",
                Qgis.DataType.UInt32: "UInt32",
                Qgis.DataType.Float32: "Float32",
                Qgis.DataType.Float64: "Float64",
            }

            band_type_name = tipo_nombres.get(band_type, str(band_type))

            if band_type not in tipos_validos:
                self.iface.messageBar().pushWarning(
                    self.tr("SecGeol"),
                    self.tr("The DEM raster type is not valid.")
                )
                self._set_help(
                    f"El raster seleccionado no parece corresponder a un modelo digital de elevación. "
                    f"Tipo de dato detectado: {band_type_name}."
                )
                return

                # Términa validación layer  ***revisar desde aquí


        if sec_layer is None and not has_drawn:
            self.iface.messageBar().pushWarning(
                self.tr("SecGeol"),
                self.tr("Select a section layer or draw one.")
            )
            return

        # Solo validar geometría si realmente viene de un layer
        if sec_layer is not None:
            if QgsWkbTypes.geometryType(sec_layer.wkbType()) != QgsWkbTypes.LineGeometry:
                self.iface.messageBar().pushWarning(
                    self.tr("SecGeol"),
                    self.tr("The section layer must be a line layer.")
                )
                return
            
        feat_sec = None
        if sec_layer is not None and not has_drawn:
            feat_sec = self.obtener_feature_seccion(sec_layer, has_drawn=False)
            if feat_sec is None:
                return
            
        # Validación geología

        campo_geo = None

        if self.dlg.checkGeo.isChecked():
            campo_geo = self.dlg.FieldClasGeo.currentField()

        if not campo_geo:
            campo_geo = None

        segmentos_geo = []
        estructuras = []
        section_work_layer = None
        
        if geo_layer is not None:

            section_work_layer = self.dlg.preparar_seccion_trabajo(
                feat_sec=feat_sec,
                has_drawn=has_drawn,
                invertida=inv_sec
            )

            section_geom = None

            for f in section_work_layer.getFeatures():
                section_geom = QgsGeometry(f.geometry())
                break

            segmentos_geo = self.dlg.section_manager.intersectar_seccion_con_geologia(
                section_geom=section_geom,
                section_crs=section_work_layer.crs(),
                geo_layer=geo_layer,
                campo_geo=campo_geo
            )

        # ESTRUCTURAS
        
        campo_dip = None
        campo_azimuth = None

        if self.dlg.checkEst.isChecked():
            campo_dip = self.dlg.FieldDipEst.currentField()
            campo_azimuth = self.dlg.FieldAzimuthEst.currentField()

        if est_layer is not None:

            if section_work_layer is None:

                section_work_layer = self.dlg.preparar_seccion_trabajo(
                    feat_sec=feat_sec,
                    has_drawn=has_drawn,
                    invertida=inv_sec
                )
            
            #guia_layer = self.dlg.crear_seccion_guia(
            #    section_layer=section_work_layer,
            #    invertida=inv_sec,
            #    layer_name="Seccion_guia",
            #    geom_override=self.dlg.section_geom_recortada
            #)

            section_geom = None

            for f in section_work_layer.getFeatures():
                section_geom = QgsGeometry(f.geometry())
                break

            estructuras = self.dlg.section_manager.intersectar_seccion_con_estructuras(
                section_geom=section_geom,
                section_crs=section_work_layer.crs(),
                est_layer=est_layer,
                campo_dip=campo_dip,
                campo_azimuth=campo_azimuth
            )

        try:
            
            perfil_layer = self.dlg.generar_perfil(
                feat_sec=feat_sec,
                has_drawn=has_drawn,
                invertida=inv_sec,
                segmentos_geo=segmentos_geo,
                estructuras=estructuras,
                section_layer=section_work_layer
                
            )
            

            if section_work_layer is None:
                section_work_layer = self.dlg.preparar_seccion_trabajo(
                    feat_sec=feat_sec,
                    has_drawn=has_drawn,
                    invertida=inv_sec
                )

            guia_layer = self.dlg.crear_seccion_guia(
                section_layer=section_work_layer,
                invertida=inv_sec,
                layer_name="Seccion_guia",
                geom_override=self.dlg.section_geom_recortada
            )

            rutas_guardadas = self.guardar_capas_salida(                              ##Verificar
                perfil_layer=perfil_layer,
                guia_layer=guia_layer,
                salida=salida
            )
            
            self.iface.messageBar().pushInfo(
                self.tr("SecGeol"),
                self.tr("Profile created successfully.")
            )

            self.dlg.accept()

        except Exception as e:
            self.iface.messageBar().pushWarning(
                self.tr("SecGeol"),
                str(e)
            )

