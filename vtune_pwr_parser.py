#!/usr/bin/env python3
"""
VTune PWR Parser

Workflow:
1) Accept a .pwr input (or discover/generate one from .etl using socwatch_pp.py)
2) Import .pwr into a VTune result directory
3) Try VTune report export per selected event group
4) Stream all parsed events to JSONL (from .pwr metadata and optional .swjson fallback)
"""

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

try:
    import ijson
except ImportError:
    ijson = None

import parsers.tools as tools


KEYWORDS = {
    "tab_group",
    "tab_group_id",
    "timeline_group",
    "timeline_group_id",
    "entity",
    "entity_id",
    "field",
    "field_id",
    "color",
    "color_id",
    "quantity",
    "quantity_type",
    "info_type",
    "info_type_id",
    "metric_type",
    "metric_type_id",
    "nameid_attribute",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="VTune PWR Parser",
        description="Parse VTune .pwr data, export VTune reports, and stream events to JSONL/CSV.",
    )
    parser.add_argument("-i", "--input", help="Input .pwr file, .etl file, or folder path")
    parser.add_argument("-o", "--output-dir", help="Output directory (default: <input_parent>/<input_stem>_pwr_parse)")
    parser.add_argument(
        "-e",
        "--events",
        nargs="+",
        help='Event group names to export (example: "DDR Bandwidth Requests by Component"). Default: all groups',
    )
    parser.add_argument("--cli", action="store_true", help="Force CLI mode (no file dialog)")
    parser.add_argument("--socwatch-dir", help="Path to SocWatch directory or socwatch.exe (forwarded to socwatch_pp.py)")
    parser.add_argument(
        "--socwatch-script",
        default=str(Path(__file__).resolve().parent / "socwatch_pp.py"),
        help="Path to socwatch_pp.py",
    )
    parser.add_argument("--vtune-exe", help="Path to vtune.exe")
    parser.add_argument(
        "--skip-swjson-fallback",
        action="store_true",
        help="Skip .swjson fallback streaming when VTune report data is unavailable",
    )
    parser.add_argument(
        "--generate-swjson",
        action="store_true",
        help="If no .swjson exists, generate it via socwatch_pp.py -r json",
    )
    parser.add_argument(
        "--keep-vtune-result",
        action="store_true",
        help="Keep VTune imported result folder (default: keep it)",
    )
    return parser.parse_args()


def select_input_dialog(script_dir: Path) -> Optional[Path]:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()

    last_folder_file = script_dir / "config" / "last_opened_folder.txt"
    initial_dir = None
    if last_folder_file.exists():
        try:
            initial_dir = last_folder_file.read_text(encoding="utf-8").strip()
        except Exception:
            initial_dir = None

    path = filedialog.askopenfilename(
        title="Select .pwr or .etl file (Cancel to choose folder)",
        initialdir=initial_dir,
        filetypes=[
            ("VTune/SocWatch files", "*.pwr *.etl"),
            ("VTune PWR", "*.pwr"),
            ("SocWatch ETL", "*.etl"),
            ("All files", "*.*"),
        ],
    )
    if path:
        tools.saveLastOpenedFolder(str(Path(path).parent))
        return Path(path)

    folder = filedialog.askdirectory(
        title="Select folder containing .pwr or .etl files",
        initialdir=initial_dir,
    )
    if folder:
        tools.saveLastOpenedFolder(str(Path(folder)))
        return Path(folder)

    return None


def find_vtune_exe(user_path: Optional[str]) -> Optional[Path]:
    candidates: List[Path] = []
    if user_path:
        candidates.append(Path(user_path))
    candidates.extend(
        [
            Path(r"C:\Program Files (x86)\Intel\oneAPI\vtune\latest\bin64\vtune.exe"),
            Path(r"C:\Program Files\Intel\oneAPI\vtune\latest\bin64\vtune.exe"),
        ]
    )
    for item in candidates:
        if item.exists() and item.is_file():
            return item
    return None


def run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def find_latest_file(folder: Path, pattern: str) -> Optional[Path]:
    matches = list(folder.rglob(pattern))
    if not matches:
        return None
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def resolve_input(args: argparse.Namespace, script_dir: Path) -> Path:
    if args.input:
        return Path(args.input)
    if args.cli:
        raise SystemExit("❌ --input is required in --cli mode")
    selected = select_input_dialog(script_dir)
    if not selected:
        raise SystemExit("❌ No input selected")
    return selected


