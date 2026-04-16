# SocWatch Post-Processor (socwatch_pp)

A simple Python tool for batch processing SocWatch .etl files using socwatch.exe.

## Features

- 🖥️ **GUI Mode** - Easy folder selection with graphical interface
- 💻 **CLI Mode** - Command-line interface for automation/scripting
- 🌐 **Network Path Support** - Seamlessly process files from network shares (UNC paths)
- 🔍 **Auto-discovery** of SocWatch installations with flexible directory support
- 📁 **Recursive scanning** for .etl files in input folders
- 🎯 **Automated processing** using file prefixes as input parameters
- ⏱️ **Time slicing** - Process specific time ranges from traces (supports multiple slices per file)
- 📊 **Export Formats** - Generate `.swjson` (`-r json`), VTune `.pwr` (`-r vtune`), or over-time `_trace.csv` (`-r int`) outputs
- 📈 **Comprehensive reporting** of processing results
- ✅ **Simple single-file solution** - no external dependencies
- 🛠️ **Flexible SocWatch location** - supports custom installation paths
- 🧹 **Clean output** - No unnecessary subdirectories, automatic temp cleanup

## Requirements

- Python 3.6 or higher
- SocWatch installation (auto-detected or manually specified)
- Windows environment (uses socwatch.exe)

## Installation

1. **Clone or download** the script:
   ```bash
   git clone <repository-url>
   cd socwatch_post_proc
   ```

2. **No additional dependencies** required - uses only Python standard library!

## Usage

### GUI Mode (Default)

Simply run without arguments to open folder selection dialog:

```bash
python socwatch_pp.py
```

This will:
1. 📂 Open a folder selection dialog
2. 🔍 Show SocWatch version selection dialog
3. 📊 Display progress in console
4. ✅ Show completion dialog with results

### CLI Mode

```bash
python socwatch_pp.py <input_folder>
```

### Examples

```bash
# GUI mode - select folder using dialog
python socwatch_pp.py

# CLI mode - use specified folder
python socwatch_pp.py C:\data\socwatch_traces

# Process files from network share
python socwatch_pp.py \\server\share\data\socwatch_traces

# CLI mode - process current directory
python socwatch_pp.py .

# Force CLI mode (useful for scripting)
python socwatch_pp.py --cli C:\data\socwatch_traces

# Use custom SocWatch installation directory
python socwatch_pp.py --socwatch-dir D:\MySocWatch C:\data\traces

# Use custom output directory (saves results to different location)
python socwatch_pp.py -o D:\results C:\data\traces
python socwatch_pp.py --output-dir D:\results C:\data\traces

# Export .swjson format with extra details
python socwatch_pp.py -r json C:\data\traces

# Export VTune .pwr format
python socwatch_pp.py -r vtune C:\data\traces

# Export over-time interval data (_trace.csv)
python socwatch_pp.py -r int C:\data\traces

# Force reprocessing even if output already exists
python socwatch_pp.py -f C:\data\traces
python socwatch_pp.py --force C:\data\traces

# Process with time slice (1000ms to 15000ms)
python socwatch_pp.py --slice-range 1000,15000 C:\data\traces

# Process multiple time slices from the same .etl file
python socwatch_pp.py --slice-range 1000,5000 --slice-range 10000,15000 C:\data\traces
python socwatch_pp.py --slice-range 0,10000 --slice-range 20000,30000 --slice-range 40000,50000 C:\data\traces

# Combine options (CLI mode with custom SocWatch directory, output, slicing, and JSON export)
python socwatch_pp.py --cli --socwatch-dir C:\Intel\SocWatch -o D:\results -r json --slice-range 1000,15000 C:\data\traces

# Force reprocessing with JSON export and custom output
python socwatch_pp.py --force -r json -o D:\results C:\data\traces

# Show help
python socwatch_pp.py --help
```

## Force Reprocessing

The `-f` or `--force` option allows you to reprocess .etl files even if output files already exist:

- **Format**: `-f` or `--force` (no additional arguments needed)
- **Behavior**: Bypasses the skip detection logic that normally skips already-processed collections
- **Use Cases**:
  - Regenerate reports with updated SocWatch version
  - Reprocess after manual deletion of partial results
  - Override previous processing that may have been incomplete
  - Force reanalysis with different SocWatch settings

**Example Usage:**
```bash
# Reprocess all traces even if output exists
python socwatch_pp.py --force C:\data\traces

# Force reprocessing with JSON export
python socwatch_pp.py -f -r json C:\data\traces

# Combine with other options
python socwatch_pp.py --force --slice-range 1000,15000 -o D:\results C:\data\traces
```

**Default Behavior (without --force):**
- Checks if `{workload_name}.csv` exists
- Checks if `{workload_name}_WakeupAnalysis.csv` exists
- Skips processing if either file is found
- Displays: "⏭️  Skipping - already processed (use --force to reprocess)"

