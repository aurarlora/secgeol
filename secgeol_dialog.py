import os, re, unicodedata

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QVariant, QCoreApplication
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
                QCoreApplication.translate(
                    "SecGeol",
                    "Error finishing drawing: "
                )
                + f"{e}",
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
        self.help_tab_uno = self.tr(
            """
            <div style="padding:10px; line-height:1.4;">
                <h3>Geological Section Tool</h3>

                <p>
                    This module generates a topographic profile along a user-defined
                    section line using one of two elevation sources:
                    a <b>Digital Elevation Model (DEM)</b> or a
                    <b>contour line layer</b>.
                </p>

                <p>
                    The resulting profile can be used as the basis for geological
                    interpretation and the construction of geological sections.
                </p>

                <p>
                    <b>Requirements:</b><br>
                    - Load all input layers into the current QGIS project.<br>
                    - Use a projected coordinate reference system with metric units
                    (UTM is recommended).<br>
                    - Ensure that the input layers use compatible coordinate reference systems.
                </p>

                <p>
                    When contour lines are used as the elevation source, the profile
                    is limited to the segment between the first and last intersections.
                    The first intersection is assigned <b>X = 0</b>.
                </p>

                <p>
                    <b>Tip:</b> Fields marked with an asterisk (*) are required.<br>
                    Hover over each control to display additional information.
                </p>
            </div>
            """
        )
        self.help_tab_dos = self.tr(
            """
            <div style="padding:10px; line-height:1.4; font-size:12px;">
                <h3>Lines to Polygons</h3>

                <p>
                    This module converts the interpreted profile lines generated from
                    the topographic profile into closed polygon geometries.
                </p>

                <p>
                    The resulting polygons represent the geological interpretation
                    of the section in local profile coordinates and can be used as
                    input for the 3D reconstruction module.
                </p>

                <p>
                    Before running this step, adjust the profile lines according to
                    the geological interpretation and verify that the geometries
                    required to form the polygons are properly connected.
                </p>
            </div>
            """
        )

        self.help_tab_tres = self.tr(
            """
            <div style="padding:10px; line-height:1.4; font-size:12px;">
                <h3>3D Geological Reconstruction</h3>

                <p>
                    Select the interpreted geological profile generated in
                    <b>2. Lines to polygons</b> and the <b>guide section</b>
                    generated in <b>1. Section to profile</b>.
                </p>

                <p>
                    The guide section preserves the spatial reference used to generate
                    the topographic profile and allows the 2D geological interpretation
                    to be reconstructed in real-world coordinates.
                </p>

                <p>
                    The resulting output is a <b>3D geological profile</b> that can be
                    visualized and analyzed in three-dimensional environments.
                </p>
            </div>
            """
        )

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
            self.tr("Select a digital elevation model (DEM).")
        )

        self.MapLayerCurvas.setToolTip(
            self.tr("Select a contour line layer as the elevation source.")
        )

        self.FieldElevCurvas.setToolTip(
            self.tr("Select the numeric field containing contour elevations.")
        )

        self.checkGeo.setToolTip(
            self.tr("Include geological information in the profile.")
        )

        self.checkEst.setToolTip(
            self.tr("Include geological structures in the profile.")
        )

        self.MapLayerSec.setToolTip(
            self.tr("Select the layer containing the section line.")
        )

        self.btnDrawSec.setToolTip(
            self.tr("Draw a section line directly on the map.")
        )

        self.checkInvSec.setToolTip(
            self.tr("Reverse the section direction (start ↔ end).")
        )

        self.MapLayerGeo.setToolTip(
            self.tr("Select an optional geology layer to intersect the section.")
        )

        self.FieldClasGeo.setToolTip(
            self.tr("Select the field used to classify geological profile segments.")
        )

        self.MapLayerEst.setToolTip(
            self.tr("Select an optional structural layer to intersect the section.")
        )

        self.doubleSpinBox.setToolTip(
            self.tr(
                "Set the profile box depth in meters. "
                "The default value is 100 m."
            )
        )

        self.checkEjes.setToolTip(
            self.tr("Create X and Y axes for the generated profile.")
        )

        self.fileWidgetPerfil.setToolTip(
            self.tr("Select the output file for the topographic profile.")
        )

        self.MapLayerSecLin.setToolTip(
            self.tr("Select the topographic profile to be converted into polygons.")
        )

        self.fileWidgetPerfilGeo.setToolTip(
            self.tr("Select the output file for the 2D geological profile.")
        )

        self.MapLayerPerGeo.setToolTip(
            self.tr("Select the polygonal 2D geological profile to reconstruct in 3D.")
        )

        self.MapLayerSecGuia.setToolTip(
            self.tr("Select the guide section that provides the profile spatial reference.")
        )

        self.fileWidgetPerfilGeo3D.setToolTip(
            self.tr("Select the output file for the 3D geological profile.")
        )

        self.FieldDipEst.setToolTip(
            self.tr("Select the numeric field containing the dip of each structure.")
        )

        self.FieldAzimuthEst.setToolTip(
            self.tr("Select the numeric field containing the dip azimuth of each structure.")
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
                    "Select an elevation source: "
                    "a digital elevation model (DEM) "
                    "or a contour line layer."
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
                    "Select an elevation source: "
                    "a digital elevation model (DEM) "
                    "or a contour line layer."
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
                    self.tr("Contour lines"),
                    self.tr(
                        """
                        <p>
                            Select a vector <b>line layer</b> containing the contour
                            lines to be used as the elevation source.
                        </p>

                        <p>
                            SecGeol will calculate the intersections between the section
                            line and the contour lines to construct the topographic profile.
                        </p>

                        <p>
                            <b>Important:</b> the profile will be limited from the first
                            to the last intersected contour line. The first intersection
                            will be set to <b>X = 0</b>.
                        </p>
                        """
                    )
                )  
                

            elif obj == self.FieldElevCurvas:
                self.mostrar_ayuda(
                self.tr("Elevation field"),
                self.tr(
                    """
                    <p>
                        Select the numeric field containing the
                        <b>elevation</b> of each contour line.
                    </p>

                    <p>
                        SecGeol displays only the <b>numeric fields</b>
                        available in the selected layer.
                    </p>

                    <p>
                        Values must be stored as numbers, without units,
                        symbols, or additional text.
                    </p>
                    """
                )
            )

            elif obj == self.btnDrawSec:
                self.mostrar_ayuda(
                self.tr("Draw section"),
                self.tr(
                    """
                    <p>
                        Draw a <b>section line</b> directly on the map
                        as an alternative to selecting a section from
                        a vector layer.
                    </p>

                    <p>
                        Click on the map to define the line vertices
                        and use <b>right-click</b> to finish drawing.
                    </p>
                    """
                )
            )

            elif obj == self.checkInvSec:
                self.mostrar_ayuda(
                self.tr("Reverse section"),
                self.tr(
                    """
                    <p>
                        Reverses the direction of the section line and,
                        therefore, the orientation of the resulting profile.
                    </p>

                    <p>
                        Enable this option when you need to swap the
                        <b>start and end</b> of the section.
                    </p>
                    """
                )
            )

            elif obj == self.checkGeo:
                self.mostrar_ayuda(
                self.tr("Include geology"),
                self.tr(
                    """
                    <p>
                        Enable this option to include a polygonal
                        geological layer in the profile.
                    </p>

                    <p>
                        SecGeol will intersect the geological units with
                        the section line and represent them on the
                        topographic profile.
                    </p>

                    <p>
                        This option is <b>optional</b>.
                    </p>
                    """
                )
            )

            elif obj == self.checkEst:
                self.mostrar_ayuda(
                self.tr("Include structures"),
                self.tr(
                    """
                    <p>
                        Enable this option to include geological structures
                        represented by a vector line layer.
                    </p>

                    <p>
                        SecGeol will use the <b>dip</b> and
                        <b>dip azimuth</b> fields to represent structures
                        that intersect the section.
                    </p>

                    <p>
                        This option is <b>optional</b>.
                    </p>
                    """
                )
            )

            elif obj == self.MapLayerGeo:
                self.mostrar_ayuda(
                self.tr("Geology layer"),
                self.tr(
                    """
                    <p>
                        Select a vector <b>polygon layer</b> containing
                        the geological units crossed by the section line.
                    </p>

                    <p>
                        SecGeol will intersect this layer with the section
                        to represent the distribution of geological units
                        on the topographic profile.
                    </p>

                    <p>
                        This input is <b>optional</b>.
                    </p>
                    """
                )
            )

            elif obj == self.FieldClasGeo:
                self.mostrar_ayuda(
                self.tr("Geological classification field"),
                self.tr(
                    """
                    <p>
                        Select the attribute field that identifies the
                        <b>geological units</b>.
                    </p>

                    <p>
                        Values from this field will be transferred to the
                        profile and stored in the <b>valor_geo</b> attribute.
                    </p>
                    """
                )
            )
            

            elif obj == self.MapLayerEst:
                self.mostrar_ayuda(
                self.tr("Structural layer"),
                self.tr(
                    """
                    <p>
                        Select a vector line layer containing the geological
                        structures that intersect the section.
                    </p>

                    <p>
                        This input is <b>optional</b>.
                    </p>
                    """
                )
            )

            elif obj == self.doubleSpinBox:
                self.mostrar_ayuda(
                self.tr("Profile box depth"),
                self.tr(
                    """
                    <p>
                        Defines, in meters, the additional depth represented
                        below the minimum elevation of the topographic profile.
                    </p>

                    <p>
                        Allowed values range from <b>1 to 10,000 m</b>.
                        The default value is <b>100 m</b>.
                    </p>

                    <p>
                        For example, a value of <b>500</b> extends the profile
                        box <b>500 m</b> below the minimum profile elevation.
                    </p>
                    """
                )
            )

            elif obj == self.checkEjes:
                self.mostrar_ayuda(
                self.tr("Create axes"),
                self.tr(
                    """
                    <p>
                        Enable this option to generate the horizontal and
                        vertical axes associated with the profile.
                    </p>

                    <p>
                        The horizontal axis represents the
                        <b>distance along the section</b>, and the vertical
                        axis represents <b>elevation</b>.
                    </p>
                    """
                )
            )


            elif obj == self.fileWidgetPerfil:
                self.mostrar_ayuda(
                self.tr("Output file"),
                self.tr(
                    """
                    <p>
                        Select the location and file name where the
                        topographic profile will be saved.
                    </p>

                    <p>
                        SecGeol will also generate the <b>guide section</b>,
                        which preserves the spatial reference required for
                        the 3D reconstruction.
                    </p>
                    """
                )
            )

            #Estructuras

            elif obj == self.FieldDipEst:
                self.mostrar_ayuda(
                self.tr("Dip field"),
                self.tr(
                    """
                    <p>
                        Select the numeric field containing the
                        <b>dip</b> of each structure.
                    </p>

                    <p>
                        Values must be stored as <b>numeric values</b>
                        between <b>0 and 90</b> degrees, without including
                        the degree symbol (°).
                    </p>

                    <p>
                        Records with values outside this range will not be
                        represented in the profile.
                    </p>
                    """
                )
            )

            elif obj == self.FieldAzimuthEst:
                self.mostrar_ayuda(
                self.tr("Dip azimuth field"),
                self.tr(
                    """
                    <p>
                        Select the numeric field containing the
                        <b>dip azimuth</b> of each structure.
                    </p>

                    <p>
                        Values must be stored as <b>numeric values</b>
                        between <b>0 and 360</b> degrees, without including
                        the degree symbol (°).
                    </p>

                    <p>
                        Records with a value of <b>-1</b> or outside this
                        range will not be represented in the profile.
                    </p>
                    """
                )
            )

            elif obj == self.MapLayerSecGuia:
                self.mostrar_ayuda(
                self.tr("Guide section"),
                self.tr(
                    """
                    <p>
                        Select the <b>guide section</b> generated in
                        <b>1. Section to profile</b>.
                    </p>

                    <p>
                        This layer preserves the spatial reference used to
                        generate the profile and allows the geological
                        interpretation to be reconstructed in its
                        real-world coordinates.
                    </p>

                    <p>
                        When the profile is generated from contour lines,
                        the guide section corresponds only to the segment
                        between the first and last intersections.
                    </p>
                    """
                )
            )

            elif obj == self.MapLayerPerGeo:
                self.mostrar_ayuda(
                self.tr("2D geological profile"),
                self.tr(
                    """
                    <p>
                        Select the polygon layer generated in
                        <b>2. Lines to polygons</b>.
                    </p>

                    <p>
                        This layer contains the geological interpretation
                        of the profile in local coordinates, where the
                        X-axis represents the distance along the section.
                    </p>

                    <p>
                        SecGeol will use this geometry together with the
                        guide section to reconstruct the profile in
                        real-world coordinates.
                    </p>
                    """
                )
            )
           

            elif obj == self.fileWidgetPerfilGeo:
                self.mostrar_ayuda(
                self.tr("Geological profile output"),
                self.tr(
                    """
                    <p>
                        Select the location and file name where the
                        <b>2D polygonal geological profile</b> will be saved.
                    </p>

                    <p>
                        This layer can later be used in
                        <b>3. 2D profile to 3D</b>.
                    </p>
                    """
                )
            )

            elif obj == self.fileWidgetPerfilGeo3D:
                self.mostrar_ayuda(
                self.tr("3D geological profile output"),
                self.tr(
                    """
                    <p>
                        Select the location and file name where the
                        geological profile reconstructed in
                        <b>real-world coordinates</b> will be saved.
                    </p>

                    <p>
                        The output preserves the three-dimensional geometry
                        required for visualization and analysis in 3D
                        environments.
                    </p>
                    """
                )
            )

            elif obj == self.MapLayerSecLin:
                self.mostrar_ayuda(
                self.tr("Topographic profile"),
                self.tr(
                    """
                    <p>
                        Select the <b>Perfil_topografico</b> layer generated
                        in <b>1. Section to profile</b>.
                    </p>

                    <p>
                        This layer contains the terrain line and the elements
                        associated with the profile. It can be edited during
                        geological interpretation before the lines are
                        converted into polygons.
                    </p>

                    <p>
                        <b>2. Lines to polygons</b> will use these geometries
                        to construct the polygonal geological profile.
                    </p>
                    """
                )
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
                    "Select an elevation source: "
                    "a digital elevation model (DEM) "
                    "or a contour line layer."
                )
            )

        # Caso 1: el usuario dibujó una sección
        if has_drawn:
            if self.drawn_section_feature is None:
                raise Exception(
                    self.tr("The drawn section was not found.")
                )
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
                raise Exception(
                    self.tr("The section layer was not found.")
                )
            source_crs = source_layer.crs()
            temp_layer = self.section_manager.prepare_section_layer_from_feature(
                source_feature=feat_sec,
                source_crs=source_crs,
                target_crs=target_crs,
                invertida=invertida
            )
         
        else:
            raise Exception(
                    self.tr("No valid section was found to prepare.")
                )

        if temp_layer is None or not temp_layer.isValid():
            raise Exception(
                self.tr("Could not prepare the working section.")
            )
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
                    "Select an elevation source: "
                    "a digital elevation model (DEM) "
                    "or a contour line layer."
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
                    "Select an elevation source: "
                    "a digital elevation model (DEM) "
                    "or a contour line layer."
                )
            )

        if section_layer is None:
            section_layer = self.preparar_seccion_trabajo(
                feat_sec=feat_sec,
                has_drawn=has_drawn,
                invertida=invertida
            )

        if section_layer is None or not section_layer.isValid():
            raise Exception(
                self.tr("Could not prepare the working section.")
            )
        caja_m = self.obtener_caja_m()
        section_geom = self.section_manager.obtener_geometria_seccion_efectiva(section_layer)

        if section_geom is None:
            raise Exception(
                self.tr("Could not obtain the effective section geometry.")
            )
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
            self.tr("Digital elevation model"),
            self.tr(
                """
                <p>
                    No <b>digital elevation model (DEM)</b> has been selected.
                </p>

                <p>
                    Select a valid raster layer to continue.
                </p>
                """
            )
        )
            return

        if dem_layer.type() != dem_layer.RasterLayer:
            self.mostrar_ayuda(
            self.tr("Invalid digital elevation model"),
            self.tr(
                """
                <p>
                    The selected layer is not a <b>raster layer</b>.
                </p>

                <p>
                    Select a digital elevation model in raster format.
                </p>
                """
            )
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
                    + self.tr("<b>Status: Compatible with SecGeol.</b>")
                    + "</p>"
                )

            else:
                detalles = []

                if not dem_crs.isValid():
                    detalles.append(
                        self.tr("The CRS is not valid.")
                    )
                elif not es_metrico:
                    detalles.append(
                        self.tr("The CRS must use meters as its unit.")
                    )

                if not una_banda:
                    detalles.append(
                        self.tr("The raster must contain a single band.")
                    )
                elif band_type_name not in tipos_validos:
                    detalles.append(
                        self.tr("The data type is not suitable")
                        + f" ({band_type_name})."
                    )

                lista_detalles = "".join(
                    f"<li>{detalle}</li>"
                    for detalle in detalles
                )

                estado = (
                    "<div style='color:red;'>"
                    + self.tr("<p><b>Status: Not compatible with SecGeol.</b></p>")
                    + self.tr("<p>Check the following characteristics:</p>")
                    + f"<ul>{lista_detalles}</ul>"
                    + "</div>"
                )
                

            self.mostrar_ayuda(
            self.tr("Digital elevation model"),
            f"""
            <p>
                <b>{self.tr("Selected DEM:")}</b> {dem_layer.name()}<br>
                <b>CRS:</b> {crs_info}<br>
                <b>{self.tr("Pixel size:")}</b> {pixel_x:.3f} × {pixel_y:.3f}<br>
                <b>{self.tr("Bands:")}</b> {dem_layer.bandCount()}<br>
                <b>{self.tr("Data type:")}</b> {band_type_name}
            </p>

            {estado}
            """
        )

        except Exception as e:
            self.mostrar_ayuda(
                self.tr("Error reading DEM"),
                f"""
                <p>
                    {self.tr(
                        "Could not correctly read the properties "
                        "of the selected layer."
                    )}
                </p>

                <p>
                    <b>{self.tr("Details:")}</b> {e}
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
                    self.tr("Invalid section"),
                    self.tr(
                        """
                        <p>
                            <span style="color:red; font-size:18px;">⚠</span>
                            <b>The drawn section does not contain a valid geometry.</b>
                        </p>

                        <p>
                            Draw the section line again to continue.
                        </p>
                        """
                    )
                )
                return

            longitud = geom.length()

            estado_invertida = self.tr("Yes") if invertida else self.tr("No")

            self.mostrar_ayuda(
                self.tr("Active section"),
                f"""
                <p>
                    <b>{self.tr("Source:")}</b> {self.tr("Drawn by the user")}<br>
                    <b>{self.tr("Length:")}</b> {longitud:.2f} m<br>
                    <b>{self.tr("Reversed orientation:")}</b> {estado_invertida}
                </p>
                """
            )
            return

        if sec_layer is None:
            self.mostrar_ayuda(
                self.tr("Section"),
                self.tr(
                    """
                    <p>
                        Select a <b>section layer</b> or draw a line
                        directly on the map.
                    </p>
                    """
                )
            )
            return

        if QgsWkbTypes.geometryType(sec_layer.wkbType()) != QgsWkbTypes.LineGeometry:
            self.mostrar_ayuda(
                self.tr("Invalid section"),
                self.tr(
                    """
                    <p>
                        <span style="color:red; font-size:18px;">⚠</span>
                        <b>The selected layer is not a line layer.</b>
                    </p>

                    <p>
                        Select a vector line layer to continue.
                    </p>
                    """
                )
            )
            return

        total = sec_layer.featureCount()
        seleccionadas = sec_layer.selectedFeatureCount()

        if total == 0:
            self.mostrar_ayuda(
                self.tr("Invalid section"),
                self.tr(
                    """
                    <p>
                        <span style="color:red; font-size:18px;">⚠</span>
                        <b>The selected layer contains no features.</b>
                    </p>
                    """
                )
            )
            return

        if seleccionadas > 1:
            self.mostrar_ayuda(
                self.tr("Section required"),
                self.tr(
                    """
                    <p>
                        <span style="color:red; font-size:18px;">⚠</span>
                        <b>More than one section is selected.</b>
                    </p>

                    <p>
                        Leave <b>only one line</b> selected to continue.
                    </p>
                    """
                )
            )
            return

        if seleccionadas == 1:
            feat = next(sec_layer.getSelectedFeatures(), None)
        elif total == 1:
            feat = next(sec_layer.getFeatures(), None)
        else:
            self.mostrar_ayuda(
                self.tr("Section required"),
                self.tr(
                    """
                    <p style="color:#b00020;">
                        <span style="color:red; font-size:18px;">⚠</span>
                        <b>The layer contains more than one section.</b>
                    </p>

                    <p>
                        Select <b>only one line</b> to continue.
                    </p>
                    """
                )
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
                self.tr("Invalid section"),
                self.tr(
                    """
                    <p>
                        <span style="color:red; font-size:18px;">⚠</span>
                        <b>The section geometry is empty.</b>
                    </p>
                    """
                )
            )
            return
        
        if geom.isMultipart():
            partes = geom.asMultiPolyline()

            if not partes:
                self.mostrar_ayuda(
                    self.tr("Invalid section"),
                    self.tr(
                        """
                        <p>
                            Could not interpret the geometry of the selected section.
                        </p>

                        <p>
                            Select a <b>valid line geometry</b> to continue.
                        </p>
                        """
                    )
                )
                return

            if len(partes) > 1:
                self.mostrar_ayuda(
                    self.tr("Invalid section"),
                    self.tr(
                        """
                        <p>
                            The selected feature contains <b>more than one independent line</b>.
                        </p>

                        <p>
                            SecGeol requires <b>only one line per feature</b>.
                            The line may contain multiple vertices and changes in direction.
                        </p>
                        """
                    )
                )
                return

        

        longitud = geom.length()
        estado_invertida = self.tr("Yes") if invertida else self.tr("No")
        self.mostrar_ayuda(
            self.tr("Active section"),
            f"""
            <p>
                <b>{self.tr("Layer:")}</b> {sec_layer.name()}<br>
                <b>{self.tr("Length:")}</b> {longitud:.2f} m<br>
                <b>{self.tr("Reversed orientation:")}</b> {estado_invertida}
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
                self.tr("No geology"),
                self.tr(
                    """
                    <p>
                        Including geological information is <b>optional</b>.
                    </p>

                    <p>
                        Enable this option to select a polygon layer
                        and represent the geological units that intersect
                        the section line.
                    </p>
                    """
                )
            )
        else:
            self.actualizar_info_geologia()

    # Si existe Geologia
    
    def actualizar_info_geologia(self):
        geo_layer = self.MapLayerGeo.currentLayer()

        if geo_layer is None:
            self.FieldClasGeo.setLayer(None)
            self.mostrar_ayuda(
                self.tr("Geology layer"),
                self.tr(
                    """
                    <p>
                        The geology option is <b>enabled</b>.
                    </p>

                    <p>
                        Select a <b>polygon vector layer</b>
                        containing the geological units.
                    </p>

                    <p>
                        After selecting the layer, SecGeol will enable its
                        attribute fields so you can select the geological
                        classification field.
                    </p>
                    """
                )
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
            mensaje_campo = self.tr(
                """
                <p>
                    The geology layer does not contain attribute fields.
                    SecGeol will continue using only <b>id_lito</b>
                    as the identifier for the geological units.
                </p>
                """
            )
        else:
            mensaje_campo = self.tr(
                """
                <p>
                    Select the attribute field that identifies the
                    <b>geological units</b>.
                </p>

                <p>
                    SecGeol will also generate the <b>id_lito</b>
                    field as an internal identifier.
                </p>
                """
            )

        self.mostrar_ayuda(
            self.tr("Geology layer"),
            f"""
            <p>
                <b>{self.tr("Selected layer:")}</b> {geo_layer.name()}<br>
                <b>CRS:</b> {crs_info}<br>
                <b>{self.tr("Available fields:")}</b> {total_campos}
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
                self.tr("No structures"),
                self.tr(
                    """
                    <p>
                        Including structural information is <b>optional</b>.
                    </p>

                    <p>
                        Enable this option to select a line layer
                        and represent the geological structures that intersect
                        the section line.
                    </p>
                    """
                )
            )
        else:
            self.actualizar_info_estructuras()


    def actualizar_info_estructuras(self):
        est_layer = self.MapLayerEst.currentLayer()

        if est_layer is None:
            self.FieldDipEst.setLayer(None)
            self.FieldAzimuthEst.setLayer(None)
            self.mostrar_ayuda(
                self.tr("Structural layer"),
                self.tr(
                    """
                    <p>
                        The structural option is <b>enabled</b>.
                    </p>

                    <p>
                        Select a <b>line vector layer</b>
                        containing the geological structures.
                    </p>

                    <p>
                        After selecting the layer, SecGeol will enable the
                        available numeric fields to define the <b>dip</b>
                        and <b>dip azimuth</b>.
                    </p>
                    """
                )
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
            self.tr("Structural layer"),
            f"""
            <p>
                <b>{self.tr("Selected layer:")}</b> {est_layer.name()}<br>
                <b>CRS:</b> {crs_info}<br>
            </p>

            <p>
                {self.tr(
                    "SecGeol displays only the available <b>numeric fields</b> "
                    "for selecting the <b>dip</b> and <b>dip azimuth</b>."
                )}
            </p>

            <p>
                {self.tr(
                    "These values will be used to represent the structures "
                    "that intersect the section line on the profile."
                )}
            </p>
            """
        )

    #---------------------Tab 2---------------------------------------    
    def ejecutar_lineas_a_poligonos(self):
        try:
            line_layer = self.MapLayerSecLin.currentLayer()
            salida_perfil_geo = self.fileWidgetPerfilGeo.filePath().strip()

            if line_layer is None:
                raise Exception(
                    self.tr("Select a profile line layer.")
                )

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
                self.tr("Lines to polygons"),
                self.tr(
                    "The temporary <b>perfil_geologico</b> layer was generated."
                )
                + (
                    self.tr(" The <b>ejes</b> layer was also generated.")
                    if ejes_layer is not None
                    else ""
                )
            )
            
            self.accept()

        except Exception as e:
            QgsMessageLog.logMessage(
                QCoreApplication.translate(
                    "SecGeol",
                    "Error generating polygons/axes: "
                )
                + str(e),
                "SecGeol",
                Qgis.Critical
            )

            self.mostrar_ayuda(
                self.tr("Error"),
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
            raise Exception(
                self.tr("The geological profile layer was not generated.")
            )

        if not salida_perfil_geo:
            raise Exception(
                self.tr("Select an output path.")
            )

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
                self.tr(
                    "Could not save the geological profile: "
                )
                + f"{resultado_perfil[1]}"
            )

        perfil_guardado = QgsVectorLayer(
            ruta_perfil,
            os.path.splitext(os.path.basename(ruta_perfil))[0],
            "ogr"
        )

        if not perfil_guardado.isValid():
            raise Exception(
                self.tr(
                    "The geological profile was saved, but could not be loaded."
                )
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
                    self.tr(
                        "Could not save the axes layer: "
                    )
                    + f"{resultado_ejes[1]}"
                )

            ejes_guardada = QgsVectorLayer(
                ruta_ejes,
                os.path.splitext(os.path.basename(ruta_ejes))[0],
                "ogr"
            )

            if not ejes_guardada.isValid():
                raise Exception(
                    self.tr(
                        "The axes layer was saved, but could not be loaded."
                    )
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
            raise Exception(
                self.tr(
                    "There is no valid working section available to create the guide section."
                )
            )

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
                raise Exception(
                    self.tr("Select a polygon layer for the geological profile.")
                )

            sec_layer = self.MapLayerSecGuia.currentLayer()

            if sec_layer is None:
                raise Exception(
                    self.tr("Select the guide section layer.")
                )


            salida_perfil_3d  = self.fileWidgetPerfilGeo3D.filePath()

            if not salida_perfil_3d:
                raise Exception(
                    self.tr("Select an output path for the 3D geological profile.")
                )
            
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
                raise Exception(
                    self.tr("Could not read the multipolygon geometry.")
                )

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
                    self.tr(
                        "There are not enough vertices to construct a polygon."
                    )
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
                    self.tr(
                        "The output file must have a .shp or .gpkg extension."
                    )
                )

            resultado = QgsVectorFileWriter.writeAsVectorFormatV3(
                out_layer,
                salida_perfil_3d,
                QgsProject.instance().transformContext(),
                opciones
            )

            if resultado[0] != QgsVectorFileWriter.NoError:
                raise Exception(
                    self.tr(
                        "Could not save the 3D geological profile.\n"
                        "Error: "
                    )
                    + f"{resultado[1]}"
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
                    self.tr(
                        "The file was generated, but could not be loaded into QGIS."
                    )
                )

            QgsProject.instance().addMapLayer(perfil_3d_guardado)

        # Quitamos la capa temporal:

            if out_layer.id() in QgsProject.instance().mapLayers():
                QgsProject.instance().removeMapLayer(out_layer.id())


            self.mostrar_ayuda(
                self.tr("3D geological profile"),
                f"""
                {self.tr("3D geological profile generated successfully.")}<br>
                {self.tr("Polygons created:")} <b>{total_3d}</b><br>
                {self.tr("Output:")} <b>{salida_perfil_3d}</b>
                """
            )

            self.accept()

        except Exception as e:
            self.mostrar_ayuda(
                "Error",
                str(e)
            )