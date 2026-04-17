import os

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QEvent, QUrl, Qt
from qgis.PyQt.QtWidgets import QDialog, QSplitter
from qgis.core import QgsMapLayerProxyModel, QgsProject, Qgis, QgsFeature, QgsGeometry, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.utils import iface
from qgis.PyQt.QtGui import QColor

from .core.workspace import WorkspaceManager
from .core.section import SectionManager
from .core.profile import ProfileManager


try:
    EVENT_ENTER = 10
except AttributeError:
    try:
        EVENT_ENTER = 10
    except AttributeError:
        EVENT_ENTER = 10


FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), 'secGeol.ui')
)

class DrawSectionMapTool(QgsMapTool):
    def __init__(self, canvas, finished_callback, cancel_callback=None):
        super().__init__(canvas)
        self.canvas = canvas
        self.finished_callback = finished_callback
        self.cancel_callback = cancel_callback
        self.points = []

        # línea ya confirmada
        self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.rubber_band.setWidth(4)
        self.rubber_band.setColor(QColor(255, 0, 0))  # rojo sólido

        #línea de seguimiento
        self.preview_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.preview_band.setWidth(2)
        self.rubber_band.setColor(QColor(255, 255, 0, 220))  # amarillo
        
        # vertices
        self.vertex_band = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
        self.vertex_band.setWidth(6)
        self.vertex_band.setColor(QColor(255, 0, 0))

    def activate(self):
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)
        super().activate()

    def deactivate(self):
        self._clear_bands()
        super().deactivate()

    def canvasPressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pt = self.toMapCoordinates(event.pos())
            self.points.append(pt)
            self._update_rubber_band()

        elif event.button() == Qt.MouseButton.RightButton:
            self._finish_drawing()

    def canvasMoveEvent(self, event):
        if len(self.points) < 1:
            return

        current_pt = self.toMapCoordinates(event.pos())
        self._update_preview_band(current_pt)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()

    def _update_rubber_band(self):
        self.rubber_band.reset(QgsWkbTypes.LineGeometry)
        self.vertex_band.reset(QgsWkbTypes.PointGeometry)

        if len(self.points) < 1:
            return

        # mostrar vértices
        for i, pt in enumerate(self.points):
            self.vertex_band.addPoint(pt, i == len(self.points) - 1)

         # mostrar línea confirmada
        if len(self.points) >= 2:
            for i, pt in enumerate(self.points):
                self.rubber_band.addPoint(pt, i == len(self.points) - 1)

        self.vertex_band.show()
        self.rubber_band.show()

    def _update_preview_band(self, current_pt):
        self.preview_band.reset(QgsWkbTypes.LineGeometry)

        all_pts = self.points + [current_pt]
        if len(all_pts) < 2:
            return

        for i, pt in enumerate(all_pts):
            self.preview_band.addPoint(pt, i == len(all_pts) - 1)

        self.preview_band.show()

    def _finish_drawing(self):
        if len(self.points) < 2:
            return

        try:
            geom = QgsGeometry.fromPolylineXY(self.points)
            feat = QgsFeature()
            feat.setGeometry(geom)

            self._clear_bands()
            self.points.clear()

            if self.finished_callback:
                self.finished_callback(feat)

        except Exception as e:
            print(f"Error al finalizar dibujo: {e}")
            self.cancel()


    def cancel(self):
        self._clear_bands()
        self.points.clear()

        if self.cancel_callback:
            self.cancel_callback()

    def _clear_bands(self):
        self.rubber_band.reset(QgsWkbTypes.LineGeometry)
        self.preview_band.reset(QgsWkbTypes.LineGeometry)
        self.vertex_band.reset(QgsWkbTypes.PointGeometry)




