# src/zip_utility/main.py
import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import logging
import zipfile  # Add missing import
from pathlib import Path
from . import core # Import from the same package

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class ZipApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Simple Zip Utility")
        self.geometry("600x550") # Increased height for progress bar and status
        self.minsize(500, 450)

        self.source_path = ctk.StringVar()
        self.target_zip_path = ctk.StringVar()
        self.source_zip_path = ctk.StringVar()
        self.extract_path = ctk.StringVar()

        # --- Main Layout ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0) # Progress bar row
        self.grid_rowconfigure(3, weight=0) # Status bar row

        # --- Compression Frame ---
        self.compress_frame = ctk.CTkFrame(self, corner_radius=10)
        self.compress_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="nsew")
        self.compress_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.compress_frame, text="Compress Files / Folder", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=3, padx=10, pady=(10, 15)
        )

        ctk.CTkButton(self.compress_frame, text="Select Source", command=self.select_source_compress).grid(
            row=1, column=0, padx=(20, 10), pady=5, sticky="ew"
        )
        ctk.CTkEntry(self.compress_frame, textvariable=self.source_path, state="readonly").grid(
            row=1, column=1, padx=0, pady=5, sticky="ew"
        )
        ctk.CTkButton(self.compress_frame, text="...", width=30, command=self.select_source_compress).grid(
            row=1, column=2, padx=(5, 20), pady=5
        )


        ctk.CTkButton(self.compress_frame, text="Select Output Zip", command=self.select_target_compress).grid(
            row=2, column=0, padx=(20, 10), pady=5, sticky="ew"
        )
        ctk.CTkEntry(self.compress_frame, textvariable=self.target_zip_path, state="readonly").grid(
            row=2, column=1, padx=0, pady=5, sticky="ew"
        )
        ctk.CTkButton(self.compress_frame, text="...", width=30, command=self.select_target_compress).grid(
             row=2, column=2, padx=(5, 20), pady=5
        )

        self.compress_button = ctk.CTkButton(self.compress_frame, text="Compress", command=self.start_compression, state="disabled")
        self.compress_button.grid(row=3, column=0, columnspan=3, padx=20, pady=(15, 10), sticky="ew")


        # --- Uncompression Frame ---
        self.uncompress_frame = ctk.CTkFrame(self, corner_radius=10)
        self.uncompress_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.uncompress_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.uncompress_frame, text="Uncompress Archive", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=3, padx=10, pady=(10, 15)
        )

        ctk.CTkButton(self.uncompress_frame, text="Select Zip File", command=self.select_source_uncompress).grid(
            row=1, column=0, padx=(20, 10), pady=5, sticky="ew"
        )
        ctk.CTkEntry(self.uncompress_frame, textvariable=self.source_zip_path, state="readonly").grid(
            row=1, column=1, padx=0, pady=5, sticky="ew"
        )
        ctk.CTkButton(self.uncompress_frame, text="...", width=30, command=self.select_source_uncompress).grid(
             row=1, column=2, padx=(5, 20), pady=5
        )

        ctk.CTkButton(self.uncompress_frame, text="Select Extract To", command=self.select_target_uncompress).grid(
            row=2, column=0, padx=(20, 10), pady=5, sticky="ew"
        )
        ctk.CTkEntry(self.uncompress_frame, textvariable=self.extract_path, state="readonly").grid(
            row=2, column=1, padx=0, pady=5, sticky="ew"
        )
        ctk.CTkButton(self.uncompress_frame, text="...", width=30, command=self.select_target_uncompress).grid(
             row=2, column=2, padx=(5, 20), pady=5
        )

        self.uncompress_button = ctk.CTkButton(self.uncompress_frame, text="Uncompress", command=self.start_uncompression, state="disabled")
        self.uncompress_button.grid(row=3, column=0, columnspan=3, padx=20, pady=(15, 10), sticky="ew")

        # --- Progress Bar ---
        self.progress_bar = ctk.CTkProgressBar(self, orientation="horizontal", mode="determinate")
        self.progress_bar.grid(row=2, column=0, padx=20, pady=(5, 0), sticky="ew")
        self.progress_bar.set(0) # Initial state

        # --- Status Bar ---
        self.status_label = ctk.CTkLabel(self, text="Ready", anchor="w")
        self.status_label.grid(row=3, column=0, padx=20, pady=(5, 10), sticky="ew")

        # Update button states initially
        self.update_button_states()


    def update_status(self, message: str, clear_progress=False):
        """Updates the status label (thread-safe)."""
        def _update():
            self.status_label.configure(text=message)
            if clear_progress:
                self.progress_bar.set(0)
        self.after(0, _update) # Schedule update in the main thread

    def update_progress(self, current: int, total: int):
        """Updates the progress bar (thread-safe)."""
        def _update():
            if total > 0:
                progress = float(current) / total
                self.progress_bar.set(progress)
            else:
                self.progress_bar.set(0) # Handle zero total case
        self.after(0, _update) # Schedule update in the main thread


    def update_button_states(self):
        """Enable/disable buttons based on selected paths."""
        compress_ready = bool(self.source_path.get() and self.target_zip_path.get())
        uncompress_ready = bool(self.source_zip_path.get() and self.extract_path.get())

        self.compress_button.configure(state=ctk.NORMAL if compress_ready else ctk.DISABLED)
        self.uncompress_button.configure(state=ctk.NORMAL if uncompress_ready else ctk.DISABLED)

    def select_source_compress(self):
        """Select source file or directory for compression."""
        # Ask for directory first, then fallback to file if cancelled
        path = filedialog.askdirectory(title="Select Folder to Compress")
        if not path: # If directory selection was cancelled, ask for a file
             path = filedialog.askopenfilename(title="Select File to Compress")

        if path:
            self.source_path.set(path)
            self.update_status(f"Selected source: {Path(path).name}")
            # Auto-suggest output filename based on source
            source_p = Path(path)
            suggested_name = f"{source_p.stem}.zip"
            initial_dir = source_p.parent
            self.target_zip_path.set(str(initial_dir / suggested_name)) # Pre-fill suggestion
        self.update_button_states()

    def select_target_compress(self):
        """Select target zip file path."""
        initial_name = Path(self.target_zip_path.get() or "archive.zip").name
        initial_dir = Path(self.target_zip_path.get() or ".").parent
        path = filedialog.asksaveasfilename(
            title="Save Zip Archive As",
            defaultextension=".zip",
            filetypes=[("Zip archives", "*.zip")],
            initialfile=initial_name,
            initialdir=initial_dir
        )
        if path:
            self.target_zip_path.set(path)
            self.update_status(f"Selected output: {Path(path).name}")
        self.update_button_states()

    def select_source_uncompress(self):
        """Select source zip file for uncompression."""
        path = filedialog.askopenfilename(
            title="Select Zip Archive to Uncompress",
            filetypes=[("Zip archives", "*.zip"), ("All files", "*.*")]
        )
        if path:
            self.source_zip_path.set(path)
            self.update_status(f"Selected archive: {Path(path).name}")
            # Auto-suggest extraction folder
            zip_p = Path(path)
            suggested_dir_name = zip_p.stem # Suggest folder name based on zip name
            initial_dir = zip_p.parent
            self.extract_path.set(str(initial_dir / suggested_dir_name)) # Pre-fill suggestion
        self.update_button_states()

    def select_target_uncompress(self):
        """Select target directory for extraction."""
        initial_dir = self.extract_path.get() or "."
        path = filedialog.askdirectory(
            title="Select Directory to Extract Files To",
            initialdir=initial_dir
            )
        if path:
            self.extract_path.set(path)
            self.update_status(f"Selected extraction target: {Path(path).name}")
        self.update_button_states()

    def _run_task(self, task_func, *args):
        """Runs a given task in a separate thread to avoid blocking the UI."""
        def task_wrapper():
            try:
                self.progress_bar.start() # Indeterminate mode while starting
                self.progress_bar.configure(mode="determinate")
                self.progress_bar.set(0)
                task_func(*args, progress_callback=self.update_progress)
                self.update_status(f"{task_func.__name__.split('_')[0].capitalize()} operation complete.", clear_progress=True)
            except FileNotFoundError as e:
                logging.error(f"Error: {e}")
                messagebox.showerror("Error", f"File not found:\n{e}")
                self.update_status(f"Error: File not found.", clear_progress=True)
            except (zipfile.BadZipFile, ValueError) as e:
                 logging.error(f"Error: {e}")
                 messagebox.showerror("Error", f"Invalid file or operation:\n{e}")
                 self.update_status(f"Error: Invalid file.", clear_progress=True)
            except Exception as e:
                logging.exception("An unexpected error occurred") # Log full traceback
                messagebox.showerror("Error", f"An unexpected error occurred:\n{e}")
                self.update_status(f"Error: {e}", clear_progress=True)
            finally:
                self.progress_bar.stop()
                self.progress_bar.set(0)
                 # Re-enable buttons after task completion/failure
                self.after(0, self.update_button_states)

        # Disable buttons during operation
        self.compress_button.configure(state=ctk.DISABLED)
        self.uncompress_button.configure(state=ctk.DISABLED)

        thread = threading.Thread(target=task_wrapper, daemon=True)
        thread.start()

    def start_compression(self):
        """Starts the compression process in a new thread."""
        source = self.source_path.get()
        target = self.target_zip_path.get()
        if not source or not target:
            messagebox.showwarning("Missing Info", "Please select source and target paths.")
            return

        self.update_status("Starting compression...")
        self._run_task(core.compress_item, source, target)


    def start_uncompression(self):
        """Starts the uncompression process in a new thread."""
        source = self.source_zip_path.get()
        target = self.extract_path.get()
        if not source or not target:
            messagebox.showwarning("Missing Info", "Please select zip file and extraction path.")
            return

        self.update_status("Starting uncompression...")
        self._run_task(core.uncompress_archive, source, target)


def run_app():
    """Runs the ZipApp."""
    logging.info("Starting Zip Utility Application")
    app = ZipApp()
    app.mainloop()

if __name__ == "__main__":
    run_app()