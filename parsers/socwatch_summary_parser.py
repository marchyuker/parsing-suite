import csv
import os
import parsers.tools as tools
# Socwatch Options:
# Command line options: -s 0 -o c:\hobl_data\socwatch\AI_GPU_model_stripped -f temp -f npu -f gfx -f memss-pstate -f cpu-cstate -f hw-cpu-hwp -f hw-cpu-cstate -f hw-cpu-pstate -f os-cpu-cstate -f os-cpu-pstate -f hw-igfx-cstate -f hw-igfx-pstate -f display-state -f ddr-bw -f bw-all -f noc-pstate -f media-pstate -m -r auto --no-post-processing 

# new socwatch header is being collected every time new header is detected
socwatch_header_dict = dict()
     

def cpuModelTable(table) :
    copied = table['table_data'].copy()
    data = dict()
    for line in copied:
        items = line[0].split("=")
        if len(items) > 1 :
            key = items[0].split("/")[1].strip()
            data[key] = items[-1].strip()
    table['table_data'] = data

def oneLineColonSeperater(table) :
    copied = table['table_data'].copy()
    data = dict()
    for line in copied:
        items = line[0].split(":")
        data[items[0]] = tools.tryIntifNumber(items[-1].strip())
    table['table_data'] = data 

def tempAvrTable(table): 
    copied = table['table_data'].copy()
    data = {table['label']:copied[0][4]}
    for index in range(1, len(copied), 1):
        line = copied[index]
        data[line[0].split("/")[-1]] = tools.tryRoundifNumber(line[4])
    table['table_data'] = data 

def bwTotalAvr(table) :
    num = len(table['table_data'])
    table['table_data'] = {table['label']+"_AvrRt(MB/s)":tools.tryRoundifNumber(table['table_data'][num-1][2])}


def coreFreqPerCoreResidencyTable(table, core_type_dict) : 
    copied = table['table_data'].copy()
    header_start = copied[0][0]

    freq_idx = 1
    data_label_lead = 2
    last_residency = 0

    header = copied[0][data_label_lead:]
    # top_bin = copied[1][data_label_lead:]

    for core_lable_idx in range(len(header)) :
        if "(%)" not in header[core_lable_idx] : 
            last_residency = core_lable_idx
            break
    
    header_residency_full = header[:last_residency]
    # top_residency_bin_trim = top_bin[:last_residency]

    short_header = list()

    for core_full_name in header_residency_full :
        core_idx = core_full_name.split("/")[2]
        short_header.append(core_idx+" "+core_type_dict[core_idx])

    data = {header_start:short_header}

    for index in range(1, len(copied), 1) :  # this is excluding freq 0, idle. : for index in range(1, len(copied)-1, 1) :
        row = copied[index]
        line_data_only = row[data_label_lead:data_label_lead+last_residency]
        key = "-".join(row[freq_idx].split(" -- "))
        if key == "0" : 
            key = "0-idle"

        data[key] = line_data_only

    table['table_data'] = data

def coreFreqResidencyTable(table, core_type_dict):
    copied = table['table_data'].copy()
    header_start = copied[0][0]

    combined_data = {header_start:[]}
    if core_type_dict is not None :
        for TYPE in core_type_dict : 
            core_name = core_type_dict[TYPE]
            if core_name not in combined_data[header_start]:
                combined_data[header_start].append(core_name)
    
    header = copied[0][2:]
    top_bin = copied[1][2:]

    for index in range(1, len(copied), 1) :  # this is excluding freq 0, idle. : for index in range(1, len(copied)-1, 1) :
        row = copied[index]
        line_dict = dict()
        line_data_only = row[2:]
        key = "-".join(row[1].split(" -- "))
        if key == "0" : 
            key = "0-idle"
        for cell_idx in range(len(header)) :
            if "(%)" not in header[cell_idx] :
                break
            column_cpu = header[cell_idx].split("/")[2]
            if column_cpu in core_type_dict and "(msec)" not in header[cell_idx] and int(float(top_bin[cell_idx])) != 100: 
                core_name = core_type_dict[column_cpu]
                if core_name not in line_dict :
                    line_dict[core_name] = float(line_data_only[cell_idx])
                    line_dict[core_name+"_num"] = 1
                else :
                    line_dict[core_name] += float(line_data_only[cell_idx])
                    line_dict[core_name+"_num"] += 1

        sum_list = ["-"] * len(combined_data[header_start])
        for core_idx in range(len(combined_data[header_start])) :    
            core_name = combined_data[header_start][core_idx]
            if core_name in line_dict:
                sum_list[core_idx] = round(line_dict[core_name] / line_dict[core_name+"_num"], 2)
        combined_data[key] = sum_list.copy()

    seperated_data = {}
    for idx, core_name in enumerate(combined_data[header_start]):
        for pstate in combined_data:
            seperated_data[str(core_name)+" "+str(pstate)] = combined_data[pstate][idx]
    
    table['table_data'] = seperated_data

