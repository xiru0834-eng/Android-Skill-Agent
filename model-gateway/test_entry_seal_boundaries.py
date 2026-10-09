"""New first-step counterexamples; localhost fake selectors, never real models."""
import copy
import http.client
import json
import io
import socket
import threading
import time
import unittest

from intent_bridge import BridgeServer
from intent_bridge import Handler
from selection_deadline import SelectionBudget
from skill_selection import build_request, validate_selection
from test_skill_selection import CATALOG
from unittest.mock import Mock
from email.message import Message


class ConfigurationSealTests(unittest.TestCase):
    def test_early_rejection_consumes_well_framed_small_body_after_reply(self):
        handler=Handler.__new__(Handler)
        handler.headers=Message();handler.headers['Content-Length']='4'
        handler.rfile=io.BytesIO(b'body');handler.connection=Mock()
        handler.send_response=Mock();handler.send_header=Mock()
        handler.end_headers=Mock();handler.wfile=io.BytesIO()
        handler.reply(401,dict(error='PAIRING_REQUIRED'))
        self.assertEqual(handler.rfile.tell(),4)
        self.assertIn(b'PAIRING_REQUIRED',handler.wfile.getvalue())

    def test_ambiguous_framing_is_never_drained_as_a_trusted_length(self):
        handler=Handler.__new__(Handler)
        handler.headers=Message();handler.headers['Content-Length']='4'
        handler.headers['Content-Length']='5'
        handler.rfile=io.BytesIO(b'body');handler.connection=Mock()
        handler.send_response=Mock();handler.send_header=Mock()
        handler.end_headers=Mock();handler.wfile=io.BytesIO()
        handler.reply(400,dict(error='INVALID_REQUEST'))
        self.assertEqual(handler.rfile.tell(),0)

    def test_consumed_request_is_not_read_again_while_replying(self):
        handler=Handler.__new__(Handler)
        handler.headers=Message();handler.headers['Content-Length']='4'
        handler.body_received=True;handler.rfile=io.BytesIO(b'next')
        handler.discard_rejected_input()
        self.assertEqual(handler.rfile.tell(),0)

    def test_oversized_decimal_length_does_not_crash_the_rejection_path(self):
        handler=Handler.__new__(Handler)
        handler.headers=Message();handler.headers['Content-Length']='9'*7000
        handler.rfile=io.BytesIO(b'body')
        handler.discard_rejected_input()
        self.assertEqual(handler.rfile.tell(),0)

    def test_disconnected_reply_does_not_escape_as_handler_error(self):
        handler = Handler.__new__(Handler)
        handler.connection = Mock()
        handler.send_response = Mock(side_effect=ConnectionAbortedError("closed by client"))
        handler.reply(400, dict(error="INVALID_REQUEST"))

    def test_remaining_budget_never_exceeds_configured_interval(self):
        budget = SelectionBudget(.3, clock=lambda: 1_000_000.)
        self.assertLessEqual(budget.check(), .3)

    def test_business_cap_rejects_bool_float_and_string(self):
        for cap in [True, False, 1.5, "20", None]:
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                server = BridgeServer(("127.0.0.1", 0), "x" * 48, max_calls=cap)
                server.server_close()

    def test_remote_call_cap_requires_an_actual_integer(self):
        for cap in [True, 1., "1", None]:
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                SelectionBudget(8, max_calls=cap)

    def test_phone_utf16_input_boundary_matches_gateway(self):
        build_request("😀" * 250, CATALOG)
        for text in ["😀" * 251, "\ud800", "x" * 501]:
            with self.subTest(text_kind=repr(text[:2])), self.assertRaises(ValueError):
                build_request(text, CATALOG)

    def test_phone_utf16_message_boundary_matches_gateway(self):
        good = dict(status="reject", skill_id=None, message="😀" * 250)
        validate_selection(good, CATALOG)
        for message in ["😀" * 251, "\ud800"]:
            with self.subTest(kind=repr(message[:2])), self.assertRaises(ValueError):
                validate_selection(dict(good, message=message), CATALOG)

    def test_catalog_name_and_goal_use_phone_length_units(self):
        for key, good_count in [("name", 30), ("goal", 120)]:
            with self.subTest(field=key):
                catalog = copy.deepcopy(CATALOG)
                catalog[0][key] = "😀" * good_count
                build_request("Run saved skill.", catalog)
                catalog[0][key] += "😀"
                with self.assertRaises(ValueError):
                    build_request("Run saved skill.", catalog)

    def test_all_goal_types_values_and_pair_scopes_are_strict(self):
        invalid = [[True,60,1,1], [1,60.,1,1], [1,"60",1,1], [1,55,1,1],
                   [2,60,1,1], [1,60,1,0], [1,60,1,4], [None,60,1,1],
                   [None,None,None,None], [1,60,None], [1,60,1,1,0]]
        for goals in invalid:
            with self.subTest(goals=goals), self.assertRaises(ValueError):
                catalog = copy.deepcopy(CATALOG)
                catalog[0]["finalGoals"] = goals
                build_request("Run saved skill.", catalog)

    def test_catalog_and_output_extra_fields_and_unknown_id_never_pass(self):
        for goals in [[1,20,None,None], [1,40,None,None], [1,60,None,None],
                      [1,80,None,None], [1,100,None,None], [None,None,0,1],
                      [None,None,1,2], [None,None,1,3]]:
            with self.subTest(valid_goals=goals):
                catalog = copy.deepcopy(CATALOG)
                catalog[0]["finalGoals"] = goals
                build_request("Run saved skill.", catalog)
        for patch_value in [dict(actions=[]), dict(skill_id="f"*64), dict(status="other"),
                            dict(status="reject",skill_id="a"*64), dict(status="invoke",skill_id=None)]:
            with self.subTest(invalid_output=patch_value), self.assertRaises(ValueError):
                validate_selection(dict(dict(status="invoke",skill_id="a"*64,message="Review"),
                                        **patch_value), CATALOG)


class HttpSealTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.release = threading.Event()
        def selector(text, skills):
            self.calls.append(text)
            return dict(status="invoke", skill_id=skills[0]["id"], message="Review")
        self.server = BridgeServer(("127.0.0.1", 0), "x" * 48, max_calls=3,
                                   skill_selector=selector, selection_seconds=.5)
        self.worker = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=.01), daemon=True)
        self.worker.start()

    def tearDown(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(1)

    def request(self, identity="a" * 32, cancellation=False, extra_headers=()):
        body = dict(request_id=identity)
        if not cancellation:
            body.update(text="Run saved skill.", skills=copy.deepcopy(CATALOG))
        raw = json.dumps(body).encode()
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        path = "skill-selection-cancellations" if cancellation else "skill-selections"
        try:
            connection.putrequest("POST", "/v1/" + path)
            connection.putheader("Authorization", "Bearer " + "x" * 48)
            connection.putheader("Content-Length", str(len(raw)))
            connection.putheader("Content-Type", "application/json")
            for key, value in extra_headers:
                connection.putheader(key, value)
            connection.endheaders(raw)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_duplicate_framing_and_auth_headers_rejected_before_model(self):
        for key, value in [("Content-Length", "1"), ("Authorization", "Bearer " + "x" * 48),
                           ("Content-Type", "text/plain")]:
            with self.subTest(header=key):
                self.assertEqual(self.request(extra_headers=[(key, value)])[0], 400)
        self.assertEqual(self.calls, [])

    def test_empty_origin_and_transfer_headers_are_still_present(self):
        for key in ["Origin", "Transfer-Encoding"]:
            with self.subTest(header=key):
                self.assertEqual(self.request(extra_headers=[(key, "")])[0], 400)
        self.assertEqual(self.calls, [])

    def test_early_eof_with_valid_partial_json_is_not_a_valid_request(self):
        body = json.dumps(dict(request_id="b" * 32, text="Run saved skill.", skills=CATALOG)).encode()
        with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=2) as channel:
            header = ("POST /v1/skill-selections HTTP/1.0\r\nAuthorization: Bearer " +
                      "x" * 48 + "\r\nContent-Length: " + str(len(body) + 10) + "\r\n\r\n").encode()
            channel.sendall(header + body)
            channel.shutdown(socket.SHUT_WR)
            reply = channel.makefile("rb")
            self.assertIn(b" 400 ", reply.readline())
            reply.close()
        self.assertEqual(self.calls, [])

    def test_rejected_slow_body_does_not_hold_the_handler_for_five_seconds(self):
        with socket.create_connection(('127.0.0.1',self.server.server_port),timeout=.7) as channel:
            channel.sendall(b'POST /v1/skill-selections HTTP/1.0\r\nAuthorization: Bearer bad\r\nContent-Length: 4\r\n\r\n')
            started=time.monotonic()
            reply=http.client.HTTPResponse(channel);reply.begin()
            self.assertEqual(reply.status,401);reply.read();reply.close()
            self.assertEqual(channel.recv(1),b'')
            self.assertLess(time.monotonic()-started,.6)
        self.assertEqual(self.calls,[])

    def test_accepted_id_has_cancellation_event_before_selector_entry(self):
        for identity in ["1" * 32, "2" * 32, "3" * 32]:
            self.assertEqual(self.request(identity, cancellation=True)[0], 200)
        admitted = threading.Event()
        original = self.server.select_with_deadline
        def between_registration_and_selection(identity, text, skills):
            admitted.set()
            if not self.release.wait(2):
                raise AssertionError("test barrier did not release")
            return original(identity, text, skills)
        self.server.select_with_deadline = between_registration_and_selection
        result = []
        caller = threading.Thread(target=lambda: result.append(self.request("4" * 32)))
        caller.start()
        try:
            self.assertTrue(admitted.wait(1))
            self.assertEqual(self.request("4" * 32, cancellation=True)[0], 200)
            self.release.set()
            caller.join(1)
            self.assertFalse(caller.is_alive())
            self.assertEqual(result, [(503, dict(error="SELECTION_CANCELLED"))])
            self.assertEqual(self.calls, [])
            self.assertEqual(len(self.server.cancelled_ids), 3)
        finally:
            self.release.set()
            caller.join(2)

    def test_incomplete_headers_have_an_absolute_receive_deadline(self):
        self.server.input_seconds = .12
        with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=.7) as channel:
            channel.sendall(b"POST /v1/skill-selections HTTP/1.0\r\nX-Test: unfinished")
            started = time.monotonic()
            self.assertEqual(channel.recv(1), b"")
            self.assertLess(time.monotonic()-started, .6)
        self.assertEqual(self.calls, [])

    def test_trickled_body_cannot_refresh_the_total_receive_budget(self):
        self.server.input_seconds = .12
        stop = threading.Event()
        with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=.7) as channel:
            headers = ("POST /v1/skill-selections HTTP/1.0\r\nAuthorization: Bearer " +
                       "x" * 48 + "\r\nContent-Length: 2000\r\n\r\n").encode()
            channel.sendall(headers)
            def trickle():
                while not stop.wait(.03):
                    try:
                        channel.sendall(b"x")
                    except OSError:
                        return
            sender = threading.Thread(target=trickle)
            sender.start()
            try:
                started = time.monotonic()
                with channel.makefile("rb") as reply:
                    self.assertIn(b" 400 ", reply.readline())
                self.assertLess(time.monotonic()-started, .6)
            finally:
                stop.set()
                sender.join(1)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