class SecGeolDialog(QDialog, FORM_CLASS):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setupUi(self)


        self.drawn_section_feature = None
        self.draw_tool = None

        self.btnDrawSec.clicked.connect(self.activar_dibujo_seccion)
        self.MapLayerSec.layerChanged.connect(self.on_section_layer_changed)

        self.section_manager = SectionManager()
        self.workspace_manager = WorkspaceManager()
        self.gpkg_path = None

        # -----------------------------
        # CONFIGURAR CAJA
        # -----------------------------
        self.doubleSpinBox.setMinimum(0.0)
        self.doubleSpinBox.setMaximum(10000.0)
        self.doubleSpinBox.setSingleStep(10.0)     #Verificar este punto
        self.doubleSpinBox.setSuffix(" m")
        self.doubleSpinBox.setValue(100.0)



        # --------  Ejecuta herramienta ---
        self.buttonBox.accepted.connect(self.ejecutar_proceso)
        self.buttonBox.rejected.connect(self.reject)

        # -----------------------------
        # SPLITTER DE AYUDA / CONTROLES
        # -----------------------------
        self.splitter_main = self.findChild(QSplitter, "splitter")

        # --------  Extraer datos de elevación ---
        self.profile_manager = ProfileManager()



        if self.splitter_main:
            self.splitter_main.setSizes([300, 100])
             # 0 = panel izquierdo (controles)
             # 1 = panel derecho (ayuda)
            self.splitter_main.setStretchFactor(0, 1)  # ayuda
            self.splitter_main.setStretchFactor(1, 0)  # controles

            self.splitter_main.setChildrenCollapsible(False)

            self.splitter_main.setStyleSheet("""
                QSplitter::handle {
                    width: 0px;
                    background: transparent;
                }
            """)

            handle = self.splitter_main.handle(1)
            if handle:
                handle.setEnabled(False)

        # -----------------------------
        # ESTADO INICIAL DE LA AYUDA
        # -----------------------------
        self.help_tab_uno = """
            <div style="padding:10px; line-height:1.4;">
                <h3>Herramienta de Secciones Geológicas</h3>

                <p>
                    Esta herramienta genera un perfil topográfico a partir de un Modelo Digital de Elevación (DEM)
                    a lo largo de una línea de sección definida por el usuario. El perfil resultante puede utilizarse
                    como base para la interpretación geológica y la construcción de secciones.
                </p>

                <p>
                    <b>Requisitos:</b><br>
                    - Cargar todas las capas de entrada en el proyecto actual de QGIS.<br>
                    - Utilizar un sistema de referencia proyectado (recomendado: UTM).<br>
                    - Asegurar que las capas compartan el mismo sistema de referencia.
                </p>

                <p>
                    <b>Tip:</b> Los campos marcados con un asterisco (*) son obligatorios.<br>
                    Haz clic en cada control para ver una breve descripción.
                </p>
            </div>
            """
        self.help_tab_dos = """
            <div style="padding:10px; line-height:1.4; font-size:12px;">
                <h3>Opciones de Interpretación</h3>
                <p>
                    En esta pestaña se integrarán opciones adicionales relacionadas con la interpretación geológica
                    y la generación de resultados derivados a partir del perfil.
                </p>
                <p>
                    Haz clic en cada control para ver una breve descripción.
                </p>
            </div>
            """

        self.help_tab_tres = """
            <div style="padding:10px; line-height:1.4; font-size:12px;">
            <h3>Herramientas y Resultados</h3>
            <p>
                Esta pestaña contendrá herramientas complementarias y opciones para la generación de resultados finales.
            </p>
            <p>
                Haz clic en cada control para ver una breve descripción.
            </p>
            </div>
            """
        # -----------------------------
        # CONEXIÓN DE TABS
        # -----------------------------
        self.tabWidget.currentChanged.connect(self.actualizar_ayuda_tab)

        # -----------------------------
        # INICIALIZAR AYUDA
        # -----------------------------
        self.actualizar_ayuda_tab()



        # -----------------------------
        # CONFIGURAR FILTROS DE CAPAS
        # -----------------------------
        self.MapLayerDEM.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.MapLayerSec.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.MapLayerGeo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.MapLayerEst.setFilters(QgsMapLayerProxyModel.LineLayer)

        # -----------------------------
        # CONFIGURAR SALIDA
        # -----------------------------
        self.fileWidgetPerfil.setFilter("Shapefile (*.shp);;GeoPackage (*.gpkg)")

        try:
            self.fileWidgetPerfil.setStorageMode(self.fileWidgetPerfil.StorageMode.SaveFile)
        except AttributeError:
            self.fileWidgetPerfil.setStorageMode(self.fileWidgetPerfil.SaveFile)



        # -----------------------------
        # EVENT FILTERS PARA AYUDA
        # -----------------------------

        for w in [
            self.MapLayerDEM,
            self.MapLayerSec,
            self.btnDrawSec,
            self.checkInvSec,
            self.MapLayerGeo,
            self.MapLayerEst,
            self.doubleSpinBox,
            self.checkEjes,
            self.fileWidgetPerfil,
        ]:
            w.installEventFilter(self)
            

        # -----------------------------
        # TOOLTIPS
        # -----------------------------
        self.MapLayerDEM.setToolTip(
            "Seleccione el modelo digital de elevación (DEM)."
        )
        self.MapLayerSec.setToolTip(
            "Seleccione la capa que contiene la línea de sección."
        )

        self.btnDrawSec.setToolTip(
            "Dibuje una línea de sección directamente sobre el mapa."
        )

        self.checkInvSec.setToolTip(
            "Invertir el sentido de la sección (inicio ↔ fin)."
        )

        self.MapLayerGeo.setToolTip(
            "Capa de geología (opcional) para intersectar la sección."
        )

        self.MapLayerEst.setToolTip(
            "Capa estructural (opcional) para intersectar la sección."
        )

        self.doubleSpinBox.setToolTip(
            "Tamaño de la caja en metros (opcional). Use 0 para no generarla."
        )

        self.checkEjes.setToolTip(
            "Crear ejes X y Y en el perfil generado."
        )

        self.fileWidgetPerfil.setToolTip(
            "Seleccione el archivo de salida para guardar el perfil."
        )


    def on_section_layer_changed(self, layer):
        if layer is not None:
            print("📌 Se seleccionó una capa de sección; se limpiará la sección dibujada")

            self.clear_drawn_section_feature()
            self._remove_layer_by_name("seccion_dibujada")


    def _remove_layer_by_name(self, layer_name):
        project = QgsProject.instance()
        for lyr in list(project.mapLayers().values()):
            if lyr.name() == layer_name:
                project.removeMapLayer(lyr.id())
                
                
    def set_drawn_section_feature(self, feature):
        self.drawn_section_feature = feature
    
    def clear_drawn_section_feature(self):
        self.drawn_section_feature = None


    def activar_dibujo_seccion(self):
        print("🖉 Activar dibujo de sección")

        dem_layer = self.MapLayerDEM.currentLayer()
        if dem_layer is None:
            raise Exception("No se ha seleccionado un DEM.")

        # limpiar cualquier selección de layer
        try:
            self.MapLayerSec.setLayer(None)
        except Exception:
            pass

        # limpiar sección dibujada previa
        self.clear_drawn_section_feature()
        self._remove_layer_by_name("seccion_dibujada")

        canvas = iface.mapCanvas()
        self.draw_tool = DrawSectionMapTool(
            canvas,
            self.on_section_drawing_finished,
            self.on_section_drawing_cancelled
        )
        canvas.setMapTool(self.draw_tool)

    def on_section_drawing_finished(self, feature):
        print("🔥 Entró a on_section_drawing_finished")
        self.set_drawn_section_feature(feature)
        self.mostrar_seccion_dibujada(feature)

        print("🎯 Dibujo terminado con clic derecho")

        iface.mapCanvas().unsetMapTool(self.draw_tool)
        self.draw_tool = None

    

    def actualizar_ayuda_tab(self):
        current_widget = self.tabWidget.currentWidget()

        if current_widget == self.uno:
            self.textBrowserHelp.setHtml(self.help_tab_uno)
        elif current_widget == self.dos:
            self.textBrowserHelp.setHtml(self.help_tab_dos)
        elif hasattr(self, "tres") and current_widget == self.tres:
            self.textBrowserHelp.setHtml(self.help_tab_tres)


    def on_section_drawing_cancelled(self):
        print("❌ Dibujo cancelado")

        if self.draw_tool is not None:
            iface.mapCanvas().unsetMapTool(self.draw_tool)
            self.draw_tool = None

