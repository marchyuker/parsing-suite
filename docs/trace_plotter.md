# SocWatch Trace CSV Plotter (`trace_plotter.py`)

A standalone Python tool that parses a SocWatch `_trace.csv` file (produced by the `-r int` export flag), separates every event section into individual CSVs, and generates time-series charts grouped by event type.

## Requirements

```bash
pip install pandas matplotlib
```

No additional dependencies — uses only Python standard library alongside pandas and matplotlib.

## Usage

```bash
python trace_plotter.py <input_trace.csv> [options]
python trace_plotter.py --from-csv <csv_dir> [options]
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `-o, --output-dir DIR` | `<stem>_plots/` beside input | Output directory for all results |
| `--from-csv DIR` | — | Load pre-exported section CSVs instead of parsing a raw trace file |
| `--format {png,svg}` | `png` | Image format for charts |
| `--filter PATTERN` | _(all sections)_ | Only process sections whose title matches this Python regex |
| `--list` | — | List all sections and exit without writing any files |
| `--no-csv` | — | Skip individual CSV export |
| `--no-plot` | — | Skip chart generation (CSV export only) |
| `--dpi N` | `150` | Chart resolution in DPI |
| `--interval-only` | — | Only process sampled-interval sections (usec time axis) |
| `--event-only` | — | Only process event/state-transition sections (ms time axis) |

## Examples

```bash
# Full run — export all CSVs and all charts
python trace_plotter.py C:\data\workload_trace.csv

# Output to a specific folder
python trace_plotter.py workload_trace.csv -o D:\results\workload_plots

# Only sampled-interval sections (bandwidth, power, frequency, temperature)
python trace_plotter.py workload_trace.csv --interval-only

# Only event/state-transition sections (C-States, P-States, wakeups)
python trace_plotter.py workload_trace.csv --event-only

# Filter by keyword — only NPU, GPU, and DDR sections
python trace_plotter.py workload_trace.csv --filter "NPU|GPU|DDR"

# Export CSVs only, no charts
python trace_plotter.py workload_trace.csv --no-plot

# Generate SVG charts at higher resolution
python trace_plotter.py workload_trace.csv --format svg --dpi 200

# List all sections and their group keys — no files written
python trace_plotter.py workload_trace.csv --list

# Combine: filter + CSV only + custom output
python trace_plotter.py workload_trace.csv --filter "Throttling" --no-plot -o D:\throttle_debug

# Regenerate all charts from a prior export (no re-parsing of the big trace file)
python trace_plotter.py --from-csv workload_trace_plots\

# Re-plot only DDR sections from a prior export, save to a new folder
python trace_plotter.py --from-csv workload_trace_plots --filter "DDR" -o D:\ddr_charts

# List sections from a prior export
python trace_plotter.py --from-csv workload_trace_plots --list

# Point directly at a sub-directory from a prior export
python trace_plotter.py --from-csv workload_trace_plots\csv\interval --filter "Throttling"
```

## How It Works

### 1. Input File Format

The `_trace.csv` file is produced by SocWatch using the `-r int` flag:

```bash
python socwatch_pp.py -r int C:\data\traces
```

The file has two parts:

- **Meta block** — header lines with SocWatch version, platform info, system name, CPU topology, collection timestamps
- **Data sections** — each section starts with a plain-text title line, followed immediately by a `Sample #, ...` column header line, then data rows

### 2. Section Detection

Sections are detected when a line starting with a letter is followed by a line starting with `Sample #`. Two section types are distinguished by the time-column unit in the column header:

| Type | Time unit | Meaning |
|------|-----------|---------|
| **interval** | `Continuous Time (usec)` | Regularly sampled metrics (bandwidth, power, frequency, temperature, residency) |
| **event** | `Continuous Time (ms)` | State-transition events (C-States, P-States, wakeups, throttling) |

### 3. Grouping

Related sections (e.g. the same metric for all 16 cores) are automatically merged into a single multi-subplot chart. The grouping rules are:

- **CPU topology suffix** — `- CPU/Package_0/Core_X[/Thread_X]` is stripped from the title; cores and threads become subplot labels (`Core_3`, `Thread_5`)
- **Throttling reasons** — `CPU Throttling Reasons - PROCHOT` groups all throttle reasons under `CPU Throttling Reasons`
- **PMT sections** — cluster/package sub-units are grouped similarly
- **Unmatched sections** — each becomes its own single-panel chart

Up to 16 subplots are placed on one chart (4 × 4 grid); if a group has more, the first 16 are shown with a note.

### 4. Chart Types

