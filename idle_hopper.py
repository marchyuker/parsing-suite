
import os
import time
import json
from pathlib import Path
from os import listdir
from os.path import isfile, join
import parsers.tools as tools
import parsers.vpt_output_parser as vop
import parsers.socwatch_summary_parser as soc
import parsers.power_summary_parser as psp
import parsers.power_trace_parser as ptp
import parsers.power_checker as pck
import parsers.reporter as rpt

import argparse


parser = argparse.ArgumentParser(prog='Youtube 4K summary parser')
parser.add_argument('-c', '--config', help='configuration path. json format, need to have all of -d -st and others')
parser.add_argument('-i', '--input', help='input path. this will be the bese of the summray, will detect all files and folders from that path tree')
parser.add_argument('-o', '--output', help='output path. location of file and file name')
parser.add_argument('-d', '--daq', help='DAQ power rail name dictionary')
parser.add_argument('-st', '--swtarget', help='a list of dictionary objects that you want to parse from the socwatch summary')
parser.add_argument('-hb', '--hobl', action='store_true', help='if the data is collected via HOBL, looking for .PASS or .FAIL file in the folder to set file path as data set ID')

# parser.print_help()
args = parser.parse_args()
print("args: ", args)




CL_UNCLASSIFIED = "unclassified"
CL_ETL = ".etl"
CL_OUTPUT = '_output.txt'
CL_SOCWATCH = 'Session.etl'
CL_AI_MODEL = '_qdq_proxy_'
CL_DAQ_SUMMARY = 'pacs-summary.csv'      
CL_FLEX_SUMMARY = 'Raw_Summary.csv'
CL_FLEX_RESULTS = '-results.json'
CL_DAQ_TRACES = 'pacs-traces'
CL_PASS = "-hopper.json"
CL_VPT = "vpt_output.log"


ETL = "ETL"
POWER = "POWER"
SOCWATCH = "SOCWATCH"
MODEL_OUTPUT = "MODEL_OUTPUT"
MIN = "MIN"
MAX = "MAX"
MED = "MED"

BASE = args.input
result_csv = args.output
# Get script directory for relative paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

hobl_sets = list()

picks = {
        "SOC_POWER_RAIL_NAME":'', "PCORE_POWER_RAIL_NAME":'', "SA_POWER_RAIL_NAME":'', "GT_POWER_RAIL_NAME":'', 
        'power_pick':MED,
        'inferencingOnlyPower':True, 
        'sortSimilarData':True,
        'inferencing_power_detection':{
            'power_obj':{'power_type':'SOCWATCH_ETL_POWER'},
            'model_output_obj':{'model_output_status':'successful'}
            }
        }

config_json = dict()

if args.config is None:
    print("============== No external default config JSON provided")
    config_json = tools.jsonLoader(f"{SCRIPT_DIR}\\config\\PTL_default.config", picks)
else :
    config_json = tools.jsonLoader(args.config, picks)
    print(config_json)


socwatch_targets = config_json["socwatch_targets"]
PCIe_targets = config_json["PCIe_targets"]
DAQ_target = config_json["DAQ_target"]
second_folder_list = config_json["Second_folder_list"]
loaded_file_num = 0

path_splitter = "\\"

def replaceSplitter(Abs_path) :
    Abs_path = Abs_path.replace("/", "\\")
    return Abs_path


if BASE is None:
    from tools.tk_dialogs import select_folder_dialog

    folder_path = select_folder_dialog(
        title="Select a folder",
        storage_name="last_opened_folder",
        base_dir=Path(SCRIPT_DIR),
    )
    if folder_path:
        BASE = replaceSplitter(folder_path)
        print(f"Selected folder: {BASE}")
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

if result_csv == None : 
    result_csv = f"{BASE}\\Phi_summary"

'''
====================================================================================


====================================================================================
'''

# tools.parsePowerRailNames(DAQ_target, picks)



    
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

