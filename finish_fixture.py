"""Reproduce V1 observation behavior and provide a terminal transport test hook."""
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from call.support import ResponseLost, Unavailable, encode
from display.http_api import TerminalClient
from tests.fixture import RehearsalCase, Timeline


@contextmanager
def terminal_traffic(timeline):
    """Interpose on the caller side of real terminal HTTP exchanges in a test."""
    request = TerminalClient.request

    def intercepted(client, station, action, payload):
        try:
            timeline(station, action, "before", payload, None)
            result = request(client, station, action, payload)
            timeline(station, action, "after", payload, result)
        except ResponseLost as exc:
            raise Unavailable() from exc
        return result

    with patch.object(TerminalClient, "request", intercepted):
        yield


class ObservationBoundary(RehearsalCase):
    def test_observation_is_frozen_while_late_show_can_commit(self):
        self.open_sample()
        traffic = Timeline()
        self.enterContext(terminal_traffic(traffic))
        first = self.preload("left", "A1", "PA")
        lost = traffic.arm("left", "show", "after", "drop", "PA")
        with self.assertRaises(Unavailable):
            self.post("show", **first)
        self.assertTrue(lost.entered.is_set())
        self.assertEqual(self.lookup("receipt", "PA"), lost.result)

        target = self.preload("right", "B1", "PB")
        held = self.arm("right", "show", "before_commit", "hold", "PB")
        future = self.background_show(target, held)
        try:
            earlier = self.post("close", session=self.session)
            self.assertEqual(earlier["roles"][0]["shown"], [lost.result["receipt"]])
            self.assertEqual(earlier["roles"][1]["missed"], ["B0", "B1", "B2"])
            other = self.post("open", edition=self.edition, bindings=self.sample["bindings"])["session"]
            other_show = dict(target, session=other, request="OTHER-PB")
            self.post("preload", **other_show)
            other_receipt = self.post("show", **other_show)["receipt"]
            self.assertEqual((other_receipt["session"], other_receipt["sequence"]), (other, 1))
        finally:
            held.resume.set()
        result = future.result(timeout=5)
        self.assertEqual(result["status"], "shown")
        actual = result["receipt"]
        self.assertEqual((actual["session"], actual["request"], actual["sequence"]), (self.session, "PB", 2))
        later = self.post("close", session=self.session)
        self.assertEqual(later["roles"][1]["shown"], [actual])
        self.assertEqual(later["roles"][1]["missed"], ["B0", "B2"])
        self.assertNotEqual(later["excerpt"], earlier["excerpt"])
        self.restart()
        self.assertEqual(self.lookup("excerpt", earlier["excerpt"]), earlier)
        self.assertEqual(self.lookup("excerpt", later["excerpt"]), later)
        print(encode({"earlier": earlier, "later": later, "other_session": other_receipt}))


if __name__ == "__main__":
    unittest.main()