| Data pattern | Chart style |
|---|---|
| Residency percentage (multi-column) | Stacked-area chart, y-axis 0–100% |
| Residency time (multi-column) | Stacked-area chart, y-axis in µs |
| Bandwidth, power, frequency, temperature (numeric) | Line chart |
| Event/state transitions (categorical) | Step chart with state labels on y-axis |
| Event/state transitions (numeric counts) | Step chart |
| DDR Bandwidth (Instantaneous rate) | **Custom chart** — see [Custom Plot Map](#custom-plot-map) |

### 5. Output Structure

```
<output_dir>/
  _meta.txt                   # Extracted collection metadata
  csv/
    interval/                 # One CSV per interval section
      _index.json             # Section index for --from-csv reload
      IO_Bandwidth.csv
      DDR_Bandwidth_Requests_by_Component_-_DDR.csv
      ...
    event/                    # One CSV per event section
      _index.json
      Core_C-State_(OS).csv
      ...
  plots/
    interval/                 # One PNG (or SVG) per interval group
      IO_Bandwidth.png
      DDR_Bandwidth_Requests_by_Component_-_DDR.png
      Core_C-State_-_Residency_Percentage.png    # 4x4 grid of 16 cores
      ...
    event/                    # One PNG (or SVG) per event group
      Core_C-State_(OS).png
      CPU_Throttling_Reasons.png
      ...
```

The `_index.json` sidecar is written automatically alongside each CSV batch. It stores the section `title`, `group_key`, `sub_label`, and `is_interval` flag so the full grouping and [custom plot](#custom-plot-map) logic is preserved when using `--from-csv`.

## Typical Workflow

```bash
# Step 1: Collect data with SocWatch using the -r int flag
python socwatch_pp.py -r int C:\data\traces

# Step 2: Run the plotter — full output (CSVs + charts)
python trace_plotter.py C:\data\traces\workload_trace.csv

# Step 3: Iterate on charts without re-parsing the big file
python trace_plotter.py --from-csv workload_trace_plots --filter "DDR Bandwidth"

# Step 4: Inspect a focused subset
python trace_plotter.py C:\data\traces\workload_trace.csv \
    --filter "DDR Bandwidth|NPU Power|IGFX P-State" \
    --interval-only -o D:\analysis
```

## --from-csv Mode

Once a trace has been exported to CSV (running without `--no-csv`), charts can be regenerated directly from those CSVs — no need to re-read the original 100+ MB trace file.

```bash
# Point at the output root — loads both csv/interval and csv/event automatically
python trace_plotter.py --from-csv workload_trace_plots

# Point directly at one sub-directory
python trace_plotter.py --from-csv workload_trace_plots\csv\interval

# All normal flags work: filter, format, dpi, list, interval-only, etc.
python trace_plotter.py --from-csv workload_trace_plots --filter "DDR|NPU" -o D:\quick
python trace_plotter.py --from-csv workload_trace_plots --list
python trace_plotter.py --from-csv workload_trace_plots --interval-only --format svg
```

**Requirement:** Each CSV sub-directory must contain an `_index.json` sidecar, which is written automatically whenever CSVs are exported. If `_index.json` is missing, re-run from the original trace to regenerate it.

## Custom Plot Map

Certain sections receive hand-crafted charts instead of the generic defaults. The `CUSTOM_PLOT_MAP` list in `trace_plotter.py` maps a regex against each section's `group_key`; the first match wins.

### Currently customised sections

#### DDR Bandwidth Requests — Instantaneous rate

**Trigger regex:** `DDR Bandwidth Requests.*Instantaneous`

Instead of drawing all 16 per-channel lines at equal weight, this chart:
- Draws every individual channel (READS + WRITES) as a faint grey background line
- Overlays **Total Read** (blue), **Total Write** (orange), and **Total BW** (bold green) as the primary lines
- Adds a dashed horizontal line at the mean Total BW with a labelled annotation box: `Avg Total BW: X.X MB/s`

### Adding a new custom chart

1. Write a draw function with this signature:
   ```python
   def _plot_my_section(ax, df, group_key, sub_label, colors, show_legend):
       ...
   ```
2. Append one entry to `CUSTOM_PLOT_MAP`:
   ```python
   CUSTOM_PLOT_MAP: List[...] = [
       (re.compile(r'DDR Bandwidth.*Instantaneous', re.IGNORECASE), _plot_ddr_bw_instantaneous),
       (re.compile(r'IO Bandwidth.*Instantaneous',  re.IGNORECASE), _plot_my_section),  # new
   ]
   ```

Custom functions are picked up automatically for both raw-parse and `--from-csv` modes.

## Section Inventory

A real trace file from a Panther Lake system typically contains ~370 sections across these categories:

| Category | Examples |
|----------|---------|
| Graphics / Display | Graphics Active State, Display State Entry, Panel Self-Refresh |
| C-State residency | Package/Core/Thread C-State (OS), PMT Package/Cluster C-State |
| P-State / Frequency | Package/Core/Thread P-State, HWP Capabilities, iGPU P-State, NPU P-State, Ring P-State, MEMSS P-State |
| Wakeups | Core Wakeups, Thread Wakeups |
| Power | NPU Power, CPU Package C-State Debug |
| Bandwidth | IO Bandwidth, DDR Bandwidth, Media NoC BW, NPU Memory BW, IPU NoC BW, CCE NoC BW, Display VC1 BW, Network-on-Chip GT/D2D/IO BW, Cluster BW, System Cache BW, HBO BW |
| Temperature | Graphics Temperature, CPU per-core Temperature |
| Throttling | CPU / iGPU / Ring Throttling Reasons (16 reason columns each) |
| Voltage | iGPU Voltage, NPU Voltage |
| C/D-State counts | CPU Package C-State Entrance Count, iGPU C-State, Media C-State, NPU D-State |

Use `--list` to see the exact sections and group keys for any specific trace file.
