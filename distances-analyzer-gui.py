import os
import runpy
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk


def _resource_path(relative_path: str) -> str:
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    return os.path.join(base_dir, relative_path)


def _launch_tool(root: tk.Tk, tool_key: str) -> None:
    subprocess.Popen([sys.executable, "--tool", tool_key])
    root.destroy()


def _run_tool(tool_key: str) -> None:
    script_map = {
        "simple": "simple-distances-analyzer.py",
        "complex": "complex-distances-analyzer.py",
    }
    script_name = script_map.get(tool_key)
    if not script_name:
        messagebox.showerror("Unknown tool", f"Unknown tool: {tool_key}")
        return
    script_path = _resource_path(script_name)
    if not os.path.isfile(script_path):
        messagebox.showerror(
            "Missing tool file",
            f"Could not find {script_name}.\n"
            "If you are running a packaged .exe, ensure the file is bundled.",
        )
        return
    runpy.run_path(script_path, run_name="__main__")


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[1] == "--tool":
        _run_tool(sys.argv[2])
        return

    root = tk.Tk()
    root.title("Ship Port Distance Helper")
    root.geometry("520x260")

    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)

    title = ttk.Label(frame, text="Choose a tool", font=("Helvetica", 14))
    title.pack(pady=(0, 12))

    ttk.Button(
        frame,
        text="Simple Distances Analyzer: load to disch",
        command=lambda: _launch_tool(root, "simple"),
        width=46,
    ).pack(pady=6)

    ttk.Button(
        frame,
        text="Complex Distances Analyzer: A-Z & Segments",
        command=lambda: _launch_tool(root, "complex"),
        width=46,
    ).pack(pady=6)

    ttk.Button(frame, text="Close", command=root.destroy, width=18).pack(pady=(16, 0))

    root.mainloop()


if __name__ == "__main__":
    main()
