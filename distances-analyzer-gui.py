import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk


def _launch_tool(script_name: str) -> None:
    script_path = os.path.join(os.path.dirname(__file__), script_name)
    subprocess.Popen([sys.executable, script_path])


def main() -> None:
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
        command=lambda: _launch_tool("simple-distances-analyzer.py"),
        width=46,
    ).pack(pady=6)

    ttk.Button(
        frame,
        text="Complex Distances Analyzer: A-Z & Segments",
        command=lambda: _launch_tool("complex-distances-analyzer.py"),
        width=46,
    ).pack(pady=6)

    ttk.Button(frame, text="Close", command=root.destroy, width=18).pack(pady=(16, 0))

    root.mainloop()


if __name__ == "__main__":
    main()
