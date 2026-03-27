# -*- coding: utf-8 -*-
def classFactory(iface):
    from .secgeol import SecGeol
    return SecGeol(iface)