# ECHOPOINT: The Last Lighthouse

**Trust your crew. Question your signals. Save the ships.**

ECHOPOINT is a cooperative real-time browser game for 2-6 players. Your crew runs a lighthouse during a storm. Each player has a role, and the crew must combine clues, plot ships through dangerous passages, and line up the lighthouse beam to bring three ships safely into harbor.

## Play online

The Render deployment URL provided for this project is <https://echopoint-last-lighthouse.onrender.com/>.

Open the URL, create a room, then share the five-character room code with 1-5 other players. Everyone joins from their own device or browser session. The host starts once at least two players are present and everyone is ready.

Render's Free web services can sleep after 15 minutes without incoming traffic. The first visit after sleep may take about a minute to wake. Game rooms are kept in server memory, so sleeping, restarting, or redeploying the service clears rooms and active voyages. For longer or high-stakes sessions, see [Deployment and hosting notes](#deployment-and-hosting-notes).

## Run locally

Requires Python 3.9 or later.

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open <http://localhost:8080> in a browser. Open the same address in a second browser session or on a second device, create a room on one, and join it on the other. Keep the terminal running while you play; press `Ctrl+C` to stop the server. If port 8080 is already in use, set `PORT` before launching:

```powershell
$env:PORT = "8081"
python app.py
```

Then visit <http://localhost:8081>. To play from a phone on the same Wi-Fi, use the computer's local network IP address and allow that port through the computer firewall.

## Quick start: how to play

1. **Create or join a room.** The room creator is the host. Share the five-character code with your crew. Rooms accept 2-6 players.
2. **Get ready.** New crew members start ready. Each player can toggle readiness in the lobby. Only the host can start, and everyone must be ready.
3. **Read your role intelligence.** Each role has its own private clue. Talk to your crew and use passage-tagged Echo Signals to relay information.
4. **Place one order for each active role.** The Navigator plots a ship and passage; the Weather Analyst braces a passage; the Reef Scout scans a passage; the Lighthouse Keeper aims the beam. With fewer than four players, some roles are absent and their information is shared with the whole crew.
5. **Check the course.** Orders resolve when every represented role has submitted, followed by a four-second course-lock window. During that window, a role's submitting player can update their order. If the crew does not finish its orders, the watch resolves when its 45-second timer expires.
6. **Repeat the rescue.** Bring three ships home to win. Lose two ships, or reach the end of watch seven without three rescues, and the storm wins.
7. **Replay.** After a victory or defeat, the host can choose **Sail Again** to return the crew to the lobby for a new voyage.

There is no numeric score: the result screen summarizes ships rescued, ships lost, and watches played.

## The crew roles

| Role | Private information | Order | What the order does |
| --- | --- | --- | --- |
| **Navigator** | Shared ocean map, ships, and route options | Choose a ship still at sea and one passage | Sets the ship's course for this watch |
| **Weather Analyst** | Storm intensity, the passage under the current storm front, and whether the weather is building or easing | Choose a passage to brace | Protects a ship on that passage from the storm hazard this watch |
| **Reef Scout** | Which passages are clear and which contain a submerged reef | Scan one passage | Immediately shares that passage's sonar result with the whole crew |
| **Lighthouse Keeper** | Lighthouse beam controls and remaining light energy | Aim at a passage | Guides the Navigator's ship only if the beam matches the chosen passage |

Roles are assigned in this order: Navigator, Lighthouse Keeper, Weather Analyst, Reef Scout, then repeated in that order for player five and six. For repeated roles, the first player to submit that role's order sets it; other players with the same role cannot submit a second order for the same watch.

When the Weather Analyst or Reef Scout role is not assigned, that role's forecast or reef chart is shared as crew intelligence. Missing roles do not prevent a small crew from getting essential clues. If the Weather Analyst is absent, the server automatically braces a passage outside the current storm front. If the Reef Scout is absent, the reef chart is shared and no scan order is needed.

## Passages, ships, and hazards

- Each voyage has four ships: **Aurora**, **Morrow**, **Solace**, and **Tern**. Each starts at sea; a ship that is rescued or lost cannot be chosen again.
- The ocean has three passages: **North**, **East**, and **South**. Each new voyage randomly makes two passages clear and one passage dangerous due to a submerged reef. The Reef Scout's chart identifies them.
- Each watch also has a forecast storm passage. The Weather Analyst can brace any passage, but a storm-braced passage is not automatically safe from a reef. The crew still needs a clear passage as well as storm protection when the selected clear passage is under the storm front.
- The Navigator and Keeper must choose the same passage. If they do not, the ship loses the beam and is lost.
- A successful rescue requires a ship at sea, a clear passage, the Keeper's beam on the same passage, and protection from the storm if the passage is under the storm front.
- A failed crossing costs a ship. If the crew's orders are incomplete at timeout because the Navigator or Keeper did not submit, a ship is lost. Missing Weather Analyst and Reef Scout orders are handled automatically as described above.

