import asyncio
import json
import math
import random
import re
import secrets
import time
from pathlib import Path

from aiohttp import WSMsgType, web

ROOT = Path(__file__).parent
rooms = {}
ROLE_ORDER = ["Navigator", "Weather Analyst", "Reef Scout", "Lighthouse Keeper"]
ROLE_ASSIGNMENT = ["Navigator", "Lighthouse Keeper", "Weather Analyst", "Reef Scout"]
ROLE_TIPS = {
    "Navigator": "Plot one ship on a route toward the harbor. Your action sets the ship's course.",
    "Weather Analyst": "Brace a route against this round's storm. An unbraced storm route is unsafe.",
    "Reef Scout": "Scan a route and share what is beneath the waves with your crew.",
    "Lighthouse Keeper": "Aim the beam at the same route the Navigator chose to guide a ship home.",
}
SIGNALS = {"SAFE ROUTE": 1, "DANGER AHEAD": 1, "NEED INFORMATION": 1, "REDIRECT THE BEAM": 1}


def now():
    return time.time()


def new_room():
    return "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(5))


def player_public(p):
    return {"id": p["id"], "name": p["name"], "role": p.get("role"), "ready": p["ready"],
            "connected": p["ws"] is not None, "host": p["id"] == p.get("host_id")}


def public_state(room):
    players = [{"id": p["id"], "name": p["name"], "role": p.get("role"), "ready": p["ready"],
                "connected": p["ws"] is not None, "host": p["id"] == room["host"]}
               for p in room["players"].values()]
    g = room.get("game")
    state = {"room": room["code"], "host": room["host"], "players": players,
             "phase": "game" if g else "lobby", "minPlayers": 2, "maxPlayers": 6}
    if not g:
        return state
    state["game"] = {
        "round": g["round"], "maxRounds": g["maxRounds"], "deadline": g["deadline"], "resolveAt": g.get("resolveAt"),
        "rescued": g["rescued"], "lost": g["lost"], "target": g["target"],
        "light": g["light"], "comms": g["comms"], "storm": g["storm"],
        "ships": g["ships"], "routes": [{"id": r["id"], "label": r["label"], "path": r["path"]} for r in g["routes"]],
        "events": g["events"][-12:], "signals": g["signals"][-8:], "result": g["result"],
        "submitted": sorted(g["actions"].keys()),
        "submittedBy": {role: action["by"] for role, action in g["actions"].items()},
        "required": g["requiredRoles"], "island": g["island"]
    }
    return state


def private_for(room, p):
    g = room.get("game")
    if not g:
        return None
    intel = {"role": p["role"], "tip": ROLE_TIPS[p["role"]], "roleReady": p["role"] in g["actions"]}
    if p["role"] == "Navigator":
        intel["brief"] = "Track each ship's bearing and plot one route per round."
    if p["role"] == "Weather Analyst":
        intel["forecast"] = g["forecast"]
    if p["role"] == "Reef Scout":
        intel["reefs"] = g["reefs"]
    assigned = {x["role"] for x in room["players"].values()}
    if "Weather Analyst" not in assigned:
        intel["crewForecast"] = g["forecast"]
    if "Reef Scout" not in assigned:
        intel["crewReefs"] = g["reefs"]
    return intel


async def send(ws, data):
    if ws is not None and not ws.closed:
        await ws.send_json(data)


async def broadcast(room):
    pub = {"type": "state", "state": public_state(room)}
    for p in list(room["players"].values()):
        await send(p["ws"], pub)
        await send(p["ws"], {"type": "private", "intel": private_for(room, p)})


def event(g, text, kind="info"):
    g["events"].append({"text": text, "kind": kind, "at": now()})
    g["events"] = g["events"][-30:]


