# parsing-suite - Unified Workload Parser Framework

A comprehensive framework for parsing and analyzing diverse workload performance data across multiple data formats and sources.

## Overview

**parsing-suite** is the unified entry point for workload-specific data analysis. It provides integrated parsers for handling complex multi-source performance data including Power, Socwatch, ETL, and model throughput metrics.

## Core Parsers

| Parser | Purpose | Link |
|--------|---------|------|
| **ParseAll.py** | Multi-source data aggregation | [Details](./docs/parseall.md) |
| **Phi_summary.py** | Microsoft Phi-Silica SLM analysis | [Details](./docs/phi-summary.md) |
| **Collection_Parser.py** | Collection-based collateral generation | [Details](./docs/collection-parser.md) |
| **CatapultV3_Full_Parser.py** | Full platform profiling | [Details](./docs/catapultv3-full-parser.md) |
| **bm_llama_parser.py** | Llama model analysis | [Details](./docs/llama-parser.md) |
| **SA_ETL_first_epoch.py** | ETL first-epoch analysis | [Details](./docs/sa-etl-first-epoch.md) |
| **socwatch_pp.py** | SocWatch ETL batch post-processor | [Details](./docs/socwatch_pp.md) |
| **trace_plotter.py** | SocWatch `_trace.csv` section splitter and chart generator | [Details](./docs/trace_plotter.md) |
| **Teams++.py** | Teams/AI mixed-source parser with Procyon integration | [Details](./docs/teams-plus-plus.md) |
| **trace_power_slicer.py** | Power trace slicer by rails and time ranges | [Details](./docs/README_trace_slicer.md) |
| **newSW_json_parser.py** | Socwatch JSON event analyzer with visualization | [Details](./docs/newSW_json_parser_usage.md) |
| **vtune_pwr_parser.py** | VTune .pwr parser with ETL auto-generation and streaming event export | Script help: `python vtune_pwr_parser.py --help` |

## Quick Start

### 1. Installation

```bash
# Clone or navigate to parsing-suite
cd parsing-suite

# Install dependencies
pip install -r requirements.txt
```

### 2. Choose Your Parser

**For multi-source aggregation:**
```bash
python ParseAll.py -i <input_path> -o <output_path> [options]
# Optional: provide a full config JSON
python ParseAll.py -i <input_path> -o <output_path> -c <config.json> [options]
```

**For collection-based analysis:**
```bash
python Collection_Parser.py -i <config.json> -o <output_path> [options]
```

**For platform profiling:**
```bash
python CatapultV3_Full_Parser.py [options]
```

**For Phi model analysis:**
```bash
python Phi_summary.py -i <input_path> -o <output_path>
```

**For power trace slicing:**
```bash
python trace_power_slicer.py <trace_file> --config src/trace_slicer.config -o <output_dir>
# Or interactive mode with file dialog:
python trace_power_slicer.py
```

**For SocWatch ETL post-processing:**
```bash
python socwatch_pp.py <input_folder>
# Or GUI mode with folder dialog:
python socwatch_pp.py
```

**For SocWatch _trace.csv plotting:**
```bash
python trace_plotter.py <trace_csv> [options]
# List all sections without writing output:
python trace_plotter.py <trace_csv> --list
# Filter to specific metrics and plot:
python trace_plotter.py <trace_csv> --filter "DDR Bandwidth|NPU Power|IGFX"
```

**For Socwatch JSON analysis:**
```bash
python newSW_json_parser.py -i <swjson_file> -e "Event Name 1" "Event Name 2"
# Or interactive mode with file dialog:
python newSW_json_parser.py
```

**For VTune .pwr parsing (with ETL fallback):**
```bash
python vtune_pwr_parser.py -i <pwr_file_or_etl_folder>
# Parse selected event groups only:
python vtune_pwr_parser.py -i <pwr_file_or_etl_folder> -e "DDR Bandwidth Requests by Component"
# Generate .swjson fallback if needed for streaming rows:
python vtune_pwr_parser.py -i <pwr_file_or_etl_folder> --generate-swjson
```

