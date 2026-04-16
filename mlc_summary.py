
import os
import time
import json
from os import listdir
from os.path import isfile, join
import parsers.tools as tools
import parsers.mlc_output_parser as mlc
import parsers.socwatch_summary_parser as soc
import parsers.power_summary_parser as psp
import parsers.power_trace_parser as ptp
import parsers.power_checker as pck
import parsers.reporter as rpt

import argparse



parser = argparse.ArgumentParser(prog='Phi summary parser')
parser.add_argument('-i', '--input', help='input path. this will be the bese of the summray, will detect all files and folders from that path tree')
parser.add_argument('-o', '--output', help='output path. location of file and file name')
parser.add_argument('-d', '--daq', help='DAQ power rail name dictionary')
parser.add_argument('-st', '--swtarget', help='a list of dictionary objects that you want to parse from the socwatch summary')
parser.add_argument('-hb', '--hobl', action='store_true', help='if the data is collected via HOBL, looking for .PASS or .FAIL file in the folder to set file path as data set ID')

# parser.print_help()
args = parser.parse_args()
print("args: ", args)

socwatch_targets = [
    {"key": "CPU_model", "lookup": "CPU native model"},
    {"key": "PCH_SLP50", "lookup": "PCH SLP-S0 State Summary: Residency (Percentage and Time)"},
    {"key": "S0ix_Substate", "lookup": "S0ix Substate Summary: Residency (Percentage and Time)"},
    {"key": "PKG_Cstate", "lookup": "Platform Monitoring Technology CPU Package C-States Residency Summary: Residency (Percentage and Time)"},
    {"key": "Core_Cstate", "lookup": "Core C-State Summary: Residency (Percentage and Time)"},
    {"key": "Core_Concurrency", "lookup": "CPU Core Concurrency (OS)"},
    {"key": "ACPI_Cstate", "lookup": "Core C-State (OS) Summary: Residency (Percentage and Time)"},
    {"key": "OS_wakeups", "lookup": "Processes by Platform Busy Duration"},
    {"key": "CPU-iGPU", "lookup": "CPU-iGPU Concurrency Summary: Residency (Percentage and Time)"},
    {"key": "CPU_Pavr", "lookup": "CPU P-State Average Frequency (excluding CPU idle time)"},
    {"key": "CPU_Pstate", "lookup": "CPU P-State/Frequency Summary: Residency (Percentage and Time)"},
    {"key": "RC_Cstate", "lookup": "Integrated Graphics C-State  Summary: Residency (Percentage and Time)"},
    {"key": "DDR_BW", "lookup": "DDR Bandwidth Requests by Component Summary: Average Rate and Total"},
    {"key": "IO_BW", "lookup": "IO Bandwidth Summary: Average Rate and Total"},
    {"key": "VC1_BW", "lookup": "Display VC1 Bandwidth Summary: Average Rate and Total"},
    {"key": "NPU_BW", "lookup": "Neural Processing Unit (NPU) to Memory Bandwidth Summary: Average Rate and Total"},
    {"key": "Media_BW", "lookup": "Media to Network on Chip (NoC) Bandwidth Summary: Average Rate and Total"},
    {"key": "IPU_BW", "lookup": "Image Processing Unit (IPU) to Network on Chip (NoC) Bandwidth Summary: Average Rate and Total"},
    {"key": "CCE_BW", "lookup": "CCE to Network on Chip (NoC) Bandwidth Summary: Average Rate and Total"},
    {"key": "GT_BW", "lookup": "Chip GT Bandwidth Summary: Average Rate and Total"},
    {"key": "D2D_BW", "lookup": "Chip Die to Die Bandwidth Summary: Average Rate and Total"},
    {"key": "IDI_BW", "lookup": "Cluster1 Cores Bandwidth Summary: Average Rate and Total"},
    {"key": "CPU_temp", "lookup": "Temperature Metrics Summary - Sampled: Min/Max/Avg"},
    {"key": "SoC_temp", "lookup": "SoC Domain Temperatures Summary - Sampled: Min/Max/Avg"},
    {"key": "NPU_Dstate", "lookup": "Neural Processing Unit (NPU) D-State Residency Summary: Residency (Percentage and Time)"},
    {"key": "PMC+SLP_S0", "lookup": "PCH Active State (as percentage of PMC Active plus SLP_S0 Time) Summary: Residency (Percentage)"},
    {"key": "DC_count", "lookup": "Dynamic Display State Enabling"},
    {"key": "Media_Cstate", "lookup": "Media C-State Residency Summary: Residency (Percentage and Time)"},
    {"key": "NPU_Pstate", "lookup": "Neural Processing Unit (NPU) P-State Summary - Sampled: Approximated Residency (Percentage)", "buckets":["0", "1900", "1901-2900", "2901-3899", "3900"]},
    {"key": "MEMSS_Pstate", "lookup": "Memory Subsystem (MEMSS) P-State Summary - Sampled: Approximated Residency (Percentage)"},
    {"key": "NoC_Pstate", "lookup": "Network on Chip (NoC) P-State Summary - Sampled: Approximated Residency (Percentage)", "buckets":["400", "401-1049", "1050"]},
    {"key": "iGFX_Pstate", "lookup": "Integrated Graphics P-State/Frequency Summary - Sampled: Approximated Residency (Percentage)", "buckets":["0", "400", "401-1799", "1800-2049", "2050"]}
]

