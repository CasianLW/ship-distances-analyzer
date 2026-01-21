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
    "region_id",
    "mgo_at_port",
    "port_country_id",
    "port_code",
    "port_type",
    "is_active_port",
    "coordinates",
    "port_nickname",
    "updated_at",
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


@dataclass
class PortsData:
    rows: list
    load_ports: list
    disch_ports: list
    by_id: dict


class ComplexDistanceAnalyzerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Complex Distances Analyzer: A-Z & Segments")
        self.root.geometry("1020x760")

        self.ports_csv_path = None
        self.rules_csv_path = None
        self.segments_csv_path = None

        self.ports_data: PortsData | None = None
        self.rules_data: list | None = None
        self.segments_data: dict | None = None
        self.segments_rows = 0

        self.analysis_result = None
        self.analysis_thread = None
        self.dnd_available = False
        self.dnd_provider = "none"

        self._build_ui()
        self._try_load_defaults()
        self._setup_dnd()

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

    def _try_load_defaults(self) -> None:
        base_dir = os.path.dirname(__file__)
        defaults_dir = os.path.join(base_dir, "csvFiles")
        ports_path = os.path.join(defaults_dir, "ports.csv")
        rules_path = os.path.join(defaults_dir, "rules.csv")
        segments_path = os.path.join(defaults_dir, "distances-arw.csv")

        if os.path.isfile(ports_path):
            self._load_ports_from_path(ports_path)
        if os.path.isfile(rules_path):
            self._load_rules_from_path(rules_path)
        if os.path.isfile(segments_path):
            self._load_segments_from_path(segments_path)

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=12)
        top.pack(fill="x")

        info_btn = ttk.Button(top, text="Info (CSV Format)", command=self.show_info)
        info_btn.pack(side="left")

        self.include_inactive_var = tk.BooleanVar(value=False)
        inactive_chk = ttk.Checkbutton(
            top,
            text="Take inactive ports into account",
            variable=self.include_inactive_var,
        )
        inactive_chk.pack(side="left", padx=12)

        files = ttk.LabelFrame(self.root, text="CSV Inputs", padding=12)
        files.pack(fill="x", padx=12, pady=(0, 12))

        self.ports_status = tk.StringVar(value="Ports CSV: not loaded")
        self.rules_status = tk.StringVar(value="Distance Rules CSV: not loaded")
        self.segments_status = tk.StringVar(value="Distances ARW (segments) CSV: not loaded")

        ports_row = ttk.Frame(files)
        ports_row.pack(fill="x", pady=4)
        ttk.Button(ports_row, text="Add Ports CSV", command=self.load_ports_csv).pack(
            side="left"
        )
        self._build_drop_square(ports_row, self._load_ports_from_path).pack(
            side="left", padx=6
        )
        ttk.Button(
            ports_row, text="Remove Ports CSV", command=self.remove_ports_csv
        ).pack(side="left", padx=6)
        ttk.Label(ports_row, textvariable=self.ports_status).pack(side="left", padx=12)

        rules_row = ttk.Frame(files)
        rules_row.pack(fill="x", pady=4)
        ttk.Button(
            rules_row, text="Add Distance Rules CSV", command=self.load_rules_csv
        ).pack(side="left")
        self._build_drop_square(rules_row, self._load_rules_from_path).pack(
            side="left", padx=6
        )
        ttk.Button(
            rules_row, text="Remove Distance Rules CSV", command=self.remove_rules_csv
        ).pack(side="left", padx=6)
        ttk.Label(rules_row, textvariable=self.rules_status).pack(side="left", padx=12)

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

        actions = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        actions.pack(fill="x")
        self.start_btn = ttk.Button(
            actions, text="Generate & Analyze", command=self.start_analysis
        )
        self.start_btn.pack(side="left")

        self.reset_btn = ttk.Button(
            actions, text="Reset Analysis", command=self.reset_analysis
        )
        self.reset_btn.pack(side="left", padx=8)

        self.progress = ttk.Progressbar(
            self.root, mode="determinate", maximum=100
        )
        self.progress.pack(fill="x", padx=12, pady=(0, 12))
        self.progress.pack_forget()

        result_frame = ttk.LabelFrame(self.root, text="Analysis Output", padding=12)
        result_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.output_text = tk.Text(result_frame, height=18, wrap="none")
        self.output_text.pack(fill="both", expand=True)

        btns = ttk.Frame(result_frame)
        btns.pack(fill="x", pady=(8, 0))

        self.copy_btn = ttk.Button(
            btns, text="Copy tabulation table analysis", command=self.copy_output
        )
        self.copy_btn.pack(side="left")
        self.download_btn = ttk.Button(
            btns, text="Download tabulation table analysis", command=self.download_output
        )
        self.download_btn.pack(side="left", padx=8)

        self._set_result_buttons_state(enabled=False)

    def show_info(self) -> None:
        message = (
            "Ports CSV columns (exact header order):\n"
            + "\t".join(PORT_COLUMNS)
            + "\n\nDistance Rules CSV columns (exact header order):\n"
            + "\t".join(RULE_COLUMNS)
            + "\n\nDistances ARW (segments) CSV columns (exact header order):\n"
            + "\t".join(SEGMENT_COLUMNS)
            + "\n\nAnalysis output:\n"
            "- Missing Distances ARW (segments): route legs required by rules that\n"
            "  are not found in the segments CSV (direct or reverse).\n"
            "- Missing ARW Complete Distances: complete distances that could not be\n"
            "  generated because there is no rule for the pair or required segments\n"
            "  are missing."
        )
        messagebox.showinfo("CSV Format Info", message)

    def _set_result_buttons_state(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.copy_btn.config(state=state)
        self.download_btn.config(state=state)

    def load_ports_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Ports CSV", filetypes=[("CSV Files", "*.csv")]
        )
        if not path:
            return
        self._load_ports_from_path(path)

    def load_rules_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Distance Rules CSV", filetypes=[("CSV Files", "*.csv")]
        )
        if not path:
            return
        self._load_rules_from_path(path)

    def load_segments_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Distances ARW (segments) CSV", filetypes=[("CSV Files", "*.csv")]
        )
        if not path:
            return
        self._load_segments_from_path(path)

    def _load_ports_from_path(self, path: str) -> None:
        try:
            ports = self._read_ports_csv(path)
        except Exception as exc:
            messagebox.showerror("Ports CSV Error", str(exc))
            return
        self.ports_csv_path = path
        self.ports_data = ports
        self.ports_status.set(f"Ports CSV: loaded ({len(ports.rows)} rows)")
        self.reset_analysis()

    def _load_rules_from_path(self, path: str) -> None:
        try:
            self.rules_data = self._read_rules_csv(path)
        except Exception as exc:
            messagebox.showerror("Rules CSV Error", str(exc))
            return
        self.rules_csv_path = path
        self.rules_status.set(f"Distance Rules CSV: loaded ({len(self.rules_data)} rows)")
        self.reset_analysis()

    def _load_segments_from_path(self, path: str) -> None:
        try:
            self.segments_data, self.segments_rows = self._read_segments_csv(path)
        except Exception as exc:
            messagebox.showerror("Segments CSV Error", str(exc))
            return
        self.segments_csv_path = path
        self.segments_status.set(
            f"Distances ARW (segments) CSV: loaded ({self.segments_rows} rows)"
        )
        self.reset_analysis()

    def remove_ports_csv(self) -> None:
        self.ports_csv_path = None
        self.ports_data = None
        self.ports_status.set("Ports CSV: not loaded")
        self.reset_analysis()

    def remove_rules_csv(self) -> None:
        self.rules_csv_path = None
        self.rules_data = None
        self.rules_status.set("Distance Rules CSV: not loaded")
        self.reset_analysis()

    def remove_segments_csv(self) -> None:
        self.segments_csv_path = None
        self.segments_data = None
        self.segments_rows = 0
        self.segments_status.set("Distances ARW (segments) CSV: not loaded")
        self.reset_analysis()

    def reset_analysis(self) -> None:
        self.analysis_result = None
        self.output_text.delete("1.0", "end")
        self._set_result_buttons_state(enabled=False)
        self.progress.pack_forget()
        self.progress["value"] = 0

    def start_analysis(self) -> None:
        if not self.ports_data or not self.rules_data or not self.segments_data:
            messagebox.showwarning(
                "Missing CSVs",
                "Please load Ports, Distance Rules, and Distances ARW CSVs first.",
            )
            return
        if self.analysis_thread and self.analysis_thread.is_alive():
            return
        self.reset_analysis()
        self.progress.pack(fill="x", padx=12, pady=(0, 12))
        self.progress["value"] = 0
        self.start_btn.config(state="disabled")
        self.analysis_thread = threading.Thread(target=self._run_analysis, daemon=True)
        self.analysis_thread.start()

    def _run_analysis(self) -> None:
        try:
            result = self._analyze_complete_distances()
        except Exception as exc:
            self.root.after(
                0, lambda: messagebox.showerror("Analysis Error", str(exc))
            )
            self.root.after(0, self._analysis_finished, None)
            return
        self.root.after(0, self._analysis_finished, result)

    def _analysis_finished(self, result) -> None:
        self.start_btn.config(state="normal")
        self.progress.pack_forget()
        if not result:
            return
        self.analysis_result = result
        table_text = self._build_output_table(result)
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", table_text)
        self._set_result_buttons_state(enabled=True)

    def _build_output_table(self, result: dict) -> str:
        summary = result["summary"]
        missing_segments = result["missing_segments"]
        missing_complete = result["missing_complete"]

        lines = []
        lines.append("Summary")
        lines.append("Metric\tValue")
        lines.append(f"Total ports CSV rows\t{summary['total_ports_rows']}")
        lines.append(f"Total load ports\t{summary['total_load_ports']}")
        lines.append(f"Total disch ports\t{summary['total_disch_ports']}")
        lines.append(f"Total rules rows\t{summary['total_rules_rows']}")
        lines.append(f"Total segments rows\t{summary['total_segments_rows']}")
        lines.append(f"Expected complete distances\t{summary['expected_complete']}")
        lines.append(f"Complete distances generated\t{summary['generated_complete']}")
        lines.append(f"Missing distances (segments)\t{summary['missing_segments']}")
        lines.append(f"Missing complete distances\t{summary['missing_complete']}")
        lines.append("")
        lines.append("Missing Distances ARW (segments)")
        lines.append(
            "From port name\tFrom port id\tTo port name\tTo port id\tRule name\tRule id"
        )
        for row in missing_segments:
            lines.append(
                f"{row['from_name']}\t{row['from_id']}\t{row['to_name']}\t"
                f"{row['to_id']}\t{row['rule_name']}\t{row['rule_id']}"
            )
        lines.append("")
        lines.append("Missing ARW Complete Distances")
        lines.append(
            "Disch port name\tDisch port id\tLoad port name\tLoad port id\t"
            "Rule name\tPriority\tReason"
        )
        for row in missing_complete:
            lines.append(
                f"{row['disch_name']}\t{row['disch_id']}\t"
                f"{row['load_name']}\t{row['load_id']}\t"
                f"{row['rule_name']}\t{row['priority']}\t{row['reason']}"
            )
        return "\n".join(lines)

    def copy_output(self) -> None:
        if not self.analysis_result:
            return
        data = self.output_text.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(data)
        messagebox.showinfo("Copied", "Tabulation table copied to clipboard.")

    def download_output(self) -> None:
        if not self.analysis_result:
            return
        path = filedialog.asksaveasfilename(
            title="Save analysis table",
            defaultextension=".tsv",
            filetypes=[("TSV Files", "*.tsv"), ("Text Files", "*.txt")],
        )
        if not path:
            return
        data = self.output_text.get("1.0", "end-1c")
        with open(path, "w", encoding="utf-8") as file:
            file.write(data)
        messagebox.showinfo("Saved", f"Saved analysis to {path}")

    def _read_ports_csv(self, path: str) -> PortsData:
        with open(path, newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            self._validate_headers(reader.fieldnames, PORT_COLUMNS, "Ports CSV")
            rows = list(reader)

        load_ports = []
        disch_ports = []
        by_id = {}
        include_inactive = self.include_inactive_var.get()

        for row in rows:
            port_id = _normalize_id(row["id"])
            if not port_id:
                continue
            is_load = _as_bool(row["load"])
            is_active = _as_bool(row["is_active_port"])
            if not include_inactive and not is_active:
                continue
            by_id[port_id] = row
            disch_ports.append(row)
            if is_load:
                load_ports.append(row)

        return PortsData(
            rows=rows, load_ports=load_ports, disch_ports=disch_ports, by_id=by_id
        )

    def _read_rules_csv(self, path: str) -> list:
        with open(path, newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            self._validate_headers(reader.fieldnames, RULE_COLUMNS, "Distance Rules CSV")
            rows = list(reader)

        normalized = []
        for row in rows:
            normalized.append(
                {
                    "id": _normalize_id(row["id"]),
                    "distance_rule_name": row["distance_rule_name"],
                    "order_of_priority": int(_as_number(row["order_of_priority"])),
                    "zone_start_id": _normalize_id(row["zone_start_id"]),
                    "zone_end_id": _normalize_id(row["zone_end_id"]),
                    "waypoints": [
                        _normalize_id(row[f"waypoint{i}_id"])
                        for i in range(1, 7)
                        if _normalize_id(row.get(f"waypoint{i}_id", ""))
                    ],
                    "discount_suez_ballast": _as_number(row["discount_suez_ballast"]),
                    "discount_suez_laden": _as_number(row["discount_suez_laden"]),
                }
            )
        return normalized

    def _read_segments_csv(self, path: str) -> tuple[dict, int]:
        with open(path, newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            self._validate_headers(
                reader.fieldnames, SEGMENT_COLUMNS, "Distances ARW (segments) CSV"
            )
            segments = {}
            row_count = 0
            for row in reader:
                row_count += 1
                load_id = _normalize_id(row["load_port_id"])
                disch_id = _normalize_id(row["disch_port_id"])
                if not load_id or not disch_id:
                    continue
                key = f"{load_id}:{disch_id}"
                segments[key] = {
                    "totalDistance": _as_number(row["total_distance"]),
                    "secaDistance": _as_number(row["total_seca_distance"]),
                    "byPanamaCanalRp": _as_bool(row["by_panama_canal_rp"]),
                    "byCapeGoodHopeRp": _as_bool(row["by_cape_good_hope_rp"]),
                    "byCapeHornRp": _as_bool(row["by_cape_horn_rp"]),
                    "byTorresStraitRp": _as_bool(row["by_torres_strait_rp"]),
                    "byBosporusStraitRp": _as_bool(row["by_bosporus_strait_rp"]),
                    "bySkawAreaRp": _as_bool(row["by_skaw_area_rp"]),
                    "byGulfOfAdenRp": _as_bool(row["by_gulf_of_aden_rp"]),
                    "byGibraltarStraitRp": _as_bool(row["by_gibraltar_strait_rp"]),
                    "byMagellanStraitRp": _as_bool(row["by_magellan_strait_rp"]),
                    "bySingaporeStraitRp": _as_bool(row["by_singapore_strait_rp"]),
                    "byVitiazStraitRp": _as_bool(row["by_vitiaz_strait_rp"]),
                    "byKielCanalRp": _as_bool(row["by_kiel_canal_rp"]),
                    "bySuezCanalRp": _as_bool(row["by_suez_canal_rp"]),
                    "bySundaStraitRp": _as_bool(row["by_sunda_strait_rp"]),
                }
            return segments, row_count

    def _validate_headers(self, actual, expected, label: str) -> None:
        if not actual:
            raise ValueError(f"{label} has no headers.")
        trimmed = [h.strip() for h in actual]
        if trimmed != expected:
            raise ValueError(
                f"{label} header mismatch.\nExpected:\n{expected}\nGot:\n{trimmed}"
            )

    def _find_rules_for_pair(self, disch_port: dict, load_port: dict) -> list:
        disch_zone = _normalize_id(disch_port.get("region_id", ""))
        load_zone = _normalize_id(load_port.get("region_id", ""))
        if not disch_zone or not load_zone:
            return []

        matches = []
        for rule in self.rules_data or []:
            if rule["zone_start_id"] == disch_zone and rule["zone_end_id"] == load_zone:
                matches.append({"rule": rule, "reversed": False})
            elif rule["zone_start_id"] == load_zone and rule["zone_end_id"] == disch_zone:
                matches.append({"rule": rule, "reversed": True})

        return sorted(
            matches,
            key=lambda r: r["rule"].get("order_of_priority", 999),
        )

    def _lookup_segment(self, from_id: str, to_id: str) -> dict | None:
        if from_id == to_id:
            return {
                "totalDistance": 1.0,
                "secaDistance": 0.0,
                "byPanamaCanalRp": False,
                "byCapeGoodHopeRp": False,
                "byCapeHornRp": False,
                "byTorresStraitRp": False,
                "byBosporusStraitRp": False,
                "bySkawAreaRp": False,
                "byGulfOfAdenRp": False,
                "byGibraltarStraitRp": False,
                "byMagellanStraitRp": False,
                "bySingaporeStraitRp": False,
                "byVitiazStraitRp": False,
                "byKielCanalRp": False,
                "bySuezCanalRp": False,
                "bySundaStraitRp": False,
            }

        segments = self.segments_data or {}
        direct = segments.get(f"{from_id}:{to_id}")
        if direct:
            return direct
        reverse = segments.get(f"{to_id}:{from_id}")
        if reverse:
            return reverse
        return None

    def _build_distance_for_rule(
        self,
        disch_port: dict,
        load_port: dict,
        rule: dict,
        reversed_rule: bool,
        ports_by_id: dict,
    ) -> tuple[dict | None, list[tuple[str, str]]]:
        waypoints = [
            ports_by_id.get(_normalize_id(wp))
            for wp in rule["waypoints"]
            if _normalize_id(wp) in ports_by_id
        ]
        if reversed_rule:
            waypoints = list(reversed(waypoints))

        if not waypoints:
            seg = self._lookup_segment(
                _normalize_id(load_port["id"]), _normalize_id(disch_port["id"])
            )
            if not seg:
                seg = self._lookup_segment(
                    _normalize_id(disch_port["id"]), _normalize_id(load_port["id"])
                )
            if not seg:
                return None, [
                    (_normalize_id(load_port["id"]), _normalize_id(disch_port["id"]))
                ]
            return {"segment": seg}, []

        route = [disch_port] + waypoints + [load_port]
        filtered_route = []
        for port in route:
            if not filtered_route or _normalize_id(port["id"]) != _normalize_id(
                filtered_route[-1]["id"]
            ):
                filtered_route.append(port)

        missing_segments = []
        for idx in range(len(filtered_route) - 1):
            from_port = filtered_route[idx]
            to_port = filtered_route[idx + 1]
            seg = self._lookup_segment(
                _normalize_id(from_port["id"]), _normalize_id(to_port["id"])
            )
            if not seg:
                missing_segments.append(
                    (_normalize_id(from_port["id"]), _normalize_id(to_port["id"]))
                )
                return None, missing_segments

        return {"segment": True}, []

    def _analyze_complete_distances(self) -> dict:
        ports = self._read_ports_csv(self.ports_csv_path)
        rules = self.rules_data or []

        load_ports = ports.load_ports
        disch_ports = ports.disch_ports
        ports_by_id = ports.by_id

        total_ports_rows = len(ports.rows)
        total_load = len(load_ports)
        total_disch = len(disch_ports)
        total_rules = len(rules)
        total_segments_rows = self.segments_rows

        missing_segments_set = set()
        missing_segments_rows = []
        missing_complete = []

        expected_complete = 0
        generated_complete = 0

        total_pairs = max(total_load * total_disch, 1)
        checked = 0

        for disch_port in disch_ports:
            for load_port in load_ports:
                rules_for_pair = self._find_rules_for_pair(disch_port, load_port)
                if not rules_for_pair:
                    missing_complete.append(
                        {
                            "disch_name": disch_port["port"],
                            "disch_id": disch_port["id"],
                            "load_name": load_port["port"],
                            "load_id": load_port["id"],
                            "rule_name": "",
                            "priority": "",
                            "reason": "no_rule",
                        }
                    )
                else:
                    for rule_info in rules_for_pair:
                        expected_complete += 1
                        rule = rule_info["rule"]
                        dist, missing_segments = self._build_distance_for_rule(
                            disch_port,
                            load_port,
                            rule,
                            rule_info["reversed"],
                            ports_by_id,
                        )
                        if dist:
                            generated_complete += 1
                        else:
                            missing_complete.append(
                                {
                                    "disch_name": disch_port["port"],
                                    "disch_id": disch_port["id"],
                                    "load_name": load_port["port"],
                                    "load_id": load_port["id"],
                                    "rule_name": rule["distance_rule_name"],
                                    "priority": rule["order_of_priority"],
                                    "reason": "missing_segments",
                                }
                            )
                            for from_id, to_id in missing_segments:
                                key = f"{from_id}:{to_id}"
                                if key in missing_segments_set:
                                    continue
                                missing_segments_set.add(key)
                                missing_segments_rows.append(
                                    {
                                        "from_id": from_id,
                                        "from_name": ports_by_id.get(from_id, {}).get(
                                            "port", ""
                                        ),
                                        "to_id": to_id,
                                        "to_name": ports_by_id.get(to_id, {}).get(
                                            "port", ""
                                        ),
                                        "rule_name": rule["distance_rule_name"],
                                        "rule_id": rule["id"],
                                    }
                                )

                checked += 1
                if checked % 200 == 0 or checked == total_pairs:
                    progress_value = int((checked / total_pairs) * 100)
                    self.root.after(
                        0, self.progress.configure, {"value": progress_value}
                    )

        return {
            "summary": {
                "total_ports_rows": total_ports_rows,
                "total_load_ports": total_load,
                "total_disch_ports": total_disch,
                "total_rules_rows": total_rules,
                "total_segments_rows": total_segments_rows,
                "expected_complete": expected_complete,
                "generated_complete": generated_complete,
                "missing_segments": len(missing_segments_rows),
                "missing_complete": len(missing_complete),
            },
            "missing_segments": missing_segments_rows,
            "missing_complete": missing_complete,
        }


def main() -> None:
    root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    app = ComplexDistanceAnalyzerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
