import csv
import os
import threading
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

REQUIRED_DISTANCE_FIELDS = (
    "load_port_id",
    "disch_port_id",
    "total_distance",
    "total_seca_distance",
)

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

MACHINE_COLUMNS = SEGMENT_COLUMNS + ["source"]

HUMAN_COLUMNS = [
    "from_id",
    "from_name",
    "to_id",
    "to_name",
] + [col for col in SEGMENT_COLUMNS if col not in ("load_port_id", "disch_port_id")] + [
    "source"
]


def _normalize_header(value: object) -> str:
    return " ".join(
        str(value or "").replace("\n", " ").replace("\r", " ").split()
    ).strip().lower()


def _canonical_header(value: object) -> str:
    return _normalize_header(value).replace(" ", "_")


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


def _distance_units(value: object) -> str:
    raw = str(value or "").strip().replace(" ", "")
    if raw == "":
        return ""
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    for sep in (".", ","):
        if sep in raw:
            raw = raw.split(sep, 1)[0]
            break
    try:
        return str(int(raw))
    except ValueError:
        return raw


def _pair_key(row: dict) -> tuple[str, str] | None:
    load_id = _normalize_id(row.get("load_port_id"))
    disch_id = _normalize_id(row.get("disch_port_id"))
    if not load_id or not disch_id:
        return None
    return tuple(sorted((load_id, disch_id)))


def _distance_signature(row: dict) -> tuple:
    return (
        _distance_units(row.get("total_distance")),
        _distance_units(row.get("total_seca_distance")),
    )


class DistancesCompareApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Compare two distances CSV")
        self.root.geometry("1020x780")

        self.directus_csv_path = None
        self.excel_csv_path = None
        self.ports_csv_path = None
        self.directus_rows = 0
        self.excel_rows = 0
        self.ports_rows = 0

        self.diff_machine_rows: list[dict] = []
        self.diff_human_rows: list[dict] = []
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
            dialect = DistancesCompareApp._detect_csv_dialect(sample)
            reader = csv.reader(file, dialect)
            next(reader, None)
            return sum(1 for _ in reader)

    @staticmethod
    def _validate_headers(actual, expected, label: str) -> None:
        if not actual:
            raise ValueError(f"{label} has no headers.")
        actual_set = {_canonical_header(h) for h in actual if h is not None}
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

        files = ttk.LabelFrame(self.root, text="CSV Inputs", padding=12)
        files.pack(fill="x", padx=12, pady=(0, 12))

        self.directus_status = tk.StringVar(value="Directus segments CSV: not loaded")
        self.excel_status = tk.StringVar(value="Excel segments CSV: not loaded")
        self.ports_status = tk.StringVar(value="Ports CSV: not loaded")

        self._add_file_row(
            files,
            "Import distances segments Directus",
            self.load_directus_csv,
            self._load_directus_from_path,
            "Remove Directus CSV",
            self.remove_directus_csv,
            self.directus_status,
        )
        self._add_file_row(
            files,
            "Import distances segments Excel",
            self.load_excel_csv,
            self._load_excel_from_path,
            "Remove Excel CSV",
            self.remove_excel_csv,
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

        actions = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        actions.pack(fill="x")
        self.start_btn = ttk.Button(
            actions,
            text="RUN compare",
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

        self.download_machine_btn = ttk.Button(
            btns,
            text="Download different distances",
            command=self.download_machine_csv,
        )
        self.download_machine_btn.pack(side="left")

        self.download_human_btn = ttk.Button(
            btns,
            text="Download different distances (human)",
            command=self.download_human_csv,
        )
        self.download_human_btn.pack(side="left", padx=8)

        self._set_download_buttons_state(enabled=False)

    def _idle_message(self) -> str:
        return (
            "Load Directus segments, Excel segments, and Ports CSVs, then press RUN.\n"
            "Pairs are matched unordered (A→B = B→A).\n"
            "Total / SECA: integer part only, no rounding (4844.38 and 4844.39 = 4844).\n"
            "Downloads stack Directus then Excel for each differing pair,\n"
            "with a final source column (directus / excel)."
        )

    def show_info(self) -> None:
        message = (
            "Directus / Excel segments columns:\n"
            + "\t".join(SEGMENT_COLUMNS)
            + "\n\nRequired on both CSVs:\n"
            + "\t".join(REQUIRED_DISTANCE_FIELDS)
            + "\n\nPorts CSV: id, port (for human names).\n\n"
            "Compare:\n"
            "- Match the same unordered load/disch pair (A→B and B→A).\n"
            "- Total and SECA: only the integer part before '.' or ',' is compared "
            "(no rounding: 4844.380 and 4844.3816 are both 4844).\n"
            "- Export: only pairs present in both CSVs whose units differ.\n"
            "- Each pair is always 2 stacked rows (Directus then Excel).\n"
            "- Pairs only in Directus or only in Excel are counted, not downloaded.\n"
            "- Different CSV: original segment format + source column.\n"
            "- Human CSV: port names + distances, dates, flags + source column.\n"
            "- Rows are stacked (Directus then Excel) so you can compare side by side."
        )
        messagebox.showinfo("Compare two distances CSV", message)

    def _pick_csv(self, title: str) -> str | None:
        path = filedialog.askopenfilename(
            title=title,
            filetypes=[("CSV Files", "*.csv"), ("All files", "*.*")],
        )
        return path or None

    def load_directus_csv(self) -> None:
        path = self._pick_csv("Select Directus distances segments CSV")
        if path:
            self._load_directus_from_path(path)

    def _load_directus_from_path(self, path: str) -> None:
        self._load_distances_from_path(
            path,
            label="Directus segments CSV",
            error_title="Directus CSV Error",
            path_attr="directus_csv_path",
            rows_attr="directus_rows",
            status_var=self.directus_status,
        )

    def remove_directus_csv(self) -> None:
        self.directus_csv_path = None
        self.directus_rows = 0
        self.directus_status.set("Directus segments CSV: not loaded")
        self.reset_output()

    def load_excel_csv(self) -> None:
        path = self._pick_csv("Select Excel distances segments CSV")
        if path:
            self._load_excel_from_path(path)

    def _load_excel_from_path(self, path: str) -> None:
        self._load_distances_from_path(
            path,
            label="Excel segments CSV",
            error_title="Excel CSV Error",
            path_attr="excel_csv_path",
            rows_attr="excel_rows",
            status_var=self.excel_status,
        )

    def remove_excel_csv(self) -> None:
        self.excel_csv_path = None
        self.excel_rows = 0
        self.excel_status.set("Excel segments CSV: not loaded")
        self.reset_output()

    def load_ports_csv(self) -> None:
        path = self._pick_csv("Select Ports CSV")
        if path:
            self._load_ports_from_path(path)

    def _load_distances_from_path(
        self,
        path: str,
        label: str,
        error_title: str,
        path_attr: str,
        rows_attr: str,
        status_var: tk.StringVar,
    ) -> None:
        if not path or not os.path.isfile(path):
            messagebox.showerror("Invalid file", "Please select a valid CSV file.")
            return
        try:
            with open(path, newline="", encoding="utf-8-sig") as file:
                sample = file.read(8192)
                file.seek(0)
                dialect = self._detect_csv_dialect(sample)
                headers = next(csv.reader(file, dialect), None)
            self._validate_headers(headers, REQUIRED_DISTANCE_FIELDS, label)
            row_count = self._count_csv_rows(path)
        except Exception as exc:
            messagebox.showerror(error_title, str(exc))
            return
        setattr(self, path_attr, path)
        setattr(self, rows_attr, row_count)
        status_var.set(f"{label}: loaded ({row_count} rows)")
        self.reset_output()

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

    def start_processing(self) -> None:
        missing = []
        if not self.directus_csv_path:
            missing.append("Directus segments CSV")
        if not self.excel_csv_path:
            missing.append("Excel segments CSV")
        if not self.ports_csv_path:
            missing.append("Ports CSV")
        if missing:
            messagebox.showerror(
                "Missing files",
                "Please load:\n- " + "\n- ".join(missing),
            )
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
            directus_rows = self._read_distance_rows(self.directus_csv_path)
            excel_rows = self._read_distance_rows(self.excel_csv_path)
            ports_by_id = self._read_ports_by_id(self.ports_csv_path)
            directus_index, directus_dupes = self._index_by_pair(directus_rows)
            excel_index, excel_dupes = self._index_by_pair(excel_rows)
            payload = self._compare(
                directus_index,
                excel_index,
                ports_by_id,
            )
            payload.update(
                {
                    "directus_input": len(directus_rows),
                    "excel_input": len(excel_rows),
                    "directus_pairs": len(directus_index),
                    "excel_pairs": len(excel_index),
                    "directus_dupes": directus_dupes,
                    "excel_dupes": excel_dupes,
                }
            )
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
        self.diff_machine_rows = payload["machine_rows"]
        self.diff_human_rows = payload["human_rows"]
        self.result_ready = True
        self._set_download_buttons_state(enabled=True)
        self.start_btn.config(state="normal")
        self.progress["value"] = 100
        self.progress.pack_forget()
        self._set_output(
            "Résultat\n\n"
            f"Directus input rows:\t{payload['directus_input']}\n"
            f"Excel input rows:\t{payload['excel_input']}\n"
            f"Directus unique pairs:\t{payload['directus_pairs']}\n"
            f"Excel unique pairs:\t{payload['excel_pairs']}\n"
            f"Extra same-pair rows skipped (Directus):\t{payload['directus_dupes']}\n"
            f"Extra same-pair rows skipped (Excel):\t{payload['excel_dupes']}\n\n"
            f"Identical pairs (same units):\t{payload['identical']}\n"
            f"Pairs with different units:\t{payload['value_diff']}\n"
            f"Only in Directus (not exported):\t{payload['only_directus']}\n"
            f"Only in Excel (not exported):\t{payload['only_excel']}\n"
            f"Export rows (2 per pair):\t{len(self.diff_machine_rows)}\n\n"
            "Downloads: only pairs present in both CSVs with different units.\n"
            "Each pair is 2 stacked rows: Directus then Excel."
        )

    def reset_output(self) -> None:
        self.diff_machine_rows = []
        self.diff_human_rows = []
        self.result_ready = False
        self._set_download_buttons_state(enabled=False)
        self.progress.pack_forget()
        self.progress["value"] = 0
        self._set_output(self._idle_message())

    def _set_download_buttons_state(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.download_machine_btn.config(state=state)
        self.download_human_btn.config(state=state)

    def _set_output(self, text: str) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", text)
        self.output_text.configure(state="disabled")

    def _read_distance_rows(self, path: str) -> list[dict]:
        with open(path, newline="", encoding="utf-8-sig") as file:
            sample = file.read(8192)
            file.seek(0)
            dialect = self._detect_csv_dialect(sample)
            reader = csv.DictReader(file, dialect=dialect)
            rows = []
            for row in reader:
                rows.append(
                    {_canonical_header(key): value for key, value in row.items()}
                )
        return rows

    def _read_ports_by_id(self, path: str) -> dict[str, dict]:
        with open(path, newline="", encoding="utf-8-sig") as file:
            sample = file.read(8192)
            file.seek(0)
            dialect = self._detect_csv_dialect(sample)
            reader = csv.DictReader(file, dialect=dialect)
            by_id: dict[str, dict] = {}
            for row in reader:
                normalized = {
                    _canonical_header(key): value for key, value in row.items()
                }
                port_id = _normalize_id(normalized.get("id"))
                if port_id:
                    by_id[port_id] = normalized
        return by_id

    @staticmethod
    def _index_by_pair(rows: list[dict]) -> tuple[dict[tuple[str, str], dict], int]:
        by_pair: dict[tuple[str, str], dict] = {}
        skipped = 0
        for row in rows:
            key = _pair_key(row)
            if key is None:
                continue
            if key in by_pair:
                skipped += 1
                continue
            by_pair[key] = row
        return by_pair, skipped

    def _port_label(self, ports_by_id: dict[str, dict], port_id: str) -> str:
        row = ports_by_id.get(port_id) or {}
        name = str(row.get("port") or "").strip()
        if not name:
            name = str(row.get("port_nickname") or "").strip()
        return name

    def _with_source(self, row: dict, source: str) -> dict:
        out = {col: row.get(col, "") for col in SEGMENT_COLUMNS}
        out["source"] = source
        return out

    def _human_row(
        self, row: dict, source: str, ports_by_id: dict[str, dict]
    ) -> dict:
        from_id = _normalize_id(row.get("load_port_id"))
        to_id = _normalize_id(row.get("disch_port_id"))
        out = {
            "from_id": from_id,
            "from_name": self._port_label(ports_by_id, from_id),
            "to_id": to_id,
            "to_name": self._port_label(ports_by_id, to_id),
        }
        for col in SEGMENT_COLUMNS:
            if col in ("load_port_id", "disch_port_id"):
                continue
            out[col] = row.get(col, "")
        out["source"] = source
        return out

    def _append_pair(
        self,
        machine_rows: list[dict],
        human_rows: list[dict],
        ports_by_id: dict[str, dict],
        directus_row: dict | None,
        excel_row: dict | None,
    ) -> None:
        if directus_row:
            machine_rows.append(self._with_source(directus_row, "directus"))
            human_rows.append(self._human_row(directus_row, "directus", ports_by_id))
        if excel_row:
            machine_rows.append(self._with_source(excel_row, "excel"))
            human_rows.append(self._human_row(excel_row, "excel", ports_by_id))

    def _compare(
        self,
        directus_index: dict[tuple[str, str], dict],
        excel_index: dict[tuple[str, str], dict],
        ports_by_id: dict[str, dict],
    ) -> dict:
        machine_rows: list[dict] = []
        human_rows: list[dict] = []
        identical = 0
        value_diff = 0
        only_directus = 0
        only_excel = 0

        keys = sorted(set(directus_index) | set(excel_index))
        total = max(len(keys), 1)
        for index, key in enumerate(keys, start=1):
            directus_row = directus_index.get(key)
            excel_row = excel_index.get(key)
            if directus_row and excel_row:
                if _distance_signature(directus_row) == _distance_signature(excel_row):
                    identical += 1
                else:
                    value_diff += 1
                    self._append_pair(
                        machine_rows,
                        human_rows,
                        ports_by_id,
                        directus_row,
                        excel_row,
                    )
            elif directus_row:
                only_directus += 1
            else:
                only_excel += 1
            if index % 200 == 0 or index == total:
                progress_value = int((index / total) * 100)
                self.root.after(
                    0, self.progress.configure, {"value": progress_value}
                )

        return {
            "machine_rows": machine_rows,
            "human_rows": human_rows,
            "identical": identical,
            "value_diff": value_diff,
            "only_directus": only_directus,
            "only_excel": only_excel,
        }

    def download_machine_csv(self) -> None:
        if not self.result_ready:
            return
        path = filedialog.asksaveasfilename(
            title="Save different distances",
            defaultextension=".csv",
            initialfile="distances-different.csv",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not path:
            return
        self._write_csv(path, MACHINE_COLUMNS, self.diff_machine_rows)
        messagebox.showinfo(
            "Saved",
            f"Different distances saved ({len(self.diff_machine_rows)} rows):\n{path}",
        )

    def download_human_csv(self) -> None:
        if not self.result_ready:
            return
        path = filedialog.asksaveasfilename(
            title="Save different distances (human)",
            defaultextension=".csv",
            initialfile="distances-different-human.csv",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not path:
            return
        self._write_csv(path, HUMAN_COLUMNS, self.diff_human_rows)
        messagebox.showinfo(
            "Saved",
            f"Different distances (human) saved ({len(self.diff_human_rows)} rows):\n{path}",
        )

    @staticmethod
    def _write_csv(path: str, fieldnames: list[str], rows: list[dict]) -> None:
        with open(path, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)


def main() -> None:
    root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    DistancesCompareApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
