import csv
import os
import tkinter as tk
import tkinter.filedialog  # Ensures PyInstaller bundles submodules
import tkinter.messagebox  # Ensures PyInstaller bundles submodules
import tkinter.ttk  # Ensures PyInstaller bundles submodules
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:
    DND_FILES = None
    TkinterDnD = None

SEGMENT_COLUMNS = [
    "id",
    "load_port_id",
    "disch_port_id",
    "total_distance",
    "total_seca_distance",
    "waypoint_data",
    "updated_at",
    "by_panama_canal_rp",
    "by_gibraltar_strait_rp",
    "by_cape_good_hope_rp",
    "by_magellan_strait_rp",
    "by_cape_horn_rp",
    "by_singapore_strait_rp",
    "by_torres_strait_rp",
    "by_vitiaz_strait_rp",
    "by_kiel_canal_rp",
    "by_skaw_area_rp",
    "by_suez_canal_rp",
    "by_gulf_of_aden_rp",
    "by_sunda_strait_rp",
    "by_bosporus_strait_rp",
    "by_malacca_strait_rp",
]

EXCEL_DISTANCES_COLUMNS = [
    "0",
    "LOAD PORT",
    "LOAD PORT UNLOCODE",
    "DISH PORT",
    "DISCH PORT UNLOCODE",
    "LOAD ZONE",
    "DISH ZONE",
    "TOTAL DISTANCE",
    "TOTAL SECA DISTANCE",
    "waypointData",
    "UPDATE",
    "load_port_id",
    "disch_port_id",
]


class DistancesDedupeWaypointsApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Distances: remove dupes & assign waypoints")
        self.root.geometry("960x640")

        self.segments_csv_path = None
        self.excel_distances_csv_path = None
        self.segments_rows = 0
        self.excel_distances_rows = 0
        self.dnd_available = False
        self.dnd_provider = "none"

        self._build_ui()
        self._setup_dnd()

    @staticmethod
    def _count_csv_rows(path: str) -> int:
        """Count data rows (header excluded). Handles comma/tab/semicolon CSVs."""
        with open(path, newline="", encoding="utf-8-sig") as file:
            sample = file.read(8192)
            file.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
            except csv.Error:
                dialect = csv.excel
            reader = csv.reader(file, dialect)
            next(reader, None)  # skip header
            return sum(1 for _ in reader)

    def _setup_dnd(self) -> None:
        if TkinterDnD is not None:
            self.dnd_available = True
            self.dnd_provider = "tkinterdnd2"
            return
        try:
            self.root.tk.eval("package require tkdnd")
            self.dnd_available = True
            self.dnd_provider = "tkdnd"
        except tk.TclError:
            self.dnd_available = False
            self.dnd_provider = "none"

    def _register_drop_target(self, widget: tk.Widget, callback) -> None:
        if not self.dnd_available:
            return
        if self.dnd_provider == "tkinterdnd2":
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind(
                "<<Drop>>",
                lambda event: self._handle_drop(event, callback),
            )
        elif self.dnd_provider == "tkdnd":
            self.root.tk.call("tkdnd::drop_target", "register", widget, "DND_Files")
            widget.bind(
                "<<Drop>>",
                lambda event: self._handle_drop(event, callback),
            )

    def _handle_drop(self, event: tk.Event, callback) -> None:
        data = getattr(event, "data", "")
        if not data:
            return
        paths = self.root.tk.splitlist(data)
        if not paths:
            return
        callback(paths[0])

    def _build_drop_square(self, parent: tk.Widget, callback) -> tk.Label:
        label = tk.Label(
            parent,
            text="Drop",
            width=6,
            height=2,
            relief="ridge",
            bd=2,
        )
        self._register_drop_target(label, callback)
        return label

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=12)
        top.pack(fill="x")

        ttk.Button(top, text="Info (CSV Format)", command=self.show_info).pack(
            side="left"
        )

        files = ttk.LabelFrame(self.root, text="CSV Inputs", padding=12)
        files.pack(fill="x", padx=12, pady=(0, 12))

        self.segments_status = tk.StringVar(
            value="Distances ARW (segments) CSV: not loaded"
        )
        self.excel_status = tk.StringVar(value="Excel Distances CSV: not loaded")

        segments_row = ttk.Frame(files)
        segments_row.pack(fill="x", pady=4)
        ttk.Button(
            segments_row,
            text="Add Distances ARW (segments) CSV",
            command=self.load_segments_csv,
        ).pack(side="left")
        self._build_drop_square(segments_row, self._load_segments_from_path).pack(
            side="left", padx=6
        )
        ttk.Button(
            segments_row,
            text="Remove Distances ARW CSV",
            command=self.remove_segments_csv,
        ).pack(side="left", padx=6)
        ttk.Label(segments_row, textvariable=self.segments_status).pack(
            side="left", padx=12
        )

        excel_row = ttk.Frame(files)
        excel_row.pack(fill="x", pady=4)
        ttk.Button(
            excel_row,
            text="Add Excel Distances CSV",
            command=self.load_excel_distances_csv,
        ).pack(side="left")
        self._build_drop_square(excel_row, self._load_excel_distances_from_path).pack(
            side="left", padx=6
        )
        ttk.Button(
            excel_row,
            text="Remove Excel Distances CSV",
            command=self.remove_excel_distances_csv,
        ).pack(side="left", padx=6)
        ttk.Label(excel_row, textvariable=self.excel_status).pack(side="left", padx=12)

        actions = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        actions.pack(fill="x")
        self.start_btn = ttk.Button(
            actions,
            text="RUN Distances remove dupes & assign wayponts",
            command=self.start_processing,
        )
        self.start_btn.pack(side="left")

        self.reset_btn = ttk.Button(actions, text="Reset", command=self.reset_output)
        self.reset_btn.pack(side="left", padx=8)

        result_frame = ttk.LabelFrame(self.root, text="Output", padding=12)
        result_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.output_text = tk.Text(result_frame, height=18, wrap="word")
        self.output_text.pack(fill="both", expand=True)
        self.output_text.insert(
            "1.0",
            "Load both CSVs, then press RUN.\n"
            "Processing logic will be added next.",
        )
        self.output_text.configure(state="disabled")

    def show_info(self) -> None:
        message = (
            "Distances ARW (segments) CSV columns (exact header order):\n"
            + "\t".join(SEGMENT_COLUMNS)
            + "\n\nExcel Distances CSV expected key columns:\n"
            + "\t".join(EXCEL_DISTANCES_COLUMNS)
            + "\n\nThis tool will later:\n"
            "- Remove duplicate distance rows\n"
            "- Assign waypoints where needed"
        )
        messagebox.showinfo(
            "Distances: remove dupes & assign waypoints",
            message,
        )

    def load_segments_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Distances ARW (segments) CSV",
            filetypes=[("CSV Files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self._load_segments_from_path(path)

    def _load_segments_from_path(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            messagebox.showerror("Invalid file", "Please select a valid CSV file.")
            return
        try:
            row_count = self._count_csv_rows(path)
        except Exception as exc:
            messagebox.showerror("Distances ARW CSV Error", str(exc))
            return
        self.segments_csv_path = path
        self.segments_rows = row_count
        self.segments_status.set(
            f"Distances ARW (segments) CSV: loaded ({row_count} rows)"
        )

    def remove_segments_csv(self) -> None:
        self.segments_csv_path = None
        self.segments_rows = 0
        self.segments_status.set("Distances ARW (segments) CSV: not loaded")

    def load_excel_distances_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Excel Distances CSV",
            filetypes=[("CSV Files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self._load_excel_distances_from_path(path)

    def _load_excel_distances_from_path(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            messagebox.showerror("Invalid file", "Please select a valid CSV file.")
            return
        try:
            row_count = self._count_csv_rows(path)
        except Exception as exc:
            messagebox.showerror("Excel Distances CSV Error", str(exc))
            return
        self.excel_distances_csv_path = path
        self.excel_distances_rows = row_count
        self.excel_status.set(f"Excel Distances CSV: loaded ({row_count} rows)")

    def remove_excel_distances_csv(self) -> None:
        self.excel_distances_csv_path = None
        self.excel_distances_rows = 0
        self.excel_status.set("Excel Distances CSV: not loaded")

    def start_processing(self) -> None:
        missing = []
        if not self.segments_csv_path:
            missing.append("Distances ARW (segments) CSV")
        if not self.excel_distances_csv_path:
            missing.append("Excel Distances CSV")
        if missing:
            messagebox.showwarning(
                "Missing input",
                "Please load:\n- " + "\n- ".join(missing),
            )
            return

        print("button pressed")
        self._set_output(
            "button pressed\n\n"
            f"Distances ARW: {self.segments_csv_path}\n"
            f"Excel Distances: {self.excel_distances_csv_path}\n\n"
            "Processing logic will be added next."
        )

    def reset_output(self) -> None:
        self._set_output(
            "Load both CSVs, then press RUN.\n"
            "Processing logic will be added next."
        )

    def _set_output(self, text: str) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", text)
        self.output_text.configure(state="disabled")


def main() -> None:
    root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    DistancesDedupeWaypointsApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
