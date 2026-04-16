import parsers.tools as tools



def readTextfile(abs_path) :

    # print(abs_path)
    with open(abs_path, 'r') as file:
        parsed = dict()

        for line in file:

            first_target = "Passed BW argument:"
            second_target = "Passed Affinity argument:"
            found = line.rfind(first_target)
            found2 = line.rfind(second_target)

            if found >= 0 :
                target_string = line[found+len(first_target):]
                parsed["NOP"] = target_string.strip()
            elif found2 >= 0 :
                target_string = line[found2+len(second_target):]
                parsed["Affinity"] = target_string.strip()
               
        return parsed


def parseSRoutResults(abs_path) :
    temp = dict()

    temp['sr_output_path'] = abs_path
    temp['sr_output_data'] = readTextfile(abs_path)

    # fps_by_name = pull_fps(temp['sr_output_data'])
    # print(f"++++++++++++++++++++++++++ fps_by_name : {fps_by_name}")
    # temp['min_cam_fps'] = min(fps_by_name) if len(fps_by_name) > 0 else 0
    # temp['median_cam_fps'] = tools.get_median(fps_by_name) if len(fps_by_name) > 0 else 0

    # if temp['min_cam_fps'] == 0 or temp['median_cam_fps'] == 0 :
    #     err = [abs_path, "=[ERROR]= : ", " it may not a result file or you may want to recollect"]
    #     temp['vpt_output_status'] = "failed"
    # else :
    #     temp['vpt_output_status'] = "successful"

    return temp