def game_new(room):
    players = list(room["players"].values())
    random.shuffle(players)
    for i, p in enumerate(players):
        p["role"] = ROLE_ASSIGNMENT[i % 4]
    safe_ids = set(random.sample(["north", "east", "south"], 2))
    routes = [
        {"id": "north", "label": "North passage", "path": [[0, 1], [1, 1], [2, 2], [3, 3], [4, 4]]},
        {"id": "east", "label": "East passage", "path": [[8, 4], [7, 4], [6, 4], [5, 4], [4, 4]]},
        {"id": "south", "label": "South passage", "path": [[1, 8], [2, 7], [3, 6], [4, 5], [4, 4]]},
    ]
    g = {"round": 1, "maxRounds": 7, "deadline": now() + 45, "rescued": 0, "lost": 0,
         "target": 3, "light": 6, "comms": 6, "storm": random.randint(1, 3),
         "ships": [{"id": f"ship-{i+1}", "name": n, "bearing": b, "status": "at sea"}
                   for i, (n, b) in enumerate([("Aurora", "outer buoy"), ("Morrow", "reef line"), ("Solace", "open water"), ("Tern", "southeast shoal")])],
         "routes": routes, "safeRoutes": list(safe_ids),
         "reefRoute": next(r for r in ["north", "east", "south"] if r not in safe_ids),
         "forecast": {"stormRoute": random.choice(["north", "east", "south"]), "nextStorm": "Building" if random.random() < .5 else "Easing", "intensity": "Gale"},
         "reefs": {r["id"]: ("clear water" if r["id"] in safe_ids else "submerged reef") for r in routes},
         "actions": {}, "requiredRoles": list(dict.fromkeys(p["role"] for p in players)),
         "signals": [], "events": [], "result": None, "island": [4, 4]}
    g["reefRoute"] = next(r for r in ["north", "east", "south"] if r not in safe_ids)
    g["forecast"]["stormRoute"] = random.choice(["north", "east", "south"])
    if "Weather Analyst" not in g["requiredRoles"]:
        # If the analyst role is unassigned, the storm forecast is crew intelligence.
        pass
    room["game"] = g
    event(g, "The storm has closed around the lighthouse. Crew, bring three ships home in seven watches.", "system")
    return g


def resolve(room):
    g = room["game"]
    if g["result"]:
        return
    acts = g["actions"]
    nav = acts.get("Navigator")
    keeper = acts.get("Lighthouse Keeper")
    analyst = acts.get("Weather Analyst")
    scout = acts.get("Reef Scout")
    # Unassigned information roles supply an automatic, solvable crew action.
    if not analyst:
        analyst = {"route": next((r for r in ["north", "east", "south"] if r != g["forecast"]["stormRoute"]), "east")}
    if not scout and nav:
        scout = {"route": nav.get("route")}
    if not nav or not keeper:
        event(g, "No course or beam was set in time. The ship slips into the dark.", "danger")
        ship = next((s for s in g["ships"] if nav and s["id"] == nav.get("ship") and s["status"] == "at sea"), None)
        ship = ship or next((s for s in g["ships"] if s["status"] == "at sea"), None)
        if ship:
            ship["status"] = "lost"
        g["lost"] += 1
    else:
        route = nav.get("route")
        ship = next((s for s in g["ships"] if s["id"] == nav.get("ship") and s["status"] == "at sea"), None)
        if not ship:
            event(g, "That ship is no longer at sea. The watch was lost to indecision.", "danger")
            g["lost"] += 1
        elif g["light"] <= 0:
            event(g, "The lighthouse has no beam energy. A ship is lost in the storm.", "danger")
            ship["status"] = "lost"
            g["lost"] += 1
        else:
            g["light"] -= 1
            hazard = route not in g["safeRoutes"] or (route == g["forecast"]["stormRoute"] and analyst.get("route") != route)
            if route not in g["safeRoutes"]:
                why = "a hidden reef"
            else:
                why = "the unbraced storm" if hazard else "clear water"
            if keeper.get("route") != route:
                event(g, f"{ship['name']} lost the beam while crossing {route}. The ship is lost.", "danger")
                ship["status"] = "lost"
                g["lost"] += 1
            elif hazard:
                event(g, f"{ship['name']} struck {why} in the {route} passage.", "danger")
                ship["status"] = "lost"
                g["lost"] += 1
            else:
                ship["status"] = "rescued"
                g["rescued"] += 1
                event(g, f"{ship['name']} found the beam and reached harbor via {route.upper()}!", "success")
                g["light"] = min(6, g["light"] + 1)
            if scout and scout.get("route") in g["reefs"]:
                result = g["reefs"][scout["route"]]
                event(g, f"Reef Scout chart: {scout['route'].upper()} is {result}.", "intel")
    if g["rescued"] >= g["target"]:
        g["result"] = "victory"
        event(g, "Three ships are safe. The last lighthouse holds through the storm!", "success")
    elif g["lost"] >= 2:
        g["result"] = "defeat"
        event(g, "Two ships have been lost. The rescue mission is over.", "danger")
    elif g["round"] >= g["maxRounds"]:
        g["result"] = "defeat"
        event(g, "The storm has passed its limit. Not enough ships reached harbor.", "danger")
    else:
        g["round"] += 1
        g["storm"] = max(1, min(5, g["storm"] + random.choice([-1, 0, 1])))
        g["forecast"] = {"stormRoute": random.choice(["north", "east", "south"]), "nextStorm": random.choice(["Building", "Easing"]), "intensity": ["Squalls", "Heavy", "Gale", "Violent", "Extreme"][g["storm"]-1]}
        g["actions"] = {}
        g.pop("resolveAt", None)
        g["deadline"] = now() + 45
        event(g, f"Watch {g['round']} begins. {g['storm']} / 5 storm intensity.", "system")


