import xml.etree.ElementTree as ET

def readTextfile(abs_path) :

    parsed = dict()
    tree = ET.parse(abs_path)
    root = tree.getroot()

    # Prefer per-pass score when available; otherwise use the aggregate score.
    preferred_tags = [
        "OfficeProductivityOneHourBatteryConsumptionPerformanceScoreForPass",
        "OfficeProductivityOneHourBatteryConsumptionPerformanceScore",
    ]

    score = None
    for tag in preferred_tags:
        elems = root.findall(".//" + tag)
        if elems:
            value = elems[-1].text
            if value is not None and value.strip() != "":
                score = value.strip()
                break

    # Fallback for future Procyon variants that keep the same score suffix.
    if score is None:
        for elem in root.iter():
            if elem.tag.endswith("PerformanceScoreForPass") or elem.tag.endswith("PerformanceScore"):
                if elem.text is not None and elem.text.strip() != "":
                    score = elem.text.strip()

    if score is not None:
        parsed['procyon_overall_score'] = score

    return parsed


def parseProcyonResultXML(abs_path) :
    temp = dict()

    # need to modify it, HoBL => AI_Phi_tester.bat => GPU_run.bat => python model runner => python model runner output => hobl.log parsing


    temp['procyon_xml_path'] = abs_path
    temp['procyon_data'] = readTextfile(abs_path)

    # token_gen_number = int(temp['mlc_output_data']['total_token_gen'][0])

    # device = ""
    # if "GPU" in tools.splitLastItem(abs_path, "\\", 1)[1] :
    #     device = "GPU"
    # elif "NPU" in tools.splitLastItem(abs_path, "\\", 1)[1] :
    #     device = "NPU"

    # temp['mlc_output_data']['device'] = [device, ""]
    # temp['mlc_output_data']['throughput'] = temp['mlc_output_data']['Tokens_per_second'].copy()
    # temp['mlc_output_data']['dur_checksum'] = [round(token_gen_number * (1 / float(temp['mlc_output_data']['throughput'][0])), 2), "ms"]

    # if temp['mlc_output_data']['throughput'][1] == "" :
    #     err = [abs_path, "=[ERROR]= : ", " it may not a result file or you may want to recollect"]
    #     temp['mlc_output_status'] = "failed"
    # else :
    #     temp['mlc_output_status'] = "successful"

    return temp





