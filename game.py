import random
from enum import Enum


class Suit(Enum):
    HEARTS = "Hearts"
    DIAMONDS = "Diamonds"
    CLUBS = "Clubs"
    SPADES = "Spades"


class Card:
    RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

    def __init__(self, rank, suit):
        self.rank = rank
        self.suit = suit

    def value(self):
        if self.rank in ("J", "Q", "K"):
            return 10
        if self.rank == "A":
            return 11
        return int(self.rank)

    def __repr__(self):
        return f"{self.rank}{self.suit.value[0]}"


class Deck:
    def __init__(self, num_decks=6):
        self.num_decks = num_decks
        self.cards = []
        self.reshuffle()

    def reshuffle(self):
        self.cards = [
            Card(rank, suit)
            for _ in range(self.num_decks)
            for suit in Suit
            for rank in Card.RANKS
        ]
        random.shuffle(self.cards)

    def deal(self):
        # Reshuffle when fewer than 25% of cards remain
        if len(self.cards) < (self.num_decks * 52 * 0.25):
            self.reshuffle()
        return self.cards.pop()


def hand_value(cards):
    total = sum(c.value() for c in cards)
    aces = sum(1 for c in cards if c.rank == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def is_blackjack(cards):
    return len(cards) == 2 and hand_value(cards) == 21


def is_bust(cards):
    return hand_value(cards) > 21


def can_split(cards):
    return len(cards) == 2 and cards[0].rank == cards[1].rank


def can_double(cards):
    return len(cards) == 2


class HandStatus(Enum):
    ACTIVE = "active"
    STOOD = "stood"
    BUST = "bust"
    BLACKJACK = "blackjack"
    DOUBLED = "doubled"


class PlayerHand:
    def __init__(self, bet, cards=None):
        self.bet = bet
        self.cards = cards or []
        self.status = HandStatus.ACTIVE
        self.is_split_hand = False

    def value(self):
        return hand_value(self.cards)

    def is_blackjack(self):
        return is_blackjack(self.cards) and not self.is_split_hand

    def is_bust(self):
        return is_bust(self.cards)

    def can_split(self):
        return self.status == HandStatus.ACTIVE and can_split(self.cards)

    def can_double(self):
        return self.status == HandStatus.ACTIVE and can_double(self.cards)

    def can_hit(self):
        return self.status == HandStatus.ACTIVE

    def can_stand(self):
        return self.status == HandStatus.ACTIVE


class Player:
    def __init__(self, name, chips):
        self.name = name
        self.chips = chips
        self.hands = []
        self.current_hand_index = 0

    @property
    def current_hand(self):
        if self.hands and self.current_hand_index < len(self.hands):
            return self.hands[self.current_hand_index]
        return None

    def place_bet(self, amount):
        if amount < 25:
            raise ValueError("Minimum bet is 25 chips.")
        if amount > self.chips:
            raise ValueError("Not enough chips.")
        self.chips -= amount
        self.hands = [PlayerHand(bet=amount)]
        self.current_hand_index = 0

    def hit(self, deck):
        hand = self.current_hand
        if not hand or not hand.can_hit():
            raise ValueError("Cannot hit.")
        hand.cards.append(deck.deal())
        if hand.is_bust():
            hand.status = HandStatus.BUST
            self._advance_hand()

    def stand(self):
        hand = self.current_hand
        if not hand or not hand.can_stand():
            raise ValueError("Cannot stand.")
        hand.status = HandStatus.STOOD
        self._advance_hand()

    def double_down(self, deck):
        hand = self.current_hand
        if not hand or not hand.can_double():
            raise ValueError("Cannot double down.")
        if hand.bet > self.chips:
            raise ValueError("Not enough chips to double down.")
        self.chips -= hand.bet
        hand.bet *= 2
        hand.cards.append(deck.deal())
        hand.status = HandStatus.BUST if hand.is_bust() else HandStatus.DOUBLED
        self._advance_hand()

    def split(self, deck):
        hand = self.current_hand
        if not hand or not hand.can_split():
            raise ValueError("Cannot split.")
        if hand.bet > self.chips:
            raise ValueError("Not enough chips to split.")
        self.chips -= hand.bet

        card_a, card_b = hand.cards
        new_hand_a = PlayerHand(bet=hand.bet, cards=[card_a, deck.deal()])
        new_hand_a.is_split_hand = True
        new_hand_b = PlayerHand(bet=hand.bet, cards=[card_b, deck.deal()])
        new_hand_b.is_split_hand = True

        self.hands[self.current_hand_index] = new_hand_a
        self.hands.insert(self.current_hand_index + 1, new_hand_b)

        if new_hand_a.is_bust():
            new_hand_a.status = HandStatus.BUST
            self._advance_hand()

    def _advance_hand(self):
        self.current_hand_index += 1

    def all_hands_done(self):
        return self.current_hand_index >= len(self.hands)

    def reload(self, amount):
        self.chips += amount


class Dealer:
    def __init__(self):
        self.cards = []

    def value(self):
        return hand_value(self.cards)

    def is_blackjack(self):
        return is_blackjack(self.cards)

    def is_bust(self):
        return is_bust(self.cards)

    def should_hit(self):
        total = self.value()
        if total < 17:
            return True
        if total == 17:
            # Soft 17: any Ace counted as 11 means hard total (all aces=1) differs
            hard_total = sum(1 if c.rank == "A" else c.value() for c in self.cards)
            return total != hard_total
        return False

    def play(self, deck):
        while self.should_hit():
            self.cards.append(deck.deal())

    def visible_card(self):
        return self.cards[0] if self.cards else None


class GamePhase(Enum):
    WAITING = "waiting"       # Lobby, not started
    BETTING = "betting"       # Players placing bets
    DEALING = "dealing"       # Cards being dealt
    PLAYING = "playing"       # Players taking turns
    DEALER = "dealer"         # Dealer playing out
    PAYOUT = "payout"         # Results shown


def resolve_hand(hand, dealer):
    """Return total chips to give back to player (stake + any profit). 0 = total loss."""
    if hand.is_blackjack():
        return hand.bet + int(hand.bet * 1.5)  # stake + 3:2 profit
    if hand.status == HandStatus.BUST:
        return 0
    dealer_bust = dealer.is_bust()
    player_val = hand.value()
    dealer_val = dealer.value()
    if dealer_bust or player_val > dealer_val:
        return hand.bet * 2  # stake + equal profit
    if player_val == dealer_val:
        return hand.bet  # push: stake back only
    return 0  # loss


class BlackjackGame:
    """
    Manages one table: up to 6 players, one shared deck, phase-based flow.

    Chip accounting: bets are deducted when placed. resolve_hand() returns the
    full amount to give back (stake + profit for win, stake only for push,
    stake + 1.5x for blackjack, 0 for loss/bust).
    """

    MAX_PLAYERS = 6
    STARTING_CHIPS = 2000

    def __init__(self):
        self.deck = Deck(num_decks=6)
        self.players = {}       # name -> Player
        self.dealer = Dealer()
        self.phase = GamePhase.WAITING
        self.turn_order = []    # ordered list of player names for current round
        self.active_player_index = 0

    # ------------------------------------------------------------------
    # Lobby
    # ------------------------------------------------------------------

    def add_player(self, name, chips=None):
        if name in self.players:
            raise ValueError(f"{name} is already at the table.")
        if len(self.players) >= self.MAX_PLAYERS:
            raise ValueError("Table is full (6 players max).")
        self.players[name] = Player(name, chips or self.STARTING_CHIPS)

    def remove_player(self, name):
        self.players.pop(name, None)
        if name in self.turn_order:
            idx = self.turn_order.index(name)
            self.turn_order.remove(name)
            # Keep active_player_index pointing at the right player
            if idx < self.active_player_index:
                self.active_player_index -= 1
            elif idx == self.active_player_index:
                # Their turn — index now points at the next player automatically
                pass

    # ------------------------------------------------------------------
    # Round flow
    # ------------------------------------------------------------------

    def start_betting(self):
        if self.phase not in (GamePhase.WAITING, GamePhase.PAYOUT):
            raise ValueError("Cannot start betting now.")
        eligible = [name for name, p in self.players.items() if p.chips >= 25]
        if not eligible:
            raise ValueError("No players have enough chips to play.")
        self.phase = GamePhase.BETTING
        self.turn_order = eligible
        for player in self.players.values():
            player.hands = []
            player.current_hand_index = 0
        self.dealer.cards = []

    def place_bet(self, player_name, amount):
        if self.phase != GamePhase.BETTING:
            raise ValueError("Not in betting phase.")
        self.players[player_name].place_bet(amount)

    def all_bets_placed(self):
        return all(len(self.players[n].hands) > 0 for n in self.turn_order)

    def deal_initial(self):
        if self.phase != GamePhase.BETTING:
            raise ValueError("Cannot deal now.")
        if not self.all_bets_placed():
            raise ValueError("Not all players have placed bets.")
        self.phase = GamePhase.DEALING

        # Two cards each, interleaved like a real deal
        for _ in range(2):
            for name in self.turn_order:
                self.players[name].hands[0].cards.append(self.deck.deal())
            self.dealer.cards.append(self.deck.deal())

        # Check dealer blackjack
        if self.dealer.is_blackjack():
            self._resolve_all()
            return

        # Check if all players have blackjack (auto-stand)
        self.phase = GamePhase.PLAYING
        self.active_player_index = 0
        self._skip_done_players()

    def _current_active_player(self):
        if self.active_player_index < len(self.turn_order):
            return self.players[self.turn_order[self.active_player_index]]
        return None

    def _skip_done_players(self):
        while True:
            player = self._current_active_player()
            if player is None:
                self._dealer_play()
                return
            if player.all_hands_done():
                self.active_player_index += 1
            elif player.current_hand.is_blackjack():
                player.current_hand.status = HandStatus.BLACKJACK
                player._advance_hand()
            else:
                break

    def whose_turn(self):
        player = self._current_active_player()
        return player.name if player else None

    def hit(self, player_name):
        self._assert_turn(player_name)
        player = self.players[player_name]
        player.hit(self.deck)
        if player.all_hands_done():
            self.active_player_index += 1
            self._skip_done_players()

    def stand(self, player_name):
        self._assert_turn(player_name)
        player = self.players[player_name]
        player.stand()
        if player.all_hands_done():
            self.active_player_index += 1
            self._skip_done_players()

    def double_down(self, player_name):
        self._assert_turn(player_name)
        player = self.players[player_name]
        player.double_down(self.deck)
        if player.all_hands_done():
            self.active_player_index += 1
            self._skip_done_players()

    def split(self, player_name):
        self._assert_turn(player_name)
        player = self.players[player_name]
        player.split(self.deck)
        self._skip_done_players()

    def _assert_turn(self, player_name):
        if self.phase != GamePhase.PLAYING:
            raise ValueError("Not in playing phase.")
        if self.whose_turn() != player_name:
            raise ValueError(f"It is not {player_name}'s turn.")

    def _dealer_play(self):
        self.phase = GamePhase.DEALER
        self.dealer.play(self.deck)
        self._resolve_all()

    def _resolve_all(self):
        self.phase = GamePhase.PAYOUT
        for player in self.players.values():
            for hand in player.hands:
                player.chips += resolve_hand(hand, self.dealer)

    def reload(self, player_name, amount=None):
        player = self.players[player_name]
        if amount is None:
            amount = self.STARTING_CHIPS
        player.reload(amount)

    def state_for(self, player_name, hide_dealer=True):
        """Return serializable game state from a player's perspective."""
        dealer_cards = self.dealer.cards
        if hide_dealer and self.phase == GamePhase.PLAYING:
            dealer_display = [str(dealer_cards[0]), "??"] if dealer_cards else []
            dealer_value = None
        else:
            dealer_display = [str(c) for c in dealer_cards]
            dealer_value = self.dealer.value()

        players_state = {}
        for name, player in self.players.items():
            players_state[name] = {
                "chips": player.chips,
                "hands": [
                    {
                        "cards": [str(c) for c in h.cards],
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
            "phase": self.phase.value,
            "whose_turn": self.whose_turn(),
            "dealer": {
                "cards": dealer_display,
                "value": dealer_value,
            },
            "players": players_state,
            "you": player_name,
        }
