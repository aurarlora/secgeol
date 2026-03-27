# SecGeol

**SecGeol** is a QGIS plugin for generating topographic profiles from a Digital Elevation Model (DEM) along a selected section line, providing a base for geological interpretation and cross-section drafting.

## Current status

This repository contains the first public development version of the plugin.  
The project is under active development and will continue evolving through open commits, documented changes, and future releases.

## Main features

- Selection of a DEM layer from the current QGIS project
- Selection of a section line layer from the current QGIS project
- Option to reverse section direction
- Optional geology layer input
- Optional structural layer input
- Optional box size parameter
- Optional axis creation
- Output file definition
- Context-sensitive help panel inside the plugin interface

## Requirements

- QGIS with Qt6-compatible plugin support
- Input layers loaded in the current QGIS project
- Projected CRS recommended
- Consistent CRS across all input layers

## Repository structure

```text
secgeol/
├── __init__.py
├── metadata.txt
├── secgeol.py
├── secgeol_dialog.py
├── secGeol.ui
├── icon.png
└── perfil_ejemplo.png
