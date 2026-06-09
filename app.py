import os
import time
from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit, join_room
from game import BlackjackGame, GamePhase

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

TABLE_PASSWORD = os.environ.get("TABLE_PASSWORD", "blackjack")

socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins="*")

# ── Tunables ───────────────────────────────────────────────────────
MIN_BET       = 25   # minimum chips to be eligible for a round
BET_WINDOW    = 30   # seconds the betting window stays open
RESULTS_PAUSE = 6    # seconds to view results before the next deal
SEAT_GRACE    = 90   # seconds a disconnected player keeps their seat + chips
TURN_GRACE    = 10   # seconds to reconnect before we auto-stand an AWOL turn

game = BlackjackGame()

# ── Connection / timing state ──────────────────────────────────────
sid_to_player = {}        # sid -> player name
disconnected_since = {}   # name -> timestamp it lost its last socket
bet_deadline = None       # epoch seconds the current betting window closes
payout_until = None       # epoch seconds the results pause ends
turn_awol_since = None    # epoch seconds the current turn's player went AWOL
_loop_started = False


def connected_names():
    return set(sid_to_player.values())


# ── State builder ──────────────────────────────────────────────────

def build_state():
    hide_dealer = game.phase == GamePhase.PLAYING

    dealer_cards = game.dealer.cards
    if hide_dealer and dealer_cards:
        dealer_display = [repr(dealer_cards[0]), "??"]
        dealer_value = None
    else:
        dealer_display = [repr(c) for c in dealer_cards]
        dealer_value = game.dealer.value() if dealer_cards else None

    conn = connected_names()
    players_out = {}
    for name, player in game.players.items():
        players_out[name] = {
            "chips": player.chips,
            "connected": name in conn,
            "hands": [
                {
                    "cards": [repr(c) for c in h.cards],
                    "value": h.value(),
                    "bet": h.bet,
                    "status": h.status.value,
                    "can_hit": h.can_hit(),
                    "can_stand": h.can_stand(),
                    "can_double": h.can_double(),
                    "can_split": h.can_split(),
                }
                for h in player.hands
            ],
        }

    return {
        "phase": game.phase.value,
        "whose_turn": game.whose_turn(),
        "turn_order": game.turn_order,
        "dealer": {"cards": dealer_display, "value": dealer_value},
        "players": players_out,
        "min_bet": MIN_BET,
        "bet_deadline": bet_deadline,
        "server_now": time.time(),
    }


def emit_state():
    socketio.emit("game_state", build_state(), room="table")


# ── Round driver (runs in a background task) ───────────────────────

def has_active_bettors():
    """Is there at least one connected player who can afford a bet?"""
    conn = connected_names()
    return any(p.chips >= MIN_BET and n in conn for n, p in game.players.items())


def betting_settled():
    """Everyone connected who could still bet has bet, and at least one did."""
    conn = connected_names()
    pending = [
        n for n, p in game.players.items()
        if n in conn and not p.hands and p.chips >= MIN_BET
    ]
    has_bets = any(p.hands for p in game.players.values())
    return has_bets and not pending


def open_betting_window(now):
    global bet_deadline, payout_until
    game.start_betting()        # BETTING phase, resets hands + dealer
    bet_deadline = now + BET_WINDOW
    payout_until = None
    emit_state()


def close_betting_now():
    global bet_deadline
    bet_deadline = None
    try:
        game.deal_initial()     # turn_order becomes the actual bettors
    except ValueError:
        # nobody bet — drop back to the lobby
        game.phase = GamePhase.WAITING
        game.turn_order = []
    emit_state()


def reap_seats(now):
    """Free seats whose grace period has expired. Only call in safe phases."""
    removed = False
    for name, since in list(disconnected_since.items()):
        if now - since >= SEAT_GRACE:
            disconnected_since.pop(name, None)
            game.remove_player(name)
            removed = True
    return removed


def handle_awol_turn(now):
    global turn_awol_since
    current = game.whose_turn()
    if current and current not in connected_names():
        if turn_awol_since is None:
            turn_awol_since = now
        elif now - turn_awol_since >= TURN_GRACE:
            game.auto_stand_current()
            turn_awol_since = None
            emit_state()
    elif turn_awol_since is not None:
        turn_awol_since = None


