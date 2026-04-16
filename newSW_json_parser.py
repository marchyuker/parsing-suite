"""
SW JSON Parser - Analyze and visualize data from .json trace files
"""

import json
import argparse
import time
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field

try:
    import ijson
except ImportError:
    ijson = None

import parsers.tools as tools

plt = None


def _ensure_matplotlib() -> bool:
    """Lazy-load matplotlib only when chart generation is needed."""
    global plt
    if plt is not None:
        return True

    try:
        import matplotlib
        matplotlib.use('Agg')
        matplotlib.rcParams['agg.path.chunksize'] = 10000
        import matplotlib.pyplot as _plt
        plt = _plt
        return True
    except ImportError:
        return False


@dataclass
class EventMetrics:
    """Container for event analysis metrics."""
    event_name: str = ""
    total_events: int = 0
    peak_value: float = 0
    start_time: float = float('inf')
    end_time: float = 0
    duration: float = 0
    accumulated: Dict[str, float] = field(default_factory=dict)
    chart_data: List[Tuple[float, float, str]] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert metrics to dictionary format for JSON export."""
        peak_str = f"{round(self.peak_value / 1e6, 2)} MB" if self.peak_value >= 1e6 else f"{round(self.peak_value, 2)}"
        
        result = {
            "event_name": self.event_name,
            "total_event_number": self.total_events,
            "peak_value": peak_str,
            "event_start": self.start_time,
            "event_end": self.end_time,
            "duration": self.duration,
            "accumulated_event": self.accumulated,
            "events_for_charts": self.chart_data
        }
        
        # Add bandwidth metrics if applicable
        if "Bandwidth" in self.event_name:
            total_bandwidth = sum(v for k, v in self.accumulated.items() 
                                if k not in ["Total_Memory_Bandwidth", "Average_Memory_BW_(GB/s)"])
            if total_bandwidth > 0 and self.duration > 0:
                duration_seconds = self.duration / 1e6
                result["accumulated_event"]["Total_Memory_Bandwidth"] = total_bandwidth
                result["accumulated_event"]["Average_Memory_BW_(GB/s)"] = round(
                    (total_bandwidth / 1e9) / duration_seconds, 2
                )
        
        return result


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog='SW JSON Parser',
        description='Parse and analyze .json trace files for event metrics and visualization'
    )
    parser.add_argument(
        '-i', '--input',
        help='Input .json file path'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output path for results (without extension)'
    )
    parser.add_argument(
        '-e', '--events',
        nargs='+',
        help='Event names to analyze (space-separated). If not provided, all events will be analyzed.'
    )
    parser.add_argument(
        '--list-events',
        action='store_true',
        help='List all available event names in the file and exit'
    )
    parser.add_argument(
        '-hb', '--hobl',
        action='store_true',
        help='HOBL mode: look for .PASS or .FAIL file in folder'
    )
    parser.add_argument(
        '--split-only',
        action='store_true',
        help='Only split events into per-event files, do not generate charts'
    )
    parser.add_argument(
        '--from-split',
        help='Directory containing per-event split files ("*_events.jsonl" or "*_events.json") to generate charts from'
    )
    parser.add_argument(
        '--split-dir',
        help='Output directory for split per-event files (default: <output_stem>_events_stream)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing split per-event files'
    )
    parser.add_argument(
        '--in-memory-split',
        action='store_true',
        help='Use legacy in-memory split behavior instead of streaming split (default is streaming)'
    )
    return parser.parse_args()


def select_file_dialog(script_dir: Path) -> Optional[Path]:
    """Show file selection dialog and return selected file path."""
    import tkinter as tk
    from tkinter import filedialog
    
    root = tk.Tk()
    root.withdraw()
    
    last_folder_file = script_dir / "src" / "last_opened_folder.txt"
    initial_dir = None
    
    # Load last opened folder
    if last_folder_file.exists():
        try:
            initial_dir = last_folder_file.read_text().strip()
        except Exception as e:
            print(f"Warning: Could not read last folder: {e}")
    
    # Show file dialog
    file_path = filedialog.askopenfilename(
        title="Select a .json file",
        initialdir=initial_dir,
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
    )
    
    if file_path:
        # Save last opened folder
        tools.saveLastOpenedFolder(str(Path(file_path).parent))
        return Path(file_path)
    
    return None


def load_swjson(file_path: Path) -> Optional[dict]:
    """Load and parse a .json file."""
    if file_path.suffix != '.json':
        print(f"Error: Invalid file extension. Expected .json, got {file_path.suffix}")
        return None
    
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON - {e}")
        return None
    except FileNotFoundError:
        print(f"Error: File not found - {file_path}")
        return None


def iter_trace_events(file_path: Path):
    """Yield trace events one-by-one using streaming when available."""
    if ijson is not None:
        with open(file_path, 'rb') as f:
            for event in ijson.items(f, 'traceEvents.item'):
                yield event
    else:
        print("Warning: ijson not installed. Falling back to json.load (non-streaming parse).")
        data = load_swjson(file_path)
        if not data:
            return
        for event in data.get("traceEvents", []):
            yield event


def parse_trace_events(data: dict) -> Dict[str, List[dict]]:
    """Parse trace events and organize by category."""
    if "traceEvents" not in data or not data["traceEvents"]:
        print("Warning: No trace events found in file")
        return {}
    
    events_by_category = {}
    for event in data["traceEvents"]:
        if "cat" in event:
            category = event["cat"]
            if category not in events_by_category:
                events_by_category[category] = []
            events_by_category[category].append(event)
    
    print(f"Found {len(events_by_category)} event categories")
    return events_by_category


def _is_per_core_freq_event(event_name: str) -> bool:
    """Return True for per-core/thread P-State/Frequency (OS) events whose args
    are keyed by frequency in MHz (e.g. {'1600': 29882.0}) rather than by metric name."""
    lowered = event_name.lower()
    return (
        ("core" in lowered or "thread" in lowered)
        and "p-state" in lowered
        and "(os)" in lowered
    )


def analyze_events(events: List[dict], event_name: str) -> EventMetrics:
    """Analyze events and calculate metrics for any event type."""
    metrics = EventMetrics(event_name=event_name)
    is_core_freq = _is_per_core_freq_event(event_name)

    for event in events:
        timestamp = event.get("ts", 0)

        # Update time range
        metrics.start_time = min(metrics.start_time, timestamp)
        metrics.end_time = max(metrics.end_time, timestamp)

        # Process event arguments
        if "args" in event and event["args"]:
            metrics.total_events += 1

            if is_core_freq:
                # args keys are frequency (MHz) strings; values are duration.
                # Store (timestamp, freq_MHz, "Core {tid}") so the chart can
                # draw one line per core with frequency on the Y axis.
                tid = event.get("tid", "unknown")
                core_label = f"Core {tid}"
                for freq_str, duration in event["args"].items():
                    freq_val = float(freq_str)
                    metrics.peak_value = max(metrics.peak_value, freq_val)
                    metrics.chart_data.append((timestamp, freq_val, core_label))
                    if core_label not in metrics.accumulated:
                        metrics.accumulated[core_label] = 0
                    metrics.accumulated[core_label] += duration
            else:
                for metric_name, value in event["args"].items():
                    # Accumulate values per metric
                    if metric_name not in metrics.accumulated:
                        metrics.accumulated[metric_name] = 0
                    metrics.accumulated[metric_name] += value

                    # Track peak value
                    metrics.peak_value = max(metrics.peak_value, value)

                    # Store data for charting
                    metrics.chart_data.append((timestamp, value, metric_name))

    # Calculate derived metrics
    metrics.duration = metrics.end_time - metrics.start_time

    return metrics


def create_event_chart(metrics: EventMetrics, output_path: Path):
    """Route event to the best chart style based on event name."""
    if not _ensure_matplotlib():
        print(f"Warning: matplotlib not installed, skipping chart for {metrics.event_name}")
        return

    if not metrics.chart_data:
        print(f"Warning: No chart data available for {metrics.event_name}")
        return

    metric_data = _build_metric_data(metrics)
    if not metric_data:
        print(f"Warning: Could not build metric data for {metrics.event_name}")
        return

    chart_type = _detect_chart_type(metrics.event_name)
    if chart_type == "bandwidth":
        _draw_bandwidth_chart(metrics, metric_data, output_path)
    elif chart_type == "core_freq":
        _draw_core_freq_chart(metrics, metric_data, output_path)
    elif chart_type == "state":
        _draw_state_chart(metrics, metric_data, output_path)
    elif chart_type == "sensor":
        _draw_sensor_chart(metrics, metric_data, output_path)
    else:
        _draw_generic_scatter_chart(metrics, metric_data, output_path)


def _build_metric_data(metrics: EventMetrics) -> Dict[str, Dict[str, List[float]]]:
    """Build normalized chart-ready metric series from chart_data."""
    metric_data: Dict[str, Dict[str, List[float]]] = {}

    for timestamp, value, metric_name in metrics.chart_data:
        key = metric_name if metric_name else "value"
        if key not in metric_data:
            metric_data[key] = {"time": [], "values": []}

        metric_data[key]["time"].append(timestamp / 1e6)  # microseconds -> seconds

        if "Bandwidth" in metrics.event_name and value >= 1e6:
            metric_data[key]["values"].append(value / 1e6)  # bytes -> MB (÷ interval for MB/s done in chart)
        elif value >= 1e9:
            metric_data[key]["values"].append(value / 1e9)
        elif value >= 1e6:
            metric_data[key]["values"].append(value / 1e6)
        else:
            metric_data[key]["values"].append(value)

    return metric_data


def _detect_chart_type(event_name: str) -> str:
    """Classify event name to determine preferred chart style."""
    lowered = event_name.lower()

    if "bandwidth" in lowered:
        return "bandwidth"

    # Per-core/thread frequency events need their own chart (one line per core).
    if _is_per_core_freq_event(event_name):
        return "core_freq"

    if "p-state" in lowered or "c-state" in lowered or "residency" in lowered:
        return "state"

    if (
        "temperature" in lowered
        or "power" in lowered
        or "voltage" in lowered
        or "frequency" in lowered
    ):
        return "sensor"

    return "generic"


def _get_y_label(metrics: EventMetrics) -> str:
    y_label = "Value"
    if "Bandwidth" in metrics.event_name:
        y_label = "Bandwidth (MB/s)" if metrics.peak_value >= 1e6 else "Bandwidth (B/s)"
    elif "Power" in metrics.event_name:
        y_label = "Power (W)"
    elif "Frequency" in metrics.event_name:
        y_label = "Frequency (MHz)"
    elif "Voltage" in metrics.event_name:
        y_label = "Voltage (V)"
    elif "Temperature" in metrics.event_name:
        y_label = "Temperature (°C)"
    elif "P-State" in metrics.event_name:
        y_label = "Residency / Value"
    elif "C-State" in metrics.event_name:
        y_label = "Residency (µs)"
    return y_label


def _safe_event_name(event_name: str) -> str:
    return event_name.replace("/", "_").replace("(", "").replace(")", "").replace(" ", "_")


def _save_chart(output_path: Path, metrics: EventMetrics):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_event_name(metrics.event_name)
    chart_path = output_path.with_name(f"{output_path.stem}_{safe_name}_chart.png")
    plt.savefig(chart_path, dpi=300, bbox_inches='tight')
    print(f"Chart saved: {chart_path.name}")
    plt.close()


def _draw_generic_scatter_chart(
    metrics: EventMetrics,
    metric_data: Dict[str, Dict[str, List[float]]],
    output_path: Path,
):
    plt.figure(figsize=(14, 8))

    for metric_name, data in metric_data.items():
        label = metric_name if metric_name else metrics.event_name
        plt.scatter(data['time'], data['values'], label=label, s=10, alpha=0.7)

    plt.xlabel('Time (seconds)', fontsize=12)
    plt.ylabel(_get_y_label(metrics), fontsize=12)
    title = metrics.event_name.replace("(", "").replace(")", "")
    plt.title(f'{title} Over Time (Scatter)', fontsize=14, fontweight='bold')
    if len(metric_data) > 1:
        plt.legend(loc='best', fontsize=9, ncol=2)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    _save_chart(output_path, metrics)


def _draw_sensor_chart(
    metrics: EventMetrics,
    metric_data: Dict[str, Dict[str, List[float]]],
    output_path: Path,
):
    """Line chart for temperature/power/voltage/frequency-style metrics."""
    plt.figure(figsize=(14, 8))

    for metric_name, data in metric_data.items():
        label = metric_name if metric_name else metrics.event_name
        plt.plot(data['time'], data['values'], label=label, linewidth=1.4, alpha=0.85)

    plt.xlabel('Time (seconds)', fontsize=12)
    plt.ylabel(_get_y_label(metrics), fontsize=12)
    title = metrics.event_name.replace("(", "").replace(")", "")
    plt.title(f'{title} Over Time (Line)', fontsize=14, fontweight='bold')
    if len(metric_data) > 1:
        plt.legend(loc='best', fontsize=9, ncol=2)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    _save_chart(output_path, metrics)


def _draw_state_chart(
    metrics: EventMetrics,
    metric_data: Dict[str, Dict[str, List[float]]],
    output_path: Path,
):
    """State/residency events often have many bins: draw top contributors with lines."""
    ranked = sorted(
        metric_data.items(),
        key=lambda item: sum(item[1]['values']) if item[1]['values'] else 0,
        reverse=True,
    )
    top_metrics = ranked[:8]

    plt.figure(figsize=(14, 8))
    for metric_name, data in top_metrics:
        label = metric_name if metric_name else metrics.event_name
        plt.plot(data['time'], data['values'], label=label, linewidth=1.2, alpha=0.85)

    plt.xlabel('Time (seconds)', fontsize=12)
    plt.ylabel(_get_y_label(metrics), fontsize=12)
    title = metrics.event_name.replace("(", "").replace(")", "")
    plt.title(f'{title} Over Time (Top State Bins)', fontsize=14, fontweight='bold')
    plt.legend(loc='best', fontsize=8, ncol=2)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    _save_chart(output_path, metrics)


def _draw_core_freq_chart(
    metrics: EventMetrics,
    metric_data: Dict[str, Dict[str, List[float]]],
    output_path: Path,
):
    """Per-core/thread frequency chart: one step-line per core, Y axis = Frequency (MHz)."""
    # Sort each core's samples by timestamp so the step line is monotonic.
    def _sort_series(data: Dict[str, List[float]]) -> Dict[str, List[float]]:
        pairs = sorted(zip(data["time"], data["values"]), key=lambda p: p[0])
        times, values = zip(*pairs) if pairs else ([], [])
        return {"time": list(times), "values": list(values)}

    sorted_data = {core: _sort_series(data) for core, data in metric_data.items()}

    # Sort cores numerically by the tid suffix ("Core 37684" -> 37684).
    def _core_sort_key(label: str) -> int:
        try:
            return int(label.split()[-1])
        except (ValueError, IndexError):
            return 0

    cores = sorted(sorted_data.keys(), key=_core_sort_key)
    n_cores = len(cores)

    fig_height = max(8, min(n_cores * 0.6 + 4, 24))
    plt.figure(figsize=(16, fig_height))

    cmap = plt.get_cmap("tab20" if n_cores <= 20 else "hsv")
    colors = [cmap(i / max(n_cores, 1)) for i in range(n_cores)]

    for i, core in enumerate(cores):
        data = sorted_data[core]
        plt.step(
            data["time"],
            data["values"],
            label=core,
            linewidth=1.2,
            alpha=0.8,
            where="post",
            color=colors[i],
        )

    plt.xlabel("Time (seconds)", fontsize=12)
    plt.ylabel("Frequency (MHz)", fontsize=12)
    title = metrics.event_name.replace("(", "").replace(")", "")
    plt.title(f"{title} — Per-Core Frequency Over Time", fontsize=14, fontweight="bold")
    ncol = max(1, (n_cores + 9) // 10)  # ~10 entries per legend column
    plt.legend(loc="best", fontsize=8, ncol=ncol)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    _save_chart(output_path, metrics)


def _draw_bandwidth_chart(
    metrics: EventMetrics,
    metric_data: Dict[str, Dict[str, List[float]]],
    output_path: Path,
):
    """Bandwidth events usually have multiple channels: draw top channels as lines."""
    from collections import defaultdict

    # Build per-timestamp interval lookup (seconds).
    # All channels share the same timestamps so we derive intervals from any one channel.
    any_times = next(iter(metric_data.values()))["time"] if metric_data else []
    sorted_unique_ts = sorted(set(any_times))
    interval_for_ts: dict = {}
    for idx, t in enumerate(sorted_unique_ts):
        if idx < len(sorted_unique_ts) - 1:
            interval_for_ts[t] = sorted_unique_ts[idx + 1] - t
        else:
            # Last sample: reuse previous interval
            interval_for_ts[t] = interval_for_ts.get(sorted_unique_ts[idx - 1], 1.0) if idx > 0 else 1.0

    def to_mb_per_sec(times: List[float], values: List[float]) -> List[float]:
        """Divide each MB-value by its sampling interval to get MB/s."""
        return [
            v / interval_for_ts.get(t, 1.0)
            for t, v in zip(times, values)
        ]

    # Convert all channel values to MB/s
    metric_data_mbs: Dict[str, Dict[str, List[float]]] = {
        ch: {"time": data["time"], "values": to_mb_per_sec(data["time"], data["values"])}
        for ch, data in metric_data.items()
    }

    ranked = sorted(
        metric_data_mbs.items(),
        key=lambda item: max(item[1]['values']) if item[1]['values'] else 0,
        reverse=True,
    )
    top_metrics = ranked[:10]

    # Build Total Memory BW series: sum all channels at each timestamp
    total_by_ts: dict = defaultdict(float)
    for _, data in metric_data_mbs.items():
        for t, v in zip(data['time'], data['values']):
            total_by_ts[t] += v
    total_bw_times = sorted(total_by_ts.keys())
    total_bw_values = [total_by_ts[t] for t in total_bw_times]

    plt.figure(figsize=(14, 8))

    # Individual channels as scatter dots (background)
    for metric_name, data in top_metrics:
        label = metric_name if metric_name else metrics.event_name
        plt.scatter(data['time'], data['values'], label=label, s=6, alpha=0.4)

    # Total Memory BW as a bold line on top
    plt.plot(
        total_bw_times,
        total_bw_values,
        label="Total Memory BW",
        color="black",
        linewidth=2.0,
        alpha=0.9,
        zorder=10,
    )

    plt.xlabel('Time (seconds)', fontsize=12)
    plt.ylabel('Bandwidth (MB/s)', fontsize=12)
    title = metrics.event_name.replace("(", "").replace(")", "")
    plt.title(f'{title} Over Time', fontsize=14, fontweight='bold')
    plt.legend(loc='best', fontsize=8, ncol=2)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    _save_chart(output_path, metrics)


def save_event_results(metrics: EventMetrics, output_path: Path):
    """Save analysis results to JSON file."""
    safe_name = metrics.event_name.replace("/", "_").replace("(", "").replace(")", "").replace(" ", "_")
    summary_path = output_path.with_name(f"{output_path.stem}_{safe_name}_summary.json")
    
    with open(summary_path, 'w') as f:
        json.dump(metrics.to_dict(), f, indent=4)
    print(f"Summary saved: {summary_path.name}")


def split_events_to_files(
    events_by_category: Dict[str, List[dict]],
    target_events: List[str],
    split_dir: Path,
    force: bool = False,
):
    """Write full raw events per event category into separate JSON files."""
    split_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nSplitting events into per-event JSON files: {split_dir}")

    for event_name in target_events:
        events = events_by_category.get(event_name, [])
        event_file = split_dir / f"{_safe_event_name(event_name)}_events.json"

        if event_file.exists() and not force:
            print(f"Split skipped: {event_file.name} (already exists)")
            continue

        payload = {
            "event_name": event_name,
            "total_events": len(events),
            "events": events,
        }

        with open(event_file, 'w') as f:
            json.dump(payload, f, indent=2)

        print(f"Split saved: {event_file.name} ({len(events)} events)")


def _json_decimal_default(obj):
    """JSON serializer fallback for types returned by streaming parsers (e.g., Decimal)."""
    if isinstance(obj, Decimal):
        if obj == obj.to_integral_value():
            return int(obj)
        return float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def stream_split_events_to_jsonl(
    input_path: Path,
    split_dir: Path,
    target_events: Optional[List[str]] = None,
    force: bool = False,
) -> Dict[str, int]:
    """One-pass streaming split: write each event into per-category JSONL file."""
    split_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nStreaming split to JSONL files: {split_dir}")

    target_set = set(target_events) if target_events else None
    counts: Dict[str, int] = {}
    handles: Dict[str, any] = {}
    skipped_existing: Dict[str, bool] = {}

    try:
        for event in iter_trace_events(input_path):
            if not isinstance(event, dict):
                continue

            event_name = event.get("cat")
            if not event_name:
                continue

            if target_set is not None and event_name not in target_set:
                continue

            safe_name = _safe_event_name(event_name)
            event_file = split_dir / f"{safe_name}_events.jsonl"

            if event_name not in handles and event_name not in skipped_existing:
                if event_file.exists() and not force:
                    skipped_existing[event_name] = True
                    print(f"Split skipped: {event_file.name} (already exists)")
                    continue

                handles[event_name] = open(event_file, 'w', encoding='utf-8')
                counts[event_name] = 0

            if event_name in skipped_existing:
                continue

            line = json.dumps(event, ensure_ascii=False, default=_json_decimal_default)
            handles[event_name].write(line + "\n")
            counts[event_name] += 1
    finally:
        for event_name, handle in handles.items():
            handle.close()
            safe_name = _safe_event_name(event_name)
            print(f"Split saved: {safe_name}_events.jsonl ({counts[event_name]} events)")

    return counts


def _load_split_event_file(event_file: Path) -> Tuple[str, List[dict]]:
    """Load one split event file and return (event_name, events)."""
    if event_file.suffix == ".jsonl":
        events = []
        with open(event_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                events.append(json.loads(line))

        event_name = event_file.stem.replace("_events", "").replace("_", " ")
        if events and isinstance(events[0], dict) and events[0].get("cat"):
            event_name = events[0].get("cat")
        return event_name, events

    with open(event_file, 'r') as f:
        payload = json.load(f)

    event_name = payload.get("event_name", event_file.stem.replace("_events", ""))
    events = payload.get("events", [])
    if not isinstance(events, list):
        raise ValueError(f"Invalid events payload in {event_file.name}")

    return event_name, events


def generate_charts_from_split(
    split_dir: Path,
    chart_output_prefix: Path,
    selected_events: Optional[List[str]] = None,
):
    """Generate charts by reading per-event JSON files one at a time."""
    if not split_dir.exists() or not split_dir.is_dir():
        tools.errorAndExit(f"Split directory not found: {split_dir}")

    split_files = sorted(list(split_dir.glob("*_events.jsonl")) + list(split_dir.glob("*_events.json")))
    if not split_files:
        tools.errorAndExit(f"No split event files found in: {split_dir}")

    selected_set = set(selected_events) if selected_events else None
    print(f"\nGenerating charts from split files ({len(split_files)} files)...")

    processed = 0
    for event_file in split_files:
        try:
            event_name, events = _load_split_event_file(event_file)
        except Exception as exc:
            print(f"Warning: Failed to load {event_file.name}: {exc}")
            continue

        if selected_set is not None and event_name not in selected_set:
            continue

        print(f"\n[{event_name}] from {event_file.name}")
        metrics = analyze_events(events, event_name)
        create_event_chart(metrics, chart_output_prefix)

        print(f"  Events: {metrics.total_events}")
        print(f"  Duration: {metrics.duration / 1e6:.2f} seconds")
        if metrics.peak_value > 0:
            if metrics.peak_value >= 1e6:
                print(f"  Peak: {metrics.peak_value / 1e6:.2f} MB")
            else:
                print(f"  Peak: {metrics.peak_value:.2f}")

        processed += 1

    print(f"\n✓ Chart generation complete! Processed {processed} event type(s).")


def main():
    """Main execution flow."""
    total_start = time.perf_counter()
    print(f"[timer] start: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    args = parse_arguments()
    script_dir = Path(__file__).parent
    
    # Stage-2 mode: chart generation from existing split files
    if args.from_split:
        split_dir = Path(args.from_split)
        if args.output:
            chart_output_prefix = Path(args.output)
        else:
            chart_output_prefix = split_dir / "from_split_analysis"

        stage_start = time.perf_counter()
        generate_charts_from_split(split_dir, chart_output_prefix, selected_events=args.events)
        stage_elapsed = time.perf_counter() - stage_start
        total_elapsed = time.perf_counter() - total_start
        print(f"[timer] stage from-split sec: {stage_elapsed:.3f}")
        print(f"[timer] end: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"[timer] total sec: {total_elapsed:.3f}")
        return

    # Stage-1 mode: split from source trace
    if args.input:
        input_path = Path(args.input)
    else:
        input_path = select_file_dialog(script_dir)
        if not input_path:
            tools.errorAndExit("No file selected")

    if not input_path.exists():
        tools.errorAndExit(f"File not found: {input_path}")

    print(f"Processing: {input_path.name}")

    # Handle --list-events flag using lightweight in-memory scan
    if args.list_events:
        stage_start = time.perf_counter()
        data = load_swjson(input_path)
        if not data:
            tools.errorAndExit(f"Failed to load {input_path}")
        events_by_category = parse_trace_events(data)
        if not events_by_category:
            tools.errorAndExit("No events found in file")
        print(f"[timer] stage list-events sec: {time.perf_counter() - stage_start:.3f}")

        print(f"\nAvailable event categories ({len(events_by_category)}):")
        for i, category in enumerate(sorted(events_by_category.keys()), 1):
            event_count = len(events_by_category[category])
            print(f"  {i:2d}. {category} ({event_count} events)")
        return
    
    # Set output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent / f"{input_path.stem}_analysis"

    if args.split_dir:
        split_dir = Path(args.split_dir)
    else:
        split_dir = output_path.parent / f"{output_path.stem}_events_stream"

    target_events = args.events if args.events else None
    if target_events:
        print(f"\nPreparing {'legacy in-memory' if args.in_memory_split else 'streaming'} split for {len(target_events)} selected event type(s)...")
    else:
        print(f"\nPreparing {'legacy in-memory' if args.in_memory_split else 'streaming'} split for all event types...")

    stage_start = time.perf_counter()
    if args.in_memory_split:
        data = load_swjson(input_path)
        if not data:
            tools.errorAndExit(f"Failed to load {input_path}")
        print(f"[timer] stage load sec: {time.perf_counter() - stage_start:.3f}")

        stage_start = time.perf_counter()
        events_by_category = parse_trace_events(data)
        if not events_by_category:
            tools.errorAndExit("No events found in file")
        print(f"[timer] stage parse/group sec: {time.perf_counter() - stage_start:.3f}")

        if target_events:
            for event_name in target_events:
                if event_name not in events_by_category:
                    print(f"Warning: Event '{event_name}' not found in file")
            target_events = [event_name for event_name in target_events if event_name in events_by_category]
            if not target_events:
                tools.errorAndExit("None of the specified events were found")
        else:
            target_events = list(events_by_category.keys())

        stage_start = time.perf_counter()
        split_events_to_files(
            events_by_category,
            target_events,
            split_dir,
            force=args.force,
        )
    else:
        event_counts = stream_split_events_to_jsonl(
            input_path,
            split_dir,
            target_events=target_events,
            force=args.force,
        )
        if target_events and not event_counts:
            print("Warning: No matching events were written during stream split.")

    print(f"[timer] stage split sec: {time.perf_counter() - stage_start:.3f}")

    if args.split_only:
        total_elapsed = time.perf_counter() - total_start
        print(f"\n✓ Split complete! Per-event files saved to: {split_dir}")
        print(f"[timer] end: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"[timer] total sec: {total_elapsed:.3f}")
        return

    stage_start = time.perf_counter()
    generate_charts_from_split(split_dir, output_path, selected_events=target_events)
    print(f"[timer] stage chart sec: {time.perf_counter() - stage_start:.3f}")

    total_elapsed = time.perf_counter() - total_start
    print(f"\n✓ Pipeline complete! Results saved to: {output_path.parent}")
    print(f"[timer] end: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[timer] total sec: {total_elapsed:.3f}")


if __name__ == "__main__":
    main()