def maybe_generate_pwr(
    input_path: Path,
    socwatch_script: Path,
    socwatch_dir: Optional[str],
) -> Tuple[Optional[Path], Optional[Path]]:
    etl_root: Optional[Path] = None
    pwr_path: Optional[Path] = None

    if input_path.is_file() and input_path.suffix.lower() == ".pwr":
        if input_path.exists():
            return input_path, input_path.parent
        etl_root = input_path.parent
    elif input_path.is_file() and input_path.suffix.lower() == ".etl":
        etl_root = input_path.parent
        pwr_path = input_path.with_suffix(".pwr")
        if pwr_path.exists():
            return pwr_path, etl_root
    elif input_path.is_dir():
        etl_root = input_path
        existing = find_latest_file(etl_root, "*.pwr")
        if existing:
            return existing, etl_root
    else:
        etl_root = input_path.parent if input_path.parent.exists() else None

    if not etl_root or not etl_root.exists():
        return None, None

    if not socwatch_script.exists():
        raise SystemExit(f"❌ socwatch_pp.py not found: {socwatch_script}")

    print(f"⚙️  .pwr not found. Generating from ETL via {socwatch_script.name} ...")
    cmd = [sys.executable, str(socwatch_script), "--cli", "-r", "vtune", str(etl_root)]
    if socwatch_dir:
        cmd = [sys.executable, str(socwatch_script), "--cli", "--socwatch-dir", socwatch_dir, "-r", "vtune", str(etl_root)]

    code, out, err = run_cmd(cmd)
    if out.strip():
        print(out.strip())
    if err.strip():
        print(err.strip())
    if code != 0:
        raise SystemExit("❌ Failed to generate .pwr using socwatch_pp.py")

    if pwr_path and pwr_path.exists():
        return pwr_path, etl_root

    generated = find_latest_file(etl_root, "*.pwr")
    if not generated:
        raise SystemExit("❌ No .pwr found after socwatch_pp.py execution")
    return generated, etl_root


def import_pwr_with_vtune(vtune_exe: Path, pwr_path: Path, result_dir: Path) -> None:
    if result_dir.exists():
        shutil.rmtree(result_dir, ignore_errors=True)
    result_dir.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(vtune_exe),
        "-import",
        str(pwr_path),
        "-result-dir",
        str(result_dir),
        "-finalization-mode=full",
    ]
    code, out, err = run_cmd(cmd)
    if out.strip():
        print(out.strip())
    if err.strip():
        print(err.strip())
    if code != 0:
        raise SystemExit("❌ VTune import failed")


def export_summary_report(vtune_exe: Path, result_dir: Path, output_csv: Path) -> None:
    cmd = [
        str(vtune_exe),
        "-report",
        "summary",
        "-r",
        str(result_dir),
        "-format",
        "csv",
        "-report-output",
        str(output_csv),
    ]
    code, out, err = run_cmd(cmd)
    if out.strip():
        print(out.strip())
    if err.strip():
        print(err.strip())
    if code != 0:
        print("⚠️  Could not export summary report")


def _is_valid_label(value: str) -> bool:
    v = value.strip()
    if len(v) < 3:
        return False
    if v.lower() in KEYWORDS:
        return False
    if re.fullmatch(r"[0-9.,#|\-_/ ]+", v):
        return False
    return True


def extract_metadata_from_pwr(pwr_path: Path) -> Dict[str, Dict[str, Set[str]]]:
    raw = pwr_path.read_bytes()
    groups: Dict[str, Dict[str, Set[str]]] = {}
    text_raw = raw.decode("latin-1", errors="ignore")

    # Pattern for concatenated metadata blocks inside .pwr:
    # <label><label>tab_grouptab_group_id / entityentity_id / fieldfield_id
    # Keep labels conservative to avoid large noisy captures.
    label_pattern = r"([A-Za-z][A-Za-z0-9 ()_\-/:.+,#]{2,}?)"

    group_matches = re.finditer(label_pattern + r"\1tab_grouptab_group_id", text_raw)
    group_order: List[str] = []
    for match in group_matches:
        label = match.group(1).strip()
        if _is_valid_label(label):
            if label not in groups:
                groups[label] = {"entities": set(), "fields": set()}
                group_order.append(label)

    # Fallback to tokenized parse if pattern matching missed everything.
    if not groups:
        text = "".join(chr(b) if 32 <= b <= 126 else "\n" for b in raw)
        tokens = [x.strip() for x in re.split(r"\n+", text) if x.strip()]
        current_group: Optional[str] = None
        for i, token in enumerate(tokens):
            low = token.lower()
            if low == "tab_group":
                candidates = [tokens[j] for j in (i - 1, i - 2, i - 3) if j >= 0]
                group = next((c for c in candidates if _is_valid_label(c)), None)
                if group:
                    current_group = group
                    groups.setdefault(group, {"entities": set(), "fields": set()})
                    if group not in group_order:
                        group_order.append(group)
            elif low == "entity" and current_group:
                candidates = [tokens[j] for j in (i - 1, i - 2) if j >= 0]
                entity = next((c for c in candidates if _is_valid_label(c)), None)
                if entity:
                    groups[current_group]["entities"].add(entity)
            elif low == "field" and current_group:
                candidates = [tokens[j] for j in (i - 1, i - 2) if j >= 0]
                field = next((c for c in candidates if _is_valid_label(c)), None)
                if field:
                    groups[current_group]["fields"].add(field)

    # Associate entity/field labels to nearest known group in encounter order.
    # This keeps extraction lightweight while still useful for inventory/export.
    if group_order:
        entity_matches = [m.group(1).strip() for m in re.finditer(label_pattern + r"\1entityentity_id", text_raw)]
        field_matches = [m.group(1).strip() for m in re.finditer(label_pattern + r"\1fieldfield_id", text_raw)]

        group_count = len(group_order)
        for idx, label in enumerate(entity_matches):
            if _is_valid_label(label):
                group_name = group_order[idx % group_count]
                groups[group_name]["entities"].add(label)

        for idx, label in enumerate(field_matches):
            if _is_valid_label(label):
                group_name = group_order[idx % group_count]
                groups[group_name]["fields"].add(label)

    return groups