#--------- Muestra la sección dibujada como capa temporal visible en el mapa. Reemplaza la anterior si existe.

    def mostrar_seccion_dibujada(self, feature):
        print("🟡 Entró a mostrar_seccion_dibujada")

        if feature is None:
            print("❌ feature es None")
            return

        geom = feature.geometry()
        if geom is None or geom.isEmpty():
            print("❌ la geometría de la sección dibujada está vacía")
            return

        print(f"✅ geometría válida: {geom.asWkt()[:200]}")

        project = QgsProject.instance()

        # eliminar capa previa si existe
        for lyr in list(project.mapLayers().values()):
            if lyr.name() == "seccion_dibujada":
                print("🧹 Eliminando capa previa 'seccion_dibujada'")
                project.removeMapLayer(lyr.id())

        dem_layer = self.MapLayerDEM.currentLayer()
        if dem_layer is None:
            raise Exception("No se ha seleccionado un DEM.")

        crs_authid = dem_layer.crs().authid()
        print(f"📌 CRS de la capa temporal: {crs_authid}")

        layer = QgsVectorLayer(f"LineString?crs={crs_authid}", "seccion_dibujada", "memory")
        if not layer.isValid():
            print("❌ La capa temporal 'seccion_dibujada' no es válida")
            return

        provider = layer.dataProvider()

        feat = QgsFeature()
        feat.setGeometry(geom)

        ok = provider.addFeatures([feat])
        print(f"➕ addFeatures result: {ok}")

        layer.updateExtents()
        print(f"📦 extent capa: {layer.extent().toString()}")

        # simbología visible
        renderer = layer.renderer()
        symbol = renderer.symbol()
        symbol.setWidth(1.5)
        symbol.setColor(QColor(255, 0, 0))  # rojo
        layer.triggerRepaint()

        project.addMapLayer(layer)
        print("✅ Capa temporal 'seccion_dibujada' agregada al mapa")

        # forzar refresco visual
        iface.mapCanvas().refresh()

        # opcional: acercar a la línea para comprobar que sí existe
        # iface.mapCanvas().setExtent(layer.extent())
        # iface.mapCanvas().refresh()


    # ---------------------------------
    # PANEL DE AYUDA
    # ---------------------------------
    def mostrar_ayuda(self, titulo, texto):
        self.textBrowserHelp.setHtml(f"""
            <h3>{titulo}</h3>
            <p>{texto}</p>
        """)

    # ---------------------------------
    # EVENT FILTER  Mostarr ayuda
    # ---------------------------------
    def eventFilter(self, obj, event):
        if event.type() == 10:

            if obj == self.MapLayerDEM:
                self.actualizar_info_dem()

            elif obj == self.MapLayerSec:
                self.actualizar_info_seccion()

            elif obj == self.btnDrawSec:
                self.mostrar_ayuda(
                    "Dibujar sección",
                    "Permite dibujar una línea de sección directamente sobre el mapa.\n"
                    "Haz clic para iniciar y clic derecho para finalizar."
                )

            elif obj == self.checkInvSec:
                self.mostrar_ayuda(
                    "Invertir sección",
                    "Invierte el sentido de la sección (inicio ↔ fin).\n"
                    "Esto cambia la orientación del perfil."
                )

            elif obj == self.MapLayerGeo:
                self.mostrar_ayuda(
                    "Capa de geología",
                    "Capa poligonal opcional que se intersecta con la sección\n"
                    "para mostrar las unidades geológicas en el perfil."
                )

            elif obj == self.MapLayerEst:
                self.mostrar_ayuda(
                    "Capa estructural",
                    "Capa lineal opcional que se intersecta con la sección\n"
                    "para representar estructuras geológicas en el perfil."
                )

            elif obj == self.doubleSpinBox:
                self.mostrar_ayuda(
                    "Tamaño de caja",
                    "Define el tamaño de la caja en metros para el perfil.\n"
                    "Usa 0 si no deseas generar la caja."
                )

            elif obj == self.checkEjes:
                self.mostrar_ayuda(
                    "Crear ejes",
                    "Genera los ejes X y Y en el perfil resultante."
                )

            elif obj == self.fileWidgetPerfil:
                self.mostrar_ayuda(
                    "Archivo de salida",
                    "Selecciona el archivo donde se guardará el perfil generado."
                )

        elif event.type() == 11:  # Leave
            self.actualizar_ayuda_tab()

        return super().eventFilter(obj, event)

    # ---------------------------------
    # Conecta la función de la sección      
    # ---------------------------------

    def preparar_seccion_trabajo(self, feat_sec=None, has_drawn=False, invertida=False):
        print("source_feature is None?:", feat_sec is None)
        print("A: entrar a preparar_seccion_trabajo")

        dem_layer = self.MapLayerDEM.currentLayer()
        if dem_layer is None:
            raise Exception(
                "No se ha seleccionado un modelo digital de elevación (DEM). "
                "Seleccione una capa raster válida para continuar."
            )

        target_crs = dem_layer.crs()

        print(f"C: feature desde layer disponible = {feat_sec is not None}")
        print(f"D: feature dibujada disponible = {self.drawn_section_feature is not None}")
        print(f"E: invertir sección = {invertida}")

        # Caso 1: el usuario dibujó una sección
        if has_drawn:
            if self.drawn_section_feature is None:
                raise Exception("No se encontró la sección dibujada.")

            # Ajusta aquí según el CRS real de tu sección dibujada
            source_crs = self.iface.mapCanvas().mapSettings().destinationCrs()

            temp_layer = self.section_manager.prepare_section_layer_from_feature(
                source_feature=self.drawn_section_feature,
                source_crs=source_crs,
                target_crs=target_crs,
                invertida=invertida
            )
            print("F: sección temporal preparada desde feature dibujada")

        # Caso 2: el usuario seleccionó una sola sección válida del layer
        elif feat_sec is not None:
            source_layer = self.MapLayerSec.currentLayer()
            if source_layer is None:
                raise Exception("No se encontró la capa de sección.")

            source_crs = source_layer.crs()

            temp_layer = self.section_manager.prepare_section_layer_from_feature(
                source_feature=feat_sec,
                source_crs=source_crs,
                target_crs=target_crs,
                invertida=invertida
            )
            print("F: sección temporal preparada desde feature seleccionada")

        else:
            raise Exception("No se encontró una sección válida para preparar.")

        if temp_layer is None or not temp_layer.isValid():
            raise Exception("No fue posible preparar la sección de trabajo.")

        return temp_layer
    


      
    
    # ---------------------------------
    # Inicializa workspace
    # ---------------------------------

    def inicializar_workspace(self):
        dem_layer = self.MapLayerDEM.currentLayer()
        if dem_layer is None:
            raise Exception("No se ha seleccionado un DEM.")

        crs_authid = dem_layer.crs().authid()
        self.gpkg_path = self.workspace_manager.create_base_geopackage(crs_authid)
        self.section_manager.set_gpkg_path(self.gpkg_path)

        print(f"GPKG creado: {self.gpkg_path}")


    # ---------------------------------
    # Prueba
    # ---------------------------------

    def probar_preparacion_seccion(self):
        self.inicializar_workspace()
        layer = self.preparar_seccion_trabajo()
        print("Sección de trabajo preparada:", layer)


    # ---------------------------------
    # Entra a secprofile
    # --------------------------------- 


    def generar_perfil(self, feat_sec=None, has_drawn=False, invertida=False):
        print("H: entrar a generar_perfil")

        dem_layer = self.MapLayerDEM.currentLayer()
        if dem_layer is None:
            raise Exception("No se ha seleccionado un DEM.")

        section_layer = self.preparar_seccion_trabajo(
            feat_sec=feat_sec,
            has_drawn=has_drawn,
            invertida=invertida
        )
        print("I: sección temporal preparada")

        if section_layer is None or not section_layer.isValid():
            raise Exception("No fue posible preparar la sección de trabajo.")

        caja_m = self.obtener_caja_m()
        print(f"J: caja_m = {caja_m}")

        section_geom = None
        for feat in section_layer.getFeatures():
            geom = feat.geometry()
            if geom is not None and not geom.isEmpty():
                section_geom = geom
                break

        break_distances = []
        if section_geom is not None:
            break_distances = self.section_manager.detect_section_break_distances(section_geom)
            print(f"J.1: quiebres detectados = {break_distances}")

        perfil_layer = self.profile_manager.build_profile_box_layer(
            section_layer=section_layer,
            dem_layer=dem_layer,
            extra_depth=caja_m,
            layer_name="Perfil_topografico",
            break_distances=break_distances
        )
        print("K: capa de perfil creada")

        return perfil_layer



    # ---------------------------------
    # ACEPTAR
    # ---------------------------------
    
    def ejecutar_proceso(self):
        try:
            print("=== SecGeol PARAMETERS ===")
            print(f"DEM: {self.MapLayerDEM.currentLayer().name() if self.MapLayerDEM.currentLayer() else 'None'}")
            print(f"Section: {self.MapLayerSec.currentLayer().name() if self.MapLayerSec.currentLayer() else 'None'}")
            print(f"Invert section: {self.checkInvSec.isChecked()}")
            print(f"Geology: {self.MapLayerGeo.currentLayer().name() if self.MapLayerGeo.currentLayer() else 'None'}")
            print(f"Structures: {self.MapLayerEst.currentLayer().name() if self.MapLayerEst.currentLayer() else 'None'}")
            print(f"Box (m): {self.caja.value()}")
            print(f"Create axes: {self.ejesXY.isChecked()}")
            print(f"Output: {self.estSHP.filePath()}")

            self.inicializar_workspace()
            self.preparar_seccion_trabajo()   

            print("Proceso ejecutado correctamente")

            ##self.accept()   # 👈 esto cierra la ventana

        except Exception as e:
            print(f"Error: {e}")


    # ---------------------------------
    # Valor de caja en metros
    # ---------------------------------   

    def obtener_caja_m(self):
        caja_m = self.doubleSpinBox.value()
        if caja_m <= 0:
            caja_m = 100.0
        return caja_m

    # ---------------------------------
    # Información DEM
    # ---------------------------------  


    def actualizar_info_dem(self):
        dem_layer = self.MapLayerDEM.currentLayer()

        if dem_layer is None:
            self.textBrowserHelp.setHtml(
                "<b>DEM:</b> No se ha seleccionado un DEM."
            )
            return

        if dem_layer.type() != dem_layer.RasterLayer:
            self.textBrowserHelp.setHtml(
                "<b>DEM:</b> La capa seleccionada no es raster."
            )
            return

        try:
            dem_crs = dem_layer.crs()

            crs_authid = dem_crs.authid()
            crs_name = dem_crs.description()

            if crs_authid:
                crs_info = f"{crs_authid} - {crs_name}"
            else:
                crs_info = crs_name

            pixel_x = dem_layer.rasterUnitsPerPixelX()
            pixel_y = dem_layer.rasterUnitsPerPixelY()

            es_metrico = dem_crs.isValid() and dem_crs.mapUnits() == Qgis.DistanceUnit.Meters
            una_banda = dem_layer.bandCount() == 1

            provider = dem_layer.dataProvider()

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

            band_type = provider.dataType(1) if una_banda else None
            band_type_name = tipo_nombres.get(band_type, "N/A") if una_banda else "N/A"

            banda_valida = una_banda and (band_type in tipos_validos)

            if es_metrico and banda_valida:
                estado = "<span style='color:green;'><b>Estado:</b> compatible con SecGeol.</span>"
            else:
                detalles = []
                if not dem_crs.isValid():
                    detalles.append("el CRS no es válido")
                elif not es_metrico:
                    detalles.append("el CRS no está en metros")
                if not una_banda:
                    detalles.append("el raster no es de una sola banda")
                elif band_type_name not in tipos_validos:
                    detalles.append(f"el tipo de dato no es adecuado ({band_type_name})")

                estado = (
                        "<span style='color:red;'><b>Estado:</b> No compatible con SecGeol.<br>"
                        "Es posible que la capa seleccionada no contenga elevación del terreno.<br>"
                        "SecGeol requiere un modelo digital de elevación (DEM) con valores numéricos de altura.</span>"
                    )
                

            self.textBrowserHelp.setHtml(
                f"<b>DEM seleccionado:</b> {dem_layer.name()}<br>"
                f"<b>CRS:</b> {crs_info}<br>"
                f"<b>Tamaño de pixel:</b> {pixel_x:.3f} x {pixel_y:.3f}<br>"
                f"<b>Bandas:</b> {dem_layer.bandCount()}<br>"
                f"<b>Tipo de dato:</b> {band_type_name}<br>"
                f"{estado}"
            )

        except Exception as e:
            self.textBrowserHelp.setHtml(
                f"<b>DEM:</b> Error al leer propiedades: {e}"
            )

    # ---------------------------------
    # Información DEM
    # --------------------------------- 

    def actualizar_info_seccion(self):
        sec_layer = self.MapLayerSec.currentLayer()
        has_drawn = self.drawn_section_feature is not None
        invertida = self.checkInvSec.isChecked()

        if has_drawn:
            geom = self.drawn_section_feature.geometry() if self.drawn_section_feature else None
            if geom is None or geom.isEmpty():
                self.textBrowserHelp.setHtml(
                    "<b>Sección:</b> La sección dibujada no es válida."
                )
                return

            longitud = geom.length()
            self.textBrowserHelp.setHtml(
                f"<b>Sección activa:</b> dibujada por el usuario<br>"
                f"<b>Longitud:</b> {longitud:.2f}<br>"
                f"<b>Invertida:</b> {'Sí' if invertida else 'No'}"
            )
            return

        if sec_layer is None:
            self.textBrowserHelp.setHtml(
                "<b>Sección:</b> Seleccione una capa de sección o dibuje una."
            )
            return

        if QgsWkbTypes.geometryType(sec_layer.wkbType()) != QgsWkbTypes.LineGeometry:
            self.textBrowserHelp.setHtml(
                "<b>Sección:</b> La capa debe ser de tipo línea."
            )
            return

        total = sec_layer.featureCount()
        seleccionadas = sec_layer.selectedFeatureCount()

        if total == 0:
            self.textBrowserHelp.setHtml(
                "<b>Sección:</b> La capa no contiene registros."
            )
            return

        if seleccionadas > 1:
            self.textBrowserHelp.setHtml(
                "<b>Sección:</b> Hay más de una línea seleccionada. "
                "Debe dejar una sola."
            )
            return

        if seleccionadas == 1:
            feat = next(sec_layer.getSelectedFeatures(), None)
        elif total == 1:
            feat = next(sec_layer.getFeatures(), None)
        else:
            self.textBrowserHelp.setHtml(
                "<b>Sección:</b> La capa contiene varias líneas. "
                "Seleccione una sola para continuar."
            )
            return

        if feat is None:
            self.textBrowserHelp.setHtml(
                "<b>Sección:</b> No fue posible recuperar la línea."
            )
            return

        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            self.textBrowserHelp.setHtml(
                "<b>Sección:</b> La geometría está vacía."
            )
            return
        
        if geom.isMultipart():
            partes = geom.asMultiPolyline()

            if not partes:
                self.mostrar_ayuda(
                    "Sección",
                    "No fue posible interpretar la geometría de la sección."
                )
                return

            if len(partes) > 1:
                self.mostrar_ayuda(
                    "Sección",
                    "La sección contiene múltiples líneas dentro de un mismo registro. "
                    "SecGeol solo acepta una sola línea por sección."
                )
                return

        

        longitud = geom.length()
        self.textBrowserHelp.setHtml(
            f"<b>Sección activa:</b> {sec_layer.name()}<br>"
            f"<b>Longitud:</b> {longitud:.2f}<br>"
            f"<b>Invertida:</b> {'Sí' if invertida else 'No'}"
        )