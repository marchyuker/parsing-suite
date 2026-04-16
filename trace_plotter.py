#!/usr/bin/env python3
"""
SocWatch Trace CSV Plotter  (trace_plotter.py)

Parses a SocWatch _trace.csv file produced by the '-r int' flag,
separates every event section into an individual CSV, and generates
time-series charts grouped by event type.

Usage
-----
    python trace_plotter.py <input_trace.csv> [options]

Options
-------
    -o, --output-dir DIR    Output directory (default: <stem>_plots/ beside input)
    --format {png,svg}      Image format (default: png)
    --filter PATTERN        Only process sections whose title matches this regex
    --list                  List all sections and exit (no I/O)
    --no-csv                Skip individual CSV export
    --no-plot               Skip chart generation
    --dpi N                 Chart resolution in DPI (default: 150)
    --from-csv DIR          Load pre-exported section CSVs from DIR instead of parsing a raw _trace.csv.  Omit DIR to open a folder-selection dialog.
    --interval-only         Only plot interval (sampled) sections; skip event sections
    --event-only            Only plot event/state sections; skip interval sections

Requirements
------------
    pip install pandas matplotlib
"""

import re
import sys
import json
import argparse
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class Section:
    """One parsed data section from a SocWatch _trace.csv file."""
    title: str              # Original section title line
    columns: List[str]      # Column names from the header row
    df: pd.DataFrame        # Parsed data (columns already named)
    is_interval: bool       # True  = sampled-interval data (Continuous Time in usec)
                            # False = event/state transition data (Continuous Time in ms)
    group_key: str          # Normalised name used to group related sections into one chart
    sub_label: str          # Per-unit label within the group (e.g. "Core_3", "PROCHOT")


# ---------------------------------------------------------------------------
# Grouping helpers
# ---------------------------------------------------------------------------

# Matches sections ending with a CPU topology identifier, optionally followed
# by a ": Residency Time/Percentage" or ": Instantaneous rate" qualifier.
# Examples:
#   "Core C-State (OS) - CPU/Package_0/Core_5"
#   "HWP Capabilities - Highest-Performance - CPU/Package_0/Core_5/Thread_5"
#   "Core C-State - CPU/Package_0/Core_3 : Residency Time"
_CPU_TOPO_RE = re.compile(
    r'^(.*?)\s*-\s*CPU/Package_\d+(?:/Core_(\d+)(?:/Thread_(\d+))?)?(\s*:\s*.+)?$'
)

# Matches throttling-reason sections (CPU, iGPU, Ring).
# Example: "CPU Throttling Reasons - PROCHOT"
_THROTTLE_RE = re.compile(
    r'^((?:CPU|Integrated GPU|Ring) Throttling Reasons)\s*-\s*(.+)$'
)

# Matches PMT sections with a Package/Cluster sub-unit.
# Example: "Platform Monitoring Technology Cluster C-States Residency - Cluster-0 : Residency Time"
_PMT_UNIT_RE = re.compile(
    r'^(Platform Monitoring Technology.*?)\s*-\s*(Package|Cluster-\d+)(\s*:\s*.+)?$'
)


def get_group_info(title: str) -> Tuple[str, str]:
    """
    Return ``(group_key, sub_label)`` for *title*.

    group_key  — base event name used for chart grouping (topology stripped)
    sub_label  — label that identifies this section within the group
                 e.g. "Core_3", "Thread_5", "PROCHOT", "Cluster-0"
    """
    # --- CPU topology suffix --------------------------------------------
    m = _CPU_TOPO_RE.match(title)
    if m:
        base     = (m.group(1) or '').strip()
        core_num = m.group(2)
        thr_num  = m.group(3)
        suffix   = (m.group(4) or '').strip()  # e.g. " : Residency Time"
        group_key = f"{base}{suffix}"
        if thr_num is not None:
            sub_label = f"Thread_{thr_num}"
        elif core_num is not None:
            sub_label = f"Core_{core_num}"
        else:
            sub_label = 'Pkg'
        return group_key, sub_label

    # --- Throttling reason suffix ---------------------------------------
    m = _THROTTLE_RE.match(title)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # --- PMT Cluster / Package suffix -----------------------------------
    m = _PMT_UNIT_RE.match(title)
    if m:
        base   = m.group(1).strip()
        suffix = (m.group(3) or '').strip()
        return f"{base}{suffix}", m.group(2).strip()

    # --- Default: section is its own group ------------------------------
    return title.strip(), ''


