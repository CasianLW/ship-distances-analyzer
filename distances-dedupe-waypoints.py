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


class DistancesDedupeWaypointsApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Distances: remove dupes & assign waypoints")
        self.root.geometry("920x640")

        self.distances_csv_path = None
        self.dnd_available = False
        self.dnd_provider = "none"

        self._build_ui()
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

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=12)
        top.pack(fill="x")

        ttk.Button(top, text="Info", command=self.show_info).pack(side="left")

        files = ttk.LabelFrame(self.root, text="CSV Inputs", padding=12)
        files.pack(fill="x", padx=12, pady=(0, 12))

        self.distances_status = tk.StringVar(value="Distances CSV: not loaded")

        distances_row = ttk.Frame(files)
        distances_row.pack(fill="x", pady=4)
        ttk.Button(
            distances_row,
            text="Add Distances CSV",
            command=self.load_distances_csv,
        ).pack(side="left")
        self._build_drop_square(distances_row, self._load_distances_from_path).pack(
            side="left", padx=6
        )
        ttk.Button(
            distances_row,
            text="Remove Distances CSV",
            command=self.remove_distances_csv,
        ).pack(side="left", padx=6)
        ttk.Label(distances_row, textvariable=self.distances_status).pack(
            side="left", padx=12
        )

        actions = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        actions.pack(fill="x")
        self.start_btn = ttk.Button(
            actions,
            text="Remove dupes & assign waypoints",
            command=self.start_processing,
        )
        self.start_btn.pack(side="left")

        self.reset_btn = ttk.Button(
            actions, text="Reset", command=self.reset_output
        )
        self.reset_btn.pack(side="left", padx=8)

        result_frame = ttk.LabelFrame(self.root, text="Output", padding=12)
        result_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.output_text = tk.Text(result_frame, height=18, wrap="word")
        self.output_text.pack(fill="both", expand=True)
        self.output_text.insert(
            "1.0",
            "This page is ready.\n\n"
            "Load a Distances CSV, then use the action button.\n"
            "Processing logic will be added next.",
        )
        self.output_text.configure(state="disabled")

    def show_info(self) -> None:
        messagebox.showinfo(
            "Distances: remove dupes & assign waypoints",
            "This tool will:\n"
            "- Remove duplicate distance rows\n"
            "- Assign waypoints where needed\n\n"
            "CSV format and processing rules will be defined as the feature is built.",
        )

    def load_distances_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Distances CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self._load_distances_from_path(path)

    def _load_distances_from_path(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            messagebox.showerror("Invalid file", "Please select a valid CSV file.")
            return
        self.distances_csv_path = path
        self.distances_status.set(f"Distances CSV: {os.path.basename(path)}")

    def remove_distances_csv(self) -> None:
        self.distances_csv_path = None
        self.distances_status.set("Distances CSV: not loaded")

    def start_processing(self) -> None:
        if not self.distances_csv_path:
            messagebox.showwarning(
                "Missing input",
                "Please load a Distances CSV first.",
            )
            return
        self._set_output(
            f"Loaded: {self.distances_csv_path}\n\n"
            "Processing is not implemented yet.\n"
            "Next step: define dedupe rules and waypoint assignment."
        )

    def reset_output(self) -> None:
        self._set_output(
            "This page is ready.\n\n"
            "Load a Distances CSV, then use the action button.\n"
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
