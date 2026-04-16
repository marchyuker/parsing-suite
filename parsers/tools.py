import re
import sys
import os
import json
import numpy as np


def tk_dialogs(
    dialog_type="open_file",
    title="Select a file",
    initial_dir=None,
    filetypes=None,
):
    """Small tkinter dialog helper for file/folder interactions.

    Supported dialog_type values:
    - open_file
    - open_folder
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None

    root = tk.Tk()
    root.withdraw()

    selected = None
    try:
        if dialog_type == "open_folder":
            selected = filedialog.askdirectory(
                title=title,
                initialdir=initial_dir,
            )
        else:
            selected = filedialog.askopenfilename(
                title=title,
                initialdir=initial_dir,
                filetypes=filetypes or [("All files", "*.*")],
            )
    finally:
        root.destroy()

    return selected if selected else None

def parseNumeric(text) :
    return ''.join(re.findall(r'[0-9.]', text))
def parseDevice(text) :
    return ''.join(re.findall(r'[A-Z.0-9]', text))


def tryRoundifNumber(value) :
    try :
        return round(float(value), 2)
    except ValueError as e:
        return value

def tryIntifNumber(value) :
    try :
        return int(value)
    except ValueError as e:
        return value
    
# add def saveLastOpenedFolder(folder_path):
def saveLastOpenedFolder(folder_path):
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(script_dir)
        last_folder_file = os.path.join(parent_dir, "config", "last_opened_folder.txt")
        with open(last_folder_file, "w") as f:
            f.write(folder_path)
    except Exception as e:
        print(f"Failed to save last opened folder: {e}")
    
def splitLastItem(abs_path, joint, cutNum) :
    item_list = abs_path.split(joint)
    return [joint.join(item_list[:-cutNum]), item_list[len(item_list)-1]]

def trim_list(data_list):
    """
    Removes empty items from the back of a list.
    An item is considered 'empty' if it evaluates to False (e.g., '', 0, None, [], {}).
    """
    while data_list and data_list[-1].strip() == "":  # Check if list is not empty and last element is falsy
        data_list.pop()
    return [item.strip() for item in data_list]

def find_dict_by_key_value(data, key, value):
    for item in data:
        if item.get(key) == value:
            return item
    return None

def get_rest_cpu_pstate(rest_dic_list, key, rest_cpu_p_residency_list):
    if len(rest_dic_list) == 0:
        for item in rest_cpu_p_residency_list :
            tdic = dict()
            tdic[key] = tryRoundifNumber(item) # round(float(item), 2)
            rest_dic_list.append(tdic)
    else :
        for idx in range(len(rest_dic_list)) :
            tdic = rest_dic_list[idx]
            if key is not tdic:
                tdic[key] = tryRoundifNumber(rest_cpu_p_residency_list[idx]) # round(float(rest_cpu_p_residency_list[idx]), 2)

def getSocPowerRailName(DAQ_target, picks):
    soc_power_rail_name = ""
    soc_list = ["P_SOC", "P_MCP", "P_SOC+MEMORY"]
    # for loop from the backward order of DAQ_target keys
    # check the possible soc power rail names if it contains "P_SOC", "P_MCP" or "P_SOC+MEMORY"
    # make this a list for future expansion
    # then assign the first found name to soc_power_rail_name   
    for key in reversed(list(DAQ_target.keys())):
        if key in soc_list:
            soc_power_rail_name = key
            break
    picks['SOC_POWER_RAIL_NAME'] = soc_power_rail_name

def flatten_model_dic(entry) :
    
    if "model_output_obj" in entry and "model_output_data" in entry["model_output_obj"] :
        copied = entry["model_output_obj"]['model_output_data'].copy()
        new_output = dict()
        for index, key in enumerate(copied):
            value_list = copied[key]
            updated_key = key+f" ({value_list[1]})" if value_list[1] != "" else key
            new_output[updated_key] = value_list[0]
        new_output['model_output_path'] = entry["model_output_obj"]["model_output_path"]
        return new_output
    else :
        return {}
    
def flatten_fps_dic(entry) :
    
    if "fps_img_obj" in entry and "fps_data" in entry["fps_img_obj"] :
        copied = entry["fps_img_obj"]['fps_data'].copy()
        new_output = dict()
        for index, key in enumerate(copied):
            value_list = copied[key]
            # updated_key = key+f" ({value_list[1]})" if value_list[1] != "" else key
            new_output[key] = value_list
        new_output['Eng(J)/Frame'] = entry["power_obj"]["power_data"]["Energy (J)"] / copied["frames_rendered"] if "Energy (J)" in entry["power_obj"]["power_data"] and "frames_rendered" in copied and copied["frames_rendered"] != '' and copied["frames_rendered"] != 0 else ''
        new_output['fps_img_path'] = entry["fps_img_obj"]["fps_img_path"]
        return new_output
    else :
        return {}

def flatten_mlc_output_dic(entry) :
    
    if "mlc_output_obj" in entry and "mlc_output_data" in entry["mlc_output_obj"] :
        copied = entry["mlc_output_obj"]['mlc_output_data'].copy()
        new_output = dict()
        for index, key in enumerate(copied):
            value_list = copied[key]
            updated_key = key+f" ({value_list[1]})" if value_list[1] != "" else key
            new_output[updated_key] = value_list[0]
        new_output['mlc_output_path'] = entry["mlc_output_obj"]["mlc_output_path"]
        return new_output
    else :
        return {}

def flatten_LPmode_sr_dic(entry):
    if "sr_output_obj" in entry and "sr_output_data" in entry["sr_output_obj"] and "NOP" in entry["sr_output_obj"]['sr_output_data'] and "Affinity" in entry["sr_output_obj"]['sr_output_data'] :
        copied = entry["sr_output_obj"]['sr_output_data'].copy()
        copied["NOP"] = entry["sr_output_obj"]['sr_output_data']["NOP"]
        copied["Affinity"] = entry["sr_output_obj"]['sr_output_data']["Affinity"]
        return copied
    else :
        return {}
        
def flatten_power_dic(entry, picks):
    if "power_obj" in entry and "power_data" in entry["power_obj"] :
        copied = entry["power_obj"]['power_data'].copy()
        copied["power_type"] = entry['power_obj']['power_type']
        copied[picks['power_pick']+"_picked"] = entry['power_obj']['picked']
        copied["power_path"] = entry['power_obj']['file_path']
        return copied
    else :
        return {}
    
def flatten_teams_vpt_camera_dic(entry):
    if "vpt_output_obj" in entry and "vpt_output_data" in entry["vpt_output_obj"] :
        copied = entry["vpt_output_obj"].copy()
        new_output = dict()
        new_output['min_cam_fps'] = copied["min_cam_fps"]
        new_output['median_cam_fps'] = copied["median_cam_fps"]
        new_output['vpt_output_path'] = copied["vpt_output_path"]
        return new_output
    else :
        return {}
    
def flatten_procyon_xml_dic(entry):
    if "procyon_result_obj" in entry and "procyon_data" in entry["procyon_result_obj"] :
        copied = entry["procyon_result_obj"]["procyon_data"].copy()
        new_output = dict()
        new_output['procyon_overall_score'] = copied["procyon_overall_score"]
        new_output['procyon_xml_path'] = entry["procyon_result_obj"]["procyon_xml_path"]
        return new_output
    else :
        return {}
    
def flatten_trace_dic(entry):
    if "trace_obj" in entry and "trace_data" in entry["trace_obj"] and entry["trace_obj"]["trace_data"] != None:
        copied = entry["trace_obj"]['trace_data'].copy()
        copied["total_row"] = entry['trace_obj']['total_row']
        copied["duration_in_scale"] = entry['trace_obj']['duration_in_scale']
        copied["inf_start"] = entry['trace_obj']['inf_start']
        copied["inf_end"] = entry['trace_obj']['inf_end']
        copied["Device"] = entry["trace_obj"]["Device"]
        copied["Token/s"] = entry["model_output_obj"]["model_output_data"]["throughput"][0] if "model_output_obj" in entry and "model_output_data" in entry["model_output_obj"] and "throughput" in entry["model_output_obj"]["model_output_data"] else None
        copied["file_path"] = entry['trace_obj']['file_path']
        return copied
    else :
        return {}
        
def flatten_socwatch_dic_per_core(entry, socwatch_targets):
    if "socwatch_obj" in entry and "socwatch_tables" in entry["socwatch_obj"] :
        flatten_list = []
        rest_cpu_pstate_list = []
        flat_socwatch = {}
        for table in entry["socwatch_obj"]["socwatch_tables"]:
            # flat_socwatch.update(table["table_data"]) if "table_data" in table else {}

            data = table["table_data"]
            if "bucketized_data" in table:
                data = table["bucketized_data"]
            for item in data :
                # print(item, item+"_"+table["label"])
                new_key = item+"        "+table["label"]
                if table["label"] == "CPU_Pstate":
                    flat_socwatch[new_key] = tryRoundifNumber(data[item][0])
                    get_rest_cpu_pstate(rest_cpu_pstate_list, new_key, data[item][1:]) if isinstance(data[item], list) else None
                else :
                    flat_socwatch[new_key] = data[item]
            # flat_socwatch[table]
        flat_socwatch['socwatch_path'] = entry['socwatch_obj']['socwatch_path']
        flatten_list.append(flat_socwatch)
        flatten_list.extend(rest_cpu_pstate_list)
        return flatten_list
    else :
        return []

def flatten_socwatch_dic(entry, socwatch_targets):
    if "socwatch_obj" in entry and "socwatch_tables" in entry["socwatch_obj"] :
        flat_socwatch = {}
        for table in entry["socwatch_obj"]["socwatch_tables"]:
            # flat_socwatch.update(table["table_data"]) if "table_data" in table else {}

            data = table["table_data"]
            if "bucketized_data" in table:
                data = table["bucketized_data"]
            for item in data :
                # print(item, item+"_"+table["label"])
                flat_socwatch[item+"        "+table["label"]] = data[item]
            # flat_socwatch[table]
        flat_socwatch['socwatch_path'] = entry['socwatch_obj']['socwatch_path']
        return flat_socwatch
    else :
        return {}
    
def flatten_pcie_socwatch_dic(entry, pcie_socwatch_targets):
    if "pcie_socwatch_obj" in entry and "pcie_socwatch_tables" in entry["pcie_socwatch_obj"] :
        flat_socwatch = {}
        for table in entry["pcie_socwatch_obj"]["pcie_socwatch_tables"]:
            # flat_socwatch.update(table["table_data"]) if "table_data" in table else {}

            data = table["table_data"]
            if "bucketized_data" in table:
                data = table["bucketized_data"]
            for item in data :
                # print(item, item+"_"+table["label"])
                flat_socwatch[item+"        "+table["label"]] = tryRoundifNumber(data[item])
            # flat_socwatch[table]
        flat_socwatch['pcie_socwatch_path'] = entry['pcie_socwatch_obj']['pcie_socwatch_path']
        return flat_socwatch
    else :
        return {}

def get_median(values) :
    return np.median(values)
        
def errorAndExit(msgs) :
    print("=============================================================================")
    sys.exit("[Error] :: " + msgs)
    print("=============================================================================")

    
def jsonLoader(filename, picks) :

    try :
        with open(os.path.join(filename), 'r') as json_file:
            data = json.load(json_file)
            parsePowerRailNames(data["DAQ_target"], picks) if "DAQ_target" in data else None
            return data
    except Exception as e:
        errorAndExit(f"Failed to load JSON file: {e}")

def parsePowerRailNames(DAQ_target, picks):
    picks["SOC_POWER_RAIL_NAME"] = DAQ_target.get("SOC_POWER_RAIL_NAME")
    picks["PCORE_POWER_RAIL_NAME"] = DAQ_target.get("PCORE_POWER_RAIL_NAME")
    picks["SA_POWER_RAIL_NAME"] = DAQ_target.get("SA_POWER_RAIL_NAME")
    picks["GT_POWER_RAIL_NAME"] = DAQ_target.get("GT_POWER_RAIL_NAME")
    print("============================= ", picks)