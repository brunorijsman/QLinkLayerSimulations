from easysquid.puppetMaster import PM_MultiDataSequence


class EGPErrorSequence(PM_MultiDataSequence):
    def getData(self, time, sourceList):
        error_source = sourceList[0]
        error_code, error_info = error_source.get_error()
        return [(error_source.egp.node.nodeID, error_code), True]

    def sumData(self, val, succ):
        pass
