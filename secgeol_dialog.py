import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QSplitter
from qgis.PyQt.QtCore import QEvent
from qgis.PyQt.QtCore import QEvent, QUrl
from qgis.core import QgsMapLayerProxyModel, QgsProject

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


class SecGeolDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.section_manager = SectionManager()
        self.workspace_manager = WorkspaceManager()
        self.gpkg_path = None


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
            <h3>Geological Section Tool</h3>

            <p>
                This tool generates a topographic profile from a Digital Elevation Model (DEM)
                along a user-defined section line. The resulting profile can be used as a base
                for geological interpretation and cross-section construction.
            </p>

            <p>
                <b>Requirements:</b><br>
                - Load all input layers into the current QGIS project.<br>
                - Use a projected coordinate system (recommended: UTM).<br>
                - Ensure layers share the same CRS.
            </p>

            <p>
                <b>Tip:</b> Fields marked with an asterisk (*) are required.  
                Click on each control to view a short description.
            </p>
        </div>

        """
        self.help_tab_dos = """
        <div style="padding:10px; line-height:1.4; font-size:12px;">
            <h3>Tab 2</h3>
            <p>
                This tab will contain additional options related to geological interpretation
                and derived outputs.
            </p>
            <p>
                Click on each control to view a short description.
            </p>
        </div>
        """

        self.help_tab_tres = """
        <div style="padding:10px; line-height:1.4; font-size:12px;">
            <h3>Tab 3</h3>
            <p>
                This tab will contain complementary tools and final outputs.
            </p>
            <p>
                Click on each control to view a short description.
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
        # CONFIGURAR CAJA
        # -----------------------------
        self.doubleSpinBox.setMinimum(0.0)
        self.doubleSpinBox.setSingleStep(10.0)
        self.doubleSpinBox.setSuffix(" m")
        self.doubleSpinBox.setValue(100.0)

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
            "Select the Digital Elevation Model (DEM) layer."
        )
        self.MapLayerSec.setToolTip(
            "Select the section line layer."
        )
        self.btnDrawSec.setToolTip(
            "Draw a temporary section line on the map canvas."
        )
        self.checkInvSec.setToolTip(
            "Reverse the section direction."
        )
        self.MapLayerGeo.setToolTip(
            "Optional geology layer."
        )
        self.MapLayerEst.setToolTip(
            "Optional structural layer."
        )
        self.doubleSpinBox.setToolTip(
            "Optional box size in meters. Leave 0 to skip box creation."
        )
        self.checkEjes.setToolTip(
            "Create X and Y axes in the output profile."
        )
        self.fileWidgetPerfil.setToolTip(
            "Select the output file."
        )


    def actualizar_ayuda_tab(self):
        current_widget = self.tabWidget.currentWidget()

        if current_widget == self.uno:
            self.textBrowserHelp.setHtml(self.help_tab_uno)
        elif current_widget == self.dos:
            self.textBrowserHelp.setHtml(self.help_tab_dos)
        elif hasattr(self, "tres") and current_widget == self.tres:
            self.textBrowserHelp.setHtml(self.help_tab_tres)



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
                self.mostrar_ayuda(
                    "Digital Elevation Model (DEM)",
                    "Select a raster layer representing terrain elevation."
                )

            elif obj == self.MapLayerSec:
                self.mostrar_ayuda(
                    "Section Line",
                    "Select a line layer representing the geological section trace."
                )

            elif obj == self.btnDrawSec:
                self.mostrar_ayuda(
                    "Draw Section",
                    "Use this button to draw a temporary section line directly on the map canvas."
                )

            elif obj == self.checkInvSec:
                self.mostrar_ayuda(
                    "Invert Section",
                    "Reverse the section direction from end to start."
                )

            elif obj == self.MapLayerGeo:
                self.mostrar_ayuda(
                    "Geology Layer",
                    "Optional polygon layer used to intersect the section with geological units."
                )

            elif obj == self.MapLayerEst:
                self.mostrar_ayuda(
                    "Structural Layer",
                    "Optional line layer used to intersect the section with structural features."
                )

            elif obj == self.doubleSpinBox:
                self.mostrar_ayuda(
                    "Box Size",
                    "Optional box size in meters. Use 0 if no box should be created."
                )

            elif obj == self.checkEjes:
                self.mostrar_ayuda(
                    "Create Axes",
                    "Enable this option to create X and Y axes in the generated profile."
                )

            elif obj == self.fileWidgetPerfil:
                self.mostrar_ayuda(
                    "Output File",
                    "Select the output file where the generated profile will be stored."
                )
        elif event.type() == 11:  # Leave
            self.actualizar_ayuda_tab()
            
        return super().eventFilter(obj, event)
    
    # ---------------------------------
    # Conecta la función de la sección
    # ---------------------------------

    def preparar_seccion_trabajo(self):
        print("A: entrar a preparar_seccion_trabajo")

        invertida = self.checkInvSec.isChecked()
        source_layer = self.MapLayerSec.currentLayer()
        print(f"C: capa origen = {source_layer.name() if source_layer else 'None'}")

        if source_layer is None:
            raise Exception("No se ha seleccionado una capa de sección.")

        dem_layer = self.MapLayerDEM.currentLayer()
        if dem_layer is None:
            raise Exception("No se ha seleccionado un DEM.")

        target_crs = dem_layer.crs()

        temp_layer = self.section_manager.prepare_section_layer_from_user(
            source_layer,
            target_crs=target_crs,
            invertida=invertida
        )
        print("D: capa temporal creada")

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


    def generar_perfil(self):
        print("H: entrar a generar_perfil")

        dem_layer = self.MapLayerDEM.currentLayer()
        if dem_layer is None:
            raise Exception("No se ha seleccionado un DEM.")

        # Preparar sección temporal en el CRS del DEM
        section_layer = self.preparar_seccion_trabajo()
        print("I: sección temporal preparada")

        if section_layer is None or not section_layer.isValid():
            raise Exception("No fue posible preparar la sección de trabajo.")

        # Metros adicionales de caja
        caja_m = self.obtener_caja_m()
        print(f"J: caja_m = {caja_m}")

        perfil_layer = self.profile_manager.build_profile_box_layer(
            section_layer=section_layer,
            dem_layer=dem_layer,
            extra_depth=caja_m,
            layer_name="Perfil_topografico"
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

