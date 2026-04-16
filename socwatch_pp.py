#!/usr/bin/env python3
"""
SocWatch Post-Processor (socwatch_pp)

A simple tool to batch process SocWatch .etl files using socwatch.exe.

Features:
- Auto-detects SocWatch installation directory or uses SOCWATCH_DIR environment variable
- User-selectable SocWatch.exe versions from installation directory
- Recursive folder scanning for .etl files (SocWatch 3 or 4)
- Automatic processing with file prefix as input parameter
- Output to same folder as source files
- Comprehensive processing report

Usage:
    python socwatch_pp.py [options] [<input_folder>]
    
Set SOCWATCH_DIR environment variable or use --socwatch-dir to specify installation path.
"""

import os
import sys
import subprocess
import glob
import shutil
from pathlib import Path
from typing import List, Tuple, Dict, Optional, NamedTuple
import time
import datetime
import threading
import tkinter as tk
from tkinter import filedialog, messagebox


class ProcessingPaths(NamedTuple):
    """Container for all path information needed during processing."""
    work_dir: Path      # Where SocWatch writes files (always local)
    final_dir: Path     # Where files should ultimately be (may be network)
    needs_copy: bool    # Whether files need copying from work_dir to final_dir


class PathManager:
    """Centralized path management for input/output directories."""
    
    def __init__(self, input_dir: Path, custom_output_dir: Optional[Path] = None):
        """
        Initialize path manager.
        
        Args:
            input_dir: Directory containing ETL files
            custom_output_dir: Optional custom output directory (from -o/--output-dir)
        """
        self.input_dir = input_dir
        self.custom_output_dir = custom_output_dir
        self.is_network_input = self._is_network_path(input_dir)
        self.local_temp_base = Path.home() / "socwatch_output"
        
    @staticmethod
    def _is_network_path(path: Path) -> bool:
        """Check if path is a UNC network path."""
        return str(path).startswith('\\\\')
    
    def get_processing_paths(self, etl_base_name: str, collection_dir: Optional[Path] = None) -> ProcessingPaths:
        """
        Determine where SocWatch should write files and where they should end up.
        
        Args:
            etl_base_name: Base name from ETL files (e.g., "AI_GPU_model_stripped")
            collection_dir: Actual directory containing the collection files (overrides input_dir)
            
        Returns:
            ProcessingPaths with work_dir, final_dir, and needs_copy flag
        """
        # Use collection_dir if provided, otherwise fall back to input_dir
        actual_input_dir = collection_dir if collection_dir else self.input_dir
        
        # Determine final destination
        if self.custom_output_dir:
            # User specified custom output with -o/--output-dir
            final_dir = self.custom_output_dir
        else:
            # Default: same location as input files (collection's directory)
            final_dir = actual_input_dir
        
        # Determine work directory (where SocWatch actually writes)
        if self._is_network_path(final_dir):
            # Network path (input or custom output): use local temp
            # Mirror the network path structure under local temp
            if len(actual_input_dir.parts) >= 4:
                # Keep last 3 parent folders + etl_base_name for uniqueness
                # Example: Base\gameSOTR_004\socwatch or XeSS\gameSOTR_004\socwatch
                path_suffix = Path(*actual_input_dir.parts[-3:]) / etl_base_name
            elif len(actual_input_dir.parts) >= 2:
                # Keep what we have if less than 4 parts
                path_suffix = Path(*actual_input_dir.parts[-2:]) / etl_base_name
            else:
                path_suffix = Path(etl_base_name)
            work_dir = self.local_temp_base / path_suffix
            needs_copy = True
        else:
            # Local path: write directly to final destination
            work_dir = final_dir
            needs_copy = False
        
        return ProcessingPaths(work_dir=work_dir, final_dir=final_dir, needs_copy=needs_copy)
    
    def log_paths(self, paths: ProcessingPaths):
        """Log path information for debugging."""
        if paths.needs_copy:
            print(f"   ⚠️  Network path detected: SocWatch.exe cannot write to network locations")
            print(f"   💡 Using local temp directory for processing")
            print(f"   📁 Work directory: {paths.work_dir}")
            print(f"   📤 Will copy results to: {paths.final_dir}")
        else:
            print(f"   📁 Output directory: {paths.work_dir}")


