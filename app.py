import os
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

game = BlackjackGame()
sid_to_player = {}  # sid -> player name, for disconnect handling


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

    players_out = {}
    for name, player in game.players.items():
        players_out[name] = {
            "chips": player.chips,
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
    }


def emit_state():
    socketio.emit("game_state", build_state(), room="table")


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
    if name and game.phase in (GamePhase.WAITING, GamePhase.PAYOUT):
        game.remove_player(name)
        emit_state()
    return redirect(url_for("login"))


# ── Socket events ──────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    name = session.get("player_name")
    if not name:
        return False
    join_room("table")
    sid_to_player[request.sid] = name
    chips = session.get("starting_chips", BlackjackGame.STARTING_CHIPS)
    if name not in game.players and game.phase in (GamePhase.WAITING, GamePhase.PAYOUT):
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

    game.remove_player(name)

    # Recover game state after removing the player
    if not game.players:
        game.phase = GamePhase.WAITING
        game.turn_order = []
        game.active_player_index = 0
    elif game.phase == GamePhase.BETTING and game.all_bets_placed():
        game.deal_initial()
    elif game.phase == GamePhase.PLAYING and game.whose_turn() is None:
        game._dealer_play()

    emit_state()


@socketio.on("start_round")
def on_start_round():
    try:
        game.start_betting()
        emit_state()
    except ValueError as e:
        emit("error", {"message": str(e)})


@socketio.on("place_bet")
def on_place_bet(data):
    name = session.get("player_name")
    try:
        amount = int(data.get("amount", 0))
        game.place_bet(name, amount)
        emit_state()
        if game.all_bets_placed():
            game.deal_initial()
            emit_state()
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
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