PCIe_targets = [
    {"key": "PCIe_LPM", "devices":["NVM"], "lookup": "PCIe LPM Summary - Sampled: Approximated Residency (Percentage)"},
    {"key": "PCIe_Active", "devices":["NVM"], "lookup": "PCIe Link Active Summary - Sampled: Approximated Residency (Percentage)"},
    {"key": "PCIe_LTRsnoop", "devices":["NVM"], "lookup": "PCIe LTR Snoop Summary - Sampled: Histogram"}
]

AI_parsing_items = [
    {"key": "MLC_ver", "lookup": "Intel(R) Memory Latency Checker - ", "unit":"ver."},
    {"key": "full_params", "lookup": "Command line parameters: ", "unit":""},
    {"key": "read_buffer", "lookup": "Using buffer size of ", "unit":"MiB/thread"},
    {"key": "write_buffer", "lookup": "for reads and an additional ", "unit":"MiB/thread"}
]
"for reads and an additional"

DAQ_target = {
"P_SSD":-1,
"V_VAL_VCC_PCORE":-1,
"I_VAL_VCC_PCORE":-1,
"V_VAL_VCC_ECORE":-1,
"I_VAL_VCC_ECORE":-1,
"V_VAL_VCCSA":-1,
"I_VAL_VCCSA":-1,
"V_VAL_VCCGT":-1,
"I_VAL_VCCGT":-1,
"P_VCC_PCORE":-1,
"P_VCC_ECORE":-1,
"P_VCCSA":-1,
"P_VCCGT":-1,
"P_VCCL2":-1,
"P_VCC1P8":-1,
"P_VCCIO":-1,
"P_VCCDDRIO":-1,
"P_VNNAON":-1,
"P_VNNAONLV":-1,
"P_VDDQ":-1,
"P_VDD2H":-1,
"P_VDD2L":-1,
"P_V1P8U_MEM":-1,
"P_SOC+MEMORY":-1,
"Run Time":-1
}



CL_UNCLASSIFIED = "unclassified"
CL_ETL = ".etl"
CL_OUTPUT = 'MLC_375000_'
CL_SOCWATCH = 'Session.etl'
CL_AI_MODEL = '_qdq_proxy_'
CL_DAQ_SUMMARY = 'pacs-summary.csv'
CL_DAQ_TRACES = 'pacs-traces'
CL_PASS = ".PASS"

ETL = "ETL"
POWER = "POWER"
SOCWATCH = "SOCWATCH"
MODEL_OUTPUT = "MODEL_OUTPUT"
MIN = "MIN"
MAX = "MAX"
MED = "MED"



path_splitter = "\\"

def replaceSplitter(Abs_path) :
    Abs_path = Abs_path.replace("/", "\\")
    return Abs_path



BASE = args.input
result_path = args.output
# Get script directory for relative paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

