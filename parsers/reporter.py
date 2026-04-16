import parsers.reporter_allpower as rap
import parsers.reporter_inferenceOnly as rinf
import parsers.reporter_picked as rpick



def writeParsedAllInExcel(result_path, hobl_sets, socwatch_targets, PCIe_targets, picks) :
    rap.reportAllPowerAndType(result_path, hobl_sets, socwatch_targets, PCIe_targets, picks)

    
def writeInferenceOnlyInExcel(result_path, hobl_sets, DAQ_target,picks) :
    rinf.reportInferencingOnlyPower(result_path, hobl_sets, DAQ_target, picks)


def writeParsedPhi(result_path, hobl_data, socwatch_targets, DAQ_target, PCIe_targets, picks) :
    
    print(hobl_data)

    rap.reportAllPowerAndType(result_path, hobl_data, socwatch_targets, PCIe_targets, picks)
    rpick.reportPickedData2(result_path, hobl_data, socwatch_targets, picks)
    rinf.reportInferencingOnlyPower(result_path, hobl_data, DAQ_target, picks) if picks['inferencingOnlyPower'] else print("[No inferencing only Power selected]") 

# def writeParsedMLC(result_path, mlc_data, socwatch_targets, PCIe_targets, picks) :

#     print(mlc_data)
#     rap.reportAllPowerAndMLC(result_path, mlc_data, socwatch_targets, PCIe_targets, picks)