**With --force:**
- Ignores existing output files
- Always processes the .etl files
- Overwrites existing output

## Time Slicing Feature

The `--slice-range` option allows you to process specific time ranges from SocWatch traces:

- **Format**: `--slice-range <start_ms>,<end_ms>` where times are in milliseconds
- **Multiple Slices**: You can specify `--slice-range` multiple times to process different time windows
- **Output Naming**: Each slice generates files with `_slice_<start>-<end>ms` suffix (e.g., `workload_slice_1000-15000ms.csv`)
- **Use Cases**:
  - Extract specific test phases from long traces
  - Compare different time periods of the same workload
  - Focus analysis on regions of interest
  - Generate multiple reports from a single collection

**Example Workflow:**
```bash
# Process entire trace normally
python socwatch_pp.py C:\data\long_test

# Then extract specific phases with slicing
python socwatch_pp.py --slice-range 5000,15000 --slice-range 30000,40000 C:\data\long_test
# This generates: workload_slice_5000-15000ms.csv and workload_slice_30000-40000ms.csv
```

## JSON Export Feature

The `-r json` option enables export of trace data in `.swjson` format with enhanced details:

- **Format**: `-r json`
- **SocWatch Flags**: Automatically passes `-m` (detailed metrics) and `-r json` (JSON report) to socwatch.exe
- **Output**: Generates `.swjson` files alongside standard CSV reports
- **Use Cases**:
  - Advanced data analysis with custom tools
  - Integration with automated pipelines
  - Parsing with swjson_parser.py for event visualization
  - Detailed event timeline analysis (NPU, GPU, CPU metrics)

**Example Usage:**
```bash
# Export trace data in .swjson format
python socwatch_pp.py -r json C:\data\traces

# Combine with time slicing
python socwatch_pp.py -r json --slice-range 1000,15000 C:\data\traces

# Full workflow: export JSON, slice time range, and save to custom location
python socwatch_pp.py -r json --slice-range 5000,15000 -o D:\results C:\data\traces
```

**What gets generated:**
- Standard CSV reports (as usual)
- `.swjson` files with detailed event data
- Event timeline data for visualization
- Enhanced metrics enabled by the `-m` flag

**Note:** The `.swjson` files can be analyzed using the `swjson_parser.py` tool in the `parsing-suite` folder for event visualization and metrics extraction.

## VTune Export Feature

The `-r vtune` option enables VTune-compatible `.pwr` export:

- **Format**: `-r vtune`
- **SocWatch Flags**: Passes `-r vtune` to socwatch.exe
- **Output**: Generates `.pwr` files alongside standard CSV reports

**Example Usage:**
```bash
# Export VTune .pwr output
python socwatch_pp.py -r vtune C:\data\traces

# Combine with slicing and custom output
python socwatch_pp.py -r vtune --slice-range 1000,15000 -o D:\results C:\data\traces
```

## Interval Export Feature

The `-r int` option exports per-interval (over-time) data in `_trace.csv` format:

- **Format**: `-r int`
- **SocWatch Flags**: Passes only `-r int` to socwatch.exe (no `-m` flag)
- **Output**: Generates `{workload}_trace.csv` with per-interval metric values
- **Use Cases**:
  - Analyze how power/performance metrics change over time
  - Plot time-series charts of CPU/GPU/memory activity
  - Identify transient events or ramp-up behavior

**Example Usage:**
```bash
# Export over-time interval data
python socwatch_pp.py -r int C:\data\traces

# Combine with custom output directory
python socwatch_pp.py -r int -o D:\results C:\data\traces

# Combine with time slicing
python socwatch_pp.py -r int --slice-range 1000,15000 C:\data\traces
```

**What gets generated:**
- `{workload}_trace.csv` with per-interval metric values over time

**Note:** Unlike `-r json`, the `-r int` flag does **not** add the `-m` (detailed metrics) flag — it passes only `-r int` directly to socwatch.exe.

## How It Works

1. **SocWatch Discovery**: The tool automatically locates SocWatch installations using:
   - Explicit `--socwatch-dir` argument
   - `SOCWATCH_DIR` environment variable  
   - Auto-detection in common locations (D:\socwatch, C:\Intel\SocWatch, etc.)
   - Fallback to default D:\socwatch

2. **Version Selection**: Scans the SocWatch directory for available socwatch.exe versions and lets you choose which one to use.

3. **Network Path Handling**: When processing files from network shares (UNC paths like `\\server\share\...`):
   - Automatically detects network paths
   - Creates a local temporary directory for processing (SocWatch cannot write directly to network locations)
   - Processes files using the local temp directory
   - Copies results back to the network location
   - Cleans up temporary files automatically