class SocWatchProcessor:
    """Main class for SocWatch post-processing operations."""
    
    def __init__(self, socwatch_base_dir: Optional[str] = None, use_gui: bool = True, force: bool = False):
        """
        Initialize SocWatch processor.
        
        Args:
            socwatch_base_dir: Base directory containing SocWatch versions. 
                              If None, will auto-detect or use environment variable.
            use_gui: Whether to use GUI for folder selection and dialogs
            force: Whether to force reprocessing even if output already exists
        """
        self.socwatch_base_dir = self._resolve_socwatch_dir(socwatch_base_dir)
        self.available_versions = []
        self.selected_version = None
        self.processed_files = []
        self.failed_files = []
        self.start_time = None
        self.use_gui = use_gui
        self.root = None
        self.custom_output_dir = None
        self.path_manager = None  # Will be initialized when input folder is known
        self.slice_ranges = []  # List of slice ranges in format [(start, end), ...]
        self.export_format = None  # Format to export (e.g., 'json' for .swjson)
        self.force = force  # Force reprocessing flag
        
    def _validate_slice_range(self, slice_range: str) -> Optional[Tuple[int, int]]:
        """
        Validate and parse slice range format (e.g., "1000,15000").
        
        Args:
            slice_range: String in format "start,end" (milliseconds)
            
        Returns:
            Tuple of (start, end) if valid, None otherwise
        """
        try:
            parts = slice_range.strip().split(',')
            if len(parts) != 2:
                print(f"❌ Invalid slice range format: {slice_range} (expected 'start,end')")
                return None
            start, end = int(parts[0].strip()), int(parts[1].strip())
            if start < 0:
                print(f"❌ Invalid slice range: start time cannot be negative ({start})")
                return None
            if end <= start:
                print(f"❌ Invalid slice range: end time ({end}) must be greater than start time ({start})")
                return None
            return (start, end)
        except (ValueError, AttributeError) as e:
            print(f"❌ Invalid slice range format: {slice_range} (error: {e})")
            return None
    
    def _is_already_processed(self, output_dir: Path, etl_base_name: str) -> bool:
        """
        Check if collection has already been processed.
        
        Args:
            output_dir: Directory to check for existing files
            etl_base_name: Base name of the ETL files
            
        Returns:
            True if already processed, False otherwise
        """
        # Check for both naming patterns
        summary_csv = output_dir / f"{etl_base_name}.csv"
        summary_csv_alt = output_dir / f"{etl_base_name}_summary.csv"
        wakeup_csv = output_dir / f"{etl_base_name}_WakeupAnalysis.csv"
        vtune_pwr = output_dir / f"{etl_base_name}.pwr"
        trace_csv = output_dir / f"{etl_base_name}_trace.csv"
        
        return summary_csv.exists() or summary_csv_alt.exists() or wakeup_csv.exists() or vtune_pwr.exists() or trace_csv.exists()
    
    def _copy_results_to_final(self, work_dir: Path, final_dir: Path, etl_base_name: str):
        """
        Copy generated files from work directory to final destination.
        
        Args:
            work_dir: Where SocWatch wrote files (local temp)
            final_dir: Where files should end up (network location)
            etl_base_name: Base name of ETL files for filtering
        """
        print(f"   📤 Copying results to: {final_dir}")
        try:
            # Find generated files with the ETL base name
            # SocWatch may write to work_dir or its parent
            patterns = ['*.csv', '*.html', '*.json', '*.swjson', '*.txt', '*.xml', '*.pwr']
            generated_files = []
            
            search_dirs = [work_dir, work_dir.parent]
            for search_dir in search_dirs:
                if search_dir.exists():
                    for pattern in patterns:
                        for file in search_dir.glob(pattern):
                            if file.name.startswith(etl_base_name) and file.is_file():
                                if file not in generated_files:
                                    generated_files.append(file)
            
            if generated_files:
                # Ensure destination exists
                final_dir.mkdir(parents=True, exist_ok=True)
                
                copied_count = 0
                for file_path in generated_files:
                    dest_path = final_dir / file_path.name
                    shutil.copy2(file_path, dest_path)
                    copied_count += 1
                    print(f"      ✓ Copied: {file_path.name}")
                
                print(f"   ✅ Successfully copied {copied_count} file(s)")
                
                # Clean up: Remove empty work_dir if it exists and is empty
                # (SocWatch creates it but writes to parent)
                try:
                    if work_dir.exists() and work_dir.is_dir():
                        # Check if directory is empty
                        if not any(work_dir.iterdir()):
                            work_dir.rmdir()
                            print(f"   🧹 Cleaned up empty directory: {work_dir.name}")
                except Exception as cleanup_err:
                    # Don't fail the whole operation if cleanup fails
                    print(f"   💡 Note: Could not remove empty directory: {cleanup_err}")
            else:
                print(f"   ⚠️  No output files found starting with: {etl_base_name}")
                print(f"   💡 Searched in: {work_dir} and {work_dir.parent}")
        except Exception as e:
            print(f"   ⚠️  Warning: Failed to copy files: {e}")
            print(f"   💡 Files may still be available at: {work_dir}")
    
    def _resolve_socwatch_dir(self, socwatch_base_dir: Optional[str]) -> Path:
        """
        Resolve SocWatch base directory from various sources.
        
        Priority order:
        1. Explicitly provided socwatch_base_dir parameter
        2. SOCWATCH_DIR environment variable
        3. Auto-detection in common locations
        4. Default fallback
        
        Args:
            socwatch_base_dir: Explicitly provided directory path
            
        Returns:
            Path object for the SocWatch base directory
        """
        # 1. Use explicitly provided directory
        if socwatch_base_dir:
            path = Path(socwatch_base_dir)
            if path.exists():
                print(f"✅ Using provided SocWatch directory: {path}")
                return path
            else:
                print(f"⚠️  Provided SocWatch directory doesn't exist: {path}")
        
        # 2. Check environment variable
        env_dir = os.environ.get('SOCWATCH_DIR')
        if env_dir:
            path = Path(env_dir)
            if path.exists():
                print(f"✅ Using SocWatch directory from SOCWATCH_DIR environment variable: {path}")
                return path
            else:
                print(f"⚠️  SOCWATCH_DIR environment variable points to non-existent directory: {path}")
        
        # 3. Auto-detection in common locations
        common_paths = [
            Path("C:/socwatch"),
            Path("D:/socwatch"),
            Path("C:/SocWatch"),
            Path("D:/SocWatch"),
            Path("C:/Intel/SocWatch"),
            Path("D:/Intel/SocWatch"),
            Path("C:/Program Files/Intel/SocWatch"),
            Path("C:/Program Files (x86)/Intel/SocWatch"),
        ]
        
        for path in common_paths:
            if path.exists():
                # Check if socwatch.exe exists directly in the path
                if (path / "socwatch.exe").exists():
                    print(f"✅ Auto-detected SocWatch directory: {path}")
                    return path
                # Check if socwatch.exe exists in any subdirectory
                for item in path.iterdir():
                    if item.is_dir() and (item / "socwatch.exe").exists():
                        print(f"✅ Auto-detected SocWatch directory: {path}")
                        return path
        
        # 4. Default fallback (original hardcoded path)
        default_path = Path("D:/socwatch")
        print(f"⚠️  Using default SocWatch directory (may not exist): {default_path}")
        print(f"💡 Tip: Set SOCWATCH_DIR environment variable or use --socwatch-dir argument")
        return default_path
        
    def discover_socwatch_versions(self) -> List[Path]:
        """
        Discover available SocWatch versions in the base directory.
        
        Returns:
            List of paths to socwatch.exe files
        """
        versions = []
        if not self.socwatch_base_dir.exists():
            print(f"❌ SocWatch base directory not found: {self.socwatch_base_dir}")
            return versions
            
        # Look for socwatch.exe in subdirectories
        for item in self.socwatch_base_dir.iterdir():
            if item.is_dir():
                socwatch_exe = item / "socwatch.exe"
                if socwatch_exe.exists():
                    versions.append(socwatch_exe)
                    
        # Also check the base directory itself
        base_socwatch = self.socwatch_base_dir / "socwatch.exe"
        if base_socwatch.exists():
            versions.append(base_socwatch)
            
        self.available_versions = sorted(versions)
        return self.available_versions
    
    def select_folder_gui(self) -> Path:
        """
        Show GUI folder selection dialog.
        
        Returns:
            Selected folder path, or None if cancelled
        """
        if not self.use_gui:
            return None
            
        # Create root window if it doesn't exist
        if not self.root:
            self.root = tk.Tk()
            self.root.withdraw()  # Hide the main window
            
        # Show folder selection dialog
        folder_path = filedialog.askdirectory(
            title="Select folder containing SocWatch .etl files",
            mustexist=True
        )
        
        if folder_path:
            return Path(folder_path)
        else:
            return None
    
    def select_socwatch_version(self) -> bool:
        """
        Present available SocWatch versions to user for selection.
        Uses GUI if enabled, otherwise command line.
        
        Returns:
            True if version selected, False otherwise
        """
        print(f"🔧 Discovering SocWatch versions (GUI mode: {self.use_gui})...")
        versions = self.discover_socwatch_versions()
        
        if not versions:
            error_msg = f"No SocWatch installations found!\nPlease ensure socwatch.exe exists in or under: {self.socwatch_base_dir}"
            if self.use_gui:
                if not self.root:
                    self.root = tk.Tk()
                    self.root.withdraw()
                messagebox.showerror("SocWatch Not Found", error_msg)
            else:
                print("❌ " + error_msg.replace('\n', '\n   '))
            return False
        
        print(f"🔍 Found {len(versions)} SocWatch version(s)")
        
        # If only one version, auto-select it
        if len(versions) == 1:
            self.selected_version = versions[0]
            print(f"✅ Auto-selected (only version available): {self.selected_version}")
            return True
        
        # Always use console selection for now - GUI dialogs are having issues
        print("📝 Using console selection for SocWatch version...")
        return self._select_version_console(versions)
    
    def _select_version_gui(self, versions: List[Path]) -> bool:
        """GUI version of version selection."""
        if not self.root:
            self.root = tk.Tk()
            self.root.withdraw()
            
        # Create selection dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Select SocWatch Version")
        dialog.geometry("600x400")
        dialog.resizable(True, True)
        
        # Make dialog modal and bring to front
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()
        
        # Center the dialog on screen
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (600 // 2)
        y = (dialog.winfo_screenheight() // 2) - (400 // 2)
        dialog.geometry(f"600x400+{x}+{y}")
        
        # Variables
        selected_version = tk.StringVar()
        result = {'selected': False}
        
        # Main frame
        main_frame = tk.Frame(dialog, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = tk.Label(main_frame, text="Available SocWatch Versions:", 
                              font=('Arial', 12, 'bold'))
        title_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Listbox with scrollbar
        list_frame = tk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, 
                            font=('Consolas', 10))
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)
        
        # Populate listbox
        for version_path in versions:
            listbox.insert(tk.END, str(version_path))
        
        # Select first item by default
        if versions:
            listbox.selection_set(0)
            
        # Button frame
        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        def on_select():
            selection = listbox.curselection()
            if selection:
                idx = selection[0]
                self.selected_version = versions[idx]
                result['selected'] = True
                dialog.destroy()
                
        def on_cancel():
            result['selected'] = False
            dialog.destroy()
            
        # Buttons
        select_btn = tk.Button(button_frame, text="Select", command=on_select,
                              bg='#0078d4', fg='white', font=('Arial', 10))
        select_btn.pack(side=tk.RIGHT, padx=(10, 0))
        
        cancel_btn = tk.Button(button_frame, text="Cancel", command=on_cancel,
                              font=('Arial', 10))
        cancel_btn.pack(side=tk.RIGHT)
        
        # Handle double-click
        def on_double_click(event):
            on_select()
        listbox.bind('<Double-Button-1>', on_double_click)
        
        # Handle Enter key
        def on_enter(event):
            on_select()
        dialog.bind('<Return>', on_enter)
        
        # Add timeout fallback - auto-select first version after 30 seconds
        def auto_select_timeout():
            if dialog.winfo_exists():
                print("⏰ Dialog timeout - auto-selecting first version...")
                if versions:
                    self.selected_version = versions[0]
                    result['selected'] = True
                dialog.destroy()
        
        dialog.after(30000, auto_select_timeout)  # 30 second timeout
        
        # Wait for dialog to close
        try:
            dialog.wait_window()
        except tk.TclError:
            # Dialog was destroyed
            pass
        
        if result['selected']:
            print(f"✅ Selected: {self.selected_version}")
            return True
        else:
            print("❌ Selection cancelled")
            return False
    
    def _select_version_console(self, versions: List[Path]) -> bool:
        """Console version of version selection."""
        print("🔍 Available SocWatch versions:")
        for i, version_path in enumerate(versions, 1):
            print(f"  {i}. {version_path}")
            
        while True:
            try:
                choice = input(f"\nSelect version (1-{len(versions)}): ").strip()
                if not choice:
                    continue
                    
                idx = int(choice) - 1
                if 0 <= idx < len(versions):
                    self.selected_version = versions[idx]
                    print(f"✅ Selected: {self.selected_version}")
                    return True
                else:
                    print(f"❌ Please enter a number between 1 and {len(versions)}")
                    
            except ValueError:
                print("❌ Please enter a valid number")
            except KeyboardInterrupt:
                print("\n❌ Selection cancelled")
                return False
    
    def find_etl_files(self, input_folder: Path) -> List[Dict]:
        """
        Recursively find all .etl files and group them by SocWatch collections.
        
        Args:
            input_folder: Root folder to search
            
        Returns:
            List of collection info dicts
        """
        if not input_folder.exists():
            print(f"❌ Input folder not found: {input_folder}")
            return []
            
        print(f"🔍 Scanning for SocWatch session files in: {input_folder}")
        
        # Use glob to recursively find SocWatch session files (ending with "Session.etl")
        try:
            pattern = str(input_folder / "**" / "*Session.etl")
            print(f"🔍 Search pattern: {pattern}")
            all_etl_files = [Path(f) for f in glob.glob(pattern, recursive=True)]
            print(f"🔍 Raw glob results: {len(all_etl_files)} SocWatch session files found")
        except Exception as e:
            print(f"❌ Error during file search: {e}")
            return []
        
        # Group SocWatch session files by directory and detect collections
        collections = {}
        
        for etl_file in all_etl_files:
            directory = etl_file.parent
            filename = etl_file.stem
            
            # Detect SocWatch session types (all files now end with "Session")
            session_types = ['_extraSession', '_hwSession', '_infoSession', '_osSession']
            base_name = filename
            is_session_file = True  # All files are session files now
            
            # Extract base name by removing session type suffix
            for session_type in session_types:
                if filename.endswith(session_type):
                    base_name = filename[:-len(session_type)]
                    break
            
            # Group by directory and base name
            collection_key = str(directory / base_name)
            
            if collection_key not in collections:
                collections[collection_key] = {
                    'directory': directory,
                    'base_name': base_name,
                    'files': [],
                    'total_size': 0,
                    'is_collection': False
                }
            
            # Add file info
            file_size = etl_file.stat().st_size / (1024 * 1024)  # Size in MB
            collections[collection_key]['files'].append({
                'path': etl_file,
                'filename': filename,
                'size': file_size
            })
            collections[collection_key]['total_size'] += file_size
            
            # Mark as collection if we found session files
            if is_session_file:
                collections[collection_key]['is_collection'] = True
        
        # Convert to processing list
        processing_list = []
        for collection_info in collections.values():
            # If multiple files with same base name, it's likely a collection
            if len(collection_info['files']) > 1:
                collection_info['is_collection'] = True
            
            processing_list.append(collection_info)
        
        print(f"🔍 Found {len(all_etl_files)} SocWatch session files in {len(processing_list)} collection(s)")
        
        # Print detailed list of found collections
        if processing_list:
            print("\n📋 Detected SocWatch collections:")
            print("=" * 50)
            for i, collection in enumerate(processing_list, 1):
                try:
                    relative_path = collection['directory'].relative_to(input_folder)
                    if collection['is_collection']:
                        print(f"  {i:2d}. {collection['base_name']} (Collection)")
                        print(f"      📁 Location: {collection['directory']}")
                        print(f"      📏 Total size: {collection['total_size']:.1f} MB")
                        print(f"      🏷️  Base prefix: {collection['base_name']}")
                        print(f"      📚 Session files:")
                        for file_info in sorted(collection['files'], key=lambda x: x['filename']):
                            print(f"         - {file_info['filename']}.etl ({file_info['size']:.1f} MB)")
                    else:
                        file_info = collection['files'][0]
                        print(f"  {i:2d}. {relative_path / (file_info['filename'] + '.etl')}")
                        print(f"      📁 Location: {collection['directory']}")
                        print(f"      📏 Size: {file_info['size']:.1f} MB")
                        print(f"      🏷️  Prefix: {file_info['filename']}")
                except Exception as e:
                    print(f"  {i:2d}. {collection['base_name']} (Error reading details: {e})")
            print("=" * 50)
        else:
            print("❌ No SocWatch session files (*Session.etl) found in the specified directory and its subdirectories")
            
        return processing_list
    

    def process_collection(self, collection: Dict) -> bool:
        """
        Process a SocWatch collection using socwatch.exe.
        If multiple slice ranges are specified, processes each slice separately.
        
        Args:
            collection: Dictionary containing collection info
            
        Returns:
            True if processing successful, False otherwise
        """
        if not self.selected_version:
            print("❌ No SocWatch version selected")
            return False
        
        # Determine if we need to process multiple slices
        slices_to_process = self.slice_ranges if self.slice_ranges else [None]
        
        overall_success = True
        for slice_idx, slice_range in enumerate(slices_to_process):
            if not self._process_collection_with_slice(collection, slice_range, slice_idx):
                overall_success = False
        
        return overall_success
    
    def _process_collection_with_slice(self, collection: Dict, slice_range: Optional[Tuple[int, int]], slice_idx: int) -> bool:
        """
        Process a single SocWatch collection or file with optional time slice.
        
        Args:
            collection: Dictionary with collection info
            slice_range: Optional tuple of (start_ms, end_ms) for time slicing
            slice_idx: Index of the slice (for display purposes)
            
        Returns:
            True if processing succeeded, False otherwise
        """
        # Get collection info
        etl_base_name = collection['base_name']
        collection_dir = collection['directory']
        
        # Add slice suffix to base name if processing with slice
        if slice_range:
            slice_suffix = f"_slice_{slice_range[0]}-{slice_range[1]}ms"
            etl_base_name = etl_base_name + slice_suffix
            print(f"\n{'='*60}")
            print(f"📊 Processing slice {slice_idx + 1}/{len(self.slice_ranges)}: {slice_range[0]}ms - {slice_range[1]}ms")
            print(f"{'='*60}")
        
        # Get processing paths from PathManager (pass collection_dir for accurate skip detection)
        paths = self.path_manager.get_processing_paths(etl_base_name, collection_dir)
        self.path_manager.log_paths(paths)
        
        # Check if already processed (unless force flag is set)
        if not self.force and self._is_already_processed(paths.final_dir, etl_base_name):
            print(f"   ⏭️  Skipping - already processed (use --force to reprocess)")
            self.processed_files.append(collection)
            return True
        
        # Create work directory (SocWatch.exe requires it to exist)
        paths.work_dir.mkdir(parents=True, exist_ok=True)
        
        # Build socwatch command
        # Note: input_name is the ETL base name, ensuring correct output file naming
        cmd = [
            str(self.selected_version),
            "-i", etl_base_name,
            "-o", str(paths.work_dir)
        ]
        
        # Add export flags if export format is specified
        if self.export_format:
            if self.export_format == 'json':
                cmd.extend(["-m", "-r", self.export_format])
            elif self.export_format == 'vtune':
                cmd.extend(["-r", self.export_format])
            elif self.export_format == 'int':
                cmd.extend(["-r", "int"])
        
        # Add slice range parameter if specified
        if slice_range:
            slice_param = f"{slice_range[0]},{slice_range[1]}"
            cmd.extend(["--result-slice-range", slice_param])
        
        # Log processing info
        if collection['is_collection']:
            print(f"📊 Processing collection: {collection['base_name']}")
            print(f"   📚 Session files: {', '.join([f['filename'] + '.etl' for f in collection['files']])}")
        else:
            print(f"📊 Processing: {collection['files'][0]['filename']}.etl")
        
        print(f"   📁 Working directory: {collection_dir}")
        print(f"   🔧 SocWatch executable: {self.selected_version}")
        print(f"   📝 Input base name: {etl_base_name}")
        print(f"   📤 Output directory: {paths.work_dir}")
        if slice_range:
            print(f"   ⏱️  Time slice: {slice_range[0]}ms - {slice_range[1]}ms")
        print(f"   ⚡ Full command:")
        print(f"      {self.selected_version}")
        print(f"      -i {etl_base_name}")
        print(f"      -o {paths.work_dir}")
        if self.export_format:
            if self.export_format == 'json':
                print(f"      -m -r {self.export_format} (export .swjson with extra details)")
            elif self.export_format == 'vtune':
                print(f"      -r {self.export_format} (export .pwr VTune results)")
            elif self.export_format == 'int':
                print(f"      -r int (export _trace.csv over-time data)")
        if slice_range:
            print(f"      --result-slice-range {slice_range[0]},{slice_range[1]}")
        
        # Validate command before execution
        if not Path(self.selected_version).exists():
            print(f"   ❌ Error: SocWatch executable not found: {self.selected_version}")
            self.failed_files.append((collection, f"SocWatch executable not found: {self.selected_version}"))
            return False
            
        try:
            # Change to the collection directory where .etl files are located
            original_cwd = os.getcwd()
            os.chdir(collection_dir)
            
            # Run socwatch.exe with extended timeout and real-time output logging
            print(f"   🚀 Starting SocWatch processing (may take several minutes for large files)...")
            print(f"   📝 SocWatch Output Log:")
            print(f"      " + "=" * 60)
            
            # Start subprocess with real-time output
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Log output with timestamps in real-time
            output_lines = []
            try:
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]  # Include milliseconds
                        output_line = output.strip()
                        output_lines.append(output_line)
                        print(f"      [{timestamp}] {output_line}")
                
                # Wait for process to complete with timeout
                try:
                    return_code = process.wait(timeout=1800)  # 30 minute timeout
                except subprocess.TimeoutExpired:
                    process.kill()
                    raise subprocess.TimeoutExpired(cmd, 1800)
                    
            except Exception as e:
                process.kill()
                raise e
            
            print(f"      " + "=" * 60)
            
            # Restore original directory
            os.chdir(original_cwd)
            
            if return_code == 0:
                print(f"   ✅ Success")
                
                # Copy files to final destination if needed
                if paths.needs_copy:
                    self._copy_results_to_final(paths.work_dir, paths.final_dir, etl_base_name)
                
                self.processed_files.append(collection)
                return True
            else:
                print(f"   ❌ Failed (exit code: {return_code})")
                
                # Show detailed error information
                if output_lines:
                    print(f"   📋 Last 15 output lines:")
                    for line in output_lines[-15:]:
                        print(f"      {line}")
                    
                    # Check for common error patterns
                    error_summary = []
                    for line in output_lines:
                        line_lower = line.lower()
                        if any(keyword in line_lower for keyword in ['error', 'failed', 'exception', 'access denied', 'permission']):
                            error_summary.append(line)
                    
                    if error_summary:
                        print(f"   ⚠️  Error indicators found:")
                        for error_line in error_summary[-5:]:  # Show last 5 error lines
                            print(f"      ⚠️  {error_line}")
                    
                    # Check output directory write permission
                    try:
                        test_file = paths.work_dir / ".write_test"
                        test_file.touch()
                        test_file.unlink()
                        print(f"   ✓ Output directory write test: PASSED")
                    except Exception as perm_error:
                        print(f"   ❌ Output directory write test: FAILED - {perm_error}")
                        error_summary.append(f"Write permission issue: {perm_error}")
                    
                    error_output = f"Exit code {return_code}. " + ('\n'.join(error_summary) if error_summary else '\n'.join(output_lines[-10:]))
                else:
                    error_output = f"Exit code {return_code}. No output captured"
                    print(f"   📋 No output captured from SocWatch")
                
                self.failed_files.append((collection, error_output))
                return False
                
        except subprocess.TimeoutExpired:
            print(f"   ❌ Timeout (>30 minutes)")
            self.failed_files.append((collection, "Timeout"))
            return False
        except Exception as e:
            print(f"   ❌ Error: {e}")
            self.failed_files.append((collection, str(e)))
            return False
        finally:
            # Ensure we're back in original directory
            os.chdir(original_cwd)
    
    def process_all_files(self, input_folder: Path) -> None:
        """
        Process all SocWatch collections in the input folder.
        
        Args:
            input_folder: Root folder to process
        """
        # Initialize path manager with input folder
        self.path_manager = PathManager(input_folder, self.custom_output_dir)
        
        self.start_time = time.time()
        collections = self.find_etl_files(input_folder)
        
        if not collections:
            print("❌ No .etl files found to process")
            return
        
        # Show SocWatch command-line information
        print(f"\n🔧 SocWatch Command-Line Information:")
        print("=" * 60)
        print(f"📍 Selected SocWatch: {self.selected_version}")
        print(f"📋 Command pattern: socwatch.exe -i <base_prefix> -o <output_folder>")
        print(f"📖 Options explanation:")
        print(f"   -i <prefix>  : Input base prefix (for collections, use base name)")
        print(f"   -o <folder>  : Output directory (local temp if network source)")
        print(f"💡 Working directory: Changes to each collection's folder before processing")
        print(f"🔍 Collection detection: Groups session files by base name (e.g., CataV3)")
        print("=" * 60)
            
        print(f"\n🚀 Starting batch processing of {len(collections)} collection(s)...")
        print("=" * 60)
        
        for i, collection in enumerate(collections, 1):
            if collection['is_collection']:
                print(f"\n[{i}/{len(collections)}] {collection['base_name']} (Collection)")
            else:
                relative_path = collection['directory'].relative_to(input_folder)
                filename = collection['files'][0]['filename']
                print(f"\n[{i}/{len(collections)}] {relative_path / (filename + '.etl')}")
            self.process_collection(collection)
            
        self.print_final_report()
    
    def print_final_report(self) -> None:
        """Print final processing report."""
        end_time = time.time()
        duration = end_time - self.start_time if self.start_time else 0
        
        print("\n" + "=" * 60)
        print("📋 FINAL PROCESSING REPORT")
        print("=" * 60)
        
        total_collections = len(self.processed_files) + len(self.failed_files)
        success_rate = (len(self.processed_files) / total_collections * 100) if total_collections > 0 else 0
        
        print(f"📊 Total collections processed: {total_collections}")
        print(f"✅ Successfully processed: {len(self.processed_files)}")
        print(f"❌ Failed: {len(self.failed_files)}")
        print(f"📈 Success rate: {success_rate:.1f}%")
        print(f"⏱️  Total time: {duration:.1f} seconds")
        
        if self.processed_files:
            print(f"\n✅ Successfully processed collections:")
            for collection in self.processed_files:
                print(f"   ✓ {collection['base_name']}")
        
        if self.failed_files:
            print(f"\n❌ Failed collections:")
            for collection, error in self.failed_files:
                print(f"   ✗ {collection['base_name']}: {error}")
                
        print(f"\n🔧 SocWatch Configuration Used:")
        print(f"   📍 Executable: {self.selected_version}")
        print(f"   📋 Command pattern: socwatch.exe -i <prefix> -o <output_dir>")
        print("✨ Processing complete!")


