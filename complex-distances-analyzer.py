import tkinter as tk
from tkinter import ttk


class ComplexDistanceAnalyzerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Complex Distances Analyzer: A-Z & Segments")
        self.root.geometry("620x240")

        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)

        title = ttk.Label(
            frame,
            text="Complex Distances Analyzer: A-Z & Segments",
            font=("Helvetica", 14),
        )
        title.pack(pady=(10, 12))

        message = ttk.Label(
            frame,
            text="Coming soon. This tool will be implemented later.",
            wraplength=560,
        )
        message.pack(pady=(0, 10))

        ttk.Button(frame, text="Close", command=self.root.destroy).pack()


def main() -> None:
    root = tk.Tk()
    app = ComplexDistanceAnalyzerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
