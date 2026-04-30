import os
import tempfile
from datetime import datetime
from .secgeol_dialog import SecGeolDialog

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import ( 
                        QgsWkbTypes,
                        Qgis, QgsGeometry
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
            self.tr("Dibuja la sección sobre el mapa: haz clic para iniciar y clic derecho para finalizar.")
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
        segmentos_geo = []
        # Geologia
        

        # DEM
        dem_layer = self.dlg.MapLayerDEM.currentLayer()

        # Sección
        sec_layer = self.dlg.MapLayerSec.currentLayer()
        has_drawn = self.dlg.drawn_section_feature is not None
        inv_sec = self.dlg.checkInvSec.isChecked()

        # Geología
        
        geo_layer = self.dlg.MapLayerGeo.currentLayer()
        campo_geo = self.dlg.FieldClasGeo.currentField()

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
        
        #------- Si no es un DEM  con elevación   -----

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


        dem_crs = dem_layer.crs()

        if not dem_crs.isValid():
            self.iface.messageBar().pushWarning(
                self.tr("SecGeol"),
                self.tr("The DEM CRS is not valid.")
            )
            self._set_help("El sistema de referencia del DEM no es válido.")
            return

        if dem_crs.mapUnits() != Qgis.DistanceUnit.Meters:
            self.iface.messageBar().pushWarning(
                self.tr("SecGeol"),
                self.tr("The DEM must use metric units.")
            )
            self._set_help(
                "El modelo digital de elevación debe estar en un sistema de referencia "
                "proyectado con unidades en metros."
            )
            return

        if dem_layer.bandCount() != 1:
            self.iface.messageBar().pushWarning(
                self.tr("SecGeol"),
                self.tr("The DEM must be a single-band raster.")
            )
            self._set_help(
                "El raster seleccionado no parece corresponder a un modelo digital de elevación. "
                "Es posible que la capa sea una imagen y no contenga elevación del terreno."
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

        #---------------------- Términa validación layer


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
            

        #--------------------- Validación geología


        if not campo_geo:
            campo_geo = None

        

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

        
        try:
            self.dlg.generar_perfil(
                feat_sec=feat_sec,
                has_drawn=has_drawn,
                invertida=inv_sec,
                segmentos_geo=segmentos_geo
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

      

        