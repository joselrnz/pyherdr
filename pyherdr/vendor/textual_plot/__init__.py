"""Vendored copy of ``textual-plot`` used for PyHerdr performance charts.

Source: https://github.com/davidfokkema/textual-plot
License: MIT, preserved in ``LICENSE`` beside this package.
"""

from pyherdr.vendor.textual_plot.axis_formatter import (
    AxisFormatter,
    DurationFormatter,
    NumericAxisFormatter,
)
from pyherdr.vendor.textual_plot.plot_widget import HiResMode, LegendLocation, PlotWidget

__all__ = [
    "AxisFormatter",
    "DurationFormatter",
    "HiResMode",
    "LegendLocation",
    "NumericAxisFormatter",
    "PlotWidget",
]