def coreFreqAvrTable(table, keyIdx, ValueIdx):
    copied = table['table_data'].copy()
    data = {copied[0][keyIdx]:copied[0][ValueIdx]}
    for index in range(1, len(copied), 1):
        key = copied[index][keyIdx].split("/")[2]
        value = copied[index][ValueIdx]
        data[key] = tools.tryIntifNumber(value)
    table['table_data'] = data

def coreResidencyTable(table) :
    copied = table['table_data'].copy()
    data = {copied[0][0]:copied[1][0]}
    for index in range(1, len(copied[0]), 1):
        key = copied[0][index].split("/")[-1]
        if key.rfind("(%)") < 0:
            break
        value = copied[1][index]
        data[key] = tools.tryRoundifNumber(value)
    table['table_data'] = data

def osWakeupsTable(table) :
    copied = table['table_data'].copy()
    data = dict()
    for idx in range(len(copied)):
        line = copied[idx]
        key = line[0]
        if idx == 0:
            key = "OS_wakeups"
            value = line[1].split(" ")[0]+" ("+" ".join(line[2].split(" ")[:-1])+")"
        elif idx == 1:
            key = "Rank"
            value = line[1].split(" ")[0]+" ("+line[2]+")"
        else :
            value = line[1].split(" ")[0]+" ("+line[2]+")"
        data[key] = value
    table['table_data'] = data

def bucketizedTable(table, keyIdx, ValueIdx, buckets) :
    copied = table['table_data'].copy()
    data = dict()
    bucketized = {bk: 0 for bk in buckets}

    for idx in range(len(copied)):
        line = copied[idx]
        key = line[keyIdx]
        if "_Pstate" in table['label'] and idx > 0:
            key = key.split(".")[0]
        data[key] = line[ValueIdx]
        """
        Change this to accumulate all values that larger than the last bucket, should be included in the last bucket
        e.g.  if the buckets are [ 5, 6-10, 11-20, 21], and the key is 25, it should be included in the '21' bucket
        elif len(ranges) == 1 and int(bucket) <= int(key) :
        """
        if idx > 0 :
            for bucket in bucketized :
                ranges = bucket.split("-")
                if len(ranges) == 1 and bucket == key :
                    bucketized[bucket] = float(line[ValueIdx])
                elif len(ranges) == 1 and int(key) > int(ranges[0]) and bucket == buckets[-1]:
                    bucketized[bucket] = bucketized[bucket] + float(line[ValueIdx]) 
                elif len(ranges) == 2:
                    min = int(ranges[0])
                    max = int(ranges[1])
                    if int(key) >= min and int(key) <= max :
                        bucketized[bucket] = bucketized[bucket] + float(line[ValueIdx])

    table['table_data'] = data
    extended = dict()
    first_key_value = next(iter(data.items()))
    extended[first_key_value[0]] = first_key_value[1]
    extended.update(bucketized)
    table['bucketized_data'] = extended

# def pchActiveTable(table) :
#     copied = table['table_data'].copy()
#     data = dict()
#     table['table_data'] = data


def defaultResidencyTable(table, keyIdx, ValueIdx) :
    copied = table['table_data'].copy()
    data = dict()
    for idx in range(len(copied)):
        line = copied[idx]
        key = line[keyIdx]
        if "_Pstate" in table['label'] and idx > 0:
            key = key.split(".")[0]

        data[key] = tools.tryRoundifNumber(line[ValueIdx])
    table['table_data'] = data