def select_groups(all_groups: List[str], requested: Optional[List[str]]) -> List[str]:
    if not requested:
        return all_groups
    req_lower = [item.lower() for item in requested]
    selected = [g for g in all_groups if any(r == g.lower() or r in g.lower() for r in req_lower)]
    return selected


def sanitize_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")[:120] or "event"


def vtune_timeline_export_group(vtune_exe: Path, result_dir: Path, group_name: str, out_csv: Path) -> Tuple[bool, str]:
    cmd = [
        str(vtune_exe),
        "-R",
        "timeline",
        "-r",
        str(result_dir),
        "-report-knob",
        f"column-by={group_name}",
        "-format",
        "csv",
        "-report-output",
        str(out_csv),
    ]
    code, out, err = run_cmd(cmd)
    msg = (out + "\n" + err).strip()
    if code != 0:
        return False, msg
    if not out_csv.exists() or out_csv.stat().st_size == 0:
        return False, "Empty CSV"
    try:
        first = out_csv.read_text(encoding="utf-8", errors="ignore")
        if "No data to show" in first:
            return False, "No data to show"
    except Exception:
        pass
    return True, "OK"


def find_swjson_candidate(pwr_path: Path, etl_root: Optional[Path]) -> Optional[Path]:
    direct = pwr_path.with_suffix(".swjson")
    if direct.exists():
        return direct
    if etl_root and etl_root.exists():
        found = find_latest_file(etl_root, "*.swjson")
        if found:
            return found
    return find_latest_file(pwr_path.parent, "*.swjson")


def maybe_generate_swjson(
    etl_root: Optional[Path],
    socwatch_script: Path,
    socwatch_dir: Optional[str],
) -> Optional[Path]:
    if not etl_root or not etl_root.exists():
        return None
    print("⚙️  Generating .swjson via socwatch_pp.py -r json ...")
    cmd = [sys.executable, str(socwatch_script), "--cli", "-r", "json", str(etl_root)]
    if socwatch_dir:
        cmd = [sys.executable, str(socwatch_script), "--cli", "--socwatch-dir", socwatch_dir, "-r", "json", str(etl_root)]
    code, out, err = run_cmd(cmd)
    if out.strip():
        print(out.strip())
    if err.strip():
        print(err.strip())
    if code != 0:
        return None
    return find_latest_file(etl_root, "*.swjson")


def iter_swjson_events(swjson_path: Path) -> Iterable[dict]:
    if ijson is not None:
        with open(swjson_path, "rb") as f:
            for item in ijson.items(f, "traceEvents.item"):
                yield item
        return

    data = json.loads(swjson_path.read_text(encoding="utf-8"))
    for item in data.get("traceEvents", []):
        yield item


def stream_swjson(
    swjson_path: Path,
    selected_groups: Set[str],
    all_events_jsonl: Path,
    events_csv_dir: Path,
) -> int:
    events_csv_dir.mkdir(parents=True, exist_ok=True)
    handles: Dict[str, Tuple[object, csv.writer]] = {}
    count = 0

    with open(all_events_jsonl, "a", encoding="utf-8") as out_jsonl:
        for event in iter_swjson_events(swjson_path):
            cat = str(event.get("cat", "Unknown"))
            if selected_groups and cat not in selected_groups:
                continue

            record = {
                "source": "swjson",
                "event_group": cat,
                "ts": event.get("ts"),
                "pid": event.get("pid"),
                "tid": event.get("tid"),
                "ph": event.get("ph"),
                "args": event.get("args", {}),
            }
            out_jsonl.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

            key = sanitize_name(cat)
            if key not in handles:
                csv_path = events_csv_dir / f"{key}.csv"
                f = open(csv_path, "w", newline="", encoding="utf-8")
                w = csv.writer(f)
                w.writerow(["event_group", "ts", "pid", "tid", "ph", "args_json"])
                handles[key] = (f, w)

            _, writer = handles[key]
            writer.writerow([
                cat,
                event.get("ts"),
                event.get("pid"),
                event.get("tid"),
                event.get("ph"),
                json.dumps(event.get("args", {}), ensure_ascii=False),
            ])

    for f, _ in handles.values():
        f.close()

    return count