def main():
    """Main entry point."""
    print("🔧 SocWatch Post-Processor (socwatch_pp)")
    print("=" * 40)
    
    # Parse command line arguments
    use_gui = True
    input_folder = None
    socwatch_dir = None
    output_dir = None
    export_format = None
    force = False
    slice_ranges_to_add = []  # Collect slice ranges to validate later
    
    args = sys.argv[1:]  # Remove script name
    i = 0
    
    while i < len(args):
        arg = args[i]
        
        if arg in ['-h', '--help', 'help']:
            print("Usage:")
            print("  python socwatch_pp.py [options] [<input_folder>]")
            print("Options:")
            print("  -h, --help                    Show this help message")
            print("  --cli                         Force CLI mode (no GUI dialogs)")
            print("  --socwatch-dir <path>         Specify SocWatch directory or exe (skips version selection)")
            print("  -o, --output-dir <path>       Specify output directory (default: same as input)")
            print("  -f, --force                   Force reprocessing even if output already exists")
            print("  -r <format>                   Export format: 'json' (swjson), 'vtune' (.pwr), or 'int' (_trace.csv over-time data)")
            print("  --slice-range <start,end>     Time slice range in milliseconds (can be specified multiple times)")
            print("\nModes:")
            print("  python socwatch_pp.py                    # GUI mode - select folder with dialog")
            print("  python socwatch_pp.py <input_folder>     # CLI mode - use specified folder")
            print("  python socwatch_pp.py --cli <folder>     # Force CLI mode")
            print("\nExamples:")
            print("  python socwatch_pp.py                              # Open folder selection dialog")
            print("  python socwatch_pp.py C:\\data\\socwatch_traces      # Use specified folder")
            print("  python socwatch_pp.py --cli C:\\data\\traces         # Use CLI mode")
            print("  python socwatch_pp.py --force C:\\data                # Reprocess even if already processed")
            print("  python socwatch_pp.py --output-dir D:\\results C:\\data  # Save results to local directory")
            print("  python socwatch_pp.py --socwatch-dir C:\\socwatch\\2025.5.0 C:\\data  # Skip version selection")
            print("  python socwatch_pp.py -r json C:\\data               # Export .swjson format")
            print("  python socwatch_pp.py -r vtune C:\\data              # Export .pwr VTune format")
            print("  python socwatch_pp.py --slice-range 1000,15000 C:\\data  # Process with time slice")
            print("  python socwatch_pp.py --slice-range 1000,5000 --slice-range 10000,15000 C:\\data  # Multiple slices")
            print("\nNetwork Paths:")
            print("  When source files are on network paths (\\\\server\\share\\...), output is saved")
            print("  to a local directory first, then copied back to the network location after")
            print("  successful processing (SocWatch.exe cannot write directly to network paths).")
            print("\nEnvironment Variables:")
            print("  SOCWATCH_DIR                  SocWatch installation directory")
            return
            
        elif arg == '--cli':
            use_gui = False
            print("💻 CLI Mode (forced)")
            
        elif arg == '--socwatch-dir':
            if i + 1 >= len(args):
                print("❌ --socwatch-dir requires a directory path")
                sys.exit(1)
            socwatch_dir = args[i + 1]
            i += 1  # Skip next argument as it's the directory path
            
        elif arg in ['-o', '--output-dir']:
            if i + 1 >= len(args):
                print("❌ -o/--output-dir requires a directory path")
                sys.exit(1)
            output_dir = Path(args[i + 1])
            i += 1  # Skip next argument as it's the directory path
        
        elif arg in ['-f', '--force']:
            force = True
            print("🔄 Force mode enabled - will reprocess even if output exists")
        
        elif arg == '-r':
            if i + 1 >= len(args):
                print("❌ -r requires a value: 'json' or 'vtune'")
                sys.exit(1)
            r_value = args[i + 1].lower()
            if r_value in ['json', 'vtune', 'int']:
                export_format = r_value
                if r_value == 'json':
                    print(f"📊 .swjson export enabled (will use -m -r {r_value} flags)")
                elif r_value == 'vtune':
                    print(f"📊 VTune export enabled (will use -r {r_value} and generate .pwr)")
                else:
                    print(f"📊 Interval export enabled (will use -r int to generate _trace.csv)")
            else:
                print(f"❌ Invalid value for -r: '{args[i + 1]}'. Expected 'json', 'vtune', or 'int'")
                sys.exit(1)
            i += 1  # Skip next argument as it's the -r value
            
        elif arg == '--slice-range':
            if i + 1 >= len(args):
                print("❌ --slice-range requires a value in format 'start,end' (milliseconds)")
                sys.exit(1)
            slice_range_str = args[i + 1]
            slice_ranges_to_add.append(slice_range_str)
            print(f"📊 Slice range specified: {slice_range_str}")
            i += 1  # Skip next argument as it's the slice range value
            
        elif arg.startswith('--'):
            print(f"❌ Unknown option: {arg}")
            print("Run 'python socwatch_pp.py --help' for usage information")
            sys.exit(1)
            
        else:
            # Assume it's the input folder
            if input_folder is None:
                input_folder = Path(arg)
                use_gui = False
                print("💻 CLI Mode: Using specified folder")
            else:
                print(f"❌ Unexpected argument: {arg}")
                print("Run 'python socwatch_pp.py --help' for usage information")
                sys.exit(1)
        
        i += 1
    
    # If no arguments, use GUI mode
    if len(sys.argv) == 1:
        print("🖥️  GUI Mode: Select folder using dialog")
        use_gui = True
    
    # Initialize processor with force flag
    processor = SocWatchProcessor(socwatch_base_dir=socwatch_dir, use_gui=use_gui, force=force)
    
    # Check if socwatch_dir is a direct path to socwatch.exe
    if socwatch_dir:
        socwatch_path = Path(socwatch_dir)
        if socwatch_path.is_file() and socwatch_path.name.lower() == 'socwatch.exe':
            # Direct path to socwatch.exe provided, skip version selection
            processor.selected_version = socwatch_path
            print(f"✅ Using specified SocWatch executable: {processor.selected_version}")
        elif socwatch_path.is_dir() and (socwatch_path / "socwatch.exe").exists():
            # Directory containing socwatch.exe provided, use it directly
            processor.selected_version = socwatch_path / "socwatch.exe"
            print(f"✅ Using SocWatch executable from specified directory: {processor.selected_version}")
    
    # Set export_format if requested
    processor.export_format = export_format
    
    # Set custom output directory if provided
    if output_dir:
        processor.custom_output_dir = output_dir
        print(f"📁 Custom output directory: {output_dir}")
        # Create output directory if it doesn't exist
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        processor.custom_output_dir = None
    
    # Validate and add slice ranges if provided
    if 'slice_ranges_to_add' in locals() and slice_ranges_to_add:
        print(f"\n📏 Validating {len(slice_ranges_to_add)} slice range(s)...")
        for slice_range_str in slice_ranges_to_add:
            validated = processor._validate_slice_range(slice_range_str)
            if validated:
                processor.slice_ranges.append(validated)
                print(f"   ✅ Valid slice range: {validated[0]}ms - {validated[1]}ms")
            else:
                print(f"   ❌ Skipping invalid slice range: {slice_range_str}")
                sys.exit(1)
        
        if processor.slice_ranges:
            print(f"\n🎯 Will process {len(processor.slice_ranges)} time slice(s) for each .etl file")
    
    # Get input folder
    if use_gui and input_folder is None:
        print("📂 Opening folder selection dialog...")
        input_folder = processor.select_folder_gui()
        if input_folder is None:
            print("❌ No folder selected. Exiting.")
            return
    
    # Validate input folder
    if not input_folder.exists():
        error_msg = f"Input folder does not exist: {input_folder}"
        if use_gui:
            if not processor.root:
                processor.root = tk.Tk()
                processor.root.withdraw()
            messagebox.showerror("Folder Not Found", error_msg)
        else:
            print(f"❌ {error_msg}")
        sys.exit(1)
        
    if not input_folder.is_dir():
        error_msg = f"Input path is not a directory: {input_folder}"
        if use_gui:
            if not processor.root:
                processor.root = tk.Tk()
                processor.root.withdraw()
            messagebox.showerror("Invalid Path", error_msg)
        else:
            print(f"❌ {error_msg}")
        sys.exit(1)
        
    print(f"📁 Input folder: {input_folder}")
    
    # Select SocWatch version (skip if already selected via --socwatch-dir)
    if not processor.selected_version:
        if not processor.select_socwatch_version():
            print("❌ No SocWatch version selected. Exiting.")
            sys.exit(1)
        # Process all files
    try:
        print("🔍 Starting file detection and processing...")
        
        # Note: Removed GUI processing dialog due to hanging issues
        # Users will see progress in terminal window
        
        processor.process_all_files(input_folder)
        
        # Note: Removed GUI completion dialog due to hanging issues
        # Processing results are shown in console output above
        
        if use_gui:
            print("🖥️  GUI Mode: Processing completed - check results above")
            print("💡 You can now close this terminal window")
                
    except KeyboardInterrupt:
        print("\n⚠️  Processing interrupted by user")
        processor.print_final_report()
        sys.exit(1)
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        print(f"❌ {error_msg}")
        if use_gui:
            print("🖥️  GUI Mode: An error occurred - check error message above")
        sys.exit(1)


if __name__ == "__main__":
    main()