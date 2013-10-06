PDN-Reader
==========

This module contains a simple PaintDotNet-Image reader.

Usage:
  document = pdn_reader(filename)
  
The returned PDNDocument has the fields
- width:  Width of the image
- height: Height of the image
- layers: a list of PDNBitmapLayer

PDNBitmapLayer:
- width:  Width of the layer
- height: Height of the layer
- layer_properties:
  - name: Name of the layer
  - opacity: 0..255
  - visible: Boolean
  - isBackground: Boolean
- surface: a PDNSurface object

PDNSurface:
- width:  Width of the surface
- height: Height of the surface
- stride:  # of bytes for one row
- data: string of data in BGRA-order 8bit