## Watches and resources

- A voyage lasts up to **7 watches**. Each watch begins with a **45-second** server-controlled timer.
- The storm has a visible intensity from 1 to 5. It changes between watches. The Weather Analyst's forecast names the passage affected by the current storm front.
- The lighthouse begins with **6 light energy**. Attempting a crossing uses 1 energy. A successful rescue replenishes that 1 energy, up to the 6-energy maximum. A failed crossing spends the energy without replenishing it. When no light remains, another ship cannot be guided home.
- The crew begins with **6 Echo charges** shared by the whole room. Each player can send one signal per watch, and each signal spends 1 charge. Charges do not replenish during a voyage.
- A signal can be **SAFE ROUTE**, **DANGER AHEAD**, **NEED INFORMATION**, or **REDIRECT THE BEAM**. Select an optional passage tag to tell the crew which route you mean. Signals are communication only; they do not change the ship's route, remove a reef, or move the beam by themselves.
- The signal list and watch log show public crew messages and outcomes. The game also shows the objective, timer, role orders, rescued/lost ships, light, Echo charge, storm, and connected crew.

## Winning and losing

- **Victory:** rescue at least 3 ships.
- **Defeat:** lose 2 ships, or finish watch 7 with fewer than 3 rescues.
- The end screen shows the result, rescue count, loss count, and final watch. The host can replay with the same room and crew.

## Refresh, disconnect, and rooms

- If a player refreshes or temporarily disconnects, the same browser can reconnect to its seat using a random token saved in browser local storage. The room and voyage remain on the server while that server process stays alive.
- Keep the browser's local storage if you want the reconnect token to remain available. Clearing browser data removes it; the room code alone does not recover a seat that is already reserved.
- New players cannot enter after a voyage begins. They can join again after the host ends the result screen with **Sail Again** and the room returns to the lobby.
- Empty and inactive rooms expire 30 minutes after their creation. Restarting the server clears every room because room state is held in memory, not a database.

## Interface and accessibility

The interface is responsive for phones, tablets, and desktop. The shared map shows the three passages, lighthouse, and ship status. Role clues and order controls are shown separately from public crew information. Buttons are touch-friendly, the tutorial is available from **How to Play**, and order and connection errors appear as on-screen messages.

## Testing

Run the server-side multiplayer checks with:

```powershell
python -m unittest -v test_multiplayer.py
```

The checks cover several connected clients, room capacity, role-information privacy, readiness and host permissions, invalid and duplicate orders, signals, reconnection, shared state, timer transitions, victory, defeat, and replay. They use independent WebSocket clients rather than automated browser windows, so verify the visual layout in a real browser at your target screen size.

## Technology and architecture

- **Backend:** Python 3.9+ with aiohttp.
- **Frontend:** HTML, CSS, and vanilla JavaScript; no frontend build step.
- **Multiplayer:** WebSockets connect browsers to one authoritative game server. The server owns room membership, roles, hidden information, order validation, timers, resources, and outcomes. Public room state is broadcast to all crew; role intelligence is sent separately to each player's connection.
- **Health check:** `GET /health` returns `{"ok": true}`.
- **Local port:** defaults to 8080 and uses the `PORT` environment variable when provided by a host.

## Deployment and hosting notes

The included [Render Blueprint](render.yaml) defines a Python web service, dependency-install command, start command, and `/health` health check. Push the project to a Git repository, connect it to Render, then create a Blueprint from that repository. Render web services support inbound WebSocket connections.

The Blueprint currently selects Render's Free plan for demos. Free services can sleep after 15 minutes without incoming traffic and take about a minute to wake. The local filesystem and in-memory room state are not durable across sleep, restart, or redeployment. For a public event that must preserve active rooms across restarts, add a persistent shared data store and use hosting without free-plan sleep. See [Render's WebSocket documentation](https://render.com/docs/websocket), [Blueprint specification](https://render.com/docs/blueprint-spec), and [free instance limitations](https://render.com/docs/free).
