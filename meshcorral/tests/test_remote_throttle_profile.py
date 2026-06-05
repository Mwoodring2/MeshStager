"""Tests for Prime v0.7 remote-mode throttle profile."""

from __future__ import annotations

import unittest

from meshcorral.utils.path_perf import (
    PRIME_PERF_LOCAL_VIEWPORT_DEBOUNCE_MS,
    PRIME_PERF_REMOTE_MAX_DECODE_WORKERS,
    PRIME_PERF_REMOTE_VIEWPORT_DEBOUNCE_MS,
    remote_throttle_profile,
)


class TestRemoteThrottleProfile(unittest.TestCase):
    def test_remote_profile_caps_workers_to_one(self) -> None:
        prof = remote_throttle_profile(True)
        self.assertTrue(prof.network_like)
        self.assertEqual(prof.decode_workers, PRIME_PERF_REMOTE_MAX_DECODE_WORKERS)
        self.assertEqual(prof.viewport_debounce_ms, PRIME_PERF_REMOTE_VIEWPORT_DEBOUNCE_MS)

    def test_local_profile_uses_local_debounce(self) -> None:
        prof = remote_throttle_profile(False)
        self.assertFalse(prof.network_like)
        self.assertEqual(prof.viewport_debounce_ms, PRIME_PERF_LOCAL_VIEWPORT_DEBOUNCE_MS)
        self.assertGreaterEqual(prof.decode_workers, 1)

    def test_remote_smaller_primer_batch(self) -> None:
        remote = remote_throttle_profile(True)
        local = remote_throttle_profile(False)
        self.assertLess(remote.primer_batch_size, local.primer_batch_size)

    def test_remote_longer_debounce_than_local(self) -> None:
        remote = remote_throttle_profile(True)
        local = remote_throttle_profile(False)
        self.assertGreater(remote.viewport_debounce_ms, local.viewport_debounce_ms)


if __name__ == "__main__":
    unittest.main()