def main() -> None:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent

    print("🔎 VTune PWR Parser")
    print("=" * 40)

    input_path = resolve_input(args, script_dir)
    socwatch_script = Path(args.socwatch_script)
    vtune_exe = find_vtune_exe(args.vtune_exe)
    if not vtune_exe:
        raise SystemExit("❌ vtune.exe not found. Use --vtune-exe or install Intel oneAPI VTune.")

    pwr_path, etl_root = maybe_generate_pwr(input_path, socwatch_script, args.socwatch_dir)
    if not pwr_path:
        raise SystemExit("❌ Could not resolve a .pwr file from the provided input")

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = pwr_path.parent / f"{pwr_path.stem}_pwr_parse"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📄 PWR input: {pwr_path}")
    print(f"📁 Output dir: {output_dir}")

    result_dir = output_dir / "vtune_result"
    import_pwr_with_vtune(vtune_exe, pwr_path, result_dir)
    export_summary_report(vtune_exe, result_dir, output_dir / "vtune_summary.csv")

    metadata = extract_metadata_from_pwr(pwr_path)
    all_groups = sorted(metadata.keys())
    selected_groups = select_groups(all_groups, args.events)

    if args.events and not selected_groups:
        if all_groups:
            print("⚠️  No requested groups matched .pwr metadata. Proceeding with all groups.")
            selected_groups = all_groups
        else:
            print("⚠️  Metadata extraction found no groups. Using requested groups directly for VTune export attempts.")
            selected_groups = list(args.events)
    elif not selected_groups and all_groups:
        selected_groups = all_groups

    groups_csv = output_dir / "event_groups.csv"
    with open(groups_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["event_group", "entities", "fields"])
        for group in all_groups:
            entities = sorted(metadata[group]["entities"])
            fields = sorted(metadata[group]["fields"])
            writer.writerow([group, "|".join(entities), "|".join(fields)])

    all_events_jsonl = output_dir / "events_stream.jsonl"
    with open(all_events_jsonl, "w", encoding="utf-8") as f:
        for group in selected_groups:
            base = {
                "source": "pwr-metadata",
                "event_group": group,
                "entities": sorted(metadata[group]["entities"]),
                "fields": sorted(metadata[group]["fields"]),
            }
            f.write(json.dumps(base, ensure_ascii=False) + "\n")

    vtune_csv_dir = output_dir / "vtune_report_csv"
    vtune_csv_dir.mkdir(parents=True, exist_ok=True)
    status_csv = output_dir / "vtune_report_status.csv"
    vtune_success = 0

    with open(status_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["event_group", "status", "message", "csv_file"])
        for group in selected_groups:
            csv_name = sanitize_name(group) + ".csv"
            csv_path = vtune_csv_dir / csv_name
            ok, message = vtune_timeline_export_group(vtune_exe, result_dir, group, csv_path)
            writer.writerow([group, "ok" if ok else "failed", message.replace("\n", " "), str(csv_path)])
            if ok:
                vtune_success += 1

    swjson_rows = 0
    if not args.skip_swjson_fallback:
        swjson_path = find_swjson_candidate(pwr_path, etl_root)
        if not swjson_path and args.generate_swjson:
            swjson_path = maybe_generate_swjson(etl_root, socwatch_script, args.socwatch_dir)

        if swjson_path and swjson_path.exists():
            print(f"📘 SWJSON fallback: {swjson_path}")
            swjson_rows = stream_swjson(
                swjson_path=swjson_path,
                selected_groups=set(selected_groups),
                all_events_jsonl=all_events_jsonl,
                events_csv_dir=output_dir / "swjson_event_csv",
            )
        else:
            print("ℹ️  No .swjson found for fallback streaming (use --generate-swjson to create one).")

    print("\n✅ Completed")
    print(f"   - Total event groups found: {len(all_groups)}")
    print(f"   - Selected event groups: {len(selected_groups)}")
    print(f"   - VTune timeline CSV success: {vtune_success}/{len(selected_groups)}")
    print(f"   - SWJSON streamed rows: {swjson_rows}")
    print(f"   - Event groups CSV: {groups_csv}")
    print(f"   - JSONL stream: {all_events_jsonl}")
    print(f"   - VTune report status: {status_csv}")


if __name__ == "__main__":
    main()