if BASE is None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    # bring last opened folder memory
    last_folder_file = os.path.join(SCRIPT_DIR, "src", "last_opened_folder.txt")
    try:
        with open(last_folder_file, "r") as f:
            last_folder = f.read()
            folder_path = filedialog.askdirectory(title="Select a folder", initialdir=last_folder)
    except Exception as e:
        print(f"Failed to read last opened folder: {e}")
        folder_path = filedialog.askdirectory(title="Select a folder")
        tools.saveLastOpenedFolder(folder_path)

    if folder_path:
        
        BASE = replaceSplitter(folder_path)
        print(f"Selected folder: {BASE}")
        # add memory to remember last opened folder
        tools.saveLastOpenedFolder(folder_path)
    else:
        tools.errorAndExit("No folder selected")


if args.daq is None:
    print("============== No external DAQ.json provided")
else :
    with open(args.daq, 'r') as f:
        DAQ_target = json.load(f)
        print(DAQ_target)

if args.swtarget is None:
    print("============== No external Socwatch_target.json provided")
else :
    with open(args.swtarget, 'r') as f:
        socwatch_targets = json.load(f)
        print(socwatch_targets)

print("===== args hobl: ", args.hobl)

if result_path == None : 
    result_path = f"{BASE}\\mlc_summary"


hobl_sets = list()

file_num = 0

'''
====================================================================================
To parse everything: 


To parse everything picked by power_pick (MIN, MAX, Median)


To parse only median picked power


To parse every POWER_SOCWATCH

====================================================================================
'''

picks = {
        "SOC_POWER_RAIL_NAME":'', "PCORE_POWER_RAIL_NAME":'', "SA_POWER_RAIL_NAME":'', "GT_POWER_RAIL_NAME":'', 
        'power_pick':MED,
        'inferencingOnlyPower':True, 
        'sortSimilarData':True,
        }
tools.parsePowerRailNames(DAQ_target, picks)




    
#=========================================================================
# this returns parent or parent*2 folder name string as a data_set name
# if ETL, Power, Socwatch folder separation structure,
# it returns grand parent folder name
#=========================================================================
def getDatasetLabel(abs_path) :
    folder_list = abs_path.split("\\")[:-1]
    last = folder_list[-1]
    last_lower = last.lower()
    if last_lower == 'etl' or last_lower == 'power' or last_lower == 'socwatch':
        return [folder_list[-3], folder_list[-2]]
    else :
        return [folder_list[-2], folder_list[-1]]

def createDataset(abs_path) :
    # print("[abs_path] ", abs_path)
    hobl_sets.append({
        "ID_path":abs_path,
        "data_label":getDatasetLabel(abs_path),
        "data_type":[]
    })

def pullData(abs_path) :
    for item in hobl_sets:
        if (abs_path.find(item["ID_path"]) == 0) : 
            return item
    return None

def calFromPowerModel(block) :
    
    if 'power_obj' in block and 'model_output_obj' in block :
        if 'power_data' in block['power_obj'] and block['model_output_obj']['model_output_status'] != "failed" and 'model_output_data' in block['model_output_obj']:
            # calculate 'Eng(J)/Token' here
            block['power_obj']['power_data']['Eng(J)/Token'] = block['power_obj']['power_data']['Energy (J)'] / block['model_output_obj']['model_output_data']['total_token_gen'][0]
        else :
            # tools.errorAndExit("===error in claFromPowerModel===" + str(block))
            block['power_obj']['power_data']['Eng(J)/Token'] = "n/a"

def add_etl(abs_path):
    path_set = tools.splitLastItem(abs_path, "\\", 1)
    dataset = pullData(path_set[0])
    if dataset == None:
        tools.errorAndExit("pulling data failed by using the Path as ID: " + abs_path)
    if ETL not in dataset["data_type"] :
        dataset["data_type"].insert(0, ETL)
    dataset["etl_path"] = abs_path

def add_mlc_output(abs_path):
    path_set = tools.splitLastItem(abs_path, "\\", 1)
    dataset = pullData(path_set[0])
    if dataset == None:
        tools.errorAndExit("pulling data failed by using the Path as ID: " + abs_path)
    dataset["mlc_output_obj"] = mlc.parseMlcResults(abs_path, AI_parsing_items)
    calFromPowerModel(dataset)
    global file_num
    file_num += 1

