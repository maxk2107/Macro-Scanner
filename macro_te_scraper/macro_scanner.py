"""Graphical user interface for the MacroScanner desktop application.

This script provides a PyQt5-based UI that allows users to fetch macroeconomic
indicators from Trading Economics for multiple countries.  It offers two
functional modes:

1. **Full List:** Scrape data for all configured countries and display the
   results in a table.
2. **Compare:** Select two countries from drop‑down menus and display their
   indicators side by side for comparison.

The UI uses a white/grey/blue color palette.  Each indicator row includes
published date, next release (currently unavailable), expected value,
difference (current minus previous), and surprise (current minus expected).

Note: This script requires PyQt5 to be installed on the system.  Install it via
``pip install PyQt5`` before running.  The script reads configuration from
``config.yaml`` located in the project root, and relies on the scraping
functions defined in the ``macro_te_scraper`` package.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT))

import yaml
from typing import Dict, List, Optional

from PyQt5 import QtWidgets, QtCore, QtGui

# For trend sparklines
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure

from src.sources.te_scrape import TradingEconomicsScraper
from src.parsing.cleaners import compute_difference
from src.parsing.validators import validate
from src.utils.logger import setup_logger


class MacroScannerApp(QtWidgets.QMainWindow):
    """Main window for the MacroScanner application."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        # Load configuration
        base_dir = Path(__file__).resolve().parents[0]
        config_path = base_dir / "config.yaml"
        with config_path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        # Countries (assets) + display names
        # Default to the 8 currency blocs you specified: USD, EUR, GBP, JPY, AUD, CAD, NZD, CHF
        self.country_labels: Dict[str, str] = {
            "united-states": "USD — United States",
            "euro-area": "EUR — Euro Area",
            "united-kingdom": "GBP — United Kingdom",
            "japan": "JPY — Japan",
            "australia": "AUD — Australia",
            "canada": "CAD — Canada",
            "new-zealand": "NZD — New Zealand",
            "switzerland": "CHF — Switzerland",
        }

        cfg_countries = config.get("countries")
        if isinstance(cfg_countries, list) and cfg_countries:
            self.countries: List[str] = [str(c).lower() for c in cfg_countries]
        else:
            # If you want fewer, set `countries:` in config.yaml
            self.countries = list(self.country_labels.keys())
        # Indicator keys
        self.indicator_keys: List[str] = config.get("indicators", [])
        # Timeouts and rate limits
        self.timeout: int = int(config.get("timeout_seconds", 30))
        self.rate_limit: float = float(config.get("rate_limit_seconds", 2))
        # Set up logging
        self.logger = setup_logger(base_dir)
        # Holder for last fetched data
        self.last_data: List[Dict[str, Optional[float]]] = []
        # Build indicator map matching fetcher definition
        self.indicator_map: Dict[str, Dict[str, str]] = {
            "unemployment": {
                "name": "Unemployment",
                "row_label": "Unemployment Rate",
                "slug": "unemployment-rate",
            },
            "inflation_mom": {
                "name": "Inflation MoM",
                "row_label": "Inflation Rate MoM",
                "slug": "inflation-rate-mom",
            },
            "inflation_yoy": {
                "name": "Inflation YoY",
                "row_label": "Inflation Rate",
                "slug": "inflation-cpi",
            },
            "interest_rate": {
                "name": "Interest Rate",
                "row_label": "Interest Rate",
                "slug": "interest-rate",
            },
            "retail_sales_mom": {
                "name": "Retail Sales MoM",
                "row_label": "Retail Sales MoM",
                "slug": "retail-sales-mom",
            },
            "retail_sales_yoy": {
                "name": "Retail Sales YoY",
                "row_label": "Retail Sales YoY",
                "slug": "retail-sales-yoy",
            },
            "services_pmi": {
                "name": "Services PMI",
                "row_label": "Services PMI",
                "slug": "services-pmi",
            },
            "manufacturing_pmi": {
                "name": "Manufacturing PMI",
                "row_label": "Manufacturing PMI",
                "slug": "manufacturing-pmi",
            },
            "ppi": {
                "name": "PPI",
                "row_label": "Producer Price Inflation MoM",
                "slug": "producer-price-inflation-mom",
            },
            "gdp_growth_qoq": {
                "name": "GDP Growth QoQ",
                "row_label": "GDP Growth Rate",
                "slug": "gdp-growth",
            },
        }
        # Window settings
        self.setWindowTitle("MacroScanner")
        self.resize(1024, 768)
        # Load and set application icon from the bundled logo
        logo_path = Path(__file__).resolve().parents[0] / "assets" / "logo.png"
        if logo_path.exists():
            self.logo_pixmap = QtGui.QPixmap(str(logo_path))
            if not self.logo_pixmap.isNull():
                self.setWindowIcon(QtGui.QIcon(self.logo_pixmap))
        # Setup UI
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize widgets and layout."""
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        # Add logo at the top if available
        try:
            if hasattr(self, "logo_pixmap") and not self.logo_pixmap.isNull():
                logo_label = QtWidgets.QLabel()
                # Scale logo to fit nicely; maintain aspect ratio
                scaled = self.logo_pixmap.scaledToHeight(80, QtCore.Qt.SmoothTransformation)
                logo_label.setPixmap(scaled)
                logo_label.setAlignment(QtCore.Qt.AlignCenter)
                layout.addWidget(logo_label)
        except Exception:
            pass
        # Tab widget to switch modes
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs)
        # Full list tab
        self.full_tab = QtWidgets.QWidget()
        self._init_full_tab()
        self.tabs.addTab(self.full_tab, "Full List")
        # Compare tab
        self.compare_tab = QtWidgets.QWidget()
        self._init_compare_tab()
        self.tabs.addTab(self.compare_tab, "Compare")
        # Apply stylesheet for color palette
        self._apply_styles()

    def _apply_styles(self) -> None:
        """Apply a clean, high-contrast palette + widget styling."""
        style = """
        /* --- Base --- */
        QMainWindow { background-color: #F3F4F6; }
        QWidget { color: #111827; font-size: 13px; }
        QLabel { color: #111827; }

        /* --- Cards / group boxes --- */
        QGroupBox {
            background-color: #FFFFFF;
            border: 1px solid #D1D5DB;
            border-radius: 12px;
            margin-top: 10px;
            padding: 12px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
            font-weight: 600;
        }

        /* --- Tabs --- */
        QTabWidget::pane {
            border: 1px solid #D1D5DB;
            background: #FFFFFF;
            border-radius: 10px;
            padding: 0px;
        }
        QTabBar::tab {
            background: #E5E7EB;
            color: #111827;
            padding: 9px 16px;
            margin-right: 4px;
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            font-weight: 600;
        }
        QTabBar::tab:selected { background: #1976D2; color: #FFFFFF; }

        /* --- Inputs (Combo / LineEdit) --- */
        QComboBox, QLineEdit {
            background: #FFFFFF;
            color: #111827;
            border: 1px solid #D1D5DB;
            border-radius: 10px;
            padding: 7px 10px;
            min-height: 30px;
        }
        QComboBox:focus, QLineEdit:focus { border: 1px solid #1976D2; }

        /* Fix: dark, unreadable combo dropdown popup (macOS dark menu etc.) */
        QComboBox QAbstractItemView {
            background-color: #FFFFFF;
            color: #111827;
            border: 1px solid #D1D5DB;
            outline: 0;
            selection-background-color: #DBEAFE;
            selection-color: #111827;
            padding: 4px;
        }
        QComboBox QAbstractItemView::item { padding: 6px 10px; border-radius: 6px; }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 28px;
            border-left: 1px solid #D1D5DB;
        }

        /* --- Buttons --- */
        QPushButton {
            background-color: #1976D2;
            color: #FFFFFF;
            border: none;
            border-radius: 12px;
            padding: 9px 14px;
            font-weight: 700;
        }
        QPushButton:hover { background-color: #1565C0; }
        QPushButton:pressed { background-color: #0D47A1; }
        QPushButton:disabled { background-color: #9CA3AF; color: #F3F4F6; }

        /* --- Tables --- */
        QTableWidget {
            background-color: #FFFFFF;
            alternate-background-color: #F9FAFB;
            gridline-color: #E5E7EB;
            selection-background-color: #DBEAFE;
            selection-color: #111827;
            border: 1px solid #D1D5DB;
            border-radius: 12px;
        }
        QTableWidget::item { padding: 6px; }
        QHeaderView::section {
            background-color: #1976D2;
            color: #FFFFFF;
            padding: 8px 10px;
            border: none;
            font-weight: 700;
        }
        QTableCornerButton::section { background-color: #1976D2; border: none; }

        /* --- Checkboxes (Fix: tick boxes too white / low contrast) --- */
        QCheckBox { spacing: 10px; }
        QCheckBox::indicator {
            width: 18px;
            height: 18px;
            border-radius: 5px;
            border: 1px solid #9CA3AF;
            background: #FFFFFF;
        }
        QCheckBox::indicator:hover { border: 1px solid #1976D2; }
        QCheckBox::indicator:checked {
            border: 1px solid #1976D2;
            background: #1976D2;
        }

        /* --- Scrollbars (subtle) --- */
        QScrollBar:vertical {
            background: transparent;
            width: 10px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #D1D5DB;
            border-radius: 5px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover { background: #9CA3AF; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

        QScrollBar:horizontal {
            background: transparent;
            height: 10px;
            margin: 0px;
        }
        QScrollBar::handle:horizontal {
            background: #D1D5DB;
            border-radius: 5px;
            min-width: 30px;
        }
        QScrollBar::handle:horizontal:hover { background: #9CA3AF; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

        /* Splitter handle */
        QSplitter::handle { background: #E5E7EB; }
        """
        self.setStyleSheet(style)

    def _display_country(self, slug: str) -> str:
        """Return a user-friendly name for a country slug."""
        return self.country_labels.get(slug, slug.replace("-", " ").title())

    # --------------- Full List Tab ---------------
    def _init_full_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.full_tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        # Country selection panel
        selection_box = QtWidgets.QGroupBox("Select Countries (Assets)")
        sel_layout = QtWidgets.QVBoxLayout(selection_box)
        self.country_checkboxes = []
        for slug in self.countries:
            chk = QtWidgets.QCheckBox(self._display_country(slug))
            chk.setProperty("slug", slug)
            chk.setChecked(False)
            self.country_checkboxes.append(chk)
            sel_layout.addWidget(chk)
        layout.addWidget(selection_box)
        # Buttons panel
        btn_layout = QtWidgets.QHBoxLayout()
        self.fetch_selected_btn = QtWidgets.QPushButton("Fetch Selected")
        self.fetch_selected_btn.clicked.connect(self._on_fetch_selected)
        btn_layout.addWidget(self.fetch_selected_btn)
        self.export_btn = QtWidgets.QPushButton("Export CSV")
        self.export_btn.setDisabled(True)
        self.export_btn.clicked.connect(self._on_export)
        btn_layout.addWidget(self.export_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        # Table for full results
        self.full_table = QtWidgets.QTableWidget()
        layout.addWidget(self.full_table)
        # Set column headers
        headers = [
            "Country",
            "Indicator",
            "Current",
            "Previous",
            "Difference",
            "Expected",
            "Surprise",
            "Published",
            "Next Release",
            "Trend",
        ]
        self.full_table.setColumnCount(len(headers))
        self.full_table.setHorizontalHeaderLabels(headers)
        self.full_table.horizontalHeader().setStretchLastSection(True)
        self.full_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.full_table.verticalHeader().setVisible(False)
        self.full_table.setAlternatingRowColors(True)
        self.full_table.setShowGrid(True)
        self.full_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.full_table.setWordWrap(False)

    def _on_fetch_selected(self) -> None:
        """Fetch data for selected countries and populate the table."""
        # Gather selected countries
        selected_countries = [
            str(chk.property("slug") or chk.text())
            for chk in self.country_checkboxes
            if chk.isChecked()
        ]
        if not selected_countries:
            QtWidgets.QMessageBox.warning(self, "No Countries Selected", "Please select at least one country.")
            return
        # Disable buttons while fetching
        self.fetch_selected_btn.setDisabled(True)
        QtWidgets.QApplication.processEvents()
        try:
            data = self._fetch_data(selected_countries)
            self.last_data = data  # store for export
            self._populate_table(self.full_table, data)
            self.export_btn.setDisabled(False)
        finally:
            self.fetch_selected_btn.setDisabled(False)

    def _on_export(self) -> None:
        """Export the currently displayed data to a CSV file chosen by the user."""
        if not hasattr(self, "last_data") or not self.last_data:
            QtWidgets.QMessageBox.warning(self, "No Data", "There is no data to export. Please fetch data first.")
            return
        # Ask user for save location
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save CSV", "latest_macro.csv", "CSV Files (*.csv)")
        if not path:
            return
        # Write CSV
        try:
            headers = [
                "Country",
                "Indicator",
                "Current",
                "Previous",
                "Difference",
                "Expected",
                "Surprise",
                "Published",
                "Next Release",
                "Trend",
            ]
            import csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for row in self.last_data:
                    trend_str = ""  # convert trend list to string
                    if row.get("Trend"):
                        trend_str = ", ".join(str(x) for x in row.get("Trend"))
                    writer.writerow([
                        row.get("Country", ""),
                        row.get("Indicator", ""),
                        row.get("Current", ""),
                        row.get("Previous", ""),
                        row.get("Difference", ""),
                        row.get("Expected", ""),
                        row.get("Surprise", ""),
                        row.get("Published", ""),
                        row.get("Next Release", ""),
                        trend_str,
                    ])
            QtWidgets.QMessageBox.information(self, "Export Complete", f"Data exported to {path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Export Failed", f"An error occurred while exporting: {e}")

    def _on_full_start(self) -> None:
        """Handle click on the fetch all button."""
        self.full_start_btn.setDisabled(True)
        QtWidgets.QApplication.processEvents()
        try:
            data = self._fetch_data(self.countries)
            self._populate_table(self.full_table, data)
        finally:
            self.full_start_btn.setDisabled(False)

    # --------------- Compare Tab ---------------
    def _init_compare_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.compare_tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # --- Asset selectors ---
        select_grid = QtWidgets.QGridLayout()
        select_grid.setHorizontalSpacing(10)
        select_grid.setVerticalSpacing(8)

        label1 = QtWidgets.QLabel("Asset 1")
        label2 = QtWidgets.QLabel("Asset 2")
        label1.setStyleSheet("font-weight: 600;")
        label2.setStyleSheet("font-weight: 600;")

        self.combo1 = QtWidgets.QComboBox()
        self.combo2 = QtWidgets.QComboBox()
        self.combo1.setMinimumWidth(260)
        self.combo2.setMinimumWidth(260)

        # Populate with display names while keeping slug as userData
        for slug in self.countries:
            self.combo1.addItem(self._display_country(slug), slug)
            self.combo2.addItem(self._display_country(slug), slug)

        select_grid.addWidget(label1, 0, 0)
        select_grid.addWidget(self.combo1, 0, 1)
        select_grid.addWidget(label2, 0, 2)
        select_grid.addWidget(self.combo2, 0, 3)
        layout.addLayout(select_grid)

        # --- Compare button ---
        btn_row = QtWidgets.QHBoxLayout()
        self.compare_btn = QtWidgets.QPushButton("Fetch Comparison")
        self.compare_btn.setFixedHeight(38)
        self.compare_btn.clicked.connect(self._on_compare)
        btn_row.addWidget(self.compare_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # --- Two result tables stacked vertically (better for comparison) ---
        headers = [
            "Country",
            "Indicator",
            "Current",
            "Previous",
            "Difference",
            "Expected",
            "Surprise",
            "Published",
            "Next Release",
            "Trend",
        ]

        self.compare_label_top = QtWidgets.QLabel("Asset 1 results")
        self.compare_label_top.setStyleSheet("font-weight: 700; font-size: 14px;")
        self.compare_label_bottom = QtWidgets.QLabel("Asset 2 results")
        self.compare_label_bottom.setStyleSheet("font-weight: 700; font-size: 14px;")

        self.table_left = QtWidgets.QTableWidget()
        self.table_right = QtWidgets.QTableWidget()
        for tbl in (self.table_left, self.table_right):
            tbl.setColumnCount(len(headers))
            tbl.setHorizontalHeaderLabels(headers)
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tbl.verticalHeader().setVisible(False)
            tbl.setAlternatingRowColors(True)

        top_wrap = QtWidgets.QWidget()
        top_layout = QtWidgets.QVBoxLayout(top_wrap)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6)
        top_layout.addWidget(self.compare_label_top)
        top_layout.addWidget(self.table_left)

        bottom_wrap = QtWidgets.QWidget()
        bottom_layout = QtWidgets.QVBoxLayout(bottom_wrap)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(6)
        bottom_layout.addWidget(self.compare_label_bottom)
        bottom_layout.addWidget(self.table_right)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        splitter.addWidget(top_wrap)
        splitter.addWidget(bottom_wrap)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

    def _on_compare(self) -> None:
        """Handle click on the Compare button."""
        slug1 = self.combo1.currentData() or self.combo1.currentText()
        slug2 = self.combo2.currentData() or self.combo2.currentText()
        if slug1 == slug2:
            QtWidgets.QMessageBox.warning(self, "Invalid Selection", "Please select two different assets.")
            return
        self.compare_btn.setDisabled(True)
        QtWidgets.QApplication.processEvents()
        try:
            data1 = self._fetch_data([str(slug1)])
            data2 = self._fetch_data([str(slug2)])
            self._populate_table(self.table_left, data1)
            self._populate_table(self.table_right, data2)
            # Update section labels using the user-friendly names
            self.compare_label_top.setText(self.combo1.currentText())
            self.compare_label_bottom.setText(self.combo2.currentText())
        finally:
            self.compare_btn.setDisabled(False)

    # --------------- Data Fetching and Display ---------------
    def _fetch_data(self, country_list: List[str]) -> List[Dict[str, Optional[float]]]:
        """Fetch macro data for the given list of countries.

        Returns a list of dictionaries representing rows for the table.
        """
        rows: List[Dict[str, Optional[float]]] = []
        for country in country_list:
            scraper = TradingEconomicsScraper(
                country_slug=country,
                indicator_map=self.indicator_map,
                timeout=self.timeout,
                rate_limit=self.rate_limit,
                logger=self.logger,
                base_dir=Path(__file__).resolve().parents[0],
            )
            data_map = scraper.fetch_all(self.indicator_keys)
            for key in self.indicator_keys:
                info = self.indicator_map.get(key)
                if not info:
                    continue
                values = data_map.get(key) or {
                    "current": None,
                    "previous": None,
                    "expected": None,
                    "published": None,
                    "next_release": None,
                    "trend": None,
                }
                current = validate(key, values.get("current"))
                previous = validate(key, values.get("previous"))
                expected = validate(key, values.get("expected"))
                published = values.get("published")
                next_release = values.get("next_release")
                trend = values.get("trend")
                diff = compute_difference(current, previous)
                surprise = compute_difference(current, expected) if expected is not None else None
                row_dict = {
                    "Country": country,
                    "Indicator": info["name"],
                    "Current": current,
                    "Previous": previous,
                    "Difference": diff,
                    "Expected": expected,
                    "Surprise": surprise,
                    "Published": published,
                    "Next Release": next_release,
                }
                if trend is not None:
                    row_dict["Trend"] = trend
                rows.append(row_dict)
        return rows

    def _populate_table(self, table: QtWidgets.QTableWidget, data: List[Dict[str, Optional[float]]]) -> None:
        """Populate a QTableWidget with the provided data rows."""
        table.setRowCount(len(data))
        for row_idx, row in enumerate(data):
            # Build list of values in order of columns
            values = [
                row.get("Country", ""),
                row.get("Indicator", ""),
                row.get("Current", ""),
                row.get("Previous", ""),
                row.get("Difference", ""),
                row.get("Expected", ""),
                row.get("Surprise", ""),
                row.get("Published", ""),
                row.get("Next Release", ""),
            ]
            # Trend values may be a list of floats; use placeholder string or sparkline
            trend_data = row.get("Trend")
            # Set up cells
            for col_idx, val in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(val))
                if col_idx in {2, 3, 4, 5, 6}:  # numeric columns
                    item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                table.setItem(row_idx, col_idx, item)
            # Trend column (last)
            trend_col = len(values)
            if trend_data and isinstance(trend_data, list):
                try:
                    pixmap = self._create_sparkline(trend_data)
                    label = QtWidgets.QLabel()
                    label.setAlignment(QtCore.Qt.AlignCenter)
                    label.setPixmap(pixmap)
                    table.setCellWidget(row_idx, trend_col, label)
                except Exception:
                    # Fallback to text representation
                    item = QtWidgets.QTableWidgetItem(
                        ", ".join(str(x) for x in trend_data)
                    )
                    table.setItem(row_idx, trend_col, item)
            else:
                # Empty cell
                table.setItem(row_idx, trend_col, QtWidgets.QTableWidgetItem(""))

    def _create_sparkline(self, data: List[float]) -> QtGui.QPixmap:
        """
        Create a small sparkline QPixmap from a list of numeric data.

        Parameters
        ----------
        data : list of float
            List of numeric values (up to 6) to plot.

        Returns
        -------
        QPixmap
            The rendered sparkline image.
        """
        # Ensure we have at least two data points to plot
        if not data or len(data) < 2:
            # Create a blank pixmap
            pix = QtGui.QPixmap(60, 20)
            pix.fill(QtGui.QColor("transparent"))
            return pix
        # Create matplotlib figure
        fig = Figure(figsize=(1.2, 0.4), dpi=100)
        canvas = FigureCanvas(fig)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.plot(data, linewidth=1, color="#1976d2")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        fig.tight_layout(pad=0)
        # Draw figure and convert to QPixmap
        canvas.draw()
        width, height = fig.canvas.get_width_height()
        image = QtGui.QImage(canvas.buffer_rgba(), width, height, QtGui.QImage.Format_RGBA8888)
        pixmap = QtGui.QPixmap.fromImage(image)
        return pixmap

    
    # The `_create_sparkline` helper is defined below within the class.  It generates a
    # small line chart (sparkline) from a list of values for display in the table.
    


def main() -> None:
    """Launch the MacroScanner application."""
    # Crisp UI + consistent widget rendering across platforms
    try:
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass
    app = QtWidgets.QApplication(sys.argv)
    try:
        app.setStyle("Fusion")
    except Exception:
        pass
    window = MacroScannerApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()