"""Daily market refresh schedule tests; never call live agencies from CI."""
import os
import threading
import unittest
from unittest.mock import patch

from ezstimate.auto_refresh import start_market_refresh


class AutoRefreshTests(unittest.TestCase):
    def test_on_boot_refresh_is_one_shot_until_next_tick(self):
        stop = threading.Event()
        called = []
        def stub():
            called.append("refreshed")
            stop.set()
            return {"status":"ok","saved":2,"unchanged":0,"conflicts":0}
        with patch.dict(os.environ, {"EZSTIMATE_MARKET_AUTO_REFRESH":"1"}):
            worker=start_market_refresh(interval_seconds=60,refresh=stub,stop_event=stop)
        self.assertIsNotNone(worker)
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(called,["refreshed"])

    def test_optout_off_does_not_contact_provider(self):
        called=[]
        with patch.dict(os.environ, {"EZSTIMATE_MARKET_AUTO_REFRESH":"0"}):
            worker=start_market_refresh(interval_seconds=1,refresh=lambda: called.append(True))
        self.assertIsNone(worker)
        self.assertEqual(called,[])

    def test_failed_refresh_cannot_stop_server_schedule(self):
        stop=threading.Event()
        called=[]
        def broken():
            called.append(True)
            stop.set()
            raise RuntimeError("simulated API outage")
        with patch.dict(os.environ, {"EZSTIMATE_MARKET_AUTO_REFRESH":"1"}):
            worker=start_market_refresh(interval_seconds=1,refresh=broken,stop_event=stop)
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(called,[True])


if __name__=="__main__":
    unittest.main()
