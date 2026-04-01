import os
import tempfile
from datetime import datetime
from .secgeol_dialog import SecGeolDialog

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import ( QgsProject, 
                        QgsWkbTypes,
                        QgsVectorFileWriter,
                        QgsVectorLayer,
                        QgsFields,
                        QgsField,
                        QgsCoordinateReferenceSystem
                       )



class SecGeol:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.menu = self.tr("SecGeol")
        self.dlg = None

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
            self.dlg = SecGeolDialog()

            # Botones
            self.dlg.buttonBox.accepted.connect(self.ejecutar)
            self.dlg.buttonBox.rejected.connect(self.dlg.close)

            # Botón de dibujo
            self.dlg.btnDrawSec.clicked.connect(self.draw_section)

        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    # -----------------------------------
    # DIBUJAR SECCIÓN (placeholder)
    # -----------------------------------
    def draw_section(self):
        self.iface.messageBar().pushInfo(
            self.tr("SecGeol"),
            self.tr("Draw section tool not implemented yet.")
        )

    # -----------------------------------
    # EJECUTAR
    # -----------------------------------
    def ejecutar(self):

        # DEM
        dem_layer = self.dlg.MapLayerDEM.currentLayer()

        # Sección
        sec_layer = self.dlg.MapLayerSec.currentLayer()
        inv_sec = self.dlg.checkInvSec.isChecked()

        # Geología
        geo_layer = self.dlg.MapLayerGeo.currentLayer()

        # Estructuras
        est_layer = self.dlg.MapLayerEst.currentLayer()

        # Caja
        caja_m = self.dlg.doubleSpinBox.value()

        # Ejes
        crear_ejes = self.dlg.checkEjes.isChecked()

        # Salida
        salida = self.dlg.fileWidgetPerfil.filePath().strip()

        # -------------------------
        # VALIDACIONES
        # -------------------------

        if not dem_layer:
            self.iface.messageBar().pushWarning(
                self.tr("SecGeol"),
                self.tr("Select a DEM layer.")
            )
            return

        if dem_layer.type() != dem_layer.RasterLayer:
            self.iface.messageBar().pushWarning(
                self.tr("SecGeol"),
                self.tr("Selected DEM is not a raster layer.")
            )
            return

        if not sec_layer:
            self.iface.messageBar().pushWarning(
                self.tr("SecGeol"),
                self.tr("Select a section layer.")
            )
            return

        if QgsWkbTypes.geometryType(sec_layer.wkbType()) != QgsWkbTypes.LineGeometry:
            self.iface.messageBar().pushWarning(
                self.tr("SecGeol"),
                self.tr("Section must be a line layer.")
            )
            return

        """
        if not salida:
            self.iface.messageBar().pushWarning(
                self.tr("SecGeol"),
                self.tr("Select an output file. jeje")
            )
            return
        """

        # -------------------------
        # INFORMACIÓN DE PRUEBA
        # -------------------------

        resumen = [
            f"DEM: {dem_layer.name()}",
            f"Section: {sec_layer.name()}",
            f"Invert section: {inv_sec}",
            f"Geology: {geo_layer.name() if geo_layer else 'None'}",
            f"Structures: {est_layer.name() if est_layer else 'None'}",
            f"Box (m): {caja_m}",
            f"Create axes: {crear_ejes}",
            f"Output: {salida}",
        ]

        print("\n=== SecGeol PARAMETERS ===")

        
        for r in resumen:
            print(r)

        
        try:
            self.dlg.inicializar_workspace()
            layer = self.dlg.preparar_seccion_trabajo()
            self.dlg.generar_perfil()   # LLama a profile

            self.iface.messageBar().pushInfo(
                self.tr("SecGeol"),
                self.tr("Section workspace created successfully.")
            )

            self.dlg.accept()

        except Exception as e:
            self.iface.messageBar().pushWarning(
                self.tr("SecGeol"),
                str(e)
            )
            print(f"Error en SecGeol: {e}")

        