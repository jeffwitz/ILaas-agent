import signal
import unittest
from unittest import mock

from ilaas_agents import processes
from ilaas_agents.processes import ProcessManager, StartedProcess


class _FakeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid


class CleanupInterruptTest(unittest.TestCase):
    def test_cleanup_swallows_keyboard_interrupt_and_restores_sigint(self):
        manager = ProcessManager()
        manager.started = [StartedProcess(name="litellm", process=_FakeProcess(1234))]
        before = signal.getsignal(signal.SIGINT)

        # Simulate an impatient Ctrl-C landing inside the shutdown wait: because
        # cleanup ignores SIGINT for its duration, this must not escape.
        with mock.patch.object(processes, "terminate_pid", side_effect=KeyboardInterrupt):
            try:
                manager.cleanup()
            except KeyboardInterrupt:  # pragma: no cover - the regression we fixed
                self.fail("cleanup must not propagate KeyboardInterrupt")

        self.assertEqual(signal.getsignal(signal.SIGINT), before)

    def test_terminate_pid_escalates_to_sigkill_on_interrupt(self):
        calls = []
        with mock.patch.object(processes.os, "kill", side_effect=lambda pid, sig: calls.append(sig)), \
             mock.patch.object(processes, "pid_alive", return_value=True), \
             mock.patch.object(processes.time, "sleep", side_effect=KeyboardInterrupt):
            processes.terminate_pid(4321, timeout=5.0)

        self.assertIn(signal.SIGTERM, calls)
        self.assertIn(signal.SIGKILL, calls)


if __name__ == "__main__":
    unittest.main()