4. **File Discovery**: Recursively searches the input folder for all `.etl` files.

5. **Smart Skip Detection**: Before processing, checks if output already exists:
   - Looks for `{workload_name}.csv` summary file
   - Looks for `{workload_name}_WakeupAnalysis.csv` file
   - Looks for `{workload_name}_trace.csv` file (from `-r int`)
   - Skips already-processed collections to save time
   - Can be overridden with `-f` or `--force` flag to reprocess

6. **Batch Processing**: For each .etl file found:
   - Extracts the file prefix (filename without .etl extension)
   - Skips if already processed (summary or wakeup analysis files exist)
   - Runs: `socwatch.exe -i <prefix> -o <output_folder>`
   - With `-r json`: `socwatch.exe -i <prefix> -o <output_folder> -m -r json` (exports `.swjson`)
   - With `-r vtune`: `socwatch.exe -i <prefix> -o <output_folder> -r vtune` (exports `.pwr`)
   - With `-r int`: `socwatch.exe -i <prefix> -o <output_folder> -r int` (exports `_trace.csv`)
   - Changes to the file's directory before processing
   - For network paths: copies results from temp to final location

7. **Clean Output**: 
   - Results are saved directly alongside input files (no subdirectories created)
   - Empty temporary directories are automatically removed
   - Network copies include cleanup of local temp files

8. **Reporting**: Provides a comprehensive report showing:
   - Total files processed
   - Success/failure counts
   - Processing time
   - Details of any failures

## Configuration

### Output Directory

By default, processed results are saved in the same directory as the input .etl files. You can specify a custom output directory:

```bash
# Using shorthand -o option
python socwatch_pp.py -o D:\results C:\data\traces

# Using full --output-dir option
python socwatch_pp.py --output-dir D:\results C:\data\traces

# Save results from network share to local directory
python socwatch_pp.py -o D:\results \\server\share\traces

# Save results back to network share
python socwatch_pp.py -o \\server\share\results C:\data\traces
```

**Important Notes:**
- Results are saved **directly** in the specified output directory (no subdirectories created)
- CSV files are placed alongside the input .etl files
- For network paths: automatic local temp processing with copy-back
- Already-processed collections are automatically skipped

### Network Path Support

The tool fully supports network shares (UNC paths):

```bash
# Process files from network share
python socwatch_pp.py \\10.54.63.126\share\data\traces

# Output to network location
python socwatch_pp.py -o \\server\results \\server\input

# Mixed: network input, local output
python socwatch_pp.py -o D:\local_results \\server\traces
```

**How Network Processing Works:**
1. ⚠️ **Detection**: Automatically detects UNC paths (`\\server\share\...`)
2. 📁 **Local Temp**: Creates temporary directory under `%USERPROFILE%\socwatch_output`
3. ⚡ **Processing**: SocWatch runs using local temp directory (it cannot write to network directly)
4. 📤 **Copy-back**: Results automatically copied to network location
5. 🧹 **Cleanup**: Temporary files and empty directories removed

**Benefits:**
- Transparent to the user - works just like local paths
- Handles SocWatch's limitation with network writes
- Automatic cleanup prevents disk waste
- Smart path mirroring preserves structure

### SocWatch Installation Path

The tool supports multiple ways to specify your SocWatch installation location:

1. **Command-line argument** (highest priority):
   ```bash
   python socwatch_pp.py --socwatch-dir "C:\Intel\SocWatch" C:\data\traces
   ```

2. **Environment variable**:
   ```bash
   # Windows (PowerShell)
   $env:SOCWATCH_DIR="C:\Intel\SocWatch"
   python socwatch_pp.py C:\data\traces
   
   # Windows (Command Prompt)
   set SOCWATCH_DIR=C:\Intel\SocWatch
   python socwatch_pp.py C:\data\traces
   ```

3. **Auto-detection**: The tool will automatically search these common locations:
   - `D:\socwatch`
   - `C:\socwatch`
   - `D:\SocWatch`
   - `C:\SocWatch`
   - `D:\Intel\SocWatch`
   - `C:\Intel\SocWatch`
   - `C:\Program Files\Intel\SocWatch`
   - `C:\Program Files (x86)\Intel\SocWatch`

4. **Default fallback**: Falls back to `D:\socwatch` if no installation is found

## SocWatch Directory Structure

The tool expects SocWatch installations in this structure:

```
D:\socwatch\
├── version1\
│   └── socwatch.exe
├── version2\
│   └── socwatch.exe
└── socwatch.exe          # Also checks base directory
```

## GUI Interface

When running in GUI mode (`python socwatch_pp.py`), you'll see:

1. **📂 Folder Selection Dialog**: Browse and select the folder containing .etl files
2. **🔍 SocWatch Version Dialog**: Choose from available SocWatch installations  
3. **📊 Console Progress**: Real-time processing updates in the console window
4. **✅ Completion Dialog**: Summary of results with success/failure counts

The GUI makes it easy for non-technical users to process SocWatch files without needing to remember command-line syntax.

## Example Output

### CLI Mode Output:
```
🔧 SocWatch Post-Processor (socwatch_pp)
========================================
💻 CLI Mode: Using specified folder
📁 Input folder: \\server\share\data\socwatch_traces

🔍 Available SocWatch versions:
  1. D:\socwatch\v2.1\socwatch.exe
  2. D:\socwatch\v2.2\socwatch.exe

Select version (1-2): 2
✅ Selected: D:\socwatch\v2.2\socwatch.exe

🔍 Found 4 SocWatch session files in 1 collection(s)

🚀 Starting batch processing of 1 collection(s)...
============================================================

[1/1] AI_GPU_model_stripped (Collection)
   ⚠️  Network path detected: SocWatch.exe cannot write to network locations
   � Using local temp directory for processing
   📁 Work directory: C:\Users\username\socwatch_output\...\AI_GPU_model_stripped
   📤 Will copy results to: \\server\share\data\socwatch_traces
📊 Processing collection: AI_GPU_model_stripped
   � Session files: AI_GPU_model_stripped_extraSession.etl, ...
   🔧 SocWatch executable: D:\socwatch\v2.2\socwatch.exe
   📝 Input base name: AI_GPU_model_stripped
   📤 Output directory: C:\Users\username\socwatch_output\...\AI_GPU_model_stripped
   🚀 Starting SocWatch processing (may take several minutes for large files)...
   ✅ Success
   📤 Copying results to: \\server\share\data\socwatch_traces
      ✓ Copied: AI_GPU_model_stripped.csv
      ✓ Copied: AI_GPU_model_stripped_WakeupAnalysis.csv
   ✅ Successfully copied 2 file(s)
   🧹 Cleaned up empty directory: AI_GPU_model_stripped

============================================================
📋 FINAL PROCESSING REPORT
============================================================
📊 Total collections processed: 1
✅ Successfully processed: 1
❌ Failed: 0
📈 Success rate: 100.0%
⏱️  Total time: 18.6 seconds
🔧 Used SocWatch: D:\socwatch\v2.2\socwatch.exe
✨ Processing complete!
```

## Error Handling

The tool handles various error conditions:

- **Missing SocWatch installations**: Clear error messages if no socwatch.exe found
- **Invalid input folders**: Validates folder existence before processing
- **Processing timeouts**: 30-minute timeout per file to prevent hanging
- **SocWatch errors**: Captures and reports socwatch.exe error output
- **File access issues**: Handles permission and path-related errors

## Troubleshooting

### Common Issues

1. **"No SocWatch installations found"**
   - Ensure socwatch.exe exists in `C:\socwatch` or use `--socwatch-dir` to specify location
   - Check file permissions

2. **"Processing timeout"**
   - Some .etl files may be very large and take >30 minutes to process
   - The tool will skip these and continue with other files

3. **"Permission denied"**
   - Run the script with administrator privileges if needed
   - Check write permissions in output directories

4. **Network Path Issues**
   - Ensure network share is accessible and you have write permissions
   - Local temp directory requires sufficient disk space
   - Network copy-back may be slow for large result files

5. **"No output files found" when copying**
   - SocWatch may write files to parent directory instead of specified output
   - Tool automatically searches both locations
   - Check local temp directory: `%USERPROFILE%\socwatch_output`

### Debug Mode

For more detailed output, you can modify the script to add verbose logging by uncommenting debug print statements.

## Customization

The script can be easily customized:

- **Change SocWatch base directory**: Use `--socwatch-dir` argument or set `SOCWATCH_DIR` environment variable
- **Adjust timeout**: Change the `timeout=1800` parameter in `subprocess.run()` (default: 30 minutes)
- **Add more SocWatch arguments**: Extend the `cmd` list in `process_collection()`

## Architecture

The tool uses a clean, modular architecture:

### PathManager Class
Centralized path management that handles:
- Network path detection (UNC paths)
- Local temporary directory creation
- Work directory vs. final directory resolution
- Copy-back requirements

### ProcessingPaths NamedTuple
Clear data structure containing:
- `work_dir`: Where SocWatch writes files (always local)
- `final_dir`: Where files should end up (may be network)
- `needs_copy`: Flag indicating if copy-back is needed

### Key Benefits
- **Clean separation**: Path logic isolated from processing logic
- **Easy debugging**: Clear variable names and structure
- **Network transparency**: Handles local and network paths uniformly
- **Automatic cleanup**: Empty directories removed after processing

## License

This project is open source and available under the MIT License.