async def timer(room):
    while room.get("game") and not room["game"]["result"]:
        g = room["game"]
        if set(g["actions"]) >= set(g["requiredRoles"]):
            if g.get("resolveAt") and now() >= g["resolveAt"]:
                resolve(room)
                await broadcast(room)
                continue
        if now() >= g["deadline"]:
            resolve(room)
            await broadcast(room)
            continue
        await asyncio.sleep(min(1, max(.1, g["deadline"] - now())))


def error(text):
    return {"type": "error", "message": text}


async def ws_handler(request):
    ws = web.WebSocketResponse(heartbeat=20, max_msg_size=4096)
    await ws.prepare(request)
    player = None
    room = None
    await send(ws, {"type": "hello"})
    async for msg in ws:
        if msg.type != WSMsgType.TEXT:
            if msg.type == WSMsgType.ERROR:
                break
            continue
        try:
            data = json.loads(msg.data)
            if not isinstance(data, dict) or not isinstance(data.get("type"), str):
                raise ValueError()
        except (json.JSONDecodeError, ValueError):
            await send(ws, error("Malformed request."))
            continue
        kind = data["type"]
        if kind in ("create", "join", "reconnect"):
            if room:
                await send(ws, error("You already occupy a room.")); continue
            name = re.sub(r"[^\w -]", "", str(data.get("name", "Player")))[:18].strip() or "Player"
            token = str(data.get("token", ""))[:100]
            if kind == "create":
                code = new_room()
                while code in rooms: code = new_room()
                pid = secrets.token_urlsafe(12)
                room = {"code": code, "host": pid, "players": {}, "game": None, "created": now()}
                rooms[code] = room
                player = {"id": pid, "token": secrets.token_urlsafe(24), "name": name, "ready": True, "ws": ws}
                room["players"][pid] = player
            else:
                code = str(data.get("code", "")).strip().upper()
                room = rooms.get(code)
                if not room:
                    await send(ws, error("Room code not found. Check the five letters and numbers.")); continue
                old = next((p for p in room["players"].values() if token and secrets.compare_digest(token, p["token"])), None)
                if kind == "reconnect":
                    if not old:
                        await send(ws, error("Reconnect token expired. Rejoin with the room code.")); room = None; continue
                    player = old
                    if player["ws"] and player["ws"] is not ws:
                        await player["ws"].close()
                    player["ws"] = ws
                elif old:
                    player = old; player["ws"] = ws
                else:
                    if room["game"]:
                        await send(ws, error("This voyage is underway. New crew can join after replay.")); room = None; continue
                    if len(room["players"]) >= 6:
                        await send(ws, error("This room is full (6/6). Try another code.")); room = None; continue
                    pid = secrets.token_urlsafe(12)
                    player = {"id": pid, "token": secrets.token_urlsafe(24), "name": name, "ready": True, "ws": ws}
                    room["players"][pid] = player
            player["name"] = name or player["name"]
            await send(ws, {"type": "joined", "code": room["code"], "id": player["id"], "token": player["token"]})
            await broadcast(room)
            continue
        if not room or not player:
            await send(ws, error("Create or join a room first.")); continue
        if kind == "ready":
            if room["game"]:
                await send(ws, error("The voyage is already underway.")); continue
            player["ready"] = bool(data.get("ready"))
            await broadcast(room)
        elif kind == "start":
            if player["id"] != room["host"]:
                await send(ws, error("Only the host can start the voyage.")); continue
            if room["game"]:
                await send(ws, error("The voyage has already started.")); continue
            crew = list(room["players"].values())
            if len(crew) < 2 or not all(p["ready"] for p in crew):
                await send(ws, error("Need 2–6 players, and every crew member must be ready.")); continue
            game_new(room)
            for p in crew:
                p["role"] = ROLE_ASSIGNMENT[crew.index(p) % 4]
            room["timer"] = asyncio.create_task(timer(room))
            await broadcast(room)
        elif kind == "action":
            g = room.get("game")
            if not g or g["result"]:
                await send(ws, error("No active watch is accepting orders.")); continue
            if now() >= g["deadline"]:
                await send(ws, error("That watch has closed.")); continue
            role = player.get("role")
            if role not in g["requiredRoles"]:
                await send(ws, error("Your role is not assigned to this crew.")); continue
            if role in g["actions"] and g["actions"][role]["by"] != player["id"]:
                await send(ws, error("A crewmate has already submitted this role's order.")); continue
            value = data.get("value")
            if not isinstance(value, dict):
                await send(ws, error("Choose an order first.")); continue
            if role == "Navigator":
                ship = next((s for s in g["ships"] if s["id"] == value.get("ship") and s["status"] == "at sea"), None)
                route = value.get("route")
                if not ship or route not in ["north", "east", "south"]:
                    await send(ws, error("Choose a ship at sea and a valid route (north, east, or south).")); continue
                clean = {"ship": ship["id"], "route": route}
            elif role in ("Weather Analyst", "Reef Scout"):
                route = value.get("route")
                if route not in ["north", "east", "south"]:
                    await send(ws, error("Choose a valid route.")); continue
                clean = {"route": route}
            elif role == "Lighthouse Keeper":
                route = value.get("route")
                if route not in ["north", "east", "south"]:
                    await send(ws, error("Aim at one of the three routes.")); continue
                clean = {"route": route}
            g["actions"][role] = {**clean, "by": player["id"]}
            event(g, f"{role} order received.", "system")
            if role == "Reef Scout":
                event(g, f"Sonar chart: {clean['route'].upper()} is {g['reefs'][clean['route']]}.", "intel")
            if set(g["actions"]) >= set(g["requiredRoles"]):
                if not g.get("resolveAt"):
                    g["resolveAt"] = now() + 4
                    event(g, "All orders are in. Course lock in four seconds.", "system")
            await broadcast(room)
        elif kind == "signal":
            g = room.get("game")
            label = data.get("signal")
            if not g or g["result"] or label not in SIGNALS:
                await send(ws, error("That signal is unavailable.")); continue
            if player.get("signalRound") == g["round"]:
                await send(ws, error("You have already sent a signal this watch.")); continue
            if g["comms"] < 1:
                await send(ws, error("The echo channel has no energy left.")); continue
            route = data.get("route")
            if route is not None and route not in ("north", "east", "south"):
                await send(ws, error("Choose a valid passage for that signal.")); continue
            g["comms"] -= 1
            player["signalRound"] = g["round"]
            g["signals"].append({"player": player["name"], "playerId": player["id"], "text": label, "route": route, "round": g["round"]})
            event(g, f"{player['name']} signals: {label}{' · ' + route.upper() if route else ''}.", "signal")
            await broadcast(room)
        elif kind == "replay":
            if player["id"] != room["host"]:
                await send(ws, error("Only the host can begin a new voyage.")); continue
            if not room["game"] or not room["game"]["result"]:
                await send(ws, error("Finish the current voyage before replaying.")); continue
            room["game"] = None
            for p in room["players"].values():
                p["role"] = None
            await broadcast(room)
        elif kind == "ping":
            await send(ws, {"type": "pong", "time": now()})
        else:
            await send(ws, error("Unknown request."))
    if player and room and room.get("players", {}).get(player["id"], {}).get("ws") is ws:
        player["ws"] = None
        await broadcast(room)
    return ws


