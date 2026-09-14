import csv
import os
import threading
import tkinter as tk
import tkinter.filedialog  # Ensures PyInstaller bundles submodules
import tkinter.messagebox  # Ensures PyInstaller bundles submodules
import tkinter.ttk  # Ensures PyInstaller bundles submodules
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:
    DND_FILES = None
    TkinterDnD = None

PORT_COLUMNS = [
    "id",
    "port",
    "load",
    "mgo_at_port",
    "is_archived",
    "region_id",
    "port_country_id",
    "port_code",
    "port_type",
    "is_active_port",
    "coordinates",
    "port_nickname",
    "refer_port_id",
]

RULE_COLUMNS = [
    "id",
    "distance_rule_name",
    "order_of_priority",
    "zone_start_id",
    "zone_end_id",
    "waypoint1_id",
    "waypoint2_id",
    "waypoint3_id",
    "waypoint4_id",
    "waypoint5_id",
    "waypoint6_id",
    "discount_suez_ballast",
    "discount_suez_laden",
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

ARW_EXPORT_COLUMNS = [
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

REQUIRED_SEGMENT_FIELDS = (
    "load_port_id",
    "disch_port_id",
    "total_distance",
    "total_seca_distance",
)

MISSING_COLUMNS = [
    "from_id",
    "from_name",
    "to_id",
    "to_name",
    "rule_name",
    "rule_id",
]

UNUSED_HUMAN_COLUMNS = [
    "from_id",
    "from_name",
    "to_id",
    "to_name",
    "from_is_load",
    "to_is_load",
    "from_region_id",
    "to_region_id",
    # "from_active",
    # "to_active",
]


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y", "t"}


def _as_number(value: str) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


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
    port_a, port_b = sorted(
        (_normalize_id(load_port_id), _normalize_id(disch_port_id))
    )
    return (
        port_a,
        port_b,
        _normalize_distance(total_distance),
        _normalize_distance(total_seca_distance),
    )


def _effective_port_id(port: dict) -> str:
    ref = _normalize_id(port.get("refer_port_id", ""))
    if ref:
        return ref
    return _normalize_id(port.get("id", ""))


def _resolve_master_port(port: dict, ports_by_id: dict) -> dict:
    current = port
    seen = set()
    while True:
        ref = _normalize_id(current.get("refer_port_id", ""))
        if not ref or ref in seen or ref not in ports_by_id:
            return current
        seen.add(ref)
        current = ports_by_id[ref]


@dataclass
class PortsData:
    rows: list
    load_ports: list
    disch_ports: list
    by_id: dict
    by_effective_id: dict
    by_id_all: dict


class DistancesDedupeWaypointsApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Distances: remove dupes")
        self.root.geometry("1020x820")

        self.excel_distances_csv_path = None
        self.ports_csv_path = None
        self.rules_csv_path = None
        self.excel_distances_rows = 0
        self.ports_rows = 0
        self.rules_rows = 0

        self.fieldnames: list[str] | None = None
        self.clean_rows: list[dict] = []
        self.duplicate_rows: list[dict] = []
        self.useful_excel_rows: list[dict] = []
        self.unused_excel_rows: list[dict] = []
        self.unused_human_rows: list[dict] = []
        self.missing_rows: list[dict] = []
        self.result_ready = False
        self.analysis_thread = None

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
        with open(path, newline="", encoding="utf-8-sig") as file:
            sample = file.read(8192)
            file.seek(0)
            dialect = DistancesDedupeWaypointsApp._detect_csv_dialect(sample)
            reader = csv.reader(file, dialect)
            next(reader, None)
            return sum(1 for _ in reader)

    @staticmethod
    def _validate_headers(actual, expected, label: str) -> None:
        if not actual:
            raise ValueError(f"{label} has no headers.")
        actual_set = {_normalize_header(h) for h in actual if h is not None}
        missing = [col for col in expected if col not in actual_set]
        if missing:
            raise ValueError(
                f"{label} is missing required columns:\n" + ", ".join(missing)
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

    def _add_file_row(
        self,
        parent: tk.Widget,
        add_text: str,
        add_command,
        drop_callback,
        remove_text: str,
        remove_command,
        status_var: tk.StringVar,
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Button(row, text=add_text, command=add_command).pack(side="left")
        self._build_drop_square(row, drop_callback).pack(side="left", padx=6)
        ttk.Button(row, text=remove_text, command=remove_command).pack(
            side="left", padx=6
        )
        ttk.Label(row, textvariable=status_var).pack(side="left", padx=12)

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=12)
        top.pack(fill="x")

        ttk.Button(top, text="Info (CSV Format)", command=self.show_info).pack(
            side="left"
        )

        self.include_inactive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            top,
            text="Take inactive ports into account",
            variable=self.include_inactive_var,
        ).pack(side="left", padx=12)

        self.all_ports_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            top,
            text="All load ports x ALL ports (each pair once)",
            variable=self.all_ports_var,
        ).pack(side="left", padx=12)

        self.remove_a_aa_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            top,
            text="Remove A & AA ports for clean",
            variable=self.remove_a_aa_var,
        ).pack(side="left", padx=12)

        files = ttk.LabelFrame(self.root, text="CSV Inputs", padding=12)
        files.pack(fill="x", padx=12, pady=(0, 12))

        self.excel_status = tk.StringVar(value="Excel Distances CSV: not loaded")
        self.ports_status = tk.StringVar(value="Ports CSV: not loaded")
        self.rules_status = tk.StringVar(value="Distance Rules CSV: not loaded")

        self._add_file_row(
            files,
            "Add Excel Distances CSV",
            self.load_excel_distances_csv,
            self._load_excel_distances_from_path,
            "Remove Excel Distances CSV",
            self.remove_excel_distances_csv,
            self.excel_status,
        )
        self._add_file_row(
            files,
            "Add Ports CSV",
            self.load_ports_csv,
            self._load_ports_from_path,
            "Remove Ports CSV",
            self.remove_ports_csv,
            self.ports_status,
        )
        self._add_file_row(
            files,
            "Add Distance Rules CSV",
            self.load_rules_csv,
            self._load_rules_from_path,
            "Remove Distance Rules CSV",
            self.remove_rules_csv,
            self.rules_status,
        )

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

        self.progress = ttk.Progressbar(self.root, mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=12, pady=(0, 12))
        self.progress.pack_forget()

        result_frame = ttk.LabelFrame(self.root, text="Output", padding=12)
        result_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.output_text = tk.Text(result_frame, height=14, wrap="word")
        self.output_text.pack(fill="both", expand=True)
        self.output_text.insert("1.0", self._idle_message())
        self.output_text.configure(state="disabled")

        btns = ttk.Frame(result_frame)
        btns.pack(fill="x", pady=(8, 0))

        self.download_clean_btn = ttk.Button(
            btns,
            text="Download clean Excel Distances CSV",
            command=self.download_clean_csv,
        )
        self.download_clean_btn.pack(side="left")

        self.download_dupes_btn = ttk.Button(
            btns,
            text="Download duplicates CSV",
            command=self.download_duplicates_csv,
        )
        self.download_dupes_btn.pack(side="left", padx=8)

        btns2 = ttk.Frame(result_frame)
        btns2.pack(fill="x", pady=(8, 0))

        self.download_useful_btn = ttk.Button(
            btns2,
            text="Download useful Excel distances",
            command=self.download_useful_csv,
        )
        self.download_useful_btn.pack(side="left")

        self.download_unused_btn = ttk.Button(
            btns2,
            text="Download unused Excel distances",
            command=self.download_unused_csv,
        )
        self.download_unused_btn.pack(side="left", padx=8)

        btns3 = ttk.Frame(result_frame)
        btns3.pack(fill="x", pady=(8, 0))

        self.download_unused_human_btn = ttk.Button(
            btns3,
            text="Download unused (human)",
            command=self.download_unused_human_csv,
        )
        self.download_unused_human_btn.pack(side="left")

        self.download_missing_btn = ttk.Button(
            btns3,
            text="Download still missing distances",
            command=self.download_missing_csv,
        )
        self.download_missing_btn.pack(side="left", padx=8)

        self._set_download_buttons_state(enabled=False)

    def _idle_message(self) -> str:
        return (
            "Load Excel Distances, Ports, and Rules CSVs, then press RUN.\n"
            "1) Dedupe Excel Distances.\n"
            "2) Simulate Complex Analyzer (no input distances) to list required legs.\n"
            "3) Retrieve those legs from the cleaned Excel Distances.\n"
            "4) Download clean, useful, unused, unused (human), and still-missing CSVs."
        )

    def show_info(self) -> None:
        message = (
            "Excel Distances CSV columns:\n"
            + "\t".join(EXCEL_DISTANCES_COLUMNS)
            + "\n\nPorts CSV columns:\n"
            + "\t".join(PORT_COLUMNS)
            + "\n\nDistance Rules CSV columns:\n"
            + "\t".join(RULE_COLUMNS)
            + "\n\nPipeline:\n"
            "- Dedupe Excel Distances (same unordered load/disch pair, including "
            "A→B and B→A, + same total + same SECA).\n"
            "- If 'Remove A & AA ports for clean' is on, any Excel row whose load or "
            "disch port has port_type A or AA is removed from clean like a duplicate.\n"
            "- Simulate Complex Analyzer without distances as input:\n"
            "  required route legs from Ports + Rules.\n"
            "- Look up those legs in the cleaned Excel Distances (direct or reverse).\n"
            "- Useful CSV = clean Excel rows that match a required leg.\n"
            "- Unused CSV = clean Excel rows not needed by any rule.\n"
            "- Unused (human) CSV = same unused pairs with port names "
            "(from_id, from_name, to_id, to_name, from_is_load, to_is_load, "
            "from_region_id, to_region_id).\n"
            "- Still missing CSV = required legs not found in clean Excel."
        )
        messagebox.showinfo("Distances: remove dupes", message)

    def _pick_csv(self, title: str) -> str | None:
        path = filedialog.askopenfilename(
            title=title,
            filetypes=[("CSV Files", "*.csv"), ("All files", "*.*")],
        )
        return path or None

    def load_excel_distances_csv(self) -> None:
        path = self._pick_csv("Select Excel Distances CSV")
        if path:
            self._load_excel_distances_from_path(path)

    def _load_excel_distances_from_path(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            messagebox.showerror("Invalid file", "Please select a valid CSV file.")
            return
        try:
            with open(path, newline="", encoding="utf-8-sig") as file:
                sample = file.read(8192)
                file.seek(0)
                dialect = self._detect_csv_dialect(sample)
                headers = next(csv.reader(file, dialect), None)
            self._validate_headers(headers, EXCEL_DISTANCES_COLUMNS, "Excel Distances CSV")
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

    def load_ports_csv(self) -> None:
        path = self._pick_csv("Select Ports CSV")
        if path:
            self._load_ports_from_path(path)

    def _load_ports_from_path(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            messagebox.showerror("Invalid file", "Please select a valid CSV file.")
            return
        try:
            with open(path, newline="", encoding="utf-8-sig") as file:
                sample = file.read(8192)
                file.seek(0)
                dialect = self._detect_csv_dialect(sample)
                headers = next(csv.reader(file, dialect), None)
            self._validate_headers(headers, ["id", "port"], "Ports CSV")
            row_count = self._count_csv_rows(path)
        except Exception as exc:
            messagebox.showerror("Ports CSV Error", str(exc))
            return
        self.ports_csv_path = path
        self.ports_rows = row_count
        self.ports_status.set(f"Ports CSV: loaded ({row_count} rows)")
        self.reset_output()

    def remove_ports_csv(self) -> None:
        self.ports_csv_path = None
        self.ports_rows = 0
        self.ports_status.set("Ports CSV: not loaded")
        self.reset_output()

    def load_rules_csv(self) -> None:
        path = self._pick_csv("Select Distance Rules CSV")
        if path:
            self._load_rules_from_path(path)

    def _load_rules_from_path(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            messagebox.showerror("Invalid file", "Please select a valid CSV file.")
            return
        try:
            with open(path, newline="", encoding="utf-8-sig") as file:
                sample = file.read(8192)
                file.seek(0)
                dialect = self._detect_csv_dialect(sample)
                headers = next(csv.reader(file, dialect), None)
            self._validate_headers(headers, RULE_COLUMNS, "Distance Rules CSV")
            row_count = self._count_csv_rows(path)
        except Exception as exc:
            messagebox.showerror("Rules CSV Error", str(exc))
            return
        self.rules_csv_path = path
        self.rules_rows = row_count
        self.rules_status.set(f"Distance Rules CSV: loaded ({row_count} rows)")
        self.reset_output()

    def remove_rules_csv(self) -> None:
        self.rules_csv_path = None
        self.rules_rows = 0
        self.rules_status.set("Distance Rules CSV: not loaded")
        self.reset_output()

    def start_processing(self) -> None:
        missing = []
        if not self.excel_distances_csv_path:
            missing.append("Excel Distances CSV")
        if not self.ports_csv_path:
            missing.append("Ports CSV")
        if not self.rules_csv_path:
            missing.append("Distance Rules CSV")
        if missing:
            messagebox.showwarning(
                "Missing input",
                "Please load:\n- " + "\n- ".join(missing),
            )
            return
        if self.analysis_thread and self.analysis_thread.is_alive():
            return

        self.reset_output()
        self.progress.pack(fill="x", padx=12, pady=(0, 12))
        self.progress["value"] = 0
        self.start_btn.config(state="disabled")
        self.analysis_thread = threading.Thread(
            target=self._run_processing, daemon=True
        )
        self.analysis_thread.start()

    def _run_processing(self) -> None:
        try:
            fieldnames, clean_rows, duplicate_rows = self._dedupe_distances_csv(
                self.excel_distances_csv_path
            )
            ports = self._read_ports_csv(self.ports_csv_path)
            a_aa_removed = 0
            if self.remove_a_aa_var.get():
                clean_rows, duplicate_rows, a_aa_removed = self._strip_a_aa_rows(
                    clean_rows, duplicate_rows, ports
                )
            rules = self._read_rules_csv(self.rules_csv_path)
            excel_by_pair = self._index_distance_rows(clean_rows)
            required, no_rule_pairs, missing_complete = self._collect_required_legs(
                ports, rules, excel_by_pair
            )
            useful_rows, missing_rows = self._match_required_in_excel(
                required, excel_by_pair, ports
            )
            unused_rows = self._unused_excel_rows(clean_rows, useful_rows)
            unused_human_rows = self._unused_human_rows(unused_rows, ports)
            payload = {
                "fieldnames": fieldnames,
                "clean_rows": clean_rows,
                "duplicate_rows": duplicate_rows,
                "useful_rows": useful_rows,
                "unused_rows": unused_rows,
                "unused_human_rows": unused_human_rows,
                "missing_rows": missing_rows,
                "required_legs": len(required),
                "no_rule_pairs": no_rule_pairs,
                "missing_complete": missing_complete,
                "all_ports_mode": self.all_ports_var.get(),
                "remove_a_aa": self.remove_a_aa_var.get(),
                "a_aa_removed": a_aa_removed,
            }
        except Exception as exc:
            self.root.after(0, self._on_processing_error, str(exc))
            return
        self.root.after(0, self._on_processing_done, payload)

    def _on_processing_error(self, message: str) -> None:
        self.start_btn.config(state="normal")
        self.progress.pack_forget()
        self.progress["value"] = 0
        messagebox.showerror("Processing Error", message)

    def _on_processing_done(self, payload: dict) -> None:
        self.fieldnames = payload["fieldnames"]
        self.clean_rows = payload["clean_rows"]
        self.duplicate_rows = payload["duplicate_rows"]
        self.useful_excel_rows = payload["useful_rows"]
        self.unused_excel_rows = payload["unused_rows"]
        self.unused_human_rows = payload["unused_human_rows"]
        self.missing_rows = payload["missing_rows"]
        self.result_ready = True
        self._set_download_buttons_state(enabled=True)
        self.start_btn.config(state="normal")
        self.progress["value"] = 100
        self.progress.pack_forget()

        mode = (
            "ALL LOAD PORTS x ALL ports (each pair once)"
            if payload["all_ports_mode"]
            else "Load ports x ALL ports"
        )
        self._set_output(
            "Résultat\n\n"
            f"Analysis mode:\t{mode}\n"
            f"Excel Distances input rows:\t{self.excel_distances_rows}\n"
            f"Clean Excel rows kept:\t{len(self.clean_rows)}\n"
            f"Duplicates removed:\t"
            f"{len(self.duplicate_rows) - payload['a_aa_removed']}\n"
            f"A/AA port rows removed from clean:\t"
            f"{payload['a_aa_removed'] if payload['remove_a_aa'] else 'off'}\n"
            f"Required legs (rules, no input distances):\t{payload['required_legs']}\n"
            f"Useful Excel distances found:\t{len(self.useful_excel_rows)}\n"
            f"Unused Excel distances:\t{len(self.unused_excel_rows)}\n"
            f"Still missing legs:\t{len(self.missing_rows)}\n"
            f"Missing complete distances:\t{payload['missing_complete']}\n"
            f"Port pairs with no rule:\t{payload['no_rule_pairs']}\n\n"
            "Downloads:\n"
            "- Clean Excel Distances CSV (sans doublons)\n"
            "- Duplicates CSV (true dupes + A/AA rows if checkbox on)\n"
            "- Useful Excel distances (legs required by rules, from clean)\n"
            "- Unused Excel distances (clean rows not needed by rules)\n"
            "- Unused (human) (same pairs with port names)\n"
            "- Still missing distances (required legs not in clean Excel)"
        )

    def reset_output(self) -> None:
        self.fieldnames = None
        self.clean_rows = []
        self.duplicate_rows = []
        self.useful_excel_rows = []
        self.unused_excel_rows = []
        self.unused_human_rows = []
        self.missing_rows = []
        self.result_ready = False
        self._set_download_buttons_state(enabled=False)
        self.progress.pack_forget()
        self.progress["value"] = 0
        self._set_output(self._idle_message())

    def _set_download_buttons_state(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.download_clean_btn.config(state=state)
        self.download_dupes_btn.config(state=state)
        self.download_useful_btn.config(state=state)
        self.download_unused_btn.config(state=state)
        self.download_unused_human_btn.config(state=state)
        self.download_missing_btn.config(state=state)

    def _set_output(self, text: str) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", text)
        self.output_text.configure(state="disabled")

    def _dedupe_distances_csv(
        self, path: str
    ) -> tuple[list[str], list[dict], list[dict]]:
        with open(path, newline="", encoding="utf-8-sig") as file:
            sample = file.read(8192)
            file.seek(0)
            dialect = self._detect_csv_dialect(sample)
            reader = csv.DictReader(file, dialect=dialect)
            if not reader.fieldnames:
                raise ValueError("Excel Distances CSV has no headers.")

            fieldnames = list(reader.fieldnames)
            missing = [c for c in REQUIRED_SEGMENT_FIELDS if c not in fieldnames]
            if missing:
                raise ValueError(
                    "Excel Distances CSV is missing required columns:\n"
                    + ", ".join(missing)
                )

            seen: set[tuple[str, str, str, str]] = set()
            clean_rows: list[dict] = []
            duplicate_rows: list[dict] = []
            for row in reader:
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

    @staticmethod
    def _port_type_of(ports: PortsData, port_id: str) -> str:
        row = ports.by_id_all.get(port_id) or {}
        return str(row.get("port_type") or "").strip().upper()

    def _strip_a_aa_rows(
        self,
        clean_rows: list[dict],
        duplicate_rows: list[dict],
        ports: PortsData,
    ) -> tuple[list[dict], list[dict], int]:
        kept: list[dict] = []
        removed: list[dict] = []
        for row in clean_rows:
            load_type = self._port_type_of(
                ports, _normalize_id(row.get("load_port_id"))
            )
            disch_type = self._port_type_of(
                ports, _normalize_id(row.get("disch_port_id"))
            )
            if load_type in {"A", "AA"} or disch_type in {"A", "AA"}:
                removed.append(row)
            else:
                kept.append(row)
        return kept, duplicate_rows + removed, len(removed)

    def _read_ports_csv(self, path: str) -> PortsData:
        with open(path, newline="", encoding="utf-8-sig") as file:
            sample = file.read(8192)
            file.seek(0)
            dialect = self._detect_csv_dialect(sample)
            reader = csv.DictReader(file, dialect=dialect)
            self._validate_headers(reader.fieldnames, ["id", "port"], "Ports CSV")
            rows = list(reader)

        load_ports = []
        disch_ports = []
        by_id = {}
        by_id_all = {}
        include_inactive = self.include_inactive_var.get()
        for row in rows:
            port_id = _normalize_id(row.get("id"))
            if not port_id:
                continue
            by_id_all[port_id] = row
            is_load = _as_bool(row.get("load", ""))
            is_active = _as_bool(row.get("is_active_port", "true"))
            if not include_inactive and row.get("is_active_port") not in (
                None,
                "",
            ) and not is_active:
                continue
            by_id[port_id] = row
            disch_ports.append(row)
            if is_load:
                load_ports.append(row)

        by_effective_id = {}
        for row in by_id.values():
            eff = _effective_port_id(row)
            if eff not in by_effective_id or _normalize_id(row.get("id")) == eff:
                by_effective_id[eff] = row

        return PortsData(
            rows=rows,
            load_ports=load_ports,
            disch_ports=disch_ports,
            by_id=by_id,
            by_effective_id=by_effective_id,
            by_id_all=by_id_all,
        )

    def _read_rules_csv(self, path: str) -> list:
        with open(path, newline="", encoding="utf-8-sig") as file:
            sample = file.read(8192)
            file.seek(0)
            dialect = self._detect_csv_dialect(sample)
            reader = csv.DictReader(file, dialect=dialect)
            self._validate_headers(reader.fieldnames, RULE_COLUMNS, "Distance Rules CSV")
            rows = list(reader)

        normalized = []
        for row in rows:
            normalized.append(
                {
                    "id": _normalize_id(row.get("id")),
                    "distance_rule_name": row.get("distance_rule_name", ""),
                    "order_of_priority": int(_as_number(row.get("order_of_priority", 0))),
                    "zone_start_id": _normalize_id(row.get("zone_start_id")),
                    "zone_end_id": _normalize_id(row.get("zone_end_id")),
                    "waypoints": [
                        _normalize_id(row.get(f"waypoint{i}_id"))
                        for i in range(1, 7)
                        if _normalize_id(row.get(f"waypoint{i}_id", ""))
                    ],
                }
            )
        return normalized

    def _index_distance_rows(self, rows: list[dict]) -> dict[str, dict]:
        by_pair: dict[str, dict] = {}
        for row in rows:
            load_id = _normalize_id(row.get("load_port_id"))
            disch_id = _normalize_id(row.get("disch_port_id"))
            if not load_id or not disch_id:
                continue
            key = f"{load_id}:{disch_id}"
            if key not in by_pair:
                by_pair[key] = row
        return by_pair

    def _find_rules_for_pair(self, disch_port: dict, load_port: dict, rules: list) -> list:
        disch_zone = _normalize_id(disch_port.get("region_id", ""))
        load_zone = _normalize_id(load_port.get("region_id", ""))
        if not disch_zone or not load_zone:
            return []
        matches = []
        for rule in rules:
            if rule["zone_start_id"] == disch_zone and rule["zone_end_id"] == load_zone:
                matches.append({"rule": rule, "reversed": False})
            elif rule["zone_start_id"] == load_zone and rule["zone_end_id"] == disch_zone:
                matches.append({"rule": rule, "reversed": True})
        return sorted(matches, key=lambda r: r["rule"].get("order_of_priority", 999))

    def _legs_for_rule(
        self,
        disch_port: dict,
        load_port: dict,
        rule: dict,
        reversed_rule: bool,
        ports_by_id: dict,
    ) -> list[tuple[str, str]]:
        waypoints = [
            _resolve_master_port(ports_by_id[_normalize_id(wp)], ports_by_id)
            for wp in rule["waypoints"]
            if _normalize_id(wp) in ports_by_id
        ]
        if reversed_rule:
            waypoints = list(reversed(waypoints))

        if not waypoints:
            load_eff = _effective_port_id(load_port)
            disch_eff = _effective_port_id(disch_port)
            if load_eff and disch_eff and load_eff != disch_eff:
                return [(load_eff, disch_eff)]
            return []

        route = [disch_port] + waypoints + [load_port]
        filtered = []
        for port in route:
            if not port:
                continue
            if not filtered or _effective_port_id(port) != _effective_port_id(
                filtered[-1]
            ):
                filtered.append(port)

        legs = []
        for idx in range(len(filtered) - 1):
            from_id = _effective_port_id(filtered[idx])
            to_id = _effective_port_id(filtered[idx + 1])
            if from_id and to_id and from_id != to_id:
                legs.append((from_id, to_id))
        return legs

    def _collect_required_legs(
        self,
        ports: PortsData,
        rules: list,
        excel_by_pair: dict[str, dict],
    ) -> tuple[dict[tuple[str, str], dict], int, int]:
        load_ports = ports.load_ports
        disch_ports = ports.disch_ports
        ports_by_id = ports.by_id
        all_ports_mode = self.all_ports_var.get()

        required: dict[tuple[str, str], dict] = {}
        processed_pairs: set[str] = set()
        no_rule_pairs = 0
        missing_complete = 0
        total_pairs = max(len(disch_ports) * len(load_ports), 1)
        checked = 0

        for disch_port in disch_ports:
            for load_port in load_ports:
                disch_master = _resolve_master_port(disch_port, ports_by_id)
                load_master = _resolve_master_port(load_port, ports_by_id)
                disch_eff = _effective_port_id(disch_master)
                load_eff = _effective_port_id(load_master)
                if all_ports_mode:
                    pair_key = ":".join(sorted((disch_eff, load_eff)))
                else:
                    pair_key = f"{disch_eff}:{load_eff}"
                if pair_key in processed_pairs:
                    checked += 1
                    continue
                processed_pairs.add(pair_key)

                rules_for_pair = self._find_rules_for_pair(
                    disch_master, load_master, rules
                )
                if not rules_for_pair:
                    no_rule_pairs += 1
                    missing_complete += 1
                else:
                    for rule_info in rules_for_pair:
                        rule = rule_info["rule"]
                        legs = self._legs_for_rule(
                            disch_master,
                            load_master,
                            rule,
                            rule_info["reversed"],
                            ports_by_id,
                        )
                        for from_id, to_id in legs:
                            if (from_id, to_id) not in required:
                                required[(from_id, to_id)] = rule
                        if any(
                            not self._lookup_excel_row(excel_by_pair, from_id, to_id)
                            for from_id, to_id in legs
                        ):
                            missing_complete += 1

                checked += 1
                if checked % 200 == 0 or checked == total_pairs:
                    progress_value = int((checked / total_pairs) * 90)
                    self.root.after(
                        0, self.progress.configure, {"value": progress_value}
                    )

        return required, no_rule_pairs, missing_complete

    def _lookup_excel_row(
        self, excel_by_pair: dict[str, dict], from_id: str, to_id: str
    ) -> dict | None:
        return excel_by_pair.get(f"{from_id}:{to_id}") or excel_by_pair.get(
            f"{to_id}:{from_id}"
        )

    def _port_row(self, ports: PortsData, port_id: str) -> dict:
        if not port_id:
            return {}
        return (
            ports.by_id_all.get(port_id)
            or ports.by_id.get(port_id)
            or ports.by_effective_id.get(port_id)
            or {}
        )

    def _port_label(self, ports: PortsData, port_id: str) -> str:
        row = self._port_row(ports, port_id)
        name = str(row.get("port") or "").strip()
        if not name:
            name = str(row.get("port_nickname") or "").strip()
        return name

    def _port_is_load_label(self, ports: PortsData, port_id: str) -> str:
        row = self._port_row(ports, port_id)
        if not row:
            return ""
        return "true" if _as_bool(row.get("load", "")) else "false"

    def _port_region_id(self, ports: PortsData, port_id: str) -> str:
        return _normalize_id(self._port_row(ports, port_id).get("region_id"))

    # def _port_active_label(self, ports: PortsData, port_id: str) -> str:
    #     row = self._port_row(ports, port_id)
    #     if not row:
    #         return ""
    #     raw = row.get("is_active_port")
    #     if raw in (None, ""):
    #         return "active"
    #     return "active" if _as_bool(raw) else "inactive"

    def _match_required_in_excel(
        self,
        required: dict[tuple[str, str], dict],
        excel_by_pair: dict[str, dict],
        ports: PortsData,
    ) -> tuple[list[dict], list[dict]]:
        useful_rows: list[dict] = []
        missing_rows: list[dict] = []
        seen_excel_rows: set[tuple[str, str]] = set()
        seen_missing: set[tuple[str, str]] = set()

        for (from_id, to_id), rule in required.items():
            excel_row = self._lookup_excel_row(excel_by_pair, from_id, to_id)
            if excel_row:
                row_key = (
                    _normalize_id(excel_row.get("load_port_id")),
                    _normalize_id(excel_row.get("disch_port_id")),
                )
                if row_key not in seen_excel_rows:
                    seen_excel_rows.add(row_key)
                    useful_rows.append(excel_row)
                continue

            miss_key = tuple(sorted((from_id, to_id)))
            if miss_key in seen_missing:
                continue
            seen_missing.add(miss_key)
            missing_rows.append(
                {
                    "from_id": from_id,
                    "from_name": self._port_label(ports, from_id),
                    "to_id": to_id,
                    "to_name": self._port_label(ports, to_id),
                    "rule_name": rule.get("distance_rule_name", ""),
                    "rule_id": rule.get("id", ""),
                }
            )
        return useful_rows, missing_rows

    @staticmethod
    def _unused_excel_rows(
        clean_rows: list[dict], useful_rows: list[dict]
    ) -> list[dict]:
        useful_keys = {
            (
                _normalize_id(row.get("load_port_id")),
                _normalize_id(row.get("disch_port_id")),
            )
            for row in useful_rows
        }
        return [
            row
            for row in clean_rows
            if (
                _normalize_id(row.get("load_port_id")),
                _normalize_id(row.get("disch_port_id")),
            )
            not in useful_keys
        ]

    def _unused_human_rows(
        self, unused_rows: list[dict], ports: PortsData
    ) -> list[dict]:
        return [
            {
                "from_id": _normalize_id(row.get("load_port_id")),
                "from_name": self._port_label(
                    ports, _normalize_id(row.get("load_port_id"))
                ),
                "to_id": _normalize_id(row.get("disch_port_id")),
                "to_name": self._port_label(
                    ports, _normalize_id(row.get("disch_port_id"))
                ),
                "from_is_load": self._port_is_load_label(
                    ports, _normalize_id(row.get("load_port_id"))
                ),
                "to_is_load": self._port_is_load_label(
                    ports, _normalize_id(row.get("disch_port_id"))
                ),
                "from_region_id": self._port_region_id(
                    ports, _normalize_id(row.get("load_port_id"))
                ),
                "to_region_id": self._port_region_id(
                    ports, _normalize_id(row.get("disch_port_id"))
                ),
                # "from_active": self._port_active_label(
                #     ports, _normalize_id(row.get("load_port_id"))
                # ),
                # "to_active": self._port_active_label(
                #     ports, _normalize_id(row.get("disch_port_id"))
                # ),
            }
            for row in unused_rows
        ]

    def download_clean_csv(self) -> None:
        if not self.result_ready or self.fieldnames is None:
            return
        path = filedialog.asksaveasfilename(
            title="Save clean Excel Distances CSV",
            defaultextension=".csv",
            initialfile="excel-distances-clean.csv",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not path:
            return
        self._write_arw_compatible_csv(path, self.clean_rows)
        messagebox.showinfo("Saved", f"Clean CSV saved:\n{path}")

    def download_duplicates_csv(self) -> None:
        if not self.result_ready or self.fieldnames is None:
            return
        path = filedialog.asksaveasfilename(
            title="Save duplicates CSV",
            defaultextension=".csv",
            initialfile="excel-distances-duplicates.csv",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not path:
            return
        self._write_arw_compatible_csv(path, self.duplicate_rows)
        messagebox.showinfo("Saved", f"Duplicates CSV saved:\n{path}")

    def download_useful_csv(self) -> None:
        if not self.result_ready or self.fieldnames is None:
            return
        path = filedialog.asksaveasfilename(
            title="Save useful Excel distances",
            defaultextension=".csv",
            initialfile="excel-distances-useful.csv",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not path:
            return
        self._write_arw_compatible_csv(path, self.useful_excel_rows)
        messagebox.showinfo(
            "Saved",
            f"Useful Excel distances saved ({len(self.useful_excel_rows)} rows):\n{path}",
        )

    def download_unused_csv(self) -> None:
        if not self.result_ready or self.fieldnames is None:
            return
        path = filedialog.asksaveasfilename(
            title="Save unused Excel distances",
            defaultextension=".csv",
            initialfile="excel-distances-unused.csv",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not path:
            return
        self._write_arw_compatible_csv(path, self.unused_excel_rows)
        messagebox.showinfo(
            "Saved",
            f"Unused Excel distances saved ({len(self.unused_excel_rows)} rows):\n{path}",
        )

    def download_unused_human_csv(self) -> None:
        if not self.result_ready:
            return
        path = filedialog.asksaveasfilename(
            title="Save unused distances (human)",
            defaultextension=".csv",
            initialfile="distances-unused-human.csv",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not path:
            return
        self._write_csv(path, UNUSED_HUMAN_COLUMNS, self.unused_human_rows)
        messagebox.showinfo(
            "Saved",
            f"Unused distances (human) saved ({len(self.unused_human_rows)} rows):\n{path}",
        )

    def download_missing_csv(self) -> None:
        if not self.result_ready:
            return
        path = filedialog.asksaveasfilename(
            title="Save still missing distances",
            defaultextension=".csv",
            initialfile="distances-still-missing.csv",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not path:
            return
        self._write_csv(path, MISSING_COLUMNS, self.missing_rows)
        messagebox.showinfo(
            "Saved",
            f"Still missing distances saved ({len(self.missing_rows)} rows):\n{path}",
        )

    @staticmethod
    def _as_arw_rows(rows: list[dict]) -> list[dict]:
        exported = []
        for index, row in enumerate(rows, start=1):
            out = {col: row.get(col, "") for col in ARW_EXPORT_COLUMNS}
            if not str(out.get("id") or "").strip():
                out["id"] = str(index)
            if not str(out.get("by_malacca_strait_rp") or "").strip():
                out["by_malacca_strait_rp"] = "0"
            exported.append(out)
        return exported

    def _write_arw_compatible_csv(self, path: str, rows: list[dict]) -> None:
        self._write_csv(path, ARW_EXPORT_COLUMNS, self._as_arw_rows(rows))

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
