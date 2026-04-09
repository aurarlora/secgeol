import os
import tempfile
from datetime import datetime
from .secgeol_dialog import SecGeolDialog

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import ( 
                        QgsWkbTypes,
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


    # --------------------------------------------------------------
    # Devuelve una única feature válida de la sección del layer.
    # Si no cumple la regla, muestra ayuda y regresa None.
    # --------------------------------------------------------------

    def _set_help(self, texto):
        if self.dlg and hasattr(self.dlg, "textBrowserHelp"):
            self.dlg.textBrowserHelp.setPlainText(texto)


    def obtener_feature_seccion(self, sec_layer, has_drawn=False):

        if has_drawn:
            return None  # la sección dibujada se resolverá aparte

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

        if seleccionadas == 1:
            feat = next(sec_layer.getSelectedFeatures(), None)
            if feat is None:
                self._set_help("No fue posible recuperar la sección seleccionada.")
                return None
            return feat

        if total == 1:
            feat = next(sec_layer.getFeatures(), None)
            if feat is None:
                self._set_help("No fue posible recuperar la sección.")
                return None
            return feat

        self._set_help(
            "La capa contiene más de una sección. "
            "Seleccione una sola línea para continuar."
        )
        return None


    # -----------------------------------
    # EJECUTAR
    # -----------------------------------
    def ejecutar(self):
        # DEM
        dem_layer = self.dlg.MapLayerDEM.currentLayer()

        # Sección
        sec_layer = self.dlg.MapLayerSec.currentLayer()
        has_drawn = self.dlg.drawn_section_feature is not None
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
            
        feat_sec = self.obtener_feature_seccion(sec_layer, has_drawn=has_drawn)
        if sec_layer is not None and not has_drawn and feat_sec is None:
            return

        # -------------------------
        # INFORMACIÓN DE PRUEBA
        # -------------------------

        section_source = sec_layer.name() if sec_layer is not None else "Drawn section"

        resumen = [
            f"DEM: {dem_layer.name()}",
            f"Section: {section_source}",
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
            self.dlg.generar_perfil()

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
            print(f"Error en SecGeol: {e}")

        