def add_power(abs_path):
    path_set = tools.splitLastItem(abs_path, "\\", 1)
    dataset = pullData(path_set[0])
    if dataset == None:
        tools.errorAndExit("pulling data failed by using the Path as ID: " + abs_path)
    if POWER not in dataset["data_type"] :
        dataset["data_type"].append(POWER)
    dataset["power_obj"] = psp.parsePowerSummaryCSV(abs_path, DAQ_target)
    calFromPowerModel(dataset)
    global file_num
    file_num += 1

def add_trace(abs_path):
    path_set = tools.splitLastItem(abs_path, "\\", 1)
    dataset = pullData(path_set[0])
    if dataset == None:
        tools.errorAndExit("pulling data failed by using the Path as ID: " + abs_path)
    dataset["trace_obj"] = ptp.parsePowerTraceCSV(abs_path)
    global file_num
    file_num += 1

def add_socwatch(abs_path):
    path_set = tools.splitLastItem(abs_path, "\\", 1)
    dataset = pullData(path_set[0])
    if dataset == None:
        tools.errorAndExit("pulling data failed by using the Path as ID: " + abs_path)
    if SOCWATCH not in dataset["data_type"] :
        dataset["data_type"].insert(0, SOCWATCH)
    dataset["socwatch_obj"] = soc.parseSocwatch(abs_path, socwatch_targets)
    global file_num
    file_num += 1


def fileClassifier(abs_path, f):

    file_type = CL_UNCLASSIFIED
    
    if f == CL_PASS :
        createDataset(tools.splitLastItem(abs_path, "\\", 1)[0])
    elif f.find(CL_ETL) >= 0 and f.find(CL_SOCWATCH) == -1 : 
        # print("ETL detected ", abs_path, f)
        add_etl(abs_path)
        file_type = CL_ETL
    elif f.find(CL_OUTPUT) >= 0 :
        add_mlc_output(abs_path)
        file_type = CL_OUTPUT
    elif f.find(CL_DAQ_SUMMARY) >= 0:
        add_power(abs_path)
        file_type = CL_DAQ_SUMMARY
    elif f.find(CL_DAQ_TRACES) >= 0 and f.find('sr.csv') >= 0:
        add_trace(abs_path)
        file_type = CL_DAQ_TRACES
    elif f.find(CL_SOCWATCH) >= 0:
        workload_name = tools.splitLastItem(f, "_", 1)[0]
        upto_path = tools.splitLastItem(abs_path, "\\", 1)[0]
        soc_summary = workload_name + ".csv"
        summary_fullPath = os.path.join(upto_path, soc_summary)
        if os.path.exists(summary_fullPath) :
            add_socwatch(summary_fullPath)
        else :
            print("===== No Socwatch summary, Socwatch post-process may have interrupted", abs_path)
        file_type = CL_SOCWATCH
    return file_type


def detectAndParseFile(path) :

    for f in os.listdir(path):
        abs_path = os.path.join(path, f)
        # if f == "Model_A3_v1_2_3_qdq_proxy_stripped":
        #     break
        if os.path.isfile(abs_path):
            fType = fileClassifier(abs_path, f)
            if fType == CL_SOCWATCH :
                # after detecting first Socwatch ETL, and it's summary, no need to go further
                break
        else:
            #recursive on a folder detection
            detectAndParseFile(abs_path)

def main():
    tools.getSocPowerRailName(DAQ_target, picks)
    detectAndParseFile(BASE)
    pck.checkAndMarkPower(hobl_sets, picks)
    # print("====[hobl_sets]", hobl_sets)
    rpt.writeParsedAllInExcel(result_path, hobl_sets, socwatch_targets, PCIe_targets, picks)

start_time = time.perf_counter()
main()
end_time = time.perf_counter()
elapsed_time = end_time - start_time
print(f"Parsing {file_num} files Successful! [Elapsed time:::] {elapsed_time} seconds")

