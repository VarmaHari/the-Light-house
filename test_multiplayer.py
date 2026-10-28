"""Local integration checks for the room and authoritative WebSocket game loop."""
import asyncio
import unittest

from aiohttp import ClientSession
from aiohttp.test_utils import TestServer
import app as game


class Client:
    def __init__(self, session, url):
        self.session, self.url = session, url
        self.ws = None
        self.id = self.token = self.code = None
        self.state = self.intel = None

    async def open(self):
        self.ws = await self.session.ws_connect(self.url)

    async def send(self, kind, **extra):
        await self.ws.send_json({"type": kind, **extra})

    async def until(self, pred, timeout=3):
        async def loop():
            while True:
                msg = await self.ws.receive_json(timeout=timeout)
                if msg["type"] == "state":
                    self.state = msg["state"]
                elif msg["type"] == "private":
                    self.intel = msg["intel"]
                if pred(msg):
                    return msg
        return await asyncio.wait_for(loop(), timeout)

    async def joined(self):
        msg = await self.until(lambda m: m["type"] == "joined")
        self.id, self.token, self.code = msg["id"], msg["token"], msg["code"]


class MultiplayerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        game.rooms.clear()
        self.server = TestServer(game.create_app())
        await self.server.start_server()
        self.session = ClientSession()
        self.url = str(self.server.make_url("/ws")).replace("http://", "ws://")
        self.clients = []

    async def asyncTearDown(self):
        for client in self.clients:
            if client.ws and not client.ws.closed:
                await client.ws.close()
        await self.session.close()
        await self.server.close()
        game.rooms.clear()

    async def client(self):
        c = Client(self.session, self.url)
        await c.open()
        self.clients.append(c)
        return c

    async def settle(self, clients, pred, timeout=3):
        await asyncio.gather(*(c.until(pred, timeout) for c in clients))

    async def test_full_cooperative_game_privacy_reconnect_and_victory(self):
        crew = [await self.client() for _ in range(5)]
        await crew[0].send("create", name="Harbor")
        await crew[0].joined()
        code = crew[0].code
        self.assertEqual(len(code), 5)
        for i, c in enumerate(crew[1:], 1):
            await c.send("join", name=f"Crew {i}", code=code)
            await c.joined()
        await self.settle(crew, lambda m: m["type"] == "state" and len(m["state"]["players"]) == 5)
        # Non-host start and malformed room actions are rejected.
        await crew[1].send("ready", ready=False)
        await crew[1].until(lambda m: m["type"] == "state" and not m["state"]["players"][1]["ready"])
        await crew[1].send("start")
        err = await crew[1].until(lambda m: m["type"] == "error")
        self.assertIn("Only the host", err["message"])
        await crew[0].send("start")
        err = await crew[0].until(lambda m: m["type"] == "error")
        self.assertIn("every crew member", err["message"])
        await crew[1].send("ready", ready=True)
        await crew[1].until(lambda m: m["type"] == "state" and m["state"]["players"][1]["ready"])
        await crew[0].send("start")
        started = await crew[0].until(lambda m: m["type"] == "state" and m["state"]["phase"] == "game")
        self.assertEqual(started["state"]["game"]["round"], 1)
        await self.settle(crew[1:], lambda m: m["type"] == "state" and m["state"]["phase"] == "game")
        self.assertEqual([p["role"] for p in crew[0].state["players"]], ["Navigator", "Lighthouse Keeper", "Weather Analyst", "Reef Scout", "Navigator"])
        # Player-specific payloads contain only their assigned secret while all roles are staffed.
        for c in crew:
            await c.until(lambda m: m["type"] == "private" and m["intel"] is not None)
        self.assertIn("forecast", crew[2].intel)
        self.assertNotIn("reefs", crew[2].intel)
        self.assertIn("reefs", crew[3].intel)
        self.assertNotIn("forecast", crew[3].intel)
        self.assertNotIn("forecast", crew[0].intel)
        self.assertNotIn("reefs", crew[0].intel)

        # Exercise server-side invalid-input and duplicate-role checks.
        await crew[0].send("action", value={"ship": "ship-1", "route": "moon"})
        err = await crew[0].until(lambda m: m["type"] == "error")
        self.assertIn("valid route", err["message"])
        safe = next(r for r, water in crew[3].intel["reefs"].items() if water == "clear water")
        await crew[0].send("action", value={"ship": "ship-1", "route": safe})
        await crew[0].until(lambda m: m["type"] == "state" and "Navigator" in m["state"]["game"]["submitted"])
        await crew[4].send("action", value={"ship": "ship-2", "route": safe})
        err = await crew[4].until(lambda m: m["type"] == "error")
        self.assertIn("already submitted", err["message"])

        # A signal consumes shared charge and a second signal from that player is rejected.
        initial_charge = crew[0].state["game"]["comms"]
        await crew[0].send("signal", signal="SAFE ROUTE", route=safe)
        sent_signal = await crew[0].until(lambda m: m["type"] == "state" and m["state"]["game"]["comms"] == initial_charge - 1)
        self.assertEqual(sent_signal["state"]["game"]["signals"][-1]["route"], safe)
        await crew[0].send("signal", signal="DANGER AHEAD")
        err = await crew[0].until(lambda m: m["type"] == "error")
        self.assertIn("already sent", err["message"])

        # Reconnect restores the same seat, player identity, and role.
        old_id, old_token = crew[4].id, crew[4].token
        await crew[4].ws.close()
        await asyncio.sleep(.05)
        replacement = await self.client()
        await replacement.send("reconnect", code=code, token=old_token, name="Crew 4")
        await replacement.joined()
        await replacement.until(lambda m: m["type"] == "state")
        self.assertEqual(replacement.id, old_id)
        self.assertEqual(replacement.state["players"][-1]["role"], "Navigator")

        # Resolve three successful watches across all clients; all see the same authoritative result.
        active = crew[:4]
        for watch in range(3):
            g = crew[0].state["game"]
            self.assertIsNone(g["result"])
            safe = next(r for r, water in crew[3].intel["reefs"].items() if water == "clear water")
            ship = next(s for s in g["ships"] if s["status"] == "at sea")
            await crew[2].send("action", value={"route": safe})
            await crew[3].send("action", value={"route": safe})
            await crew[1].send("action", value={"route": safe})
            await crew[0].send("action", value={"ship": ship["id"], "route": safe})
            pred = lambda m: m["type"] == "state" and m["state"]["game"]["rescued"] == watch + 1
            await self.settle(active, pred, timeout=6)
            self.assertEqual({c.state["game"]["rescued"] for c in active}, {watch + 1})
        self.assertEqual(crew[0].state["game"]["result"], "victory")
        await crew[0].send("replay")
        replay_crew = [crew[0], crew[1], crew[2], crew[3], replacement]
        await self.settle(replay_crew, lambda m: m["type"] == "state" and m["state"]["phase"] == "lobby")
        self.assertTrue(all(c.state["phase"] == "lobby" for c in replay_crew))

    async def test_invalid_code_full_room_and_unstaffed_role_intel(self):
        c = await self.client()
        await c.send("join", name="Lost", code="ZZZZZ")
        err = await c.until(lambda m: m["type"] == "error")
        self.assertIn("not found", err["message"])
        # Two-person crew always has Navigator + Keeper; absent-role intelligence is shared.
        a, b = await self.client(), await self.client()
        await a.send("create", name="Beacon")
        await a.joined()
        await b.send("join", name="Sailor", code=a.code)
        await b.joined()
        await self.settle([a, b], lambda m: m["type"] == "state" and len(m["state"]["players"]) == 2)
        await a.send("start")
        await self.settle([a, b], lambda m: m["type"] == "state" and m["state"]["phase"] == "game")
        for p in (a, b):
            await p.until(lambda m: m["type"] == "private" and m["intel"] is not None)
            self.assertIn("crewForecast", p.intel)
            self.assertIn("crewReefs", p.intel)
        # Force the server-owned deadline to expire and verify every socket gets the same transition.
        room = game.rooms[a.code]
        room["game"]["deadline"] = game.now() + .05
        await self.settle([a, b], lambda m: m["type"] == "state" and m["state"]["game"]["round"] == 2, timeout=3)
        self.assertEqual(a.state["game"]["deadline"], b.state["game"]["deadline"])

    async def test_six_player_limit(self):
        crew = [await self.client() for _ in range(7)]
        await crew[0].send("create", name="Host")
        await crew[0].joined()
        for i, c in enumerate(crew[1:6], 1):
            await c.send("join", name=f"Sailor {i}", code=crew[0].code)
            await c.joined()
        await crew[6].send("join", name="One too many", code=crew[0].code)
        err = await crew[6].until(lambda m: m["type"] == "error")
        self.assertIn("full", err["message"])

    async def test_defeat_resolution(self):
        room = {"code": "UNIT1", "host": "p1", "players": {
            "p1": {"id": "p1", "name": "One", "role": "Navigator"},
            "p2": {"id": "p2", "name": "Two", "role": "Lighthouse Keeper"}}, "game": None}
        game.game_new(room)
        g = room["game"]
        g["lost"] = 1
        g["actions"] = {"Navigator": {"ship": "invalid", "route": "north"}, "Lighthouse Keeper": {"route": "north"}}
        game.resolve(room)
        self.assertEqual(g["result"], "defeat")
        self.assertEqual(g["lost"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