def add_vpt_out(abs_path):
    path_set = tools.splitLastItem(abs_path, "\\", 1)
    dataset = pullData(path_set[0])
    if dataset == None:
        tools.errorAndExit("pulling data failed by using the Path as ID: " + abs_path)
    dataset["vpt_output_obj"] = vop.parseVptResults(abs_path)
    # calFromPowerModel(dataset)
    global loaded_file_num
    loaded_file_num += 1

def add_power(abs_path):
    path_set = tools.splitLastItem(abs_path, "\\", 1)
    dataset = pullData(path_set[0])
    if dataset == None:
        tools.errorAndExit("pulling data failed by using the Path as ID: " + abs_path)
    if POWER not in dataset["data_type"] :
        dataset["data_type"].append(POWER)
    dataset["power_obj"] = psp.parsePowerSummaryCSV(abs_path, DAQ_target)
    calFromPowerModel(dataset)
    global loaded_file_num
    loaded_file_num += 1

def add_power_runtime(abs_path):
    path_set = tools.splitLastItem(abs_path, "\\", 1)
    dataset = pullData(path_set[0])
    if dataset == None:
        tools.errorAndExit("pulling data failed by using the Path as ID: " + abs_path)
    if POWER not in dataset["data_type"] :
        dataset["data_type"].append(POWER)
    if "power_obj" in dataset and "power_data" in dataset["power_obj"] : 
        dataset["power_obj"]["power_data"]["Run Time"] = psp.parseHopperRuntime(abs_path, None)
        calFromPowerModel(dataset)
        global loaded_file_num
        loaded_file_num += 1

def add_trace(abs_path):
    path_set = tools.splitLastItem(abs_path, "\\", 1)
    dataset = pullData(path_set[0])
    if dataset == None:
        tools.errorAndExit("pulling data failed by using the Path as ID: " + abs_path)
    dataset["trace_obj"] = ptp.parsePowerTraceCSV(abs_path)
    global loaded_file_num
    loaded_file_num += 1

def add_socwatch(abs_path):
    path_set = tools.splitLastItem(abs_path, "\\", 1)
    dataset = pullData(path_set[0])
    if dataset == None:
        tools.errorAndExit("pulling data failed by using the Path as ID: " + abs_path)
    if SOCWATCH not in dataset["data_type"] :
        dataset["data_type"].insert(0, SOCWATCH)
    dataset["socwatch_obj"] = soc.parseSocwatch(abs_path, socwatch_targets)
    global loaded_file_num
    loaded_file_num += 1



def fileClassifier(abs_path, f):

    file_type = CL_UNCLASSIFIED
    
    if f.find(CL_PASS) >= 0:
        createDataset(tools.splitLastItem(abs_path, "\\", 1)[0])
    elif f == CL_VPT:
        add_vpt_out(abs_path)
        file_type = CL_VPT
    elif f.find(CL_ETL) >= 0 and f.find(CL_SOCWATCH) == -1 : 
        # print("ETL detected ", abs_path, f)
        add_etl(abs_path)
        file_type = CL_ETL
    elif f.find(CL_DAQ_SUMMARY) >= 0:
        add_power(abs_path)
        file_type = CL_DAQ_SUMMARY
    elif f.find(CL_FLEX_SUMMARY) >= 0:
        add_power(abs_path)
        file_type = CL_FLEX_SUMMARY
    elif f.find(CL_FLEX_RESULTS) >= 0:
        add_power_runtime(abs_path)
        file_type = CL_FLEX_RESULTS
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
            # if fType == CL_SOCWATCH :
            #     # after detecting first Socwatch ETL, and it's summary, no need to go further
            #     break
        else:
            #recursive on a folder detection
            detectAndParseFile(abs_path)

def main():
    detectAndParseFile(BASE)
    pck.checkAndMarkPower(hobl_sets, picks)
    print("====[hobl_sets]", hobl_sets)
    rpt.writeParsedAllInExcel(result_csv, hobl_sets, socwatch_targets, PCIe_targets, picks)

start_time = time.perf_counter()
main()
end_time = time.perf_counter()
elapsed_time = end_time - start_time
print(f"Parsing {loaded_file_num} files Successful! [Elapsed time:::] {elapsed_time} seconds")