**For FPS screenshot OCR:**
```bash
python parsers/fps_img_parser.py <image_or_folder> --debug
```

### 3. Detailed Guidance

- **New users**: Start with [ParseAll documentation](./docs/parseall.md)
- **Advanced workflows**: See [Collection_Parser documentation](./docs/collection-parser.md)
- **Model-specific analysis**: Review [Phi_summary](./docs/phi-summary.md) or [Llama parser](./docs/llama-parser.md)
- **SocWatch ETL processing**: See [socwatch_pp](./docs/socwatch_pp.md) for batch .etl file processing
- **SocWatch trace plotting**: See [trace_plotter](./docs/trace_plotter.md) for `_trace.csv` section splitting and chart generation
- **Teams/Procyon mixed parsing**: See [Teams++ guide](./docs/teams-plus-plus.md) for recursive dataset parsing and Excel export
- **Power trace slicing**: See [trace_power_slicer](./docs/README_trace_slicer.md) for workload analysis
- **Socwatch JSON analysis**: See [newSW_json_parser](./docs/newSW_json_parser_usage.md) for event visualization
- **Best practices**: Review individual parser documentation in [docs](./docs/) folder

## Supported Data Types

- **Power Metrics**: Multi-rail power measurement data
- **Socwatch Data**: Performance monitoring and profiling
- **PCIe Data**: PCIe-specific performance metrics
- **ETL Data**: Early Termination Layer results
- **Model Throughput**: AI/ML model performance metrics
- **Temperature Data**: Thermal monitoring
- **Bandwidth Data**: Memory and I/O bandwidth metrics

## Features

✓ **Multi-format Support** - Handles various data structure layouts
✓ **Configurable Analysis** - JSON-based configuration for customization
✓ **Batch Processing** - Process large datasets efficiently
✓ **Excel Output** - Professional Excel reports
✓ **Per-Core Analysis** - Detailed per-core CPU metrics
✓ **Flexible Input** - JSON config or direct Python configuration
✓ **Data Prioritization** - Power metrics prioritized; optional secondary sources
✓ **Collapsible Visualization** - Hide/show core data for cleaner presentation

## Configuration

Many parsers support configuration through:

1. **JSON Files** - External JSON configuration (recommended for reproducibility)
2. **Direct Python** - Hardcoded configuration in the Python file
3. **Command-line Arguments** - Dynamic parameter passing

### Common Configuration Parameters

| Parameter | Type | Example |
|-----------|------|---------|
| `-i, --input` | Path | `\\server\data\location` or `./data` |
| `-o, --output` | Path | `./results/output.xlsx` |
| `-c, --config` | JSON File | `./config/PTL_default.config` |
| `-d, --daq` | JSON File | `./config/daq_targets.json` |
| `-st, --swtarget` | JSON File | `./config/socwatch_targets.json` |
| `-hb, --hobl` | Flag | (no value, include if HOBL data) |

See individual parser documentation for specific parameters.

## Output Formats

- **Excel (.xlsx)** - Primary format for all parsers
- **CSV** - Legacy format (where applicable)
- **Structured Sheets** - Organized data in multiple worksheets
- **Summary Views** - High-level overviews and detailed analysis

## Data Structure Guidelines

### Flat Structure (Single Level)
```
BaselineFolder/
├── CataV3_000/  (ETL + Power)
├── CataV3_001/  (Power)
├── CataV3_002/  (Power)
└── CataV3_003/  (Socwatch + Power)
```

### Hierarchical Structure (Two Levels)
```
BaselineFolder/
├── ETL/
│   └── CataV3_000/
├── Power/
│   ├── CataV3_001/
│   ├── CataV3_002/
│   └── CataV3_003/
├── Socwatch/
│   ├── CataV3_004/
│   └── CataV3_005/
└── PCIe/
    ├── CataV3_006/
    └── CataV3_007/
```

