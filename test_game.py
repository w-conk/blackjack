"""
Quick smoke test — run with:  python test_game.py
No test framework needed, just prints results.
"""
from game import BlackjackGame, GamePhase, HandStatus, hand_value, Card, Suit


def separator(label):
    print(f"\n{'='*50}")
    print(f"  {label}")
    print('='*50)


# ------------------------------------------------------------------
# Helper: force specific cards into a hand for deterministic testing
# ------------------------------------------------------------------

def make_card(rank, suit_char="H"):
    suit_map = {"H": Suit.HEARTS, "D": Suit.DIAMONDS, "C": Suit.CLUBS, "S": Suit.SPADES}
    return Card(rank, suit_map[suit_char])


# ------------------------------------------------------------------
# Test 1: Basic round — two players, normal play
# ------------------------------------------------------------------

separator("Test 1: Basic round")

game = BlackjackGame()
game.add_player("Alice", chips=2000)
game.add_player("Bob", chips=2000)

game.start_betting()
game.place_bet("Alice", 100)
game.place_bet("Bob", 200)

game.deal_initial()
print(f"Phase after deal: {game.phase.value}")

state = game.state_for("Alice")
print(f"Alice's hand: {state['players']['Alice']['hands'][0]['cards']}")
print(f"Bob's hand:   {state['players']['Bob']['hands'][0]['cards']}")
print(f"Dealer shows: {state['dealer']['cards']}")
print(f"Whose turn:   {state['whose_turn']}")

# Play out whoever's turn it is
while game.phase == GamePhase.PLAYING:
    name = game.whose_turn()
    player = game.players[name]
    hand = player.current_hand
    print(f"\n{name}'s turn — hand: {hand.cards}, value: {hand.value()}")
    if hand.value() < 17:
        print(f"  → {name} hits")
        game.hit(name)
    else:
        print(f"  → {name} stands")
        game.stand(name)

print(f"\nDealer final hand: {game.dealer.cards}, value: {game.dealer.value()}")
print(f"Alice chips: {game.players['Alice'].chips}")
print(f"Bob chips:   {game.players['Bob'].chips}")
print(f"Phase: {game.phase.value}")


# ------------------------------------------------------------------
# Test 2: Hand value logic with Aces
# ------------------------------------------------------------------

separator("Test 2: Ace handling")

cases = [
    (["A", "K"], 21, "Ace+King = 21"),
    (["A", "A"], 12, "Ace+Ace = 12"),
    (["A", "9", "5"], 15, "Ace+9+5 = 15 (ace drops to 1)"),
    (["A", "A", "9"], 21, "Ace+Ace+9 = 21"),
    (["A", "A", "A", "8"], 21, "Three aces + 8 = 21"),
    (["10", "10", "2"], 22, "Bust: 10+10+2 = 22"),
]

for ranks, expected, desc in cases:
    cards = [make_card(r) for r in ranks]
    val = hand_value(cards)
    status = "PASS" if val == expected else f"FAIL (got {val})"
    print(f"  {status}: {desc}")


# ------------------------------------------------------------------
# Test 3: Soft 17 — dealer must hit
# ------------------------------------------------------------------

separator("Test 3: Dealer hits soft 17")

game2 = BlackjackGame()
game2.add_player("Carol", chips=2000)
game2.start_betting()
game2.place_bet("Carol", 100)
game2.deal_initial()

# Force dealer to have soft 17 and check should_hit
dealer = game2.dealer
dealer.cards = [make_card("A"), make_card("6")]
print(f"Dealer has: {dealer.cards}, value: {dealer.value()}")
print(f"should_hit: {dealer.should_hit()} (expected: True)")

dealer.cards = [make_card("A"), make_card("7")]
print(f"Dealer has: {dealer.cards}, value: {dealer.value()}")
print(f"should_hit: {dealer.should_hit()} (expected: False — soft 18 stands)")

