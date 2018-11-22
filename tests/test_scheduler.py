import unittest
from easysquid.easynetwork import EasyNetwork
from easysquid.qnode import QuantumNode
from easysquid.quantumMemoryDevice import NVCommunicationDevice
from easysquid.easyprotocol import TimedProtocol
from netsquid.simutil import sim_run, sim_reset
from netsquid.pydynaa import EventHandler, Entity
from qlinklayer.distQueue import EGPDistributedQueue
from qlinklayer.scheduler import RequestScheduler
from qlinklayer.qmm import QuantumMemoryManagement
from qlinklayer.egp import EGPRequest
from qlinklayer.scenario import EGPSimulationScenario


class IncreasMHPCycleProtocol(TimedProtocol):
    def __init__(self, timeStep=1, t0=10, scheduler=None):
        super().__init__(timeStep=timeStep, t0=t0)
        self.scheduler = scheduler

    def run_protocol(self):
        self.scheduler.inc_cycle()


class TestRequestScheduler(unittest.TestCase, Entity):
    def setUp(self):
        memA = NVCommunicationDevice(name="AMem", num_positions=2)
        memB = NVCommunicationDevice(name="BMem", num_positions=2)
        self.nodeA = QuantumNode(name="TestA", nodeID=1, memDevice=memA)
        self.nodeB = QuantumNode(name="TestB", nodeID=2, memDevice=memB)

        self.dqpA = EGPDistributedQueue(node=self.nodeA)
        self.dqpB = EGPDistributedQueue(node=self.nodeB)
        self.dqpA.connect_to_peer_protocol(self.dqpB)

    def test_init(self):
        qmm = QuantumMemoryManagement(node=self.nodeA)
        with self.assertRaises(TypeError):
            RequestScheduler()

        with self.assertRaises(TypeError):
            RequestScheduler(distQueue=self.dqpA)

        with self.assertRaises(TypeError):
            RequestScheduler(qmm=qmm)

        test_scheduler = RequestScheduler(distQueue=self.dqpA, qmm=qmm)
        self.assertEqual(test_scheduler.distQueue, self.dqpA)
        self.assertEqual(test_scheduler.qmm, qmm)
        self.assertEqual(test_scheduler.my_free_memory, qmm.get_free_mem_ad())
        self.assertEqual(test_scheduler.other_mem, (0, 0))

    def test_timeout(self):
        def timeout_handler(evt):
            timeout_handler_called[0] = True
        sim_reset()

        timeout_handler_called = [False]

        memA = NVCommunicationDevice(name="AMem", num_positions=2)
        memB = NVCommunicationDevice(name="BMem", num_positions=2)
        nodeA = QuantumNode(name="TestA", nodeID=1, memDevice=memA)
        nodeB = QuantumNode(name="TestB", nodeID=2, memDevice=memB)

        dqpA = EGPDistributedQueue(node=nodeA, accept_all=True)
        dqpB = EGPDistributedQueue(node=nodeB, accept_all=True)
        dqpA.connect_to_peer_protocol(dqpB)
        qmm = QuantumMemoryManagement(node=nodeA)
        test_scheduler = RequestScheduler(distQueue=dqpA, qmm=qmm)
        test_scheduler.configure_mhp_timings(1, 2, 0, 0)
        request = EGPRequest()
        request.max_time = 2
        request.is_set = True

        increase_mhp_cycle_protocol = IncreasMHPCycleProtocol(timeStep=1, t0=10, scheduler=test_scheduler)
        increase_mhp_cycle_protocol.start()

        conn = dqpA.conn
        network = EasyNetwork(name="DQPNetwork",
                                   nodes=[(nodeA, [dqpA]), (nodeB, [dqpB])],
                                   connections=[(conn, "dqp_conn", [dqpA, dqpB])])
        network.start()
        test_scheduler.add_request(request)

        handler = EventHandler(timeout_handler)
        self._wait(handler, entity=test_scheduler, event_type=test_scheduler._EVT_REQ_TIMEOUT)
        sim_run(10)
        test_scheduler.inc_cycle()
        self.assertFalse(timeout_handler_called[0])

        sim_run(20)

        self.assertTrue(timeout_handler_called[0])

    def test_next_pop(self):
        qmm = QuantumMemoryManagement(node=self.nodeA)
        test_scheduler = RequestScheduler(distQueue=self.dqpA, qmm=qmm)
        self.assertEqual(test_scheduler.next_pop(), 0)

    def test_get_queue(self):
        qmm = QuantumMemoryManagement(node=self.nodeA)
        request = EGPRequest(EGPSimulationScenario.construct_cqc_epr_request(otherID=self.nodeB.nodeID, num_pairs=1,
                                                                             min_fidelity=1, max_time=1, purpose_id=0,
                                                                             priority=0))
        test_scheduler = RequestScheduler(distQueue=self.dqpA, qmm=qmm)
        self.assertEqual(test_scheduler.get_queue(request), 0)

    def test_update_other_mem_size(self):
        qmm = QuantumMemoryManagement(node=self.nodeA)
        test_scheduler = RequestScheduler(distQueue=self.dqpA, qmm=qmm)

        test_size = 3
        test_scheduler.update_other_mem_size(mem=test_size)

    def test_next(self):
        sim_reset()
        dqpA = EGPDistributedQueue(node=self.nodeA, accept_all=True)
        dqpB = EGPDistributedQueue(node=self.nodeB, accept_all=True)
        dqpA.connect_to_peer_protocol(dqpB)
        qmmA = QuantumMemoryManagement(node=self.nodeA)
        test_scheduler = RequestScheduler(distQueue=dqpA, qmm=qmmA)
        test_scheduler.configure_mhp_timings(1, 2, 0, 0)

        request = EGPRequest(EGPSimulationScenario.construct_cqc_epr_request(otherID=self.nodeB.nodeID, num_pairs=1,
                                                                             min_fidelity=1, max_time=12, purpose_id=0,
                                                                             priority=0))

        conn = dqpA.conn
        self.network = EasyNetwork(name="DQPNetwork",
                                   nodes=[(self.nodeA, [dqpA]), (self.nodeB, [dqpB])],
                                   connections=[(conn, "dqp_conn", [dqpA, dqpB])])
        self.network.start()

        # Check that an empty queue has a default request
        self.assertEqual(test_scheduler.get_default_gen(), test_scheduler.next())

        # Check that an item not agreed upon also yields a default request
        test_scheduler.add_request(request)
        self.assertEqual(test_scheduler.get_default_gen(), test_scheduler.next())

        for i in range(11):
            sim_run(11)
            test_scheduler.inc_cycle()
            self.assertEqual(test_scheduler.get_default_gen(), test_scheduler.next())
        test_scheduler.inc_cycle()

        # Check that QMM reserve failure yields a default request
        comm_q = qmmA.reserve_communication_qubit()
        storage_q = [qmmA.reserve_storage_qubit() for _ in range(request.num_pairs)]
        self.assertEqual(test_scheduler.get_default_gen(), test_scheduler.next())

        # Return the reserved resources
        qmmA.vacate_qubit(comm_q)
        for q in storage_q:
            qmmA.vacate_qubit(q)

        # Check that lack of peer resources causes a default request
        self.assertEqual(test_scheduler.get_default_gen(), test_scheduler.next())

        # Verify that now we can obtain the next request
        test_scheduler.other_mem = (1, request.num_pairs)

        # Verify that the next request is the one we submitted
        gen = test_scheduler.next()
        self.assertEqual(gen, (True, (0, 0), 0, 1, None))


if __name__ == "__main__":
    unittest.main()
