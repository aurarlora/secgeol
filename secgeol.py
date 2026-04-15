import os
import tempfile
from datetime import datetime
from .secgeol_dialog import SecGeolDialog

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import ( 
                        QgsWkbTypes,
                        QgsGeometry
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
            self.dlg = SecGeolDialog(self.iface)
            self.dlg.MapLayerDEM.layerChanged.connect(self.dlg.actualizar_info_dem)
            self.dlg.MapLayerSec.layerChanged.connect(self.dlg.actualizar_info_seccion)
            self.dlg.checkInvSec.toggled.connect(self.dlg.actualizar_info_seccion)

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

        # -------------------------
        # Validación geométrica del registro
        # -------------------------
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


    
    #-------------------------------------------------------------------------
    # Devuelve la geometría base de la sección: dibujada por el usuario, o tomada del layer/selección
    #-------------------------------------------------------------------------

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




    # --------------------------------------------------------------
    # Devuelve la geometría efectiva de la sección. Si checkInvSec está activado, la invierte.
    # --------------------------------------------------------------

    def obtener_geometria_seccion(self, sec_layer, has_drawn=False):
        geom = self.obtener_geometria_seccion_base(sec_layer, has_drawn)
        if geom is None:
            return None

        return geom


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
            
        feat_sec = None
        if sec_layer is not None and not has_drawn:
            feat_sec = self.obtener_feature_seccion(sec_layer, has_drawn=False)
            if feat_sec is None:
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
            self.dlg.generar_perfil(
            feat_sec=feat_sec,
            has_drawn=has_drawn,
            invertida=inv_sec
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
            print(f"Error en SecGeol: {e}")

        