dealer.cards = [make_card("10"), make_card("7")]
print(f"Dealer has: {dealer.cards}, value: {dealer.value()}")
print(f"should_hit: {dealer.should_hit()} (expected: False — hard 17 stands)")


# ------------------------------------------------------------------
# Test 4: Split
# ------------------------------------------------------------------

separator("Test 4: Split")

game3 = BlackjackGame()
game3.add_player("Dave", chips=2000)
game3.start_betting()
game3.place_bet("Dave", 200)
game3.deal_initial()

dave = game3.players["Dave"]
# Force a pair of 8s
dave.hands[0].cards = [make_card("8"), make_card("8")]
dave.hands[0].status = HandStatus.ACTIVE
print(f"Dave's hand before split: {dave.hands[0].cards}")
print(f"Can split: {dave.hands[0].can_split()}")
print(f"Dave chips before split: {dave.chips}")

if game3.phase == GamePhase.PLAYING and game3.whose_turn() == "Dave":
    game3.split("Dave")
    print(f"Dave hands after split: {[str(h.cards) for h in dave.hands]}")
    print(f"Dave chips after split: {dave.chips} (should be 200 less = 1600)")


# ------------------------------------------------------------------
# Test 5: Double down
# ------------------------------------------------------------------

separator("Test 5: Double down")

game4 = BlackjackGame()
game4.add_player("Eve", chips=2000)
game4.start_betting()
game4.place_bet("Eve", 300)
game4.deal_initial()

eve = game4.players["Eve"]
# Force Eve to have 11, dealer to stand on 20 (so Eve loses with ~18)
eve.hands[0].cards = [make_card("6"), make_card("5")]
eve.hands[0].status = HandStatus.ACTIVE
game4.dealer.cards = [make_card("10"), make_card("J")]  # dealer stands at 20
print(f"Eve's hand: {eve.hands[0].cards}, value: {eve.hands[0].value()}")
print(f"Can double: {eve.hands[0].can_double()}")
print(f"Eve chips before double: {eve.chips} (bet 300, so 1700)")

if game4.phase == GamePhase.PLAYING and game4.whose_turn() == "Eve":
    game4.double_down("Eve")
    h = eve.hands[0]
    print(f"Eve's hand after double: {h.cards}, value: {h.value()}")
    print(f"Bet is now: {h.bet} (should be 600)")
    if h.value() > 20 or h.value() <= game4.dealer.value():
        # Eve busted or lost to dealer 20
        print(f"Eve chips: {eve.chips} (Eve lost — should be 1400 if busted, else depends on card drawn)")
    else:
        print(f"Eve chips: {eve.chips}")


# ------------------------------------------------------------------
# Test 6: Reload
# ------------------------------------------------------------------

separator("Test 6: Reload")

game5 = BlackjackGame()
game5.add_player("Frank", chips=2000)
game5.players["Frank"].chips = 0
print(f"Frank chips before reload: {game5.players['Frank'].chips}")
game5.reload("Frank")
print(f"Frank chips after reload:  {game5.players['Frank'].chips} (should be 2000)")


# ------------------------------------------------------------------
# Test 7: 3:2 Blackjack payout
# ------------------------------------------------------------------

separator("Test 7: Blackjack 3:2 payout")

game6 = BlackjackGame()
game6.add_player("Grace", chips=2000)
game6.start_betting()
game6.place_bet("Grace", 200)
# Force Grace to have blackjack, dealer doesn't
grace = game6.players["Grace"]
grace.hands[0].cards = [make_card("A"), make_card("K")]
game6.dealer.cards = [make_card("10"), make_card("7")]
game6.phase = GamePhase.DEALER
game6.dealer.play(game6.deck)
game6._resolve_all()
print(f"Grace bet 200, got blackjack. Chips: {grace.chips} (should be 2300: 1800 kept + 200 stake + 300 profit)")


print("\n\nAll tests complete.")
