# src/zip_utility/main.py
import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import logging
import zipfile
import psutil
from pathlib import Path
import os
import time
from . import core
from . import utils  # Import the new utilities module

# Configure module logger
logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class ZipApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("zippy")
        self.geometry("600x550")
        self.minsize(500, 450)

        # Operation control
        self.cancel_event = threading.Event()
        self.current_task_thread = None

        self.source_path = ctk.StringVar()
        self.target_zip_path = ctk.StringVar()
        self.source_zip_path = ctk.StringVar()
        self.extract_path = ctk.StringVar()
        # Changed to empty StringVar since we'll use placeholder text
        self.output_label = ctk.StringVar(value="")
        
        # Resource monitoring variables
        self.resource_label = ctk.StringVar(value="Memory: --%, CPU: --%")
        self.resource_check_after_id = None

        # --- Main Layout ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)  # Progress bar row
        self.grid_rowconfigure(3, weight=0)  # Resource monitor row
        self.grid_rowconfigure(4, weight=0)  # Status bar row

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

        # Output location - Modified to be editable
        ctk.CTkLabel(self.compress_frame, text="Save to:", anchor="w").grid(
            row=2, column=0, padx=(20, 10), pady=5, sticky="ew"
        )
        ctk.CTkEntry(self.compress_frame, textvariable=self.output_label, placeholder_text="Output will be saved to Desktop").grid(
            row=2, column=1, padx=0, pady=5, sticky="ew"
        )
        ctk.CTkButton(self.compress_frame, text="...", width=30, command=self.select_save_location).grid(
            row=2, column=2, padx=(5, 20), pady=5
        )

        # Add button frame for compress/cancel
        self.compress_btn_frame = ctk.CTkFrame(self.compress_frame, fg_color="transparent")
        self.compress_btn_frame.grid(row=3, column=0, columnspan=3, padx=20, pady=(15, 10), sticky="ew")
        self.compress_btn_frame.grid_columnconfigure(0, weight=1)
        self.compress_btn_frame.grid_columnconfigure(1, weight=1)
        
        self.compress_button = ctk.CTkButton(
            self.compress_btn_frame, 
            text="Compress", 
            command=self.start_compression, 
            state="disabled"
        )
        self.compress_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        self.cancel_compress_button = ctk.CTkButton(
            self.compress_btn_frame, 
            text="Cancel", 
            command=self.cancel_operation,
            fg_color="#D32F2F",
            hover_color="#B71C1C",
            state="disabled"
        )
        self.cancel_compress_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # --- Uncompression Frame ---
        self.uncompress_frame = ctk.CTkFrame(self, corner_radius=10)
        self.uncompress_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.uncompress_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.uncompress_frame, text="Uncompress Archive", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=3, padx=10, pady=(10, 15)
        )

        ctk.CTkButton(self.uncompress_frame, text="Select Archive", command=self.select_source_uncompress).grid(
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

        # Add button frame for uncompress/cancel
        self.uncompress_btn_frame = ctk.CTkFrame(self.uncompress_frame, fg_color="transparent")
        self.uncompress_btn_frame.grid(row=3, column=0, columnspan=3, padx=20, pady=(15, 10), sticky="ew")
        self.uncompress_btn_frame.grid_columnconfigure(0, weight=1)
        self.uncompress_btn_frame.grid_columnconfigure(1, weight=1)
        
        self.uncompress_button = ctk.CTkButton(
            self.uncompress_btn_frame, 
            text="Uncompress", 
            command=self.start_uncompression, 
            state="disabled"
        )
        self.uncompress_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        self.cancel_uncompress_button = ctk.CTkButton(
            self.uncompress_btn_frame, 
            text="Cancel", 
            command=self.cancel_operation,
            fg_color="#D32F2F",
            hover_color="#B71C1C",
            state="disabled"
        )
        self.cancel_uncompress_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # --- Progress Bar ---
        self.progress_bar = ctk.CTkProgressBar(self, orientation="horizontal", mode="determinate")
        self.progress_bar.grid(row=2, column=0, padx=20, pady=(10, 0), sticky="ew")
        self.progress_bar.set(0)  # Initial state

        # --- Resource Monitor ---
        self.resource_monitor_label = ctk.CTkLabel(self, textvariable=self.resource_label, anchor="w")
        self.resource_monitor_label.grid(row=3, column=0, padx=20, pady=(5, 0), sticky="ew")

        # --- Status Bar ---
        self.status_label = ctk.CTkLabel(self, text="Ready", anchor="w")
        self.status_label.grid(row=4, column=0, padx=20, pady=(5, 10), sticky="ew")

        # Configure protocol for clean shutdown
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Update button states initially
        self.update_button_states()

    def on_closing(self):
        """Handle application closing."""
        # If a task is running, ask for confirmation
        if self.current_task_thread and self.current_task_thread.is_alive():
            if messagebox.askyesno("Confirm Exit", "An operation is in progress. Are you sure you want to exit?"):
                self.cancel_operation()
                # Give a moment for threads to clean up
                time.sleep(0.5)
                self.destroy()
        else:
            self.destroy()

    def update_resource_display(self):
        """Update the resource monitor display."""
        try:
            # Get current RAM usage
            memory_percent = psutil.virtual_memory().percent
            # Get current CPU usage (for this process)
            cpu_percent = psutil.Process().cpu_percent(interval=0.1)
            
            self.resource_label.set(f"Memory: {memory_percent:.1f}%, CPU: {cpu_percent:.1f}%")
            
            # If memory usage is high, change color
            if memory_percent > 85:
                self.resource_monitor_label.configure(text_color="#FF5252")  # Red
            elif memory_percent > 70:
                self.resource_monitor_label.configure(text_color="#FFC107")  # Amber
            else:
                self.resource_monitor_label.configure(text_color=None)  # Default
            
            # Schedule next update if not cancelled
            if not self.cancel_event.is_set():
                self.resource_check_after_id = self.after(1000, self.update_resource_display)
                
        except Exception as e:
            logger.warning(f"Error updating resource display: {e}")
            # Re-schedule anyway
            self.resource_check_after_id = self.after(1000, self.update_resource_display)

    def cancel_resource_monitoring(self):
        """Cancel the resource display updates."""
        if self.resource_check_after_id:
            self.after_cancel(self.resource_check_after_id)
            self.resource_check_after_id = None
            self.resource_label.set("Memory: --%, CPU: --%")

    def update_status(self, message: str, clear_progress=False):
        """Updates the status label (thread-safe)."""
        def _update():
            self.status_label.configure(text=message)
            if clear_progress:
                self.progress_bar.set(0)
        self.after(0, _update)  # Schedule update in the main thread

    def update_progress(self, current: int, total: int):
        """Updates the progress bar (thread-safe)."""
        def _update():
            if total > 0:
                progress = float(current) / total
                self.progress_bar.set(progress)
                
                # Update the status with percentage
                percentage = int(progress * 100)
                current_mb = current / (1024 * 1024)
                total_mb = total / (1024 * 1024)
                
                if current_mb > 1 and total_mb > 1:
                    # Only show MB information for larger files
                    self.status_label.configure(
                        text=f"Processing: {percentage}% ({current_mb:.1f} MB / {total_mb:.1f} MB)"
                    )
                else:
                    self.status_label.configure(text=f"Processing: {percentage}%")
            else:
                self.progress_bar.set(0)  # Handle zero total case
                self.status_label.configure(text="Processing...")
        self.after(0, _update)  # Schedule update in the main thread

    def update_button_states(self, operation_running=False):
        """Enable/disable buttons based on selected paths and operation state."""
        compress_ready = bool(self.source_path.get())  # Only need source now
        uncompress_ready = bool(self.source_zip_path.get() and self.extract_path.get())
        
        if operation_running:
            # Disable all action buttons during operation
            self.compress_button.configure(state=ctk.DISABLED)
            self.uncompress_button.configure(state=ctk.DISABLED)
            # Enable cancel buttons
            self.cancel_compress_button.configure(state=ctk.NORMAL)
            self.cancel_uncompress_button.configure(state=ctk.NORMAL)
        else:
            # Normal state - enable/disable based on input fields
            self.compress_button.configure(state=ctk.NORMAL if compress_ready else ctk.DISABLED)
            self.uncompress_button.configure(state=ctk.NORMAL if uncompress_ready else ctk.DISABLED)
            # Disable cancel buttons
            self.cancel_compress_button.configure(state=ctk.DISABLED)
            self.cancel_uncompress_button.configure(state=ctk.DISABLED)

    def cancel_operation(self):
        """Cancel the current operation if one is running."""
        if self.current_task_thread and self.current_task_thread.is_alive():
            self.cancel_event.set()
            self.update_status("Cancelling operation... Please wait.")
            # Note: The thread will clean up and reset states when it completes
        else:
            self.update_status("No operation in progress to cancel.")

    def update_output_label(self, source_path=None):
        """Updates the output label with the generated filename."""
        if source_path:
            zip_path = utils.get_default_zip_path(source_path)
            filename = zip_path.name
            self.target_zip_path.set(str(zip_path))
            self.output_label.set(f"Desktop/{filename}")
        else:
            self.target_zip_path.set("")
            # Clear the field to show placeholder text
            self.output_label.set("")

    def select_source_compress(self):
        """Select source file(s) or directory for compression."""
        # Ask for directory first
        path = filedialog.askdirectory(title="Select Folder to Compress")
        
        if not path:  # If directory selection was cancelled, ask for file(s)
            paths = filedialog.askopenfilenames(title="Select File(s) to Compress")
            
            if paths:  # If files were selected
                if len(paths) == 1:
                    # Single file selected
                    path = paths[0]
                    self.source_path.set(path)
                    self.update_status(f"Selected source: {Path(path).name}")
                else:
                    # Multiple files selected
                    # Store the list of paths as a semicolon-separated string
                    path = ";".join(paths)
                    self.source_path.set(path)
                    self.update_status(f"Selected {len(paths)} files for compression")
        
        if path:  # Either directory or file(s) were selected
            if ";" not in path:  # Single path (directory or file)
                self.source_path.set(path)
                # Update the output label with auto-generated filename
                self.update_output_label(path)
            else:
                # For multiple files, we've already set the path and status above
                # Use the first file for generating the default output name
                first_file = path.split(";")[0]
                self.update_output_label(first_file)
                
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
            suggested_dir_name = zip_p.stem  # Suggest folder name based on zip name
            initial_dir = zip_p.parent
            self.extract_path.set(str(initial_dir / suggested_dir_name))  # Pre-fill suggestion
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

    def select_save_location(self):
        """Select custom save location for compressed file."""
        path = filedialog.askdirectory(title="Select Save Location")
        if path:
            self.output_label.set(path)
            self.update_status(f"Selected save location: {Path(path).name}")
        self.update_button_states()

    def _run_task(self, task_func, *args):
        """Runs a given task in a separate thread to avoid blocking the UI."""
        # Reset cancel event
        self.cancel_event.clear()
        
        def task_wrapper():
            success = False
            try:
                # Update UI to show operation is starting
                self.after(0, lambda: self.update_button_states(operation_running=True))
                self.progress_bar.start()  # Indeterminate mode while starting
                self.progress_bar.configure(mode="determinate")
                self.progress_bar.set(0)
                
                # Start resource monitoring
                self.after(0, self.update_resource_display)
                
                # Run the task with progress callback and cancel event
                task_func(*args, progress_callback=self.update_progress, cancel_event=self.cancel_event)
                
                # Only mark as complete if not cancelled
                if not self.cancel_event.is_set():
                    operation_name = task_func.__name__.split('_')[0].capitalize()
                    self.update_status(f"{operation_name} operation complete.", clear_progress=True)
                    success = True
                else:
                    self.update_status("Operation cancelled by user.", clear_progress=True)
                    
            except FileNotFoundError as e:
                logger.error(f"Error: {e}")
                messagebox.showerror("Error", f"File not found:\n{e}")
                self.update_status(f"Error: File not found.", clear_progress=True)
            except (zipfile.BadZipFile, ValueError) as e:
                logger.error(f"Error: {e}")
                messagebox.showerror("Error", f"Invalid file or operation:\n{e}")
                self.update_status(f"Error: Invalid file.", clear_progress=True)
            except MemoryError:
                logger.error("Memory limit exceeded")
                messagebox.showerror(
                    "Resource Error", 
                    "The operation was aborted because your system is running low on memory. "
                    "Try closing other applications or processing smaller files."
                )
                self.update_status("Error: Memory limit exceeded.", clear_progress=True)
            except InterruptedError:
                # This is expected when cancelled, already handled
                pass
            except Exception as e:
                logger.exception("An unexpected error occurred")  # Log full traceback
                messagebox.showerror(
                    "Error", 
                    f"An unexpected error occurred:\n{e}\n\n"
                    f"Check the log file for details."
                )
                self.update_status(f"Error: {e}", clear_progress=True)
            finally:
                # Clean up UI state
                self.progress_bar.stop()
                self.progress_bar.set(0)
                
                # Stop resource monitoring
                self.after(0, self.cancel_resource_monitoring)
                
                # Re-enable buttons
                self.after(0, lambda: self.update_button_states(operation_running=False))
                
                # Reset cancel event
                self.cancel_event.clear()
                
                # Reference cleanup
                self.current_task_thread = None
                
                # Reset output label if compression was successful
                if success and task_func.__name__ == "compress_item":
                    self.after(0, lambda: self.update_output_label())

        # Disable buttons during operation
        self.update_button_states(operation_running=True)

        # Start the task thread
        self.current_task_thread = threading.Thread(target=task_wrapper, daemon=True)
        self.current_task_thread.start()

    def start_compression(self):
        """Starts the compression process in a new thread."""
        source = self.source_path.get()
        custom_output = self.output_label.get()
        
        if not source:
            messagebox.showwarning("Missing Info", "Please select a source file or folder to compress.")
            return
            
        # Handle custom output location if provided
        if custom_output and custom_output != "Output will be saved to Desktop":
            # Check if a custom path was provided
            output_path = Path(custom_output)
            
            # If the path is a directory, generate a filename within it
            if os.path.isdir(custom_output):
                filename = Path(utils.generate_filename(source) + ".zip").name
                target = str(output_path / filename)
            else:
                # If it's not an existing directory, assume it's a complete path including filename
                # Make sure it has .zip extension
                if not custom_output.lower().endswith('.zip'):
                    custom_output += '.zip'
                target = custom_output
        else:
            # Use default path
            target = str(utils.get_default_zip_path(source))
            
        self.target_zip_path.set(target)
            
        # Create parent directory if it doesn't exist
        os.makedirs(Path(target).parent, exist_ok=True)

        self.update_status(f"Starting compression to {Path(target).name}...")
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
    logger.info("Starting Zip Utility Application")
    app = ZipApp()
    app.mainloop()

if __name__ == "__main__":
    run_app()