def game_loop():
    global payout_until
    while True:
        socketio.sleep(1)
        now = time.time()
        try:
            phase = game.phase
            if phase == GamePhase.WAITING:
                if reap_seats(now):
                    emit_state()
                if has_active_bettors():
                    open_betting_window(now)
            elif phase == GamePhase.BETTING:
                if betting_settled() or (bet_deadline and now >= bet_deadline):
                    close_betting_now()
            elif phase == GamePhase.PLAYING:
                handle_awol_turn(now)
            elif phase == GamePhase.PAYOUT:
                if reap_seats(now):
                    emit_state()
                if payout_until is None:
                    payout_until = now + RESULTS_PAUSE
                elif now >= payout_until:
                    payout_until = None
                    game.phase = GamePhase.WAITING
                    game.turn_order = []
                    emit_state()
        except Exception as exc:  # never let the driver die
            print("game_loop error:", repr(exc))


def ensure_loop():
    global _loop_started
    if not _loop_started:
        _loop_started = True
        socketio.start_background_task(game_loop)


# ── Routes ─────────────────────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        session.clear()
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        chips_str = request.form.get("chips", "2000").strip()
        if not name:
            error = "Please enter your name."
        elif len(name) > 20:
            error = "Name too long (20 chars max)."
        elif password != TABLE_PASSWORD:
            error = "Wrong password."
        elif name in game.players and name in connected_names():
            error = "That name is already at the table."
        else:
            try:
                chips = int(chips_str)
                if chips < 100 or chips > 100_000:
                    error = "Chips must be between 100 and 100,000."
                else:
                    session["player_name"] = name
                    session["starting_chips"] = chips
                    return redirect(url_for("table"))
            except ValueError:
                error = "Invalid chip amount."
    return render_template("login.html", error=error)


@app.route("/table")
def table():
    if "player_name" not in session:
        return redirect(url_for("login"))
    return render_template("game.html", player_name=session["player_name"])


@app.route("/logout")
def logout():
    name = session.pop("player_name", None)
    session.pop("starting_chips", None)
    if name:
        disconnected_since.pop(name, None)
        # Only pull them from the table if they're not mid-hand; otherwise the
        # round driver auto-stands and the seat is reaped after the round.
        if game.phase in (GamePhase.WAITING, GamePhase.PAYOUT):
            game.remove_player(name)
            emit_state()
    return redirect(url_for("login"))


# ── Socket events ──────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    name = session.get("player_name")
    if not name:
        return False
    ensure_loop()
    join_room("table")
    sid_to_player[request.sid] = name
    disconnected_since.pop(name, None)   # reattaching cancels the grace timer
    if name not in game.players:
        chips = session.get("starting_chips", BlackjackGame.STARTING_CHIPS)
        try:
            game.add_player(name, chips)
        except ValueError:
            pass
    emit_state()


@socketio.on("disconnect")
def on_disconnect():
    name = sid_to_player.pop(request.sid, None)
    if not name:
        return
    # Hold the seat + chips; the round driver reaps it after SEAT_GRACE.
    if name not in connected_names():
        disconnected_since[name] = time.time()
    emit_state()


@socketio.on("place_bet")
def on_place_bet(data):
    name = session.get("player_name")
    try:
        amount = int(data.get("amount", 0))
        game.place_bet(name, amount)
        emit_state()
        if betting_settled():
            close_betting_now()
    except (ValueError, TypeError) as e:
        emit("error", {"message": str(e)})


@socketio.on("hit")
def on_hit():
    name = session.get("player_name")
    try:
        game.hit(name)
        emit_state()
    except ValueError as e:
        emit("error", {"message": str(e)})


@socketio.on("stand")
def on_stand():
    name = session.get("player_name")
    try:
        game.stand(name)
        emit_state()
    except ValueError as e:
        emit("error", {"message": str(e)})


@socketio.on("double_down")
def on_double_down():
    name = session.get("player_name")
    try:
        game.double_down(name)
        emit_state()
    except ValueError as e:
        emit("error", {"message": str(e)})


@socketio.on("split")
def on_split():
    name = session.get("player_name")
    try:
        game.split(name)
        emit_state()
    except ValueError as e:
        emit("error", {"message": str(e)})


@socketio.on("reload_chips")
def on_reload(data):
    name = session.get("player_name")
    try:
        amount = int(data.get("amount", BlackjackGame.STARTING_CHIPS))
        game.reload(name, amount)
        emit_state()
    except (ValueError, TypeError) as e:
        emit("error", {"message": str(e)})


if __name__ == "__main__":
    ensure_loop()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
