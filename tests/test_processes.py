import signal
import sys
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
        with mock.patch.object(processes, "terminate_process", side_effect=KeyboardInterrupt):
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


class TerminateProcessTest(unittest.TestCase):
    def test_sigterm_honoring_child_is_reaped_fast(self):
        import subprocess
        import time

        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        start = time.monotonic()
        processes.terminate_process(proc, timeout=5.0)
        elapsed = time.monotonic() - start
        self.assertIsNotNone(proc.poll())          # reaped, not a lingering zombie
        self.assertLess(elapsed, 2.0)              # nowhere near the 5s timeout

    @unittest.skipIf(sys.platform.startswith("win"), "POSIX signal handling")
    def test_sigterm_ignoring_child_is_escalated_to_kill(self):
        import subprocess

        proc = subprocess.Popen([
            sys.executable,
            "-c",
            "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)",
        ])
        processes.terminate_process(proc, timeout=0.5)
        self.assertIsNotNone(proc.poll())


class ForegroundCallTest(unittest.TestCase):
    def test_returns_child_exit_code(self):
        self.assertEqual(processes.foreground_call([sys.executable, "-c", "raise SystemExit(7)"]), 7)

    def test_restores_parent_sigint_handler(self):
        before = signal.getsignal(signal.SIGINT)
        processes.foreground_call([sys.executable, "-c", ""])
        self.assertEqual(signal.getsignal(signal.SIGINT), before)

    @unittest.skipIf(sys.platform.startswith("win"), "POSIX signal reset only")
    def test_child_does_not_inherit_ignored_sigint(self):
        # Parent ignores SIGINT during the call; the child must NOT inherit that
        # SIG_IGN (else it would ignore Ctrl-C entirely). A Python child re-arms
        # its own handler once the disposition is no longer SIG_IGN, so we assert
        # the child sees anything other than SIG_IGN.
        code = processes.foreground_call([
            sys.executable,
            "-c",
            "import signal,sys; sys.exit(3 if signal.getsignal(signal.SIGINT)==signal.SIG_IGN else 0)",
        ])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