def socwatchTableTypeChecker(table, core_type, soc_target, tdic) :

    label = table['label']
    surfix = label.split("_")[-1]

    if label == 'CPU_model':
        cpuModelTable(table)
    elif label == 'Core_Cstate' or label == 'ACPI_Cstate' : 
        coreResidencyTable(table)
    elif label == 'OS_wakeups':
        osWakeupsTable(table)
    elif label == 'CPU_Pavr' : 
        coreFreqAvrTable(table, 0, 1)
    elif label == 'CPU_Pstate' :        
        coreFreqPerCoreResidencyTable(table, core_type) if "data_summary_type" in tdic else coreFreqResidencyTable(table, core_type)
    elif label == 'DC_count':
        oneLineColonSeperater(table)
    elif surfix == "BW":
        bwTotalAvr(table)
    elif label == "CPU_temp" or label == "SoC_temp":
        tempAvrTable(table)
    elif label == "PMC+SLP_S0":
        defaultResidencyTable(table, 0, 2) 
    elif "buckets" in soc_target :
        bucketizedTable(table, 0, 1, soc_target['buckets'])
    else :
        defaultResidencyTable(table, 0, 1)

def extractHeader(table) :

    if table["label"] not in socwatch_header_dict:
        socwatch_header_dict[table["label"]] = [key for key in table['table_data']]
    else :
        prev_keys = socwatch_header_dict[table["label"]]
        new_keys = [key for key in table['table_data']]
        set_keys = prev_keys.copy()
        for item in new_keys :
            if item not in prev_keys :
                set_keys.append(item)
        socwatch_header_dict[table["label"]] = set_keys


def parseTargetTable(target, csvreader, CORE_TYPE, tdic) :

    tTable = dict()
    for tlist in csvreader :

        if 'isCompleted' in tTable and tTable['isCompleted'] == False :
            # if the table_data is initiated, 'isCompleted' exists, keep collecting line until empty line comes
            if "".join(tlist) == "" :
                tTable['isCompleted'] = True
                socwatchTableTypeChecker(tTable, CORE_TYPE, target, tdic)
                # When socwatch data is being parsed, header is also being collected and expended for unified header later
                extractHeader(tTable)
                break
            else :
                trimmed_list = tools.trim_list(tlist)
                if len(trimmed_list) > 0 :
                    tset = set("".join(trimmed_list))
                    if all(char in {" ", "-"} for char in tset) == False :
                        tTable['table_data'].append(trimmed_list)
        elif len(tlist) > 0 and tlist[0].rfind(target['lookup']) >=0 :
            tTable['label'] = target['key']
            tTable['table_data'] = list()
            tTable['isCompleted'] = False  
    return tTable


def parseSocwatch(tdic, socwatch_targets) :

    abs_path = None
    if "socwatch_summary_path" in tdic :
        abs_path = tdic["socwatch_summary_path"] 
    elif os.path.exists(tdic):
        abs_path = tdic
        # tdic = dict()
        # tdic["socwatch_summary_path"] = abs_path
        # tdic["data_summary_type"] = "compact"
    else :
        tools.errorAndExit("socwatch summary path is not supplied")

    socwatch_obj = dict()
    socwatch_obj['socwatch_path'] = abs_path
    socwatch_obj['socwatch_tables'] = []
    socwatch_obj['core_number'] = 0
    CORE_TYPE = None

    with open(abs_path, encoding='utf-8-sig', newline='') as csvfile:

        csvreader = csv.reader(csvfile)
        recheck_list = list()
        nonexist_list = list()
        for target in socwatch_targets : 
            tTable = parseTargetTable(target, csvreader, CORE_TYPE, tdic)

            if "label" in tTable and tTable['label'] == 'CPU_model':
                CORE_TYPE = tTable['table_data'].copy()

            if len(tTable) == 0:
                # print("traget line not detected", tTable, target)
                if target["key"] not in recheck_list:
                    recheck_list.append(target["key"])
                    csvfile.seek(0)
                    csvreader = csv.reader(csvfile)
                    tTable = parseTargetTable(target, csvreader, CORE_TYPE, tdic)
                    if len(tTable) == 0:
                        nonexist_list.append(target["key"])
                    else :
                        socwatch_obj['socwatch_tables'].append(tTable)
            else :
                socwatch_obj['socwatch_tables'].append(tTable)
        if len(recheck_list) > 0 :
            print("[re-looped table] : ", recheck_list, " you may want to match the order for ultimate performance") 
        if len(nonexist_list) > 0 :
            print("[nonexist searched table] : ", nonexist_list, " check socwatch summary source if the table is exist or check the look up text") 
        return socwatch_obj

        