# ---------------------------------------------------------------------------
# GUI helpers
# ---------------------------------------------------------------------------

def _select_file_gui() -> Optional[Path]:
    """Open a Tkinter file-selection dialog and return the chosen path.

    The dialog is filtered to ``*_trace.csv`` files by default but allows
    selecting any CSV.  Returns ``None`` if the user cancels.
    """
    root = tk.Tk()
    root.withdraw()       # hide the empty root window
    root.attributes('-topmost', True)  # bring dialog to front

    file_path = filedialog.askopenfilename(
        title='Select a SocWatch _trace.csv file',
        filetypes=[
            ('SocWatch trace CSV', '*_trace.csv'),
            ('All CSV files',      '*.csv'),
            ('All files',          '*.*'),
        ],
    )
    root.destroy()

    if not file_path:
        return None
    return Path(file_path)


def _load_single_csv(csv_path: Path) -> Section:
    """Load a single CSV file as a Section without needing ``_index.json``.

    Section metadata (title, group_key, is_interval) is inferred from the
    file name and column headers.
    """
    df = pd.read_csv(csv_path)
    # Infer section type from column names
    is_interval = any('(usec)' in c for c in df.columns)
    title = csv_path.stem.replace('_', ' ')
    group_key, sub_label = get_group_info(title)
    return Section(
        title=title,
        columns=list(df.columns),
        df=df,
        is_interval=is_interval,
        group_key=group_key,
        sub_label=sub_label,
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_trace_csv(path: Path) -> Tuple[List[str], List[Section]]:
    """
    Parse a SocWatch _trace.csv file.

    Returns
    -------
    meta_lines : lines of the header block (before the first data section)
    sections   : list of Section objects, one per data section found
    """
    with open(path, encoding='utf-8', errors='replace') as fh:
        raw = fh.readlines()

    # ---- Find section start positions ----------------------------------
    # A section starts at line i when:
    #   • line i is non-blank and starts with a letter
    #   • line i+1 starts with "Sample #"
    starts: List[int] = []
    for i in range(len(raw) - 1):
        stripped = raw[i].strip()
        if (stripped
                and stripped[0].isalpha()
                and raw[i + 1].strip().startswith('Sample #')):
            starts.append(i)

    # ---- Meta block ----------------------------------------------------
    meta_end   = starts[0] if starts else len(raw)
    meta_lines = [l.rstrip('\n\r') for l in raw[:meta_end]]

    # ---- Parse each section --------------------------------------------
    sections: List[Section] = []
    for idx, start in enumerate(starts):
        title    = raw[start].strip()
        col_line = raw[start + 1].strip()
        columns  = [c.strip() for c in col_line.split(',')]

        # Data rows live between this section's header and the next header.
        next_start = starts[idx + 1] if idx + 1 < len(starts) else len(raw)
        data_lines = [
            raw[k].strip()
            for k in range(start + 2, next_start)
            if raw[k].strip()
        ]

        sec = _build_section(title, columns, data_lines)
        if sec is not None:
            sections.append(sec)

    return meta_lines, sections


def _build_section(
    title: str,
    columns: List[str],
    data_lines: List[str],
) -> Optional[Section]:
    """Build a Section from raw text rows, or return None if empty/unparseable."""
    if not data_lines:
        return None

    # Detect section type from the time-unit in column 2 (index 1).
    is_interval = len(columns) > 1 and '(usec)' in columns[1]

    # Parse rows: split on comma, strip whitespace.
    records = []
    for line in data_lines:
        parts = [p.strip() for p in line.split(',')]
        if len(parts) == len(columns):
            records.append(parts)

    if not records:
        return None

    df = pd.DataFrame(records, columns=columns)

    # Convert columns to numeric where possible; leave strings as-is.
    # (errors='coerce' would silently convert non-numeric to NaN, so we only
    #  keep the conversion when every value in the column parsed successfully.)
    for col in df.columns:
        converted = pd.to_numeric(df[col], errors='coerce')
        if not converted.isna().any():
            df[col] = converted

    group_key, sub_label = get_group_info(title)

    return Section(
        title=title,
        columns=columns,
        df=df,
        is_interval=is_interval,
        group_key=group_key,
        sub_label=sub_label,
    )


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def safe_filename(name: str, max_len: int = 80) -> str:
    """Turn an arbitrary string into a safe, filesystem-friendly filename stem."""
    name = re.sub(r'[^\w\s\-]', '_', name)
    name = re.sub(r'[\s]+', '_', name)
    name = re.sub(r'_+', '_', name)
    return name.strip('_')[:max_len]


def export_csvs(sections: List[Section], output_dir: Path) -> None:
    """Write each section to its own CSV file inside *output_dir*.

    Also writes a ``_index.json`` sidecar so sections can be reloaded later
    with :func:`load_sections_from_csv_dir` without re-parsing the original
    trace file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for sec in sections:
        fname = safe_filename(sec.title) + '.csv'
        sec.df.to_csv(output_dir / fname, index=False)
        index.append({
            'file':        fname,
            'title':       sec.title,
            'group_key':   sec.group_key,
            'sub_label':   sec.sub_label,
            'is_interval': sec.is_interval,
        })
    with open(output_dir / '_index.json', 'w', encoding='utf-8') as fh:
        json.dump(index, fh, indent=2)
    print(f"  [+] Exported {len(sections)} CSV file(s) -> {output_dir}")


def load_sections_from_csv_dir(csv_dir: Path) -> List[Section]:
    """Reconstruct Section objects from a directory previously written by
    :func:`export_csvs`.  Requires the ``_index.json`` sidecar to exist."""
    index_path = csv_dir / '_index.json'
    if not index_path.exists():
        raise FileNotFoundError(
            f"No _index.json found in {csv_dir}.\n"
            f"Run without --from-csv first to generate the CSV export."
        )
    with open(index_path, encoding='utf-8') as fh:
        index = json.load(fh)

    sections: List[Section] = []
    for entry in index:
        csv_path = csv_dir / entry['file']
        if not csv_path.exists():
            print(f"  [!] Missing CSV, skipping: {entry['file']}")
            continue
        df = pd.read_csv(csv_path)
        sections.append(Section(
            title=entry['title'],
            columns=list(df.columns),
            df=df,
            is_interval=entry['is_interval'],
            group_key=entry['group_key'],
            sub_label=entry['sub_label'],
        ))
    return sections


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------

_TAB20 = plt.get_cmap('tab20')
_COLORS = [_TAB20(i / 20) for i in range(20)]

MAX_SUBPLOTS = 16   # Maximum subplots per figure for grouped charts


def _subplot_grid(n: int) -> Tuple[int, int]:
    """Return (nrows, ncols) for a roughly-square grid of *n* subplots."""
    n = min(n, MAX_SUBPLOTS)
    ncols = min(4, n)
    nrows = (n + ncols - 1) // ncols
    return nrows, ncols


def _time_series(df: pd.DataFrame) -> Optional[pd.Series]:
    """Return the time column in **seconds** (converts usec or ms to s)."""
    for col in df.columns:
        if 'Continuous Time' in col:
            t = pd.to_numeric(df[col], errors='coerce')
            if '(usec)' in col:
                return t / 1e6
            if '(ms)' in col:
                return t / 1e3
    return None


def _trim_df_to_time_range(
    df: pd.DataFrame,
    t_start: Optional[float],
    t_end: Optional[float],
) -> pd.DataFrame:
    """Return a slice of *df* keeping only rows where the time column
    (converted to seconds) falls within [t_start, t_end].
    Either bound may be ``None`` to leave that end open."""
    if t_start is None and t_end is None:
        return df
    t = _time_series(df)
    if t is None:
        return df
    mask = pd.Series(True, index=df.index)
    if t_start is not None:
        mask &= t >= t_start
    if t_end is not None:
        mask &= t <= t_end
    return df.loc[mask].reset_index(drop=True)


def _metric_cols(df: pd.DataFrame) -> List[str]:
    """Return columns that are numeric and not bookkeeping columns."""
    skip_patterns = ('Sample', 'Continuous Time', 'Duration')
    result = []
    for col in df.columns:
        if any(p in col for p in skip_patterns):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            result.append(col)
    return result


def _draw_interval(
    ax,
    df: pd.DataFrame,
    group_key: str,
    sub_label: str,
    colors: List,
    show_legend: bool = False,
    plot_style: str = 'line',
) -> None:
    """Draw interval (sampled) data onto *ax*."""
    t = _time_series(df)
    if t is None:
        return

    mcols = _metric_cols(df)
    if not mcols:
        return

    is_pct      = 'Residency Percentage' in group_key
    is_residual = 'Residency' in group_key

    if (is_pct or is_residual) and len(mcols) > 1 and plot_style not in ('scatter', 'bar'):
        # Stacked-area chart for residency data
        data = df[mcols].apply(pd.to_numeric, errors='coerce').fillna(0).values.T
        ax.stackplot(t, data, labels=mcols, colors=colors[:len(mcols)], alpha=0.85)
        if is_pct:
            ax.set_ylim(0, 100)
            ax.set_ylabel('%')
        else:
            ax.set_ylabel('µs')
    else:
        for col, c in zip(mcols, colors):
            y = pd.to_numeric(df[col], errors='coerce')
            if plot_style == 'scatter':
                ax.scatter(t, y, color=c, s=12, alpha=0.6, linewidths=0, label=col)
            elif plot_style == 'bar':
                ax.bar(t, y, color=c, label=col, width=(t.iloc[1] - t.iloc[0]) * 0.8
                       if len(t) > 1 else 0.8, align='edge', alpha=0.7)
            elif plot_style == 'step':
                ax.step(t, y, where='post', color=c, linewidth=0.8, label=col)
            elif plot_style == 'area':
                ax.fill_between(t, y, color=c, alpha=0.4, label=col)
                ax.plot(t, y, color=c, linewidth=0.6)
            else:  # line (default)
                ax.plot(t, y, color=c, linewidth=0.8, label=col)

    ax.set_xlabel('Time (s)', fontsize=7)
    ax.tick_params(labelsize=7)
    ax.grid(True, alpha=0.25)

    if sub_label:
        ax.set_title(sub_label, fontsize=8, pad=2)

    if show_legend and mcols:
        ax.legend(fontsize=6, loc='upper right', ncol=max(1, len(mcols) // 6))


def _draw_event(
    ax,
    df: pd.DataFrame,
    group_key: str,
    sub_label: str,
    show_legend: bool = False,
) -> None:
    """Draw event/state-transition data as a step chart onto *ax*."""
    t = _time_series(df)
    if t is None:
        return

    mcols = _metric_cols(df)
    if mcols:
        # Numeric metric columns (e.g., wakeup counts)
        for col, c in zip(mcols, _COLORS):
            ax.step(t, pd.to_numeric(df[col], errors='coerce'),
                    where='post', color=c, linewidth=0.8, label=col)
        if show_legend and len(mcols) > 1:
            ax.legend(fontsize=6, loc='upper right')
    else:
        # Find the first categorical (state) column
        skip = ('Sample', 'Continuous Time', 'Duration')
        for col in df.columns:
            if any(p in col for p in skip):
                continue
            cats = df[col].astype('category')
            codes = cats.cat.codes
            ax.step(t, codes, where='post', linewidth=0.8)
            ax.set_yticks(range(len(cats.cat.categories)))
            ax.set_yticklabels(cats.cat.categories, fontsize=6)
            break

    ax.set_xlabel('Time (s)', fontsize=7)
    ax.tick_params(labelsize=7)
    ax.grid(True, alpha=0.25)

    if sub_label:
        ax.set_title(sub_label, fontsize=8, pad=2)


# ---------------------------------------------------------------------------
# Custom plot functions
# ---------------------------------------------------------------------------
# Each function shares the same signature as _draw_interval / _draw_event:
#   fn(ax, df, group_key, sub_label, colors, show_legend, plot_style) -> None
#
# To add a new customisation:
#   1. Write  def _plot_<name>(ax, df, group_key, sub_label, colors, show_legend, plot_style): ...
#   2. Add an entry to CUSTOM_PLOT_MAP at the bottom of this section.
#      The regex is matched (re.search) against the section's group_key.
# ---------------------------------------------------------------------------

def _plot_ddr_bw_instantaneous(
    ax,
    df: pd.DataFrame,
    group_key: str,
    sub_label: str,
    colors: List,
    show_legend: bool = False,
    plot_style: str = 'line',
) -> None:
    """
    Custom chart for DDR Bandwidth Requests (Instantaneous rate).

    Aggregates per-channel read/write columns into:
      - Total Read  (sum of all READS columns)
      - Total Write (sum of all WRITES columns)
      - Total BW    (Total Read + Total Write)  — bold line

    Individual channels are drawn as faint grey background lines.
    A dashed horizontal line and a text box show the average Total BW.
    """
    t = _time_series(df)
    if t is None:
        return

    read_cols  = [c for c in df.columns
                  if re.search(r'\bREADS\b', c, re.IGNORECASE)
                  and pd.api.types.is_numeric_dtype(df[c])]
    write_cols = [c for c in df.columns
                  if re.search(r'\bWRITES\b', c, re.IGNORECASE)
                  and pd.api.types.is_numeric_dtype(df[c])]

    if not read_cols and not write_cols:
        # Fall back to default renderer if columns not found
        _draw_interval(ax, df, group_key, sub_label, colors, show_legend,
                       plot_style=plot_style)
        return

    # Determine unit label from the first matching column (e.g. "MB/s" or "bytes")
    sample_col = (read_cols + write_cols)[0]
    unit_m = re.search(r'\(([^)]+)\)', sample_col)
    unit   = unit_m.group(1) if unit_m else ''

    # --- Individual channel lines (light grey, thin, no legend) ----------
    # Always drawn as lines regardless of plot_style (context/background role)
    for col in read_cols + write_cols:
        ax.plot(t, df[col], color='#cccccc', linewidth=0.35, zorder=1)

    # --- Aggregate lines/markers (respects plot_style) ------------------
    total_read  = df[read_cols].sum(axis=1)
    total_write = df[write_cols].sum(axis=1)
    total_bw    = total_read + total_write

    def _draw_agg(y, color, label, lw, zorder):
        if plot_style == 'scatter':
            ax.scatter(t, y, color=color, s=12, alpha=0.6, linewidths=0,
                       label=label, zorder=zorder)
        elif plot_style == 'bar':
            w = (t.iloc[1] - t.iloc[0]) * 0.8 if len(t) > 1 else 0.8
            ax.bar(t, y, color=color, label=label, width=w, align='edge',
                   alpha=0.7, zorder=zorder)
        elif plot_style == 'step':
            ax.step(t, y, where='post', color=color, linewidth=lw,
                    label=label, zorder=zorder)
        elif plot_style == 'area':
            ax.fill_between(t, y, color=color, alpha=0.3, zorder=zorder)
            ax.plot(t, y, color=color, linewidth=lw * 0.7,
                    label=label, zorder=zorder)
        else:  # line
            ax.plot(t, y, color=color, linewidth=lw, label=label, zorder=zorder)

    _draw_agg(total_read,  '#1f77b4', f'Total Read ({unit})',  lw=1.4, zorder=3)
    _draw_agg(total_write, '#ff7f0e', f'Total Write ({unit})', lw=1.4, zorder=3)
    _draw_agg(total_bw,    '#2ca02c', f'Total BW ({unit})',    lw=2.2, zorder=4)

    # --- Average Total BW annotation ------------------------------------
    avg_bw = total_bw.mean()
    ax.axhline(avg_bw, color='#2ca02c', linewidth=1.0, linestyle='--', alpha=0.6, zorder=2)
    ax.text(
        0.98, 0.97,
        f'Avg Total BW: {avg_bw:.1f} {unit}',
        transform=ax.transAxes,
        fontsize=7, color='#2ca02c',
        ha='right', va='top',
        bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='#2ca02c', alpha=0.8),
    )

    ax.set_xlabel('Time (s)', fontsize=7)
    ax.set_ylabel(unit, fontsize=7)
    ax.tick_params(labelsize=7)
    ax.grid(True, alpha=0.25)

    if sub_label:
        ax.set_title(sub_label, fontsize=8, pad=2)

    ax.legend(fontsize=6, loc='upper left')


# ---------------------------------------------------------------------------
# Custom plot map
# ---------------------------------------------------------------------------
# List of (compiled_regex, draw_fn) pairs.
# Checked in order against each group's group_key; first match wins.
# If no match, the default _draw_interval / _draw_event is used.

CUSTOM_PLOT_MAP: List[Tuple[re.Pattern, Callable]] = [
    (
        re.compile(r'DDR Bandwidth Requests.*Instantaneous', re.IGNORECASE),
        _plot_ddr_bw_instantaneous,
    ),
    # Add more entries here as needed, e.g.:
    # (
    #     re.compile(r'IO Bandwidth.*Instantaneous', re.IGNORECASE),
    #     _plot_io_bw_instantaneous,
    # ),
]


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------

def plot_groups(
    sections: List[Section],
    output_dir: Path,
    fmt: str,
    dpi: int,
    time_range: Optional[Tuple[Optional[float], Optional[float]]] = None,
    figsize: Optional[Tuple[float, float]] = None,
    plot_style: str = 'line',
) -> None:
    """Group sections by group_key and generate one chart per group."""
    output_dir.mkdir(parents=True, exist_ok=True)

    groups: Dict[str, List[Section]] = {}
    for s in sections:
        groups.setdefault(s.group_key, []).append(s)

    ok = 0
    for group_key, grp in groups.items():
        try:
            _plot_one_group(group_key, grp, output_dir, fmt, dpi,
                            time_range=time_range, figsize=figsize,
                            plot_style=plot_style)
            ok += 1
        except Exception as exc:
            print(f"  [!] Skipped '{group_key}': {exc}")

    print(f"  [+] Saved {ok} chart(s) -> {output_dir.resolve()}")


def _plot_one_group(
    group_key: str,
    sections: List[Section],
    output_dir: Path,
    fmt: str,
    dpi: int,
    time_range: Optional[Tuple[Optional[float], Optional[float]]] = None,
    figsize: Optional[Tuple[float, float]] = None,
    plot_style: str = 'line',
) -> None:
    n      = len(sections)
    n_plot = min(n, MAX_SUBPLOTS)
    nrows, ncols = _subplot_grid(n_plot)

    if figsize:
        fig_w, fig_h = figsize
    else:
        fig_w = max(10, ncols * 5)
        fig_h = max(4,  nrows * 3)

    fig, axes = plt.subplots(nrows, ncols, figsize=(fig_w, fig_h), squeeze=False)
    axes_flat = axes.flatten()

    is_interval = sections[0].is_interval

    # Check CUSTOM_PLOT_MAP once for the whole group
    custom_fn: Optional[Callable] = None
    for pattern, fn in CUSTOM_PLOT_MAP:
        if pattern.search(group_key):
            custom_fn = fn
            break

    t_start, t_end = (time_range if time_range else (None, None))

    for plot_idx, sec in enumerate(sections[:n_plot]):
        ax          = axes_flat[plot_idx]
        show_legend = (n == 1)   # Only show per-column legend when there is one subplot
        df = _trim_df_to_time_range(sec.df, t_start, t_end)
        if custom_fn is not None:
            custom_fn(ax, df, group_key, sec.sub_label, _COLORS, show_legend,
                      plot_style)
        elif is_interval:
            _draw_interval(ax, df, group_key, sec.sub_label,
                           _COLORS, show_legend=show_legend, plot_style=plot_style)
        else:
            _draw_event(ax, df, group_key, sec.sub_label,
                        show_legend=show_legend)

    # Hide any unused subplot slots in the grid
    for ax in axes_flat[n_plot:]:
        ax.set_visible(False)

    suptitle = group_key
    if n > MAX_SUBPLOTS:
        suptitle += f"\n(first {MAX_SUBPLOTS} of {n} shown)"
    fig.suptitle(suptitle, fontsize=10, y=0.98)

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        plt.tight_layout(rect=[0, 0, 1, 0.96])

    if time_range and time_range[0] is not None and time_range[1] is not None:
        t0 = int(round(time_range[0] * 1000))
        t1 = int(round(time_range[1] * 1000))
        tr_suffix = f'_{t0}ms-{t1}ms'
    else:
        tr_suffix = ''
    style_suffix = f'_{plot_style}' if plot_style != 'line' else ''
    fname = safe_filename(group_key) + tr_suffix + style_suffix + '.' + fmt
    out_path = (output_dir / fname).resolve()
    fig.savefig(out_path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    print(f"    {out_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class _SuggestingParser(argparse.ArgumentParser):
    """ArgumentParser that suggests the closest known flag on a typo."""

    def error(self, message: str) -> None:
        import difflib
        # Extract the unrecognised token from the standard message
        # e.g. "unrecognized arguments: --from-cvs"
        token_match = re.search(r'unrecognized arguments: (\S+)', message)
        if token_match:
            token = token_match.group(1)
            known = [opt
                     for action in self._actions
                     if hasattr(action, 'option_strings')
                     for opt in action.option_strings]
            close = difflib.get_close_matches(token, known, n=1, cutoff=0.6)
            if close:
                message = f"{message}\n  Did you mean: {close[0]}?"
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    p = _SuggestingParser(
        prog='trace_plotter',
        description='Parse and plot a SocWatch _trace.csv file.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument('input', nargs='?', default=None,
                   help='Path to the _trace.csv file (omit when using --from-csv)')
    p.add_argument('--from-csv', nargs='?', const='__GUI__', default=None,
                   metavar='DIR',
                   help=('Load pre-exported section CSVs from DIR instead of parsing '
                         'a raw _trace.csv.  DIR must contain _index.json (written '
                         'automatically by a previous export run).  '
                         'Accepts a single directory with mixed sections, or the '
                         'csv/interval or csv/event sub-directories.  '
                         'Omit DIR to open a folder-selection dialog.'))
    p.add_argument('-o', '--output-dir', default=None,
                   help='Output directory (default: <input_stem>_plots/ beside input)')
    p.add_argument('--format', choices=['png', 'svg'], default='png',
                   help='Image format (default: png)')
    p.add_argument('--filter', default=None, metavar='PATTERN',
                   help='Only process sections whose title matches this regex')
    p.add_argument('--list', action='store_true',
                   help='List all sections and exit without writing any files')
    p.add_argument('--no-csv', action='store_true',
                   help='Skip individual CSV export')
    p.add_argument('--no-plot', action='store_true',
                   help='Skip chart generation')
    p.add_argument('--dpi', type=int, default=150,
                   help='Chart resolution in DPI (default: 150)')
    p.add_argument('--interval-only', action='store_true',
                   help='Only process sampled-interval sections')
    p.add_argument('--event-only', action='store_true',
                   help='Only process event/state-transition sections')
    p.add_argument('--time-range', default=None, metavar='START,END',
                   help='Only plot data within this time window in ms (e.g. --time-range 5000,6000 for 5 s ~ 6 s)')
    p.add_argument('--figsize', default=None, metavar='W,H',
                   help='Figure size in inches (e.g. --figsize 24,4); overrides auto-sizing')
    p.add_argument('--plot-style', choices=['line', 'scatter', 'bar', 'step', 'area'],
                   default='line',
                   help='Plot style for interval sections (default: line)')
    return p


def _parse_pair(s: Optional[str], flag: str) -> Optional[Tuple[float, float]]:
    """Parse a ``'A,B'`` string into ``(float(A), float(B))``.
    Exits with an error message on bad input."""
    if s is None:
        return None
    parts = s.split(',')
    if len(parts) != 2:
        print(f"[!] {flag} expects two comma-separated numbers (e.g. {flag} 5000,6000)")
        sys.exit(1)
    try:
        return (float(parts[0].strip()), float(parts[1].strip()))
    except ValueError:
        print(f"[!] {flag} values must be numbers, got: {s!r}")
        sys.exit(1)


def main() -> None:
    args = build_parser().parse_args()

    # ---- Mode: --from-csv ----------------------------------------------
    if args.from_csv is not None:
        # Resolve source: GUI if flag given without a value
        if args.from_csv == '__GUI__':
            print("[*] No file specified -- opening file selection dialog ...")
            _root = tk.Tk()
            _root.withdraw()
            _root.attributes('-topmost', True)
            _p = filedialog.askopenfilename(
                parent=_root,
                title='Select a section CSV file',
                filetypes=[('CSV files', '*.csv'), ('All files', '*.*')],
            )
            _root.destroy()
            if not _p:
                print("[!] Nothing selected. Exiting.")
                sys.exit(0)
            selected = Path(_p)
            print(f"[+] Selected: {selected}")
        else:
            selected = Path(args.from_csv)

        if not selected.exists():
            print(f"[!] File not found: {selected}")
            sys.exit(1)
        if selected.suffix.lower() != '.csv':
            print(f"[!] Expected a .csv file, got: {selected}")
            sys.exit(1)

        output_dir = Path(args.output_dir) if args.output_dir \
                     else selected.parent / (selected.stem + '_plots')
        print(f"[+] Loading single CSV: {selected.name}")
        sections: List[Section] = [_load_single_csv(selected)]

        # Apply same filter / type flags as the normal path
        if args.filter:
            pat = re.compile(args.filter, re.IGNORECASE)
            sections = [s for s in sections if pat.search(s.title)]
            print(f"[~] After filter '{args.filter}': {len(sections)} section(s)")

        if args.interval_only:
            sections = [s for s in sections if s.is_interval]
        elif args.event_only:
            sections = [s for s in sections if not s.is_interval]

        if args.list:
            print(f"\n{'#':>6}  {'Type':8}  {'Group':60}  Title")
            print('-' * 120)
            for i, s in enumerate(sections, 1):
                kind = 'interval' if s.is_interval else 'event'
                print(f"{i:6d}  {kind:8}  {s.group_key[:60]:60}  {s.title}")
            return

        if not args.no_plot:
            interval_secs = [s for s in sections if s.is_interval]
            event_secs    = [s for s in sections if not s.is_interval]

            _tr_raw = _parse_pair(args.time_range, '--time-range')
            _tr = (_tr_raw[0] / 1000.0, _tr_raw[1] / 1000.0) if _tr_raw else None
            _fs = _parse_pair(args.figsize, '--figsize')

            if interval_secs:
                print(f"\n[+] Plotting {len(interval_secs)} interval section(s) "
                      f"({len({s.group_key for s in interval_secs})} chart group(s)) ...")
                plot_groups(interval_secs,
                            output_dir / 'plots' / 'interval',
                            args.format, args.dpi,
                            time_range=_tr, figsize=_fs,
                            plot_style=args.plot_style)

            if event_secs:
                print(f"\n[+] Plotting {len(event_secs)} event section(s) "
                      f"({len({s.group_key for s in event_secs})} chart group(s)) ...")
                plot_groups(event_secs,
                            output_dir / 'plots' / 'event',
                            args.format, args.dpi,
                            time_range=_tr, figsize=_fs,
                            plot_style=args.plot_style)

        print(f"\nDone!  Results -> {output_dir.resolve()}")
        return

    # ---- Mode: parse raw _trace.csv ------------------------------------
    if not args.input:
        print("[*] No input file specified — opening file selection dialog ...")
        selected = _select_file_gui()
        if not selected:
            print("[!] No file selected. Exiting.")
            sys.exit(0)
        input_path = selected
        print(f"[+] Selected: {input_path}")
    else:
        input_path = Path(args.input)
    if not input_path.exists():
        print(f"[!] File not found: {input_path}")
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir \
                 else input_path.parent / (input_path.stem + '_plots')

    print(f"[*] Parsing: {input_path.name}  ({input_path.stat().st_size / 1e6:.1f} MB)")

    meta_lines, sections = parse_trace_csv(input_path)
    print(f"[+] Found {len(sections)} section(s)")

    # ---- Optional filter -----------------------------------------------
    if args.filter:
        pat = re.compile(args.filter, re.IGNORECASE)
        sections = [s for s in sections if pat.search(s.title)]
        print(f"[~] After filter '{args.filter}': {len(sections)} section(s)")

    # ---- Interval / event filter ---------------------------------------
    if args.interval_only:
        sections = [s for s in sections if s.is_interval]
    elif args.event_only:
        sections = [s for s in sections if not s.is_interval]

    # ---- --list mode ---------------------------------------------------
    if args.list:
        print(f"\n{'#':>6}  {'Type':8}  {'Group':60}  Title")
        print('-' * 120)
        for i, s in enumerate(sections, 1):
            kind = 'interval' if s.is_interval else 'event'
            print(f"{i:6d}  {kind:8}  {s.group_key[:60]:60}  {s.title}")
        return

    # ---- Create output directory & write meta --------------------------
    output_dir.mkdir(parents=True, exist_ok=True)

    meta_path = output_dir / '_meta.txt'
    with open(meta_path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(meta_lines))
    print(f"[+] Meta info saved -> {meta_path.name}")

    # ---- CSV export ----------------------------------------------------
    if not args.no_csv:
        interval_secs = [s for s in sections if s.is_interval]
        event_secs    = [s for s in sections if not s.is_interval]
        print(f"\n[+] Exporting CSVs ...")
        if interval_secs:
            export_csvs(interval_secs, output_dir / 'csv' / 'interval')
        if event_secs:
            export_csvs(event_secs,    output_dir / 'csv' / 'event')

    # ---- Chart generation ----------------------------------------------
    if not args.no_plot:
        interval_secs = [s for s in sections if s.is_interval]
        event_secs    = [s for s in sections if not s.is_interval]

        _tr_raw = _parse_pair(args.time_range, '--time-range')
        _tr = (_tr_raw[0] / 1000.0, _tr_raw[1] / 1000.0) if _tr_raw else None
        _fs = _parse_pair(args.figsize, '--figsize')

        if interval_secs:
            print(f"\n[+] Plotting {len(interval_secs)} interval section(s) "
                  f"({len({s.group_key for s in interval_secs})} chart group(s)) ...")
            plot_groups(interval_secs,
                        output_dir / 'plots' / 'interval',
                        args.format, args.dpi,
                        time_range=_tr, figsize=_fs,
                        plot_style=args.plot_style)

        if event_secs:
            print(f"\n[+] Plotting {len(event_secs)} event section(s) "
                  f"({len({s.group_key for s in event_secs})} chart group(s)) ...")
            plot_groups(event_secs,
                        output_dir / 'plots' / 'event',
                        args.format, args.dpi,
                        time_range=_tr, figsize=_fs,
                        plot_style=args.plot_style)

    print(f"\nDone!  Results -> {output_dir.resolve()}")


if __name__ == '__main__':
    main()
