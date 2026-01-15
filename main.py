import csv
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk


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

DIST_COLUMNS = [
    "id",
    "load_port_id",
    "disch_port_id",
    "total_distance",
    "total_seca_distance",
    "by_panama_canal_rp",
    "by_gibraltar_strait_rp",
    "by_cape_good_hope_rp",
    "by_magellan_strait_rp",
    "by_cape_horn_rp",
    "by_singapore_strait_rp",
    "by_torres_strait_rp",
    "by_vitiaz_strait_rp",
    "by_malacca_strait_rp",
    "by_kiel_canal_rp",
    "by_skaw_area_rp",
    "by_suez_canal_rp",
    "by_gulf_of_aden_rp",
    "by_sunda_strait_rp",
    "discount_suez_ballast",
    "complete_distance_priority",
    "by_bosporus_strait_rp",
]


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y", "t"}


@dataclass
class PortsData:
    rows: list
    load_ports: list
    disch_ports: list
    by_id: dict


class DistanceAnalyzerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Ship Port Distance Helper")
        self.root.geometry("980x720")

        self.ports_csv_path = None
        self.distances_csv_path = None
        self.ports_data: PortsData | None = None
        self.distance_pairs: set[tuple[str, str]] | None = None
        self.distance_rows = 0

        self.analysis_result = None
        self.analysis_thread = None

        self._build_ui()

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
        self.dist_status = tk.StringVar(value="Complete Distances CSV: not loaded")

        ports_row = ttk.Frame(files)
        ports_row.pack(fill="x", pady=4)
        ttk.Button(ports_row, text="Add Ports CSV", command=self.load_ports_csv).pack(
            side="left"
        )
        ttk.Button(
            ports_row, text="Remove Ports CSV", command=self.remove_ports_csv
        ).pack(side="left", padx=6)
        ttk.Label(ports_row, textvariable=self.ports_status).pack(side="left", padx=12)

        dist_row = ttk.Frame(files)
        dist_row.pack(fill="x", pady=4)
        ttk.Button(
            dist_row, text="Add Complete Distances CSV", command=self.load_distances_csv
        ).pack(side="left")
        ttk.Button(
            dist_row, text="Remove Distances CSV", command=self.remove_distances_csv
        ).pack(side="left", padx=6)
        ttk.Label(dist_row, textvariable=self.dist_status).pack(side="left", padx=12)

        actions = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        actions.pack(fill="x")
        self.start_btn = ttk.Button(
            actions, text="Search Missing Distances", command=self.start_analysis
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
            + "\n\nExample:\n"
            "10\tCOTONOU\tFALSE\t4\tFALSE\t58\tBJCOOU\tP\tTRUE\t"
            "6.333300113678,2.4333000183105\tCOTONOU\t2025-10-14 16:23:10\n\n"
            "Complete Distances CSV columns (exact header order):\n"
            + "\t".join(DIST_COLUMNS)
            + "\n\nExample:\n"
            "2892971\t690\t749\t21400.290\t1057.780\tTRUE\tTRUE\tFALSE\t"
            "FALSE\tFALSE\tFALSE\tFALSE\tFALSE\tFALSE\tFALSE\tFALSE\t"
            "FALSE\tFALSE\tFALSE\t0.000\t1\tTRUE"
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
        try:
            ports = self._read_ports_csv(path)
        except Exception as exc:
            messagebox.showerror("Ports CSV Error", str(exc))
            return
        self.ports_csv_path = path
        self.ports_data = ports
        self.ports_status.set(f"Ports CSV: loaded ({len(ports.rows)} rows)")
        self.reset_analysis()

    def load_distances_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Complete Distances CSV", filetypes=[("CSV Files", "*.csv")]
        )
        if not path:
            return
        try:
            self.distance_pairs, self.distance_rows = self._read_distances_csv(path)
        except Exception as exc:
            messagebox.showerror("Distances CSV Error", str(exc))
            return
        self.distances_csv_path = path
        self.dist_status.set(
            "Complete Distances CSV: loaded "
            f"({self.distance_rows} rows, {len(self.distance_pairs)} pairs)"
        )
        self.reset_analysis()

    def remove_ports_csv(self) -> None:
        self.ports_csv_path = None
        self.ports_data = None
        self.ports_status.set("Ports CSV: not loaded")
        self.reset_analysis()

    def remove_distances_csv(self) -> None:
        self.distances_csv_path = None
        self.distance_pairs = None
        self.distance_rows = 0
        self.dist_status.set("Complete Distances CSV: not loaded")
        self.reset_analysis()

    def reset_analysis(self) -> None:
        self.analysis_result = None
        self.output_text.delete("1.0", "end")
        self._set_result_buttons_state(enabled=False)
        self.progress.pack_forget()
        self.progress["value"] = 0

    def start_analysis(self) -> None:
        if not self.ports_data or not self.distance_pairs:
            messagebox.showwarning(
                "Missing CSVs",
                "Please load both the Ports CSV and Complete Distances CSV first.",
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
            result = self._analyze_missing_distances()
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
        missing = result["missing"]

        lines = []
        lines.append("Summary")
        lines.append("Metric\tValue")
        lines.append(f"Total load ports\t{summary['total_load_ports']}")
        lines.append(f"Total disch ports\t{summary['total_disch_ports']}")
        lines.append(f"Total distance CSV rows\t{summary['total_distance_rows']}")
        lines.append(f"Total distances (pairs)\t{summary['total_distances']}")
        lines.append(f"Number of distances found\t{summary['found']}")
        lines.append(f"Number of distances missing\t{summary['missing']}")
        lines.append("")
        lines.append("Missing distances")
        lines.append("Load port name\tLoad port id\tDisch port name\tDisch port id")
        for row in missing:
            lines.append(
                f"{row['load_name']}\t{row['load_id']}\t{row['disch_name']}\t{row['disch_id']}"
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
            port_id = str(row["id"]).strip()
            if not port_id:
                continue
            is_load = _as_bool(row["load"])
            is_active = _as_bool(row["is_active_port"])
            if not include_inactive and not is_active:
                continue
            by_id[port_id] = row
            if is_load:
                load_ports.append(row)
            else:
                disch_ports.append(row)

        return PortsData(rows=rows, load_ports=load_ports, disch_ports=disch_ports, by_id=by_id)

    def _read_distances_csv(self, path: str) -> tuple[set[tuple[str, str]], int]:
        with open(path, newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            self._validate_headers(reader.fieldnames, DIST_COLUMNS, "Complete Distances CSV")
            pairs = set()
            row_count = 0
            for row in reader:
                row_count += 1
                load_id = str(row["load_port_id"]).strip()
                disch_id = str(row["disch_port_id"]).strip()
                if load_id and disch_id:
                    pairs.add((load_id, disch_id))
            return pairs, row_count

    def _validate_headers(self, actual, expected, label: str) -> None:
        if not actual:
            raise ValueError(f"{label} has no headers.")
        trimmed = [h.strip() for h in actual]
        if trimmed != expected:
            raise ValueError(
                f"{label} header mismatch.\nExpected:\n{expected}\nGot:\n{trimmed}"
            )

    def _analyze_missing_distances(self) -> dict:
        ports = self._read_ports_csv(self.ports_csv_path)
        distance_pairs = self.distance_pairs or set()

        load_ports = ports.load_ports
        disch_ports = ports.disch_ports

        total_pairs = len(distance_pairs)
        total_rows = self.distance_rows
        total_load = len(load_ports)
        total_disch = len(disch_ports)

        missing = []
        found = 0
        total_checks = max(total_load * total_disch, 1)
        checked = 0

        for load in load_ports:
            load_id = str(load["id"]).strip()
            load_name = load["port"]
            for disch in disch_ports:
                disch_id = str(disch["id"]).strip()
                if load_id == disch_id:
                    checked += 1
                    continue
                if (load_id, disch_id) in distance_pairs or (
                    disch_id,
                    load_id,
                ) in distance_pairs:
                    found += 1
                else:
                    missing.append(
                        {
                            "load_name": load_name,
                            "load_id": load_id,
                            "disch_name": disch["port"],
                            "disch_id": disch_id,
                        }
                    )
                checked += 1
                if checked % 200 == 0 or checked == total_checks:
                    progress_value = int((checked / total_checks) * 100)
                    self.root.after(0, self.progress.configure, {"value": progress_value})

        return {
            "summary": {
                "total_load_ports": total_load,
                "total_disch_ports": total_disch,
                "total_distance_rows": total_rows,
                "total_distances": total_pairs,
                "found": found,
                "missing": len(missing),
            },
            "missing": missing,
        }


def main() -> None:
    root = tk.Tk()
    app = DistanceAnalyzerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
