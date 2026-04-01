import os
import tempfile
from datetime import datetime

from qgis.core import (
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsProject,
    QgsWkbTypes
)

from .fields import (
    fields_section_internal,
    fields_profile_points,
    fields_draw_lines
)


class WorkspaceManager:
    def __init__(self):
        self.gpkg_path = None

    def create_workspace_path(self):
        base_tmp = tempfile.gettempdir()
        secgeol_dir = os.path.join(base_tmp, "secgeol_workspace")
        os.makedirs(secgeol_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.gpkg_path = os.path.join(secgeol_dir, f"secgeol_{timestamp}.gpkg")
        return self.gpkg_path

    def create_layer(self, gpkg_path, layer_name, geometry_type, crs_authid, fields):
        uri = f"{QgsWkbTypes.displayString(geometry_type)}?crs={crs_authid}"
        mem_layer = QgsVectorLayer(uri, layer_name, "memory")
        provider = mem_layer.dataProvider()
        provider.addAttributes(fields)
        mem_layer.updateFields()

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer_name

        if os.path.exists(gpkg_path):
            options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
        else:
            options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

        writer_result = QgsVectorFileWriter.writeAsVectorFormatV3(
            mem_layer,
            gpkg_path,
            QgsProject.instance().transformContext(),
            options
        )

        print(f"Resultado al crear capa {layer_name}: {writer_result}")

        result = writer_result[0]
        error_message = writer_result[1] if len(writer_result) > 1 else ""
        

        if result != QgsVectorFileWriter.NoError:
            raise Exception(f"Error al crear capa '{layer_name}': {error_message}")



    def create_base_geopackage(self, crs_authid):
        gpkg_path = self.create_workspace_path()
        self.create_layer(
            gpkg_path, "sec_draw_lines", QgsWkbTypes.LineString, crs_authid, fields_draw_lines()
        )

        return gpkg_path