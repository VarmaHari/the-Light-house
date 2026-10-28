# ECHOPOINT: The Last Lighthouse

A cooperative, real-time browser game for 2–6 players. Each crew member gets a different role, and the server keeps the shared game state and resolves every watch.

## Run locally

Requires Python 3.9+.

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open <http://localhost:8080> in two browser sessions, create a room in one, and join with the five-character code in the other. The port can be changed with `PORT`.

## Play

- The host creates a room; crew join by room code. All crew must be ready before the host can start.
- Roles are assigned in a crew-friendly order. Every crew needs a Navigator and Lighthouse Keeper; unassigned Weather Analyst and Reef Scout information is shared with the crew.
- Each watch lasts 45 seconds. Submit one order per active role: plot a ship and route, brace against the forecast, scan a passage, and/or aim the beam. A Reef Scout's scan is shared live; when all orders are in, the crew has four seconds to adjust before course lock. Otherwise, the watch resolves at the deadline.
- Safe water, the Keeper's matching beam, and protection from the forecast storm are needed to rescue a ship. Three rescues win; two lost ships or seven watches lose.
- Each player may spend one Echo charge per watch. Predefined signals are shared live and can tag a passage.
- Refreshing a tab restores its seat using a random local reconnect token. Rooms expire after 30 minutes.

## Architecture

Python 3.9+ and aiohttp serve the static, responsive frontend and an authoritative WebSocket server. Rooms, role actions, timers, random layouts, validation, scoring, and outcomes live on the server. Public game state is broadcast to the room; role intelligence is sent only to the individual player's socket, with information from unassigned roles explicitly shared as crew intelligence. Room state is in memory and is cleared on server restart.

## Deployment

The app listens on `0.0.0.0` and honors the `PORT` environment variable. To deploy on Render, push this project to a Git repository, connect that repository in Render, and create a Blueprint from `render.yaml`. It configures the Python build command, server start command, and `/health` check.

The included Blueprint selects Render's Free plan for a demo. Free web services sleep after 15 minutes without incoming requests or WebSocket messages, then take about a minute to wake. Rooms are held in process memory and disappear whenever the server restarts or sleeps, so this setup is for trying the game, not a reliable public competition. For a persistent public game, the server state needs a database and the service needs hosting without free-plan sleep. See [Render's WebSocket documentation](https://render.com/docs/websocket) and [free instance limitations](https://render.com/docs/free).