async def cleanup(app):
    for room in list(rooms.values()):
        if now() - room["created"] > 1800:
            task = room.get("timer")
            if task: task.cancel()
            rooms.pop(room["code"], None)


async def on_startup(app):
    app["cleanup_task"] = asyncio.create_task(cleanup_loop())


async def cleanup_loop():
    while True:
        await asyncio.sleep(60)
        for code, room in list(rooms.items()):
            if now() - room["created"] > 1800:
                task = room.get("timer")
                if task: task.cancel()
                rooms.pop(code, None)


async def on_cleanup(app):
    app["cleanup_task"].cancel()
    for room in rooms.values():
        task = room.get("timer")
        if task: task.cancel()


def create_app():
    application = web.Application(client_max_size=1024 * 1024)
    application.router.add_get("/ws", ws_handler)
    application.router.add_get("/", lambda request: web.FileResponse(ROOT / "static" / "index.html"))
    application.router.add_get("/style.css", lambda request: web.FileResponse(ROOT / "static" / "style.css"))
    application.router.add_get("/game.js", lambda request: web.FileResponse(ROOT / "static" / "game.js"))
    application.router.add_get("/health", lambda request: web.json_response({"ok": True}))
    application.on_startup.append(on_startup)
    application.on_cleanup.append(on_cleanup)
    return application


app = create_app()

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(__import__("os").environ.get("PORT", "8080")))
