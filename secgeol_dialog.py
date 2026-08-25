import os, re, unicodedata

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import QDialog, QSplitter
from qgis.core import (QgsMapLayerProxyModel, QgsProject, Qgis,QgsPoint, QgsPolygon,QgsVectorFileWriter,
                       QgsFeature, QgsGeometry, QgsVectorLayer, QgsField, QgsLineString,
                       QgsWkbTypes, QgsFieldProxyModel, QgsMessageLog,  QgsPointXY,)
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
            QgsMessageLog.logMessage(
                f"Error al finalizar dibujo: {e}",
                "SecGeol",
                Qgis.Critical
            )
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

        # Estado inicial de controles opcionales
        self.FieldElevCurvas.setEnabled(False)   
        self.MapLayerGeo.setEnabled(False)
        self.MapLayerEst.setEnabled(False)

        self.FieldClasGeo.setEnabled(False)
        self.FieldDipEst.setEnabled(False)
        self.FieldAzimuthEst.setEnabled(False)

        # Conectar checks
        self.checkGeo.toggled.connect(self.actualizar_estado_geologia)
        self.checkEst.toggled.connect(self.actualizar_estado_estructuras)

        # Aplicar estado inicial
        self.actualizar_estado_geologia()
        self.actualizar_estado_estructuras()

        self.drawn_section_feature = None
        self.draw_tool = None
        self.section_geom_recortada = None


        # para cambiar entre dem y contour
        self.MapLayerCurvas.layerChanged.connect(self.al_cambiar_curvas)
        self.MapLayerDEM.layerChanged.connect(self.al_cambiar_dem)
        self.btnDrawSec.clicked.connect(self.activar_dibujo_seccion)
        self.MapLayerSec.layerChanged.connect(self.on_section_layer_changed)
        self.MapLayerGeo.layerChanged.connect(self.actualizar_info_geologia)
        self.MapLayerEst.layerChanged.connect(self.actualizar_info_estructuras)

        #Campos filtrados
        self.FieldDipEst.setFilters(QgsFieldProxyModel.Numeric)
        self.FieldAzimuthEst.setFilters(QgsFieldProxyModel.Numeric)
        self.FieldClasGeo.setFilters(QgsFieldProxyModel.AllTypes)
        self.MapLayerSecLin.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.MapLayerPerGeo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.MapLayerSecGuia.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.MapLayerCurvas.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.FieldElevCurvas.setFilters(QgsFieldProxyModel.Numeric)

        #Conectar TAB 2
        self.buttonBox_2.accepted.connect(self.ejecutar_lineas_a_poligonos)
        self.buttonBox_2.rejected.connect(self.reject)

        #Conectar TAB 3
        self.buttonBox_3.accepted.connect(self.ejecutar_perfil_3d)
        self.buttonBox_3.rejected.connect(self.reject)

        # Conectar TAB 1
        self.buttonBox.rejected.connect(self.reject)
        
        self.section_manager = SectionManager()
        self.workspace_manager = WorkspaceManager()
        self.gpkg_path = None


        # CONFIGURAR CAJA
        self.doubleSpinBox.setMinimum(0.0)
        self.doubleSpinBox.setMaximum(10000.0)
        self.doubleSpinBox.setSingleStep(10.0)     #Verificar este punto
        self.doubleSpinBox.setSuffix(" m")
        self.doubleSpinBox.setValue(100.0)

        # SPLITTER DE AYUDA / CONTROLES
        self.splitter_main = self.findChild(QSplitter, "splitter")

        # Extraer datos de elevación ---
        self.profile_manager = ProfileManager()

        if self.splitter_main:
            self.splitter_main.setSizes([300, 100])   #Tamaño de la ventana
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

        # ESTADO INICIAL DE LA AYUDA
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
            <h3>Reconstrucción Geológica 3D</h3>
            <p>
                Seleccione el perfil geológico interpretado generado en el módulo 2 y la sección guía creada en el módulo 1.


            </p>
            <p>
                La sección guía conserva la referencia espacial utilizada para generar el perfil topográfico y permite reconstruir la geometría en coordenadas reales para su visualización en entornos 3D.
            </p>
            <p>
            Salida:
                Perfil_geologico3D

            </p>
            </div>
            """

        # CONEXIÓN DE TABS
        self.tabWidget.currentChanged.connect(self.actualizar_ayuda_tab)

        # INICIALIZAR AYUDA
        self.actualizar_ayuda_tab()

        # CONFIGURAR FILTROS DE CAPAS
        self.MapLayerDEM.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.MapLayerSec.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.MapLayerGeo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.MapLayerEst.setFilters(QgsMapLayerProxyModel.LineLayer)

        # CONFIGURAR SALIDAS

        # Módulo 1
        self.fileWidgetPerfil.setFilter(
            "Shapefile (*.shp);;GeoPackage (*.gpkg)"
        )

        try:
            self.fileWidgetPerfil.setStorageMode(
                self.fileWidgetPerfil.StorageMode.SaveFile
            )
        except AttributeError:
            self.fileWidgetPerfil.setStorageMode(
                self.fileWidgetPerfil.SaveFile
            )

        # Módulo 2
        self.fileWidgetPerfilGeo.setFilter(
            "Shapefile (*.shp);;GeoPackage (*.gpkg)"
        )

        try:
            self.fileWidgetPerfilGeo.setStorageMode(
                self.fileWidgetPerfilGeo.StorageMode.SaveFile
            )
        except AttributeError:
            self.fileWidgetPerfilGeo.setStorageMode(
                self.fileWidgetPerfilGeo.SaveFile
            )

        # Módulo 3
        self.fileWidgetPerfilGeo3D.setFilter(
            "Shapefile (*.shp);;GeoPackage (*.gpkg)"
        )

        try:
            self.fileWidgetPerfilGeo3D.setStorageMode(
                self.fileWidgetPerfilGeo3D.StorageMode.SaveFile
            )
        except AttributeError:
            self.fileWidgetPerfilGeo3D.setStorageMode(
                self.fileWidgetPerfilGeo3D.SaveFile
            )


        # EVENT FILTERS PARA AYUDA
        
        for w in [
            self.MapLayerDEM,
            self.MapLayerCurvas,
            self.MapLayerSec,
            self.btnDrawSec,
            self.checkInvSec,
            self.MapLayerGeo,
            self.FieldClasGeo,
            self.FieldElevCurvas,
            self.MapLayerEst,
            self.doubleSpinBox,
            self.checkEjes,
            self.fileWidgetPerfil,
            self.FieldDipEst,
            self.FieldAzimuthEst,
            self.MapLayerSecLin,
            self.checkGeo,
            self.checkEst,
            self.MapLayerPerGeo,
            self.MapLayerSecGuia,
            self.fileWidgetPerfilGeo3D,
            self.fileWidgetPerfilGeo

        ]:
            w.installEventFilter(self)
            
        # TOOLTIPS

        self.MapLayerDEM.setToolTip(
            "Seleccione el modelo digital de elevación (DEM)."
        )

        self.MapLayerCurvas.setToolTip(
            "Seleccione una capa de curvas de nivel como fuente de elevación."
        )

        self.FieldElevCurvas.setToolTip(
            "Seleccione el campo numérico que contiene la elevación de las curvas de nivel."
        )

        self.checkGeo.setToolTip(
            "Incorporar información geológica al perfil."
        )

        self.checkEst.setToolTip(
            "Incorporar estructuras geológicas al perfil."
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

        self.FieldClasGeo.setToolTip(
            "Campo utilizado para clasificar los segmentos geológicos del perfil."
        )

        self.MapLayerEst.setToolTip(
            "Capa estructural (opcional) para intersectar la sección."
        )

        self.doubleSpinBox.setToolTip(
             "Profundidad de la caja del perfil en metros. El valor predeterminado es 100 m."
        )

        self.checkEjes.setToolTip(
            "Crear ejes X y Y en el perfil generado."
        )

        self.fileWidgetPerfil.setToolTip(
            "Seleccione el archivo de salida para guardar el perfil."
        )

        #Tab3
        self.MapLayerSecLin.setToolTip(
            "Seleccione el perfil topográfico que será convertido en polígonos."
        )

        self.fileWidgetPerfilGeo.setToolTip(
            "Seleccione el archivo de salida para guardar el perfil geológico 2D."
        )

        self.MapLayerPerGeo.setToolTip(
            "Seleccione el perfil geológico poligonal 2D que será reconstruido en 3D."
        )

        self.MapLayerSecGuia.setToolTip(
            "Seleccione la sección guía que proporciona la referencia espacial del perfil."
        )

        self.fileWidgetPerfilGeo3D.setToolTip(
            "Seleccione el archivo de salida para guardar el perfil geológico 3D."
        )

    def on_section_layer_changed(self, layer):
        if layer is not None:
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
        dem_layer = self.MapLayerDEM.currentLayer()
        curvas_layer = self.MapLayerCurvas.currentLayer()

        if dem_layer is None and curvas_layer is None:
            raise Exception(
                self.tr(
                    "Seleccione una fuente de elevación: "
                    "un modelo digital de elevación (DEM) "
                    "o una capa de curvas de nivel."
                )
            )

        self.MapLayerSec.setLayer(None)

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
       
        self.set_drawn_section_feature(feature)
        self.mostrar_seccion_dibujada(feature)

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
        if self.draw_tool is not None:
            iface.mapCanvas().unsetMapTool(self.draw_tool)
            self.draw_tool = None

# Muestra la sección dibujada como capa temporal visible en el mapa. Reemplaza la anterior si existe.

    def mostrar_seccion_dibujada(self, feature):
        if feature is None:
            return

        geom = feature.geometry()
        if geom is None or geom.isEmpty():
            return

        project = QgsProject.instance()

        # eliminar capa previa si existe
        for lyr in list(project.mapLayers().values()):
            if lyr.name() == "seccion_dibujada":
                
                project.removeMapLayer(lyr.id())

        #Verifica que haya proyección en DEM o en curvas

        dem_layer = self.MapLayerDEM.currentLayer()
        curvas_layer = self.MapLayerCurvas.currentLayer()

        if dem_layer is not None:
            crs_authid = dem_layer.crs().authid()

        elif curvas_layer is not None:
            crs_authid = curvas_layer.crs().authid()

        else:
            raise Exception(
                self.tr(
                    "Seleccione una fuente de elevación: "
                    "un modelo digital de elevación (DEM) "
                    "o una capa de curvas de nivel."
                )
            )
       
        layer = QgsVectorLayer(f"LineString?crs={crs_authid}", "seccion_dibujada", "memory")
        if not layer.isValid():
            return

        provider = layer.dataProvider()
        feat = QgsFeature()
        feat.setGeometry(geom)

        provider.addFeatures([feat])
        layer.updateExtents()

        # simbología visible
        renderer = layer.renderer()
        symbol = renderer.symbol()
        symbol.setWidth(1.5)
        symbol.setColor(QColor(255, 0, 0))  # rojo
        layer.triggerRepaint()

        project.addMapLayer(layer)

        # forzar refresco visual
        iface.mapCanvas().refresh()

    # PANEL DE AYUDA
    def mostrar_ayuda(self, titulo, html):
         self.textBrowserHelp.setHtml(f"""
                <div style="font-family: 'Segoe UI', Arial, sans-serif;">
                    <h3 style="margin-bottom: 8px;">{titulo}</h3>
                    {html}
                </div>
            """)

    # EVENT FILTER  Mostarr ayuda
    def eventFilter(self, obj, event):
        if event.type() == 10:

            if obj == self.MapLayerDEM:
                self.actualizar_info_dem()

            elif obj == self.MapLayerSec:
                self.actualizar_info_seccion()


            elif obj == self.MapLayerCurvas:  
                self.mostrar_ayuda(
                    "Curvas de nivel",
                    """
                    <p>
                        Seleccione una capa vectorial de <b>líneas</b> que contenga
                        las curvas de nivel utilizadas como fuente de elevación.
                    </p>

                    <p>
                        SecGeol calculará las intersecciones entre la línea de sección
                        y las curvas de nivel para construir el perfil topográfico.
                    </p>

                    <p>
                        <b>Importante:</b> el perfil se limitará desde la primera
                        hasta la última curva de nivel intersectada. La primera
                        intersección se establecerá como <b>X = 0</b>.
                    </p>
                    """
                )

            elif obj == self.FieldElevCurvas:
                self.mostrar_ayuda(
                    "Campo de elevación",
                    """
                    <p>
                        Seleccione el campo numérico que contiene la
                        <b>cota o elevación</b> de cada curva de nivel.
                    </p>

                    <p>
                        SecGeol muestra únicamente los <b>campos numéricos</b>
                        disponibles en la capa seleccionada.
                    </p>

                    <p>
                        Los valores deben almacenarse como números, sin unidades,
                        símbolos ni texto adicional.
                    </p>
                    """
                )

            elif obj == self.btnDrawSec:
                self.mostrar_ayuda(
                   "Dibujar sección",
                    """
                    <p>
                        Permite dibujar una <b>línea de sección</b> directamente
                        sobre el mapa, como alternativa a seleccionar una sección
                        desde una capa vectorial.
                    </p>

                    <p>
                        Haga clic sobre el mapa para definir los vértices de la línea
                        y utilice <b>clic derecho</b> para finalizar el dibujo.
                    </p>
                    """
                )

            elif obj == self.checkInvSec:
                self.mostrar_ayuda(
                    "Invertir sección",
                    """
                    <p>
                        Invierte el sentido de la línea de sección y, por lo tanto,
                        la orientación del perfil resultante.
                    </p>

                    <p>
                        Active esta opción cuando necesite intercambiar el
                        <b>inicio y el final</b> de la sección.
                    </p>
                    """
                )

            elif obj == self.checkGeo:
                self.mostrar_ayuda(
                    "Incorporar geología",
                    """
                    <p>
                        Active esta opción para incorporar una capa geológica
                        poligonal al perfil.
                    </p>

                    <p>
                        SecGeol intersectará las unidades geológicas con la línea
                        de sección y las representará sobre el perfil topográfico.
                    </p>

                    <p>
                        Esta opción es <b>opcional</b>.
                    </p>
                    """
                )

            elif obj == self.checkEst:
                self.mostrar_ayuda(
                    "Incorporar estructuras",
                    """
                    <p>
                        Active esta opción para incorporar estructuras geológicas
                        representadas mediante una capa vectorial de líneas.
                    </p>

                    <p>
                        SecGeol utilizará los campos de <b>echado</b> y
                        <b>azimut de buzamiento</b> para representar las estructuras
                        que intersectan la sección.
                    </p>

                    <p>
                        Esta opción es <b>opcional</b>.
                    </p>
                    """
                )

            elif obj == self.MapLayerGeo:
                self.mostrar_ayuda(
                   "Capa de geología",
                    """
                    <p>
                        Seleccione una capa vectorial de <b>polígonos</b> que contenga
                        las unidades geológicas atravesadas por la línea de sección.
                    </p>

                    <p>
                        SecGeol intersectará esta capa con la sección para representar
                        la distribución de las unidades geológicas sobre el perfil
                        topográfico.
                    </p>

                    <p>
                        Esta entrada es <b>opcional</b>.
                    </p>
                    """
                )

            elif obj == self.FieldClasGeo:
                self.mostrar_ayuda(
                    "Campo de clasificación geológica",
                    """
                    <p>
                        Seleccione el campo de atributos que identifica las
                        <b>unidades geológicas</b>.
                    </p>

                    <p>
                        Los valores de este campo se transferirán al perfil y
                        se almacenarán en el atributo <b>valor_geo</b>.
                    </p>
                    """
                )
            

            elif obj == self.MapLayerEst:
                self.mostrar_ayuda(
                   "Capa estructural",
                    """
                    <p>
                        Seleccione una capa vectorial de líneas que contenga
                        las estructuras geológicas que intersectan la sección.
                    </p>

                    <p>
                        Esta entrada es <b>opcional</b>.
                    </p>
                    """
                )

            elif obj == self.doubleSpinBox:
                self.mostrar_ayuda(
                   "Profundidad de la caja",
                    """
                    <p>
                        Define, en metros, la profundidad adicional que se
                        representará por debajo de la elevación mínima del
                        perfil topográfico.
                    </p>

                    <p>
                        El valor permitido está entre <b>1 y 10 000 m</b>.
                        El valor predeterminado es <b>100 m</b>.
                    </p>

                    <p>
                        Por ejemplo, un valor de <b>500</b> extiende la caja
                        <b>500 m</b> por debajo de la elevación mínima del perfil.
                    </p>
                    """
                )

            elif obj == self.checkEjes:
                self.mostrar_ayuda(
                    "Crear ejes",
                    """
                    <p>
                        Active esta opción para generar los ejes horizontal y
                        vertical asociados al perfil.
                    </p>

                    <p>
                        El eje horizontal representa la <b>distancia sobre la sección</b>
                        y el eje vertical la <b>elevación</b>.
                    </p>
                    """
                )

            elif obj == self.fileWidgetPerfil:
                self.mostrar_ayuda(
                    "Archivo de salida",
                    """
                    <p>
                        Seleccione la ubicación y el nombre del archivo donde
                        se guardará el perfil topográfico.
                    </p>

                    <p>
                        SecGeol generará también la <b>sección guía</b>, que conserva
                        la referencia espacial necesaria para la reconstrucción 3D.
                    </p>
                    """
                )

            #Estructuras

            elif obj == self.FieldDipEst:
                self.mostrar_ayuda(
                    "Campo de echado",
                    """
                    <p>
                        Seleccione el campo numérico que contiene el
                        <b>echado</b> de cada estructura.
                    </p>

                    <p>
                        Los valores deben almacenarse como <b>valores numéricos</b>
                        entre <b>0 y 90</b> grados, sin incluir el símbolo de grado (°).
                    </p>

                    <p>
                        Los registros con valores fuera de este intervalo
                        no se representarán en el perfil.
                    </p>
                    """
                )

            elif obj == self.FieldAzimuthEst:
                self.mostrar_ayuda(
                    "Campo de azimut de buzamiento",
                        """
                        <p>
                            Seleccione el campo numérico que contiene el
                            <b>azimut de buzamiento</b> de cada estructura.
                        </p>

                        <p>
                            Los valores deben almacenarse como <b>valores numéricos</b> entre
                            <b>0 y 360</b> grados, sin incluir el símbolo de grado (°).
                        </p>

                        <p>
                            Los registros con valor <b>-1</b> o fuera de este intervalo
                            no se representarán en el perfil.
                        </p>
                        """
                )

            elif obj == self.MapLayerSecGuia:
                self.mostrar_ayuda(
                    "Sección guía",
                    """
                    <p>
                        Seleccione la <b>sección guía</b> generada en el módulo
                        <b>1. Sección a perfil</b>.
                    </p>

                    <p>
                        Esta capa conserva la referencia espacial utilizada para
                        generar el perfil y permite reconstruir la interpretación
                        geológica en sus coordenadas reales.
                    </p>

                    <p>
                        Cuando el perfil se genera a partir de curvas de nivel,
                        la sección guía corresponde únicamente al tramo comprendido
                        entre la primera y la última intersección.
                    </p>
                    """
                )

            elif obj == self.MapLayerPerGeo:
                self.mostrar_ayuda(
                    "Perfil geológico 2D",
                    """
                    <p>
                        Seleccione la capa poligonal generada en el módulo
                        <b>2. Líneas a polígonos</b>.
                    </p>

                    <p>
                        Esta capa contiene la interpretación geológica del perfil
                        en coordenadas locales, donde el eje X representa la
                        distancia a lo largo de la sección.
                    </p>

                    <p>
                        SecGeol utilizará esta geometría junto con la sección guía
                        para reconstruir el perfil en coordenadas espaciales reales.
                    </p>
                    """
                )
           

            elif obj == self.fileWidgetPerfilGeo:
                self.mostrar_ayuda(
                    "Salida del perfil geológico",
                    """
                    <p>
                        Seleccione la ubicación y el nombre del archivo donde se
                        guardará el <b>perfil geológico poligonal 2D</b>.
                    </p>

                    <p>
                        Esta capa podrá utilizarse posteriormente en el módulo
                        <b>3. Perfil 2D a 3D</b>.
                    </p>
                    """
                )

            elif obj == self.fileWidgetPerfilGeo3D:
                self.mostrar_ayuda(
                    "Salida del perfil geológico 3D",
                    """
                    <p>
                        Seleccione la ubicación y el nombre del archivo donde se
                        guardará el perfil geológico reconstruido en
                        <b>coordenadas espaciales reales</b>.
                    </p>

                    <p>
                        La salida conserva la geometría tridimensional necesaria
                        para su visualización y análisis en entornos 3D.
                    </p>
                    """
                )

            elif obj == self.MapLayerSecLin:
                self.mostrar_ayuda(
                    "Perfil topográfico",
                    """
                    <p>
                        Seleccione la capa <b>Perfil_topografico</b> generada en el
                        módulo <b>1. Sección a perfil</b>.
                    </p>

                    <p>
                        Esta capa contiene la línea del terreno y los elementos
                        asociados al perfil. Puede ser ajustada durante la
                        interpretación geológica antes de convertir las líneas
                        en polígonos.
                    </p>

                    <p>
                        El módulo <b>2. Líneas a polígonos</b> utilizará estas
                        geometrías para construir el perfil geológico poligonal.
                    </p>
                    """
                )


        elif event.type() == 11:  # Leave
            self.actualizar_ayuda_tab()

        return super().eventFilter(obj, event)

    #Selección de DEM o curvas de nivel
    def al_cambiar_curvas(self, layer):
        if layer is not None:
            self.MapLayerDEM.setLayer(None)
            self.FieldElevCurvas.setLayer(layer)
            self.FieldElevCurvas.setEnabled(True)
        else:
            self.FieldElevCurvas.setLayer(None)
            self.FieldElevCurvas.setEnabled(False)


    def al_cambiar_dem(self, layer):
        if layer is not None:
            self.MapLayerCurvas.setLayer(None)
            self.FieldElevCurvas.setLayer(None)
            self.FieldElevCurvas.setEnabled(False)

    # Conecta la función de la sección      
    
    def preparar_seccion_trabajo(self, feat_sec=None, has_drawn=False, invertida=False):
        dem_layer = self.MapLayerDEM.currentLayer()
        curvas_layer = self.MapLayerCurvas.currentLayer()

        if dem_layer is not None:
            target_crs = dem_layer.crs()

        elif curvas_layer is not None:
            target_crs = curvas_layer.crs()

        else:
            raise Exception(
                self.tr(
                    "Seleccione una fuente de elevación: "
                    "un modelo digital de elevación (DEM) "
                    "o una capa de curvas de nivel."
                )
            )

        # Caso 1: el usuario dibujó una sección
        if has_drawn:
            if self.drawn_section_feature is None:
                raise Exception(self.tr("No se encontró la sección dibujada."))
            # Ajusta aquí según el CRS real de tu sección dibujada
            source_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
            temp_layer = self.section_manager.prepare_section_layer_from_feature(
                source_feature=self.drawn_section_feature,
                source_crs=source_crs,
                target_crs=target_crs,
                invertida=invertida
            )           

        # Caso 2: el usuario seleccionó una sola sección válida del layer
        elif feat_sec is not None:
            source_layer = self.MapLayerSec.currentLayer()
            if source_layer is None:
                raise Exception(self.tr("No se encontró la capa de sección."))
            source_crs = source_layer.crs()
            temp_layer = self.section_manager.prepare_section_layer_from_feature(
                source_feature=feat_sec,
                source_crs=source_crs,
                target_crs=target_crs,
                invertida=invertida
            )
         
        else:
            raise Exception(self.tr("No se encontró una sección válida para preparar."))

        if temp_layer is None or not temp_layer.isValid():
            raise Exception(self.tr("No fue posible preparar la sección de trabajo."))
        return temp_layer
    
    # Inicializa workspace
    def inicializar_workspace(self):
        dem_layer = self.MapLayerDEM.currentLayer()
        curvas_layer = self.MapLayerCurvas.currentLayer()

        if dem_layer is not None:
            crs_authid = dem_layer.crs().authid()

        elif curvas_layer is not None:
            crs_authid = curvas_layer.crs().authid()

        else:
            raise Exception(
                self.tr(
                    "Seleccione una fuente de elevación: "
                    "un modelo digital de elevación (DEM) "
                    "o una capa de curvas de nivel."
                )
            )

        self.gpkg_path = self.workspace_manager.create_base_geopackage(crs_authid)
        self.section_manager.set_gpkg_path(self.gpkg_path)

    # Entra a secprofile    
    def generar_perfil(self, feat_sec=None, has_drawn=False, invertida=False, segmentos_geo=None, estructuras=None, section_layer=None):
        if segmentos_geo is None:
            segmentos_geo = []

        if estructuras is None:
            estructuras = []

        dem_layer = self.MapLayerDEM.currentLayer()
        curvas_layer = self.MapLayerCurvas.currentLayer()

        if dem_layer is None and curvas_layer is None:
            raise Exception(
                self.tr(
                    "Seleccione una fuente de elevación: "
                    "un modelo digital de elevación (DEM) "
                    "o una capa de curvas de nivel."
                )
            )

        if section_layer is None:
            section_layer = self.preparar_seccion_trabajo(
                feat_sec=feat_sec,
                has_drawn=has_drawn,
                invertida=invertida
            )

        if section_layer is None or not section_layer.isValid():
            raise Exception(self.tr("No fue posible preparar la sección de trabajo."))
        caja_m = self.obtener_caja_m()
        section_geom = self.section_manager.obtener_geometria_seccion_efectiva(section_layer)

        if section_geom is None:
            raise Exception(self.tr("No fue posible obtener la geometría efectiva de la sección."))

        # Variables para la fuente de elevación
        profile_point_features = None
        dist_inicio = None
        dist_fin = None

        self.section_geom_recortada = None

        if curvas_layer is not None:
            campo_elev = self.FieldElevCurvas.currentField()

            profile_point_features, dist_inicio, dist_fin = (
                self.profile_manager.build_profile_points_from_contours(
                    section_geom=section_geom,
                    contour_layer=curvas_layer,
                    elevation_field=campo_elev
                )
            )

            # Recortar la sección al intervalo cubierto por las curvas de nivel
            seccion_recortada = self.section_manager.recortar_seccion_por_distancia(
                section_geom,
                dist_inicio,
                dist_fin
            )

            self.section_geom_recortada = seccion_recortada
            

        break_distances = []
        if section_geom is not None:
            break_distances = self.section_manager.detect_section_break_distances(section_geom)

        perfil_layer = self.profile_manager.build_profile_box_layer(
            section_layer=section_layer,
            dem_layer=dem_layer,
            profile_point_features=profile_point_features,
            extra_depth=caja_m,
            layer_name="Perfil_topografico",
            break_distances=break_distances,
            segmentos_geo=segmentos_geo,
            estructuras=estructuras
        )

        return perfil_layer

    # Valor de caja en metros

    def obtener_caja_m(self):
        caja_m = self.doubleSpinBox.value()
        if caja_m <= 0:
            caja_m = 100.0
        return caja_m

    # Información DEM
    def actualizar_info_dem(self):
        dem_layer = self.MapLayerDEM.currentLayer()

        if dem_layer is None:
            self.mostrar_ayuda(
                "Modelo digital de elevación",
                """
                <p>
                    No se ha seleccionado un <b>modelo digital de elevación (DEM)</b>.
                </p>

                <p>
                    Seleccione una capa raster válida para continuar.
                </p>
                """
            )
            return

        if dem_layer.type() != dem_layer.RasterLayer:
            self.mostrar_ayuda(
                "Modelo digital de elevación no válido",
                """
                <p>
                    La capa seleccionada no es una <b>capa raster</b>.
                </p>

                <p>
                    Seleccione un modelo digital de elevación en formato raster.
                </p>
                """
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
                estado = (
                    "<p style='color:green;'>"
                    "<b>Estado: Compatible con SecGeol.</b>"
                    "</p>"
                )

            else:
                detalles = []

                if not dem_crs.isValid():
                    detalles.append("El CRS no es válido.")
                elif not es_metrico:
                    detalles.append("El CRS debe utilizar metros como unidad.")

                if not una_banda:
                    detalles.append("El raster debe contener una sola banda.")
                elif band_type_name not in tipos_validos:
                    detalles.append(
                        f"El tipo de dato no es adecuado ({band_type_name})."
                    )

                lista_detalles = "".join(
                    f"<li>{detalle}</li>"
                    for detalle in detalles
                )

                estado = (
                    "<div style='color:red;'>"
                    "<p><b>Estado: No compatible con SecGeol.</b></p>"
                    "<p>Revise las siguientes características:</p>"
                    f"<ul>{lista_detalles}</ul>"
                    "</div>"
                )
                

            self.mostrar_ayuda(
                "Modelo digital de elevación",
                f"""
                <p>
                    <b>DEM seleccionado:</b> {dem_layer.name()}<br>
                    <b>CRS:</b> {crs_info}<br>
                    <b>Tamaño de píxel:</b> {pixel_x:.3f} × {pixel_y:.3f}<br>
                    <b>Bandas:</b> {dem_layer.bandCount()}<br>
                    <b>Tipo de dato:</b> {band_type_name}
                </p>

                {estado}
                """
            )

        except Exception as e:
            self.mostrar_ayuda(
                "Error al leer el DEM",
                f"""
                <p>
                    No fue posible leer correctamente las propiedades
                    de la capa seleccionada.
                </p>

                <p>
                    <b>Detalle:</b> {e}
                </p>
                """
            )

    # Información DEM

    def actualizar_info_seccion(self):
        sec_layer = self.MapLayerSec.currentLayer()
        has_drawn = self.drawn_section_feature is not None
        invertida = self.checkInvSec.isChecked()

        if has_drawn:
            geom = self.drawn_section_feature.geometry() if self.drawn_section_feature else None
            if geom is None or geom.isEmpty():
                self.mostrar_ayuda(
                    "Sección no válida",
                    """
                    <p>
                        <span style="color:red; font-size:18px;">⚠</span>
                        <b> La sección dibujada no contiene una geometría válida.</b>
                    </p>

                    <p>
                        Dibuje nuevamente la línea de sección para continuar.
                    </p>
                    """
                )
                return

            longitud = geom.length()
            self.mostrar_ayuda(
                    "Sección activa",
                    f"""
                    <p>
                        <b>Origen:</b> dibujada por el usuario<br>
                        <b>Longitud:</b> {longitud:.2f} m<br>
                        <b>Orientación invertida:</b> {'Sí' if invertida else 'No'}
                    </p>
                    """
                )
            return

        if sec_layer is None:
            self.mostrar_ayuda(
                "Sección",
                """
                <p>
                    Seleccione una <b>capa de sección</b> o dibuje una línea
                    directamente sobre el mapa.
                </p>
                """
            )
            return

        if QgsWkbTypes.geometryType(sec_layer.wkbType()) != QgsWkbTypes.LineGeometry:
            self.mostrar_ayuda(
                    "Sección no válida",
                    """
                    <p>
                        <span style="color:red; font-size:18px;">⚠</span>
                        <b> La capa seleccionada no es de tipo línea.</b>
                    </p>

                    <p>
                        Seleccione una capa vectorial lineal para continuar.
                    </p>
                    """
                )
            return

        total = sec_layer.featureCount()
        seleccionadas = sec_layer.selectedFeatureCount()

        if total == 0:
            self.mostrar_ayuda(
                    "Sección no válida",
                    """
                    <p>
                        <span style="color:red; font-size:18px;">⚠</span>
                        <b> La capa seleccionada no contiene registros.</b>
                    </p>
                    """
                )
            return

        if seleccionadas > 1:
            self.mostrar_ayuda(
                    "Sección requerida",
                    """
                    <p>
                        <span style="color:red; font-size:18px;">⚠</span>
                        <b> Hay más de una sección seleccionada.</b>
                    </p>

                    <p>
                        Deje seleccionada <b>una sola línea</b> para continuar.
                    </p>
                    """
                )
            return

        if seleccionadas == 1:
            feat = next(sec_layer.getSelectedFeatures(), None)
        elif total == 1:
            feat = next(sec_layer.getFeatures(), None)
        else:
            self.mostrar_ayuda(
                "Sección requerida",
                """
                <p style="color:#b00020;">
                    <span style="color:red; font-size:18px;">⚠</span>
                    <b> La capa contiene más de una sección.</b>
                </p>

                <p>
                    Seleccione <b>una sola línea</b> para continuar.
                </p>
                """
            )
            return

        if feat is None:
           self.mostrar_ayuda(
                "Sección no válida",
                """
                <p>
                    <span style="color:red; font-size:18px;">⚠</span>
                    <b> No fue posible recuperar la sección seleccionada.</b>
                </p>
                """
           )
           return

        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            self.mostrar_ayuda(
                "Sección no válida",
                """
                <p>
                    <span style="color:red; font-size:18px;">⚠</span>
                    <b> La geometría de la sección está vacía.</b>
                </p>
                """
            )
            return
        
        if geom.isMultipart():
            partes = geom.asMultiPolyline()

            if not partes:
                self.mostrar_ayuda(
                    "Sección no válida",
                    """
                    <p>
                        No fue posible interpretar la geometría de la sección seleccionada.
                    </p>

                    <p>
                        Seleccione una <b>geometría lineal válida</b> para continuar.
                    </p>
                    """
                )
                return

            if len(partes) > 1:
                self.mostrar_ayuda(
                    "Sección no válida",
                    """
                    <p>
                        El registro seleccionado contiene <b>más de una línea independiente</b>.
                    </p>

                    <p>
                        SecGeol requiere <b>una sola línea por registro</b>.
                        La línea puede contener múltiples vértices y cambios de dirección.
                    </p>
                    """
                )
                return

        

        longitud = geom.length()
        self.mostrar_ayuda(
            "Sección activa",
            f"""
            <p>
                <b>Capa:</b> {sec_layer.name()}<br>
                <b>Longitud:</b> {longitud:.2f} m<br>
                <b>Orientación invertida:</b> {'Sí' if invertida else 'No'}
            </p>
            """
        )

    # Existe comentarios de ayuda de la capa Geologia
    
    def actualizar_estado_geologia(self):
        activo = self.checkGeo.isChecked()

        self.MapLayerGeo.setEnabled(activo)
        self.FieldClasGeo.setEnabled(activo)

        if not activo:
            self.MapLayerGeo.setLayer(None)
            self.FieldClasGeo.setLayer(None)
            self.mostrar_ayuda(
                "Sin geología",
                """
                <p>
                    La incorporación de información geológica es <b>opcional</b>.
                </p>

                <p>
                    Active esta opción para seleccionar una capa poligonal
                    y representar las unidades geológicas que intersectan
                    la línea de sección.
                </p>
                """
            )
        else:
            self.actualizar_info_geologia()

    # Si existe Geologia
    
    def actualizar_info_geologia(self):
        geo_layer = self.MapLayerGeo.currentLayer()

        if geo_layer is None:
            self.FieldClasGeo.setLayer(None)
            self.mostrar_ayuda(
                "Capa de geología",
                """
                <p>
                    La opción de geología está <b>activada</b>.
                </p>

                <p>
                    Seleccione una capa vectorial de <b>polígonos</b>
                    que contenga las unidades geológicas.
                </p>

                <p>
                    Al seleccionar la capa, SecGeol habilitará sus campos
                    de atributos para elegir el campo de clasificación geológica.
                </p>
                """
            )
            return

        self.FieldClasGeo.setLayer(geo_layer)

        campos = geo_layer.fields()
        total_campos = len(campos)

        campo_geo = self.FieldClasGeo.currentField()
        if not campo_geo:
            campo_geo = None

        crs = geo_layer.crs()
        crs_authid = crs.authid()
        crs_name = crs.description()

        crs_info = f"{crs_authid} - {crs_name}" if crs_authid else crs_name

        if total_campos == 0:
            mensaje_campo = """
                <p>
                    La capa geológica no contiene campos de atributos.
                    SecGeol continuará utilizando únicamente <b>id_lito</b>
                    como identificador de las unidades.
                </p>
            """
        else:
            mensaje_campo = """
                <p>
                    Seleccione el campo de atributos que identifica las
                    <b>unidades geológicas</b>.
                </p>

                <p>
                    SecGeol generará además el campo <b>id_lito</b>
                    como identificador interno.
                </p>
            """

        self.mostrar_ayuda(
            "Capa de geología",
            f"""
            <p>
                <b>Capa seleccionada:</b> {geo_layer.name()}<br>
                <b>CRS:</b> {crs_info}<br>
                <b>Campos disponibles:</b> {total_campos}
            </p>

            {mensaje_campo}
            """
        )


    # Actualizar información de ayuda si es que se selecciona Estructuras
    
    def actualizar_estado_estructuras(self):
        activo = self.checkEst.isChecked()

        self.MapLayerEst.setEnabled(activo)
        self.FieldDipEst.setEnabled(activo)
        self.FieldAzimuthEst.setEnabled(activo)

        if not activo:
            self.MapLayerEst.setLayer(None)
            self.FieldDipEst.setLayer(None)
            self.FieldAzimuthEst.setLayer(None)
            self.mostrar_ayuda(
                "Sin estructuras",
                """
                <p>
                    La incorporación de información estructural es <b>opcional</b>.
                </p>

                <p>
                    Active esta opción para seleccionar una capa lineal
                    y representar las estructuras geológicas que intersectan
                    la línea de sección.
                </p>
                """
            )
        else:
            self.actualizar_info_estructuras()


    def actualizar_info_estructuras(self):
        est_layer = self.MapLayerEst.currentLayer()

        if est_layer is None:
            self.FieldDipEst.setLayer(None)
            self.FieldAzimuthEst.setLayer(None)
            self.mostrar_ayuda(
                "Capa de estructuras",
                """
                <p>
                    La opción de estructuras está <b>activada</b>.
                </p>

                <p>
                    Seleccione una capa vectorial de <b>líneas</b>
                    que contenga las estructuras geológicas.
                </p>

                <p>
                    Al seleccionar la capa, SecGeol habilitará los campos
                    numéricos disponibles para definir el <b>echado</b>
                    y el <b>azimut de buzamiento</b>.
                </p>
                """
            )
            return

        self.FieldDipEst.setLayer(est_layer)
        self.FieldAzimuthEst.setLayer(est_layer)

        crs = est_layer.crs()
        crs_authid = crs.authid()
        crs_name = crs.description()

        crs_info = f"{crs_authid} - {crs_name}" if crs_authid else crs_name
        total_campos = len(est_layer.fields())

        self.mostrar_ayuda(
            "Capa de estructuras",
            f"""
            <p>
                <b>Capa seleccionada:</b> {est_layer.name()}<br>
                <b>CRS:</b> {crs_info}<br>
            </p>

            <p>
                SecGeol muestra únicamente los <b>campos numéricos</b>
                disponibles para seleccionar el <b>echado</b> y el
                <b>azimut de buzamiento</b>.
            </p>

            <p>
                Estos valores se utilizarán para representar las estructuras
                que intersectan la línea de sección sobre el perfil.
            </p>
            """
        )

    #---------------------Tab 2---------------------------------------    
    def ejecutar_lineas_a_poligonos(self):
        try:
            line_layer = self.MapLayerSecLin.currentLayer()
            salida_perfil_geo = self.fileWidgetPerfilGeo.filePath().strip()

            if line_layer is None:
                raise Exception("Seleccione una capa de líneas del perfil.")

            perfil_poly_layer = self.profile_manager.build_geological_polygon_layer(
                line_layer=line_layer,
                layer_name="perfil_geologico"
            )

            ejes_layer = None

            if self.checkEjes.isChecked():
                ejes_layer = self.profile_manager.build_axes_layer(
                    line_layer=line_layer,
                    layer_name="ejes"
                )

            self.guardar_salida_tab2(
                perfil_poly_layer=perfil_poly_layer,
                ejes_layer=ejes_layer,
                salida_perfil_geo=salida_perfil_geo
            )

            self.mostrar_ayuda(
                "Líneas a polígonos",
                "Se generó la capa temporal <b>perfil_geologico</b>."
                + (
                    " y la capa <b>ejes</b>."
                    if ejes_layer is not None
                    else "."
                )
            )
            
            self.accept()

        except Exception as e:
            QgsMessageLog.logMessage(
            f"Error en líneas a polígonos/ejes: {e}",
            "SecGeol",
            Qgis.Critical
            )

            self.mostrar_ayuda(
                "Error",
                str(e)
            )
    
 
    #Tab2

    def guardar_salida_tab2(
        self,
        perfil_poly_layer,
        ejes_layer,
        salida_perfil_geo
    ):
       
        if perfil_poly_layer is None:
            raise Exception("No se generó la capa del perfil geológico.")

        if not salida_perfil_geo:
            raise Exception("Seleccione una ruta de salida.")

        carpeta = os.path.dirname(salida_perfil_geo)
        nombre_archivo = os.path.basename(salida_perfil_geo)
        nombre_base, extension = os.path.splitext(nombre_archivo)

        if not extension:
            extension = ".shp"

        nombre_base = unicodedata.normalize("NFKD", nombre_base)
        nombre_base = "".join(
            caracter for caracter in nombre_base
            if not unicodedata.combining(caracter)
        )

        nombre_base = nombre_base.lower()
        nombre_base = nombre_base.replace(" ", "_")
        nombre_base = re.sub(r"[^a-z0-9_]", "", nombre_base)
        nombre_base = re.sub(r"_+", "_", nombre_base).strip("_")
        nombre_base = nombre_base[:30]

        if not nombre_base:
            nombre_base = "perfil_geologico"

        contador = 0

        while True:
            sufijo = "" if contador == 0 else f"_{contador}"

            ruta_perfil = os.path.join(
                carpeta,
                f"{nombre_base}{sufijo}.shp"
            )

            ruta_ejes = os.path.join(
                carpeta,
                f"{nombre_base}{sufijo}_ejes.shp"
            )

            existe_perfil = os.path.exists(ruta_perfil)
            existe_ejes = (
                ejes_layer is not None
                and os.path.exists(ruta_ejes)
            )

            if not existe_perfil and not existe_ejes:
                break

            contador += 1

        opciones = QgsVectorFileWriter.SaveVectorOptions()
        opciones.driverName = "ESRI Shapefile"
        opciones.fileEncoding = "UTF-8"

        contexto = QgsProject.instance().transformContext()

        resultado_perfil = QgsVectorFileWriter.writeAsVectorFormatV3(
            perfil_poly_layer,
            ruta_perfil,
            contexto,
            opciones
        )

        if resultado_perfil[0] != QgsVectorFileWriter.NoError:
            raise Exception(
                f"No fue posible guardar el perfil geológico: "
                f"{resultado_perfil[1]}"
            )

        perfil_guardado = QgsVectorLayer(
            ruta_perfil,
            os.path.splitext(os.path.basename(ruta_perfil))[0],
            "ogr"
        )

        if not perfil_guardado.isValid():
            raise Exception(
                "El perfil geológico se guardó, pero no pudo cargarse."
            )

        QgsProject.instance().addMapLayer(perfil_guardado)

        ejes_guardada = None

        if ejes_layer is not None:
            resultado_ejes = QgsVectorFileWriter.writeAsVectorFormatV3(
                ejes_layer,
                ruta_ejes,
                contexto,
                opciones
            )

            if resultado_ejes[0] != QgsVectorFileWriter.NoError:
                raise Exception(
                    f"No fue posible guardar la capa de ejes: "
                    f"{resultado_ejes[1]}"
                )

            ejes_guardada = QgsVectorLayer(
                ruta_ejes,
                os.path.splitext(os.path.basename(ruta_ejes))[0],
                "ogr"
            )

            if not ejes_guardada.isValid():
                raise Exception(
                    "La capa de ejes se guardó, pero no pudo cargarse."
                )

            QgsProject.instance().addMapLayer(ejes_guardada)

        QgsProject.instance().removeMapLayer(perfil_poly_layer.id())

        if ejes_layer is not None:
            QgsProject.instance().removeMapLayer(ejes_layer.id())

        return {
            "perfil": ruta_perfil,
            "ejes": ruta_ejes if ejes_layer is not None else None,
            "perfil_layer": perfil_guardado,
            "ejes_layer": ejes_guardada
        }

    # Tab 1
    def crear_seccion_guia(
        self,
        section_layer,
        invertida=False,
        layer_name="Seccion_guia",
        geom_override=None
    ):
        

        if section_layer is None or not section_layer.isValid():
            raise Exception("No hay sección de trabajo válida para crear la sección guía.")

        crs_authid = section_layer.crs().authid()

        guia_layer = QgsVectorLayer(
            f"LineString?crs={crs_authid}",
            layer_name,
            "memory"
        )

        prov = guia_layer.dataProvider()

        prov.addAttributes([
            QgsField("sec_id", QVariant.Int),
            QgsField("long_m", QVariant.Double),
            QgsField("invert", QVariant.Int),
            QgsField("crs", QVariant.String)

        ])

        guia_layer.updateFields()

        out_features = []

        for f in section_layer.getFeatures():
            long_override = (
                f"{geom_override.length():.3f}"
                if geom_override is not None
                else "None"
            )

            if geom_override is not None:
                geom = QgsGeometry(geom_override)
            else:
                geom = QgsGeometry(f.geometry())

            feat = QgsFeature(guia_layer.fields())
            feat.setGeometry(geom)
            feat.setAttributes([
                1,
                float(geom.length()),
                1 if invertida else 0,
                section_layer.crs().authid()
            ])

            out_features.append(feat)
            break

        prov.addFeatures(out_features)
        guia_layer.updateExtents()

        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == layer_name:
                QgsProject.instance().removeMapLayer(lyr.id())

        QgsProject.instance().addMapLayer(guia_layer)

        return guia_layer


    # Tab 3

    def ejecutar_perfil_3d(self):
        try:
            poly_layer = self.MapLayerPerGeo.currentLayer()

            if poly_layer is None:
                raise Exception("Seleccione una capa poligonal del perfil geológico.")

            sec_layer = self.MapLayerSecGuia.currentLayer()

            if sec_layer is None:
                raise Exception(
                    "Seleccione la capa Seccion_guia."
            )


            salida_perfil_3d  = self.fileWidgetPerfilGeo3D.filePath()

            if not salida_perfil_3d :
                raise Exception("Seleccione una ruta de salida para el perfil 3D.")
            
            sec_feat = next(sec_layer.getFeatures())
            sec_geom = sec_feat.geometry()


            crs_authid = sec_layer.crs().authid()

            out_layer = QgsVectorLayer(
                f"PolygonZ?crs={crs_authid}",
                "perfil_geologico3D",
                "memory"
            )

            prov = out_layer.dataProvider()
            prov.addAttributes(poly_layer.fields())
            out_layer.updateFields()

            total_3d = 0

            for feat in poly_layer.getFeatures():

                geom = feat.geometry()

                if geom is None or geom.isEmpty():
                    continue

                multi = geom.asMultiPolygon()

                if not multi:
                    continue

                for poly in multi:

                    if not poly:
                        continue

                    exterior_ring = poly[0]

                    nuevos_vertices = []

                    for pt in exterior_ring:

                        x_perfil = pt.x()
                        z_perfil = pt.y()

                        long_guia = sec_geom.length()
                        tolerancia = 1e-6

                        # Tratar explícitamente el extremo final de la sección guía
                        if abs(x_perfil - long_guia) <= tolerancia:
                            vertices_guia = list(sec_geom.vertices())
                            ultimo = vertices_guia[-1]
                            xy = QgsPointXY(ultimo.x(), ultimo.y())

                        else:
                            punto_real = sec_geom.interpolate(x_perfil)

                            if punto_real is None or punto_real.isEmpty():
                                continue
                            xy = punto_real.asPoint()

                        
                        nuevos_vertices.append(
                            QgsPoint(
                                xy.x(),
                                xy.y(),
                                z_perfil
                            )
                        )

                    if len(nuevos_vertices) < 4:
                        continue

                    ring = QgsLineString(nuevos_vertices)

                    poly_3d = QgsPolygon()
                    poly_3d.setExteriorRing(ring)

                    geom_3d = QgsGeometry(poly_3d)

                    feat_3d = QgsFeature(out_layer.fields())
                    feat_3d.setGeometry(geom_3d)
                    feat_3d.setAttributes(feat.attributes())

                    prov.addFeature(feat_3d)

                    total_3d += 1

            out_layer.updateExtents()

            for lyr in QgsProject.instance().mapLayers().values():
                if lyr.name() == "perfil_geologico3D":
                    QgsProject.instance().removeMapLayer(lyr.id())

            QgsProject.instance().addMapLayer(out_layer)


            if not multi:
                raise Exception("No fue posible leer la geometría multipolígono.")

            primer_anillo = multi[0][0]

            nuevos_vertices = []

            for pt in primer_anillo:

                x_perfil = pt.x()
                z_perfil = pt.y()

                punto_real = sec_geom.interpolate(x_perfil)

                if punto_real is None or punto_real.isEmpty():
                    continue

                xy = punto_real.asPoint()

                nuevos_vertices.append(
                    QgsPoint(
                        xy.x(),
                        xy.y(),
                        z_perfil
                    )
                )


            if len(nuevos_vertices) < 4:
                raise Exception(
                    "No hay suficientes vértices para construir un polígono."
                )
            

            # GUARDAR PERFIL GEOLÓGICO 3D
            
            opciones = QgsVectorFileWriter.SaveVectorOptions()
            opciones.fileEncoding = "UTF-8"

            extension = os.path.splitext(salida_perfil_3d)[1].lower()

            if extension == ".shp":
                opciones.driverName = "ESRI Shapefile"

            elif extension == ".gpkg":
                opciones.driverName = "GPKG"
                opciones.layerName = os.path.splitext(
                    os.path.basename(salida_perfil_3d)
                )[0]

            else:
                raise Exception(
                    "La salida debe tener extensión .shp o .gpkg."
                )

            resultado = QgsVectorFileWriter.writeAsVectorFormatV3(
                out_layer,
                salida_perfil_3d,
                QgsProject.instance().transformContext(),
                opciones
            )

            if resultado[0] != QgsVectorFileWriter.NoError:
                raise Exception(
                    f"No fue posible guardar el perfil geológico 3D.\n"
                    f"Error: {resultado[1]}"
                )        


            # Después cargamos la capa guardada:

            nombre_capa = os.path.splitext(
                os.path.basename(salida_perfil_3d)
            )[0]

            perfil_3d_guardado = QgsVectorLayer(
                salida_perfil_3d,
                nombre_capa,
                "ogr"
            )

            if not perfil_3d_guardado.isValid():
                raise Exception(
                    "El archivo fue generado, pero no pudo cargarse en QGIS."
                )

            QgsProject.instance().addMapLayer(perfil_3d_guardado)

        # Quitamos la capa temporal:

            if out_layer.id() in QgsProject.instance().mapLayers():
                QgsProject.instance().removeMapLayer(out_layer.id())


            self.mostrar_ayuda(
                "Perfil geológico 3D",
                f"Perfil geológico 3D generado correctamente.<br>"
                f"Polígonos creados: <b>{total_3d}</b><br>"
                f"Salida: <b>{salida_perfil_3d}</b>"
            )

            self.accept()

        except Exception as e:
            self.mostrar_ayuda(
                "Error",
                str(e)
            )