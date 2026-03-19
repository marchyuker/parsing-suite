# Teams++.py Guide

## Overview

`Teams++.py` parses mixed workload result folders and generates a consolidated Excel report. It is designed for AI/Teams-style run folders where each dataset can include combinations of:

- Procyon XML result
- DAQ power summary and traces
- Socwatch summary
- ETL files
- PCIe-only socwatch summary

The script recursively scans the input tree, auto-classifies files by naming patterns, parses each recognized source through modules in `parsers/`, then writes a unified workbook.

## What It Parses

The file classifier in `Teams++.py` detects:

- Procyon result XML: file name contains `1h_bl_` and ends with `.xml`
- ETL: file name contains `.etl` but not `Session.etl`
- DAQ summary: file name contains `pacs-summary.csv`
- DAQ traces: file name contains `pacs-traces` and `sr.csv`
- Socwatch session ETL: file name contains `Session.etl`
- Socwatch regular CSV: file name contains `socwatch_regular` and ends with `.csv`

## CLI Usage

```bash
python Teams++.py -i <input_folder> -o <output_base_path> [options]
```

### Arguments

- `-i, --input`: Root folder to scan recursively.
- `-o, --output`: Output base path (without extension is allowed; writer controls final file naming).
- `-c, --config`: Optional config JSON that can override default targets.
- `-d, --daq`: Optional DAQ rail dictionary JSON.
- `-st, --swtarget`: Optional Socwatch target JSON.
- `-hb, --hobl`: HOBL mode; uses `.PASS` / `.FAIL` markers to identify dataset boundaries.

## Default Config Behavior

When `--config` is omitted, the script loads:

- `config/PTL_default.config` (resolved relative to script directory)

This config provides:

- `socwatch_targets`
- `PCIe_targets`
- `DAQ_target`
- `Second_folder_list`

## Dataset Assembly Logic

1. Discover dataset folders recursively.
2. Classify each file by name pattern.
3. Parse detected files using parser modules:
   - `parsers.procyon_xml_parser`
   - `parsers.power_summary_parser`
   - `parsers.power_trace_parser`
   - `parsers.socwatch_summary_parser`
   - `parsers.pcie_socwatch_summary_parser`
4. Aggregate parsed objects into in-memory `hobl_sets`.
5. Run power quality checks via `parsers.power_checker`.
6. Export to Excel via `parsers.reporter.writeParsedAllInExcel`.

## Example

```bash
python Teams++.py ^
  -i "C:\\data\\teams_run" ^
  -o "C:\\data\\teams_run\\teams_parse_output" ^
  -c "config\\PTL_default.config"
```

## Output

- Primary output is an Excel report written by `parsers.reporter`.
- Console prints parsed argument info, detected data summary, and elapsed processing time.

## Notes

- If `-i` is not provided, a folder picker dialog is used.
- In Socwatch handling, both `<workload>.csv` and `<workload>_summary.csv` naming conventions are supported.
- For Procyon XML parsing, score extraction is handled by `parsers.procyon_xml_parser`.
