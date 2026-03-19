import parsers.tools as tools


def parseTotalFrameAndDuration(last_two_items) :

    tdic = {}
    for item in last_two_items :
        
        key_value = list(map(str.strip, item.split(':')))
        if "totalBuffersReceived" in key_value[0] :
            tdic["total_frame"] = int(key_value[1])
        elif "time" in key_value[0] :
            tdic["duration(s)"] = int(key_value[1].split(" ")[0])
    return tdic

def pull_fps(vpt_data) :
    
    fps_list = []
    for user in vpt_data :
        user_buffer_list = vpt_data[user]
        if len(user_buffer_list) > 0  :
            max_buffer = max(user_buffer_list, key=lambda x: x['total_frame'])

            fps_list.append(round(max_buffer["total_frame"] / max_buffer["duration(s)"], 2))
    
    return fps_list

def readTextfile(abs_path) :

    detector = "|"
    num_detector = 4

    with open(abs_path, 'r') as file:
        parsed = dict()
        for line in reversed(list(file)):

            counter = line.count(detector)
            if counter == num_detector :
                items = line.split(" ")
                user = items[3].strip()
                if user not in parsed :
                    parsed[user] = list()
                parsed[user].append(parseTotalFrameAndDuration(line.split(detector)[-2:]))

        return parsed


def parseVptResults(abs_path) :
    temp = dict()

    temp['vpt_output_path'] = abs_path
    temp['vpt_output_data'] = readTextfile(abs_path)

    fps_by_name = pull_fps(temp['vpt_output_data'])
    print(f"++++++++++++++++++++++++++ fps_by_name : {fps_by_name}")
    temp['min_cam_fps'] = min(fps_by_name) if len(fps_by_name) > 0 else 0
    temp['median_cam_fps'] = tools.get_median(fps_by_name) if len(fps_by_name) > 0 else 0

    # if temp['min_cam_fps'] == 0 or temp['median_cam_fps'] == 0 :
    #     err = [abs_path, "=[ERROR]= : ", " it may not a result file or you may want to recollect"]
    #     temp['vpt_output_status'] = "failed"
    # else :
    #     temp['vpt_output_status'] = "successful"

    return temp





