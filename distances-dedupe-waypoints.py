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
]

REQUIRED_SEGMENT_FIELDS = (
    "load_port_id",
    "disch_port_id",
    "total_distance",
    "total_seca_distance",
)


def _normalize_id(value: object) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if raw == "":
        return ""
    try:
        num = float(raw)
        if num.is_integer():
            return str(int(num))
        return str(num)
    except ValueError:
        return raw


def _normalize_distance(value: object) -> str:
    raw = str(value or "").strip()
    if raw == "":
        return ""
    try:
        return f"{float(raw):.10f}".rstrip("0").rstrip(".")
    except ValueError:
        return raw


def _normalize_header(value: object) -> str:
    return " ".join(str(value or "").replace("\n", " ").replace("\r", " ").split()).strip().lower()


def _match_key(
    load_port_id: object,
    disch_port_id: object,
    total_distance: object,
    total_seca_distance: object,
) -> tuple[str, str, str, str]:
    return (
        _normalize_id(load_port_id),
        _normalize_id(disch_port_id),
        _normalize_distance(total_distance),
        _normalize_distance(total_seca_distance),
    )


class DistancesDedupeWaypointsApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Distances: remove dupes")
        self.root.geometry("960x640")

        self.segments_csv_path = None
        self.excel_distances_csv_path = None
        self.segments_rows = 0
        self.excel_distances_rows = 0

        self.fieldnames: list[str] | None = None
        self.clean_rows: list[dict] = []
        self.duplicate_rows: list[dict] = []
        self.result_ready = False

        self.dnd_available = False
        self.dnd_provider = "none"

        self._build_ui()
        self._setup_dnd()

    @staticmethod
    def _detect_csv_dialect(sample: str):
        first_line = sample.splitlines()[0] if sample else ""
        if first_line.count("\t") >= 2:
            return csv.excel_tab
        try:
            return csv.Sniffer().sniff(sample, delimiters=",\t;")
        except csv.Error:
            return csv.excel

    @staticmethod
    def _count_csv_rows(path: str) -> int:
        """Count data rows (header excluded). Handles comma/tab/semicolon CSVs."""
        with open(path, newline="", encoding="utf-8-sig") as file:
            sample = file.read(8192)
            file.seek(0)
            dialect = DistancesDedupeWaypointsApp._detect_csv_dialect(sample)
            reader = csv.reader(file, dialect)
            next(reader, None)  # skip header
            return sum(1 for _ in reader)

    @staticmethod
    def _validate_excel_headers(path: str) -> None:
        with open(path, newline="", encoding="utf-8-sig") as file:
            sample = file.read(8192)
            file.seek(0)
            dialect = DistancesDedupeWaypointsApp._detect_csv_dialect(sample)
            reader = csv.reader(file, dialect)
            headers = next(reader, None)
        if not headers:
            raise ValueError("Excel Distances CSV has no headers.")
        actual = {_normalize_header(h) for h in headers if h is not None}
        missing = [
            col for col in EXCEL_DISTANCES_COLUMNS if col not in actual
        ]
        if missing:
            raise ValueError(
                "Excel Distances CSV is missing required columns:\n"
                + ", ".join(missing)
            )

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
            text="RUN Distances remove dupes",
            command=self.start_processing,
        )
        self.start_btn.pack(side="left")

        self.reset_btn = ttk.Button(actions, text="Reset", command=self.reset_output)
        self.reset_btn.pack(side="left", padx=8)

        result_frame = ttk.LabelFrame(self.root, text="Output", padding=12)
        result_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.output_text = tk.Text(result_frame, height=16, wrap="word")
        self.output_text.pack(fill="both", expand=True)
        self.output_text.insert(
            "1.0",
            "Load Distances ARW and Excel Distances CSVs, then press RUN.\n"
            "This tool removes ARW duplicates.",
        )
        self.output_text.configure(state="disabled")

        btns = ttk.Frame(result_frame)
        btns.pack(fill="x", pady=(8, 0))

        self.download_clean_btn = ttk.Button(
            btns,
            text="Download clean Distances ARW CSV",
            command=self.download_clean_csv,
        )
        self.download_clean_btn.pack(side="left")

        self.download_dupes_btn = ttk.Button(
            btns,
            text="Download duplicates CSV",
            command=self.download_duplicates_csv,
        )
        self.download_dupes_btn.pack(side="left", padx=8)

        self._set_download_buttons_state(enabled=False)

    def show_info(self) -> None:
        message = (
            "Distances ARW (segments) CSV columns:\n"
            + "\t".join(SEGMENT_COLUMNS)
            + "\n\nExcel Distances CSV columns:\n"
            + "\t".join(EXCEL_DISTANCES_COLUMNS)
            + "\n\nDuplicate rule (on Distances ARW):\n"
            "A row is a duplicate only if ALL of these are true at the same time:\n"
            "- Same load_port_id\n"
            "- AND same disch_port_id\n"
            "- AND same total_distance\n"
            "- AND same total_seca_distance\n"
            "If any one of these differs, the row is kept.\n"
            "First occurrence is kept in the clean CSV;\n"
            "later full matches go to the duplicates CSV."
        )
        messagebox.showinfo("Distances: remove dupes", message)

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
        self.reset_output()

    def remove_segments_csv(self) -> None:
        self.segments_csv_path = None
        self.segments_rows = 0
        self.segments_status.set("Distances ARW (segments) CSV: not loaded")
        self.reset_output()

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
            self._validate_excel_headers(path)
            row_count = self._count_csv_rows(path)
        except Exception as exc:
            messagebox.showerror("Excel Distances CSV Error", str(exc))
            return
        self.excel_distances_csv_path = path
        self.excel_distances_rows = row_count
        self.excel_status.set(f"Excel Distances CSV: loaded ({row_count} rows)")
        self.reset_output()

    def remove_excel_distances_csv(self) -> None:
        self.excel_distances_csv_path = None
        self.excel_distances_rows = 0
        self.excel_status.set("Excel Distances CSV: not loaded")
        self.reset_output()

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

        try:
            fieldnames, clean_rows, duplicate_rows = self._dedupe_segments_csv(
                self.segments_csv_path
            )
        except Exception as exc:
            messagebox.showerror("Processing Error", str(exc))
            return

        self.fieldnames = fieldnames
        self.clean_rows = clean_rows
        self.duplicate_rows = duplicate_rows
        self.result_ready = True
        self._set_download_buttons_state(enabled=True)

        self._set_output(
            "Résultat\n\n"
            f"Distances ARW input rows:\t{self.segments_rows}\n"
            f"Excel Distances rows:\t{self.excel_distances_rows}\n"
            f"Clean rows kept:\t{len(clean_rows)}\n"
            f"Duplicates removed:\t{len(duplicate_rows)}\n\n"
            "Duplicate rule (toutes les conditions en même temps, ET et non OU):\n"
            "- Même load_port_id\n"
            "- ET même disch_port_id\n"
            "- ET même total_distance\n"
            "- ET même total_seca_distance\n"
            "Première occurrence conservée; suivantes mises dans le CSV doublons.\n\n"
            "Use the download buttons below to export:\n"
            "- Clean Distances ARW CSV (sans doublons)\n"
            "- Duplicates CSV (lignes effacées)"
        )

    def reset_output(self) -> None:
        self.fieldnames = None
        self.clean_rows = []
        self.duplicate_rows = []
        self.result_ready = False
        self._set_download_buttons_state(enabled=False)
        self._set_output(
            "Load Distances ARW and Excel Distances CSVs, then press RUN.\n"
            "This tool removes ARW duplicates."
        )

    def _set_download_buttons_state(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.download_clean_btn.config(state=state)
        self.download_dupes_btn.config(state=state)

    def _set_output(self, text: str) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", text)
        self.output_text.configure(state="disabled")

    def _dedupe_segments_csv(
        self, path: str
    ) -> tuple[list[str], list[dict], list[dict]]:
        with open(path, newline="", encoding="utf-8-sig") as file:
            sample = file.read(8192)
            file.seek(0)
            dialect = DistancesDedupeWaypointsApp._detect_csv_dialect(sample)
            reader = csv.DictReader(file, dialect=dialect)
            if not reader.fieldnames:
                raise ValueError("Distances ARW CSV has no headers.")

            fieldnames = list(reader.fieldnames)
            missing = [c for c in REQUIRED_SEGMENT_FIELDS if c not in fieldnames]
            if missing:
                raise ValueError(
                    "Distances ARW CSV is missing required columns:\n"
                    + ", ".join(missing)
                )

            seen: set[tuple[str, str, str, str]] = set()
            clean_rows: list[dict] = []
            duplicate_rows: list[dict] = []

            for row in reader:
                # Duplicate only when ALL four values match together (AND, not OR).
                key = _match_key(
                    row.get("load_port_id"),
                    row.get("disch_port_id"),
                    row.get("total_distance"),
                    row.get("total_seca_distance"),
                )
                if key in seen:
                    duplicate_rows.append(row)
                else:
                    seen.add(key)
                    clean_rows.append(row)

        return fieldnames, clean_rows, duplicate_rows

    def download_clean_csv(self) -> None:
        if not self.result_ready or self.fieldnames is None:
            return
        path = filedialog.asksaveasfilename(
            title="Save clean Distances ARW CSV",
            defaultextension=".csv",
            initialfile="distances-arw-clean.csv",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not path:
            return
        self._write_csv(path, self.fieldnames, self.clean_rows)
        messagebox.showinfo("Saved", f"Clean CSV saved:\n{path}")

    def download_duplicates_csv(self) -> None:
        if not self.result_ready or self.fieldnames is None:
            return
        path = filedialog.asksaveasfilename(
            title="Save duplicates CSV",
            defaultextension=".csv",
            initialfile="distances-arw-duplicates.csv",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not path:
            return
        self._write_csv(path, self.fieldnames, self.duplicate_rows)
        messagebox.showinfo("Saved", f"Duplicates CSV saved:\n{path}")

    @staticmethod
    def _write_csv(path: str, fieldnames: list[str], rows: list[dict]) -> None:
        with open(path, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)


def main() -> None:
    root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    DistancesDedupeWaypointsApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
