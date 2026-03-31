from qgis.core import QgsFields, QgsField
from qgis.PyQt.QtCore import QVariant


def fields_section_internal():
    fields = QgsFields()
    fields.append(QgsField("sec_id", QVariant.Int))
    fields.append(QgsField("origen", QVariant.String, len=20))
    fields.append(QgsField("invertida", QVariant.Int))
    return fields


def fields_profile_points():
    fields = QgsFields()
    fields.append(QgsField("pt_id", QVariant.Int))
    fields.append(QgsField("dist_m", QVariant.Double))
    fields.append(QgsField("elev", QVariant.Double))
    fields.append(QgsField("x", QVariant.Double))
    fields.append(QgsField("y", QVariant.Double))
    return fields


def fields_draw_lines():
    fields = QgsFields()
    fields.append(QgsField("line_id", QVariant.Int))
    fields.append(QgsField("clv_lito", QVariant.String, len=30))
    fields.append(QgsField("nombre", QVariant.String, len=80))
    return fields