## Workflow Examples

### Single-Run Analysis
```
Data Collection → ParseAll → Excel Report
```

### Multi-Step Collateral Generation
```
Data Collection → ParseAll → Manual Selection → Collection_Parser → Collateral
```

### Model-Specific Analysis
```
AI Model Results + Power/Thermal Data → Phi_summary/Llama_parser → Analysis Report
```

## Documentation

Complete documentation for each tool is in the [docs](./docs/) folder:

- [ParseAll Guide](./docs/parseall.md)
- [Phi_summary Guide](./docs/phi-summary.md)
- [Collection_Parser Guide](./docs/collection-parser.md)
- [CatapultV3_Full_Parser Guide](./docs/catapultv3-full-parser.md)
- [Llama Parser Guide](./docs/llama-parser.md)
- [SA ETL First Epoch Guide](./docs/sa-etl-first-epoch.md)
- [SocWatch Post-Processor Guide](./docs/socwatch_pp.md)
- [Teams++ Guide](./docs/teams-plus-plus.md)
- [Trace Power Slicer Guide](./docs/README_trace_slicer.md)
- [Socwatch JSON Parser Guide](./docs/SWJSON_PARSER_USAGE.md)

## Best Known Methods (BKM)

For detailed step-by-step guidance and best practices, refer to individual parser documentation in the [docs](./docs/) folder.

## Directory Structure

```
parsing-suite/
├── ParseAll.py                      # Multi-source parser
├── Phi_summary.py                   # Phi model parser
├── Collection_Parser.py             # Collection aggregator
├── CatapultV3_Full_Parser.py        # Platform profiler
├── bm_llama_parser.py               # Llama model parser
├── SA_ETL_first_epoch.py            # ETL analysis
├── socwatch_pp.py                   # SocWatch ETL post-processor
├── Teams++.py                       # Teams/AI mixed-source parser
├── trace_power_slicer.py            # Power trace slicer
├── swjson_parser.py                 # Socwatch JSON analyzer
├── requirements.txt                 # Python dependencies
├── docs/                            # Detailed documentation
│   ├── parseall.md
│   ├── phi-summary.md
│   ├── collection-parser.md
│   ├── catapultv3-full-parser.md
│   ├── llama-parser.md
│   ├── sa-etl-first-epoch.md
│   ├── socwatch_pp.md
│   ├── teams-plus-plus.md
│   ├── README_trace_slicer.md
│   └── SWJSON_PARSER_USAGE.md
├── parsers/                         # Shared parser modules
├── src/                             # Configuration and source data
├── tools/                           # Utility functions
├── test/                            # Test cases
├── .gitignore                       # Git ignore rules
└── README.md                        # This file
```

## Requirements

- Python 3.7+
- pandas
- openpyxl
- numpy
- Additional dependencies listed in `requirements.txt`

## Troubleshooting

### Common Issues

**No data found?**
- Verify input path is correct and accessible
- Check file naming conventions match expectations
- Ensure folder structure matches supported layouts

**Memory issues?**
- Process data in smaller batches
- Reduce concurrent file processing
- Increase available system memory

**Output file issues?**
- Verify output directory is writable
- Ensure file is not open in Excel
- Check sufficient disk space available

See specific parser documentation for detailed troubleshooting.

## Contributing

When adding new parsers:
1. Place in parsing-suite root directory
2. Add dependencies to `requirements.txt`
3. Create documentation in `docs/` folder
4. Update this README with parser reference
5. Add configuration examples to relevant `.json` files

## Related Projects

- **[parseCSV](../parseCSV/)** - Specialized single-purpose parsing tools
- **[socwatch_post_proc](../socwatch_post_proc/)** - Socwatch post-processing utilities

---

For detailed information, refer to the comprehensive parser documentation in the [docs](./docs/) folder.
