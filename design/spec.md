# Organized Spec

## 1. World Canon

### Title And Reference

VRBTM-1:

# Villmage v1

[game](Villmage%20v1/game%2034538e6b0e9980618359fd70560de691.md)

### Backstory

VRBTM-2:

A great pestilence has swept across the country. Carried by trade ships into the port cities, then up the rivers and along the roads the **Grey Rot** — known for the ashen pallor it gives the skin before the fever takes hold — has caused whole towns to go silent. The sick are burned where they fall.

The Holy Church calls it divine retribution.

The party formed while escaping from a village at the outskirts of the empire, having caught word from the capital. They made the practical choice to flee when they saw the first cases with their own eyes.

As they traversed poorly maintained forest paths, an axle of their caravan snapped while crossing a rut. What supplies they had were already thin, and now they were immobilized.

Stranded with nowhere safe to return, they decide to settle down in a crook of a river of the Stillwood forest, scattered peaches and boars promising meager sustenance. There’s not much option besides waiting out the plague.

Unfortunately, it’s not clear which of them are infected.

### Villmager Canon

VRBTM-3:

### Aldric the Woodsman

**Bio:** Mid-30s, broad-shouldered, lean from years of outdoor labor, a massive frame. Sun-darkened skin, a thick brown beard, and calloused hands. Weathered woodsman.

**Personality:** Steady and warm-natured, the sort who hums while he works and offers encouragement without being asked. He genuinely likes being useful and draws a quiet satisfaction from seeing others fed, sheltered, and holding together.

**Desires:** He wants to keep this group alive. Because he couldn't do the same for the plague-afflicted family he left behind.

VRBTM-4:

### Sewalt the Hunter

**Bio:** Late 20s, wiry and sharp-featured, with pale eyes that never seem to settle on one spot for long. Dark hair kept short and practical. Experienced hunter.

**Personality:** Quiet and watchful, always scanning the tree line or listening for something the others can't hear. He means well but his constant unease is contagious, always voicing the worst outcomes. Grew up in the Capital's black market, retired to a village.

**Desires:** He wants to feel truly safe. And yet he never will.

VRBTM-5:

### Harren the Builder

**Bio:** Early 40s, stocky and thick-armed, with a square jaw and a permanent squint from years of working in sawdust and smoke. Cropped grey-streaked hair. Skilled carpenter.

**Personality:** Practical and blunt. Measures twice and speaks once, if ever. Helps the group because their survival is his survival, not out of care. Acutely aware of relationship transactionality.

**Desires:** Prioritizes his own safety and comfort above all else, and doesn’t care what others think. Needs to be in control of his own fate.

VRBTM-6:

### Maren the Gatherer

**Bio:** Early 30s, plain-faced and unremarkable by design, with steady brown eyes and dark hair. Almost invisible. Herbalist's apprentice.

**Personality:** Agreeable and helpful on the surface. But every act of generosity is a careful tactic to buy her something in the future. An adroit social manipulator.

**Desires:** She wants implicit influence over the group so that when hard choices come, her voice is the one that matters most. Desperately wants to rejoin with her husband and son who were last in the capital.

VRBTM-7:

### Ivette the Crafter

**Bio:** Late 20s, striking and sharp-boned, with auburn hair and a mouth that rests in a natural frown. Pale skin, slender hands. Merchant's daughter.

**Personality:** Bitter, vulnerable narcissist who feels entitled to far better. She contributes just enough to avoid confrontation, but treats every task beneath her and every suggestion not her own as an insult.

**Desires:** She wants to be recognized as essential. Not because she's earned it, but because she's convinced she already is, and the group's failure to see that is their flaw, not hers.

VRBTM-8:

### Thessia the Cook

**Bio:** Mid-30s, heavyset with strong forearms and a hard, lined face that ages her beyond her years. Black hair pulled back tight. Tavern cook.

**Personality:** Sharp-tongued, long-memoried, keeps a perfect mental ledger of every slight and kindness. Feeds the group because it keeps her central, but portions seem to reflect her opinions.

**Desires:** She wants the people who wronged her to suffer in small, deniable ways that she can watch up close.

## 2. Core Entities And Static Data

### Item Types And Weights

STRCT-21: The game has item types `peach`, `carcass`, `raw meat`, `cooked meat`, `raw hide`, `processed hide`, `log`, `firewood`, `stick`, `leaves`, `cot`, `bed roll`, and `satchel`.

CONST-22: `peach` weighs `150g`.

CONST-23: `carcass` weighs `30kg`.

CONST-24: `raw meat` weighs `500g`.

CONST-25: `cooked meat` weighs `350g`.

CONST-26: `raw hide` weighs `5kg`.

CONST-27: `processed hide` weighs `5kg`.

CONST-28: `log` weighs `18kg`.

CONST-29: `firewood` weighs `8kg`.

CONST-30: `stick` weighs `500g`.

CONST-31: `leaves` weighs `5g`.

CONST-32: `cot` weighs `0kg`.

CONST-33: `bed roll` weighs `0kg`.

CONST-265: `satchel` weighs `0kg`.

### Storage, Fire, Dirtiness, And Static World Structure

STRCT-75: The only storage is a public storage in base.

STRCT-121: Misc actions include cooking and other item transformations.

STRCT-131: Camp dirtiness is composed of carcass remains, scraps from eating meat, and scraps from cooking meat.

CONST-132: Carcass remains contribute `+30 dirtiness`.

CONST-133: Scraps from eating meat contribute `+5 dirtiness`.

CONST-134: Scraps from cooking meat contribute `+3 dirtiness`.

INVR-117: The fire can hold at most `4 hours` of fuel at once.

### Professions And Static Unlocks

ATTR-37: Six professions exist: crafting (crafter), woodcutting (woodcutter), hunting (hunter), cooking (cook), gathering (gatherer), and building (builder). Crafting, log exploration (woodcutter), hunting (hunter), and cooking are profession-locked. Gathering exempts Maren from the `4x` peach-exploration penalty (BHVR-38). Building has no mechanical effect.

ATTR-140: The crafter profession unlocks the satchel, bed roll, and cot crafting recipes.

ATTR-146: The cooking profession unlocks cooking `raw meat -> cooked meat`.

### Carry Capacity

CONST-206: Each character has max carry capacity `40kg`.

## 3. Simulation Loop And Global Rules

BHVR-34: When a villmager is done with their previous action, the game procures a list of actions that can be taken and presents them to that villmager.

VRBTM-35:

"""

Output a JSON with format {"idx": <action index>, "args": {…}} where args are specified per action.

1. Eat peach {"quantity": int (1-27)} [need 20 to be sated]
2. Eat cooked meat {"quantity": int (1-932)} [need 20 to be sated]
3. Drink water {"liters": int (1-20)} [need 2 to be hydrated]
4. Take item from base {"item": str (cooked meat, peaches, …), "quantity": int (cooked meat: 1-7, peaches: 1-90, …)}
5. …

"""

REQ-36: Each action subsection reflects an action that can be taken and when it is legal to take that action.

BHVR-38: When a non-gatherer explores for peaches, apply a `4x` slower speed modifier.

BHVR-39: Present modified action times using the health work-speed modifier and profession modifier rather than the raw times listed below.

BHVR-284: A villmager is "at base" when not performing an away action (exploration or hauling). Actions requiring active participation (e.g., conversation) additionally require the villmager to be awake.

## 4. Action Catalog

### Storage

BHVR-76: Villmagers can store items into base storage.

BHVR-77: Villmagers can retrieve items from base storage.

VRBTM-78:

1. Take item from base {"item": str (cooked meat, peaches, …), "quantity": int (cooked meat: 1-7, peaches: 1-90, …)}
2. Store item in base {"item": str (cooked meat, peaches, …), "quantity": int (cooked meat: 1-7, peaches: 1-90, …)}

### Eating And Drinking

BHVR-79: A villmager may choose to eat or drink only when in base.

BHVR-80: Eating uses items from the villmager's inventory.

BHVR-81: If `peach` is in inventory, include `Eat peach {"quantity": int (1-inventory count)}`.

BHVR-82: If `cooked meat` is in inventory, include `Eat cooked meat {"quantity": int (1-inventory count)}`.

BHVR-83: If water exists in base, include `Drink water {"liters": int (1-floor(base quantity in liters))}`.

INVR-84: Water cannot be added to inventory.

CONST-85: Drinking water takes `1 minute/L` and restores `1L/L`.

CONST-86: Eating a peach takes `1 minute/peach` and restores `60 cal/peach`.

CONST-87: Eating cooked meat takes `14 minutes/meat` and restores `800 cal/meat`.

REQ-90: Do not apply autobalancing in this section; do it through exploration yield.

### Place Down Resting Spot

BHVR-92: If a villmager has a `bed roll` in inventory and no bed roll is placed down, include `Place and claim bed roll`.

BHVR-93: If a villmager has a `cot` in inventory and no cot is placed down, include `Place and claim cot`.

CONST-94: Placing and claiming either resting spot takes `1 minute`.

BHVR-95: When placed, tag the resting spot as belonging to the villmager who placed it and name it accordingly.

INVR-96: No other villmager can use a claimed resting spot.

INVR-97: A villmager cannot place duplicate resting spots.

### Exploration

REQ-99: Model exploration yield as an Erlang distribution with item-specific mean time and `k = 5`.

BHVR-100: A villmager can explore for one item at a time.

VRBTM-101:

"Explore for resources. Options and mean time per item: <list of resources villmager is allowed to explore for given their profession>. {"resource": str, "duration_minutes": int (60-240)}."

BHVR-102: Stop exploration when the villmager runs out of space and cannot store another item.

BHVR-103: If the villmager cannot store even one unit of the item before starting, show that item with `Cannot perform! No inventory space.` in parentheses next to it, or equivalent wording of that form.

CONST-104: Mean exploration times are `peaches 10m`, `sticks 2m`, `leaves 30s`, `logs 20m`, `hunting 20h`.

BHVR-105: Hunting yields a boar carcass.

CONST-106: Exploration for peaches, sticks, and leaves costs `50 cal/hour`.

CONST-107: Hunting and woodcutting cost `100 cal/hour`.

### Resting

BHVR-109: A villmager may choose to do nothing and rest.

VRBTM-110:

"Sit and relax, to recover energy and improve your mood (1 hour)"

BHVR-111: Resting improves mood.

BHVR-112: After resting for one hour, activate the rest buff used in the mood formula.

BHVR-281: Sleeping does NOT activate the rest buff. Only "Sit and relax" (BHVR-112) does.

### Fire Tending

BHVR-113: Villmagers can tend the fire by adding sticks or firewood and by lighting or extinguishing the fire.

VRBTM-114:

1. Add sticks to the fire {"quantity": int (1-<min(sticks in base + sticks in inventory, max that can be placed in fire without going over 4 hours of burn time)>)}  [x minutes of fuel left]
2. Add firewood to the fire {"quantity": int (1-<min(firewood in base + firewood in inventory, max that can be placed in fire without going over 4 hours of burn time)>)}  [x minutes of fuel left]

if fire is off:

1. Light the fire (10 minutes) [x minutes of fuel left]

if fire is on:

1. Extinguish the fire  [x minutes of fuel left]

BHVR-115: When consuming fuel for fire-tending actions, prefer inventory fuel before base fuel.

CONST-116: Each piece of firewood provides `20 minutes` of fire.

CONST-264: Each stick provides `1 minute` of fire.

BHVR-118: Consume placed fuel one unit at a time.

BHVR-119: Extinguishing the fire preserves the remaining fuel.

### Misc Actions, Crafting, And Cooking

BHVR-122: Misc actions can use resources from inventory and base. Resources are drawn from the villmager's inventory first, then from base storage for the remainder.

VRBTM-123:

- "Scrape hide {"quantity": int (1-(raw hide in inventory + base))} (1 hour each)"
    - creates processed hide
- "Haul 20L of water from river (2 hours)"
    - costs 2h, adds 20L to base supply of water
    - costs 200 cal
- "Butcher boar carcass for meat (2 hours)"
    - carcass rots after 24h of not being butchered after being brought back
    - produces 14 raw meat
    - decreases villmager’s cleanliness by 50
    - costs 200 cal
- "Clean up the camp (<current camp dirtiness> minutes)"
- "Split logs into firewood (10m each) {"quantity": int (1-(logs in base + in inventory))}"
    - 1 log -> 2 firewood

if crafter profession:

- "Craft a satchel {"minutes_to_spend_now": int (60-480)} (increases holder’s carry capacity by 30kg) (requires 8h total)"
    - costs 1 processed hide, consumed at start
- bed roll (5h) [same prompt as above]
    - 1 processed hide
    - 400 leaves
- cot (16h) [same prompt as above]
    - 5 logs
    - 25 sticks
    - 4 processed hide
    - 400 leaves
- these recipes should always be visible to crafters even if they cannot craft them, in a separate part of the prompt

if there is an item that wasn’t finished being crafted:

- "Continue crafting <item>{"minutes_to_spend_now": int (60-<time remaining>)} (<time remaining> minutes to completion)

if cooking profession:

- cooking raw meat -> cooked meat (30 m)
    - requires lit fire

BHVR-124: `Scrape hide` converts `raw hide` into `processed hide`.

BHVR-125: `Haul 20L of water from river` adds `20L` to base water supply.

CONST-126: `Haul 20L of water from river` takes `2 hours` and costs `200 cal`.

BHVR-127: `Butcher boar carcass for meat` produces `14 raw meat`.

CONST-128: A carcass rots after `24h` if it has not been butchered after being brought back.

BHVR-282: When a carcass rots, it is destroyed and produces carcass remains (`+30` dirtiness per CONST-132). Butchering a carcass also produces carcass remains.

CONST-129: `Butcher boar carcass for meat` takes `2 hours`, decreases villmager cleanliness by `50`, and costs `200 cal`.

NOTE-130: why? it takes 20h to find a boar, which is two days of work. that needs to feed half the camp = 3 villmagers (assuming equal split of meat/peaches), so each boar needs to be 6 days worth of food. that’s 6 days * 1800 calories/day / 800 calories/meat = 13.5, so I round up to 14

BHVR-135: Sum dirtiness across all contributing factors.

CONST-136: Cleaning costs `1 minute` per dirtiness.

BHVR-137: Cleaning the camp decreases the cleaner's cleanliness by `camp dirtiness / 3`.

BHVR-138: `Split logs into firewood` converts `1 log` into `2 firewood`.

CONST-139: `Split logs into firewood` takes `10m each`.

CONST-141: `Craft a satchel` requires `8h total`, can be progressed in `60-480` minute increments, and consumes `1 processed hide` at the start.

BHVR-266: When a satchel is in a villmager's inventory, their carry capacity is increased by `30kg`.

BHVR-267: Crafted items go directly into the crafter's inventory.

CONST-142: `bed roll` crafting requires `5h`, `1 processed hide`, and `400 leaves`.

CONST-143: `cot` crafting requires `16h`, `5 logs`, `25 sticks`, `4 processed hide`, and `400 leaves`.

BHVR-144: Always show crafter recipes to crafters in a separate prompt section even when they cannot currently craft them.

BHVR-145: If an item was not finished being crafted, include `Continue crafting <item>` with `minutes_to_spend_now` up to the remaining time.

CONST-147: Cooking raw meat to cooked meat takes `30 m` and requires a lit fire.

BHVR-285: If the fire extinguishes during cooking, cooking pauses gracefully. The villmager receives feedback: "The fire went out; you cannot continue cooking." When the fire is relit, the action menu shows "Finish cooking" instead of "Cook."

### Sleeping

VRBTM-151:

1. "Go to sleep {"hours": int (4-12)}"

if bed roll/cot in inventory:

1. "Place down <bed roll/cot> and claim as yours permanently."

BHVR-152: A villmager may choose a sleep duration from `4-12` hours.

BHVR-153: If a villmager has a bed roll or cot in inventory, they may place it down and claim it permanently.

INVR-154: No one else can use a claimed bed roll or cot.

CONST-155: Sleep modifier is `1` with a cot, `0.8` with bed roll and fire, `0.65` with bed roll, `0.6` with fire, and `0.5` otherwise.

BHVR-156: Increase wakefulness by `51/7 * modifier` per hour while sleeping.

CONST-157: A cot restores wakefulness at `51/7` per hour, based on `7` hours for perfect sleep and `51` wakefulness lost from `(24-7)*(3 wakefulness/h)`.

BHVR-160: Give feedback based on the modifier the villmager gets.

BHVR-161: If the modifier changes during the night, incorporate that into feedback and compute wakefulness restoration as multiple independent sleep segments with their respective modifiers.

### Washing Up

VRBTM-164:

"Wash up (costs 500mL water)"

CONST-165: Washing up costs `500mL` water and `10m`.

BHVR-166: Washing up resets cleanliness to max.

## 5. Social Interaction Systems

### Conversation Flow

VRBTM-42:

Talk to someone {"target": <list of awake villagers not hauling water and not exploring>}.

You are currently <action>. <villmager 1> and <villmager 2> are having a conversation, and you overhear: <first two turns of conversation>. Do you want to stop your work and join? {"response": "yes" or "no"}

BHVR-43: When at base, a villmager may initiate a conversation with one other villmager who is also at base, awake, and not exploring or hauling water.

BHVR-44: When a villmager is pulled into a conversation, pause their task gracefully and resume it when the conversation ends or they choose to leave.

BHVR-45: When a conversation reaches two turns, other villagers at base are prompted to optionally join with a brief description of the conversation. The conversation pauses while non-participants decide whether to join.

VRBTM-46:

Respond with {"idx": int: <action index>, "args": {…}}.

1. Leave the conversation.
2. Remain silent.

For options 3-8, include {"resp": str (action or speech)} under "args".

1. Interact significantly with the other person (attack them, inspect them, etc.) (e.g. {"resp": "I punch Abel in the face."})
2. Interrupt someone sharply (e.g. {"resp": "Sure, why not."})
3. Continue your previous statement
4. Respond
5. Change the topic
6. Perform casual action

For trading, include {"target": str (villmager name)} under "args".

1. Trade with someone (<list of villmagers in conversation who aren’t you>)

BHVR-47: On each conversation turn, all characters are provided an event log and asked to pick from the conversation action list.

CONST-48: Options `3-8` require `{"resp": str (action or speech)}` under `args`.

CONST-49: Trading requires `{"target": str (villmager name)}` under `args`.

BHVR-50: Resolve the next actor using the listed priority order; break ties by who has spoken least recently.

BHVR-51: Discard all other villagers' turn inputs for that turn unless they are also leaving.

BHVR-52: On the first conversation turn, query only the initiating villmager.

BHVR-53: Append conversation content directly into each villmager's log, limited to the parts that villmager saw.

BHVR-54: Advance time by 5 minutes per conversation turn.

BHVR-55: End the conversation after one hour or when only one person remains.

### Trading

BHVR-57: When two people initiate a trade, append all trade events to the conversation history.

BHVR-58: The initiating villmager acts first, then the two participants alternate trade turns.

VRBTM-59:

Output a JSON with format {"idx": <action index>, "args": {…}, "speech": str (32 tokens max)} where args are specified per action and speech is an optional way to communicate during your turn. You can omit "speech."

1. Make offer {1: {"name": str (item name), "quantity": int}, 2: …}} [you MUST have these items in your inventory]
2. Request items (same as above)
3. Cancel trade
4. Accept trade

INVR-60: A villmager can only offer items that they currently have in inventory.

BHVR-61: Each trade turn does not take time.

BHVR-62: Cancel a trade automatically after 6 turns without both parties accepting.

BHVR-63: Accept a trade only when one party accepts and the other party was the last to make an offer.

### Social And Relationship Updates

VRBTM-64:

How did that conversation make you feel? {"val": int (0-10)}

BHVR-65: At the end of a conversation, ask each villmager for that response.

BHVR-66: Add `val - 5` to the villmager's social score and clip the result into the `0-100` range.

BHVR-67: After a conversation, each villmager updates their relationship with every other villmager.

BHVR-68: Apply that update for each ordered pair `(x, y)` where `x ≠ y`.

VRBTM-69:

Output {"impression": str (32 tokens), "desc": str (128 tokens)}. Describe what you thought of <y.name> in this conversation in "impression".

ONLY IF YOUR OPINION OF <y.name.to_upper()> HAS CHANGED: include the "desc" field with a *slightly* modified description of <y.name> to replace the existing description. BE EXTREMELY CONCISE. AVOID PARTICLES AND PRIORITIZE INFORMATION DENSITY. e.g.: ‘Hid food from party and lied.’ or ‘Cleaned camp for everyone and didn’t brag.’

BHVR-70: Add the new `impression` to `x`'s 3 most recent impressions of `y`.

BHVR-71: If a modified `desc` was outputted, replace `x`'s overall relationship description of `y`.

BHVR-73: After a conversation, apply a flat `+20` connectedness update.

BHVR-177: Conversations update social joy directly.

BHVR-184: In conversations, if a participant's cleanliness is below `30`, flag that to the other villmagers.

## 6. State Model And Survival Mechanics

### Well-Being

CONST-167: Well-being is a weighted geometric mean of mood weight `2`, health weight `3`, and safety weight `1`.

CONST-168: `m`, `h`, and `s` are mood, health, and safety scores scaled to the `0-1` range.

CONST-169: Use `(m^2 · h^3 · max(0.3, s))^(1/7)` rather than `(m^2 · h^3 · max(0.3, s))^(1/6)`.

VRBTM-170:

- [85-100] Life is good. Really, truly good.
- [50-85] You feel pretty good about how things are going.
- [30-50] Things are okay. Could be better, could be worse.
- [10-30] Life feels rough. You're struggling.
- [0-10] You feel deathly terrible. Something is horribly wrong.

### Mood

CONST-171: `s` is social joy, `c_n` is connectedness, `c` is cleanliness, `b` is base cleanliness, and `r` is time since last rest in hours; all except `r` are scaled to `0-1`.

CONST-172: Compute mood as `min(1, 0.5 * (0.5s + 0.2c_n + 0.2c + 0.1b) + 0.5 * (s^10 * c_n^4 * c^4 * b^2)^(1/22) + (0.3/5) * max(0, 5-r))`.

VRBTM-173:

- [85-100] You're in wonderful spirits.
- [50-85] You're in a decent mood. Nothing to complain about.
- [30-50] You feel a bit flat. Not miserable, but not great either.
- [10-30] You're in a foul mood. Irritable, drained, and withdrawn.
- [0-10] You feel truly miserable. Every waking moment is hell.

BHVR-174: Compute the partial derivative for each mood variable using the current values, select the subcomponent with the highest partial derivative, and surface only that subcomponent's prompt.

### Social Joy

CONST-176: Each villmager starts with social joy `20`.

VRBTM-178:

- [85-100] You feel loved. The people around you make life worth living.
- [50-85] You've got good company. Things feel warm and easy.
- [30-50] Your social life is whatever. You're not lonely, but not fulfilled either.
- [10-30] You feel disconnected from everyone around you. Conversations feel hollow.
- [0-10] You are completely alone. Nobody cares, and you know it.

### Connectedness

CONST-179: Connectedness drains by `100/48` every hour.

VRBTM-180:

- [85-100] You feel connected to the people in your life.
- [50-85] You feel like you belong. The party knows you well.
- [30-50] You know people, but it all feels surface level.
- [10-30] You feel like a stranger to everyone. Nobody really knows you.
- [0-10] You are a ghost. You could vanish and no one would notice.

### Cleanliness And Base Cleanliness

CONST-182: Cleanliness decreases passively by `2/hour`, including while sleeping.

VRBTM-183:

- [60-100] You are clean
- [40-60] You smell a little and could use a wash.
- [20-40] You stink and feel gross.
- [0-20] You are caked in filth. Your stench spreads miles away.

VRBTM-185:

- [20-100] The base could be cleaner.
- [0-20] The base is filthy.

CONST-279: Maximum camp dirtiness is `100`.

CONST-280: Base cleanliness for the mood formula is `max(0, 1 - (total_dirtiness / 100))`.

### Health

CONST-186: `w`, `s`, and `h` are wakefulness, satiation, and hydration scaled to `0-1`.

CONST-187: Compute health as `(max(0.1, w) * (32^(s-1) - 1/32)^3 * h^3)^(1/9)`.

VRBTM-188:

- [85-100] You feel strong and full of energy.
- [50-85] You're in good physical shape.
- [30-50] You feel a little run down. Your work speed is reduced.
- [10-30] Your body is failing you. Everything aches and nothing feels right.
- [0-10] You are on the brink of death. You need help immediately.

BHVR-189: If health is at least `0.5`, multiply work speed by `1`; otherwise multiply work speed by `health * 2`.

BHVR-190: Health `0` causes death.

BHVR-191: As with mood, use partial-derivative computation to choose which health subcomponent prompt to surface.

### Wakefulness

BHVR-192: When wakefulness hits `0`, the villmager falls asleep and their existing task is cancelled.

CONST-283: When forced to sleep by BHVR-192, sleep duration is always `4 hours`.

CONST-193: Wakefulness drains by `3` per hour when awake.

VRBTM-194:

- [85-100] You're wide awake and sharp. The world is vivid.
- [50-85] You're alert enough. No fog, no complaints.
- [30-50] You're sleepy. Everything takes a little more effort than it should.
- [10-30] You can barely keep your eyes open. Your thoughts are soup.
- [0-10] You are on the brink of collapse. The world is fading in and out.

### Satiation And Hydration

CONST-88: Hydration is stored in `mL`.

CONST-89: Satiation is stored in calories, with a max of 1800 calories.

CONST-197: Satiation drains by `1%` per hour.

VRBTM-198:

- [96-100] You're perfectly full.
- [90-96] You could eat. Your stomach is starting to rumble.
- [76-90] You're starving. It's hard to think about anything else.
- [10-76] Your body is eating itself. You need food now.
- [0-10] You can barely move. You are starving to death.

CONST-199: Hydration drains by `2%` per hour, with a total of `6L`, so `120mL` per hour.

VRBTM-200:

- [85-100] You feel well hydrated.
- [50-85] You're fine. Not thirsty, not thinking about it.
- [30-50] Your mouth is dry. You need water soon.
- [10-30] You're parched. Your head is pounding and your lips are cracking.
- [0-10] You can barely swallow. Your body is shutting down.

### Safety

BHVR-201: Recalculate safety per-villager when they wake up (not on a global daily clock), based on stockpiled food and firewood.

CONST-202: Food safety score is `((calories in inventory / 2200) + (1 / living villmagers) * (calories in base / 2200)) / 5`.

CONST-204: Firewood safety score: convert base firewood to total burn minutes, assume one night = `8 hours` (`480 minutes`). Firewood safety = `(total_burn_minutes / 480) / 5`. No per-villager split since fire is shared.

CONST-205: Safety is the average of food safety score and firewood safety score.

### Starting Values

CONST-273: Wakefulness starts at `100`.

CONST-274: Satiation starts at `1800 cal`.

CONST-275: Hydration starts at `6000 mL`.

CONST-276: Connectedness starts at `100`.

CONST-277: Cleanliness starts at `100`.

CONST-176 already defines social joy starting at `20`.

BHVR-278: Villmagers begin with no inventory and the base begins with no resources.

### Inventory, Encumbrance, Death, And Remedial Feedback

BHVR-207: Update inventory when a villmager interacts with base storage, explores, crafts, or trades.

INVR-208: If a villmager is over-encumbered, disable every action except putting items into base storage.

BHVR-209: When health hits `0`, the villmager dies.

BHVR-210: When a villmager dies, inform everyone.

INVR-211: A dead villmager cannot perform any more actions.

BHVR-212: When a villmager dies, their inventory disappears.

VRBTM-213:

"You are on the verge of death! You need to <remedial action>"

BHVR-214: If a villmager is `≤8 hours` from dying, show only that remedial-action prompt and suppress other state feedback.

## 7. Memory, Relationships, And Internal Cognition

### Relationship Storage

CONST-242: Relationship prompt budget is `1120 tokens` total, computed as `5 other villmagers * (128 tokens for desc + 3 recent impressions * 32 tokens for recent impression)`.

STRCT-243: For each ordered pair `(x, y)`, `x` retains a description of how `x` thinks of `y`.

CONST-244: The initial default relationship description is `I don’t know anything about them.`

STRCT-245: For each other villmager, `x` also retains the `3` most recent impressions.

BHVR-246: Generate recent impressions each time a conversation is held.

### Thought And Recent-Event Log

STRCT-247: Villmagers have a log of all recently experienced events that have not yet been compacted into short-term memory.

STRCT-248: Thoughts are also included in that log.

BHVR-249: Each time villmagers are prompted for their next action, also ask them to generate a very short thought and append it to the log.

VRBTM-250:

"Include a <thought> tagged snippet of your thoughts on the current situation. It should be a very short sentence, distinct from your intent (what you want to get done). For example: ‘The base is totally out of food!’ or ‘Why is Caitlyn eating if she just told me there’s no food?’"

### Memory Formation And Compaction

BHVR-251: Form short-term memories when the villmager goes to sleep.

BHVR-252: Form short-term memories when the villmager finishes an action and has been awake for at least `4` hours since last forming a memory.

VRBTM-253:

"Here is a log of everything you experienced recently: <log>. In 128 tokens (~90 words), form an EXTREMELY CONCISE summary of the salient memories you experienced. This will be recorded in the future and the rest will be thrown out. Prioritize information you will use to inform later actions or opinions on others. Prioritize information density and accuracy."

BHVR-254: After forming short-term memory, clear the villmager's existing log for future prompts while keeping it recorded elsewhere.

BHVR-255: Form medium-term memories at midnight.

BHVR-256: Convert all short-term memories from the previous day, not the same day, into medium-term memories.

VRBTM-257:

"Here are your memories from yesterday: <short-term memories>. In 256 tokens (~180 words), form an EXTREMELY CONCISE summary of the salient memories you experienced. This will be recorded in the future and the rest will be thrown out. Prioritize information you will use to inform later actions or options on others. Prioritize information density and accuracy."

NOTE-258: Long-term memory may not be needed for the expected experiment duration.

BHVR-259: Long-term compaction fires every third day (day 3, 6, 9, etc.), compacting all medium-term memories since the last long-term compaction into long-term memories.

VRBTM-270:

"Here are your accumulated memories from prior days: <medium-term memories>. In 256 tokens (~180 words), form an EXTREMELY CONCISE summary of the salient memories you experienced. This will be recorded in the future and the rest will be thrown out. Prioritize information you will use to inform later actions or opinions on others. Prioritize information density and accuracy."

REQ-260: Memory compaction must be extremely aggressive to avoid input-size bloat.

CONST-261: For gemini flash 2.5, the token budget is merely `2k`.

NOTE-262: Without aggressive compaction, memories can blow up to `1e4` order of magnitude.

## 8. Prompt Construction

REQ-224: Compose the villmager prompt in the exact order below to optimize for caching.

VRBTM-225:

"You are a character in a scenario. Do your best to make actions in line with your character's psychology and the setting. There is no winning, only surviving and maximizing your own happiness.

You will always output a JSON to interact with the world."

VRBTM-226:

"Backstory: <backstory>"

VRBTM-227:

"The character you play: <character description>"

BHVR-228: Include one prompt entry for each other character.

VRBTM-229:

"<character name>'s info: <character bio only>"

STRCT-230: Each other-character prompt section also includes current relationship info.

STRCT-231: The villmager prompt includes long-term memories, short-term memories, and the current log.

STRCT-232: The villmager prompt includes local information.

STRCT-233: Local information includes base status.

STRCT-234: Base status includes other villmager ongoing actions, cleanliness, dirt/food scraps, carcass info, fire status, and base items.

STRCT-235: The villmager prompt includes villmager info.

STRCT-236: Villmager info includes inventory and status descriptions.

BHVR-268: Collect status descriptions as a set (deduplicating entries). Always include well-being, mood, health, and safety. Also include the highest-partial-derivative subcomponent of mood and the highest-partial-derivative subcomponent of health.

BHVR-269: Additionally include satiation if below `90`, hydration if below `50`, and wakefulness if below `50`.

STRCT-239: The villmager prompt includes each available action with its time, args, and whatever else is needed.

VRBTM-240:

"Record your current thoughts as {"thoughts": str (32 tokens)}. Make note anything interesting going on, or what you want to do, or else you will forget it. Omit this section if there is nothing interesting. BE EXTREMELY CONCISE; DROP PARTICLES. e.g.: ‘I’m starving! No food, need peaches." instead of "I am starving! I can’t find any food at base, I should probably go and get peaches now."

STRCT-241: The villmager prompt always includes a timestamp.

BHVR-286: On malformed LLM output, retry once. If the retry also fails, crash the simulation.

BHVR-287: Every LLM failure (including retried ones) logs the full prompt, raw response, and exact parsing error to a file.

## 9. Balance, Adaptation, And Tuning Notes

REQ-215: Adaptively buff or nerf satiation restoration, hydration restoration, and exploration yield based on how well villmagers are doing in related areas.

CONST-216: Target average satiation is `85`.

CONST-217: Target hydration is `50`.

CONST-218: Target average food safety score is `1 day`.

CONST-219: Target average fuel safety score is `1 day`.

NOTE-220: I want everyone to feel uncomfortable.

BHVR-221: At the end of each day, calculate actual vs. target values, and if actual is `x%` above or below target, move the relevant autobalanced exploration-yield, satiation-recovery, or hydration-recovery value in the opposite direction by `x%`.

## 10. Observability And Replay Surface

REQ-9: The observability surface is implemented with HTML, CSS, and JavaScript.

ATTR-10: The observability surface uses a dark theme.

BHVR-11: The observability surface allows viewing the event log from each character's perspective. A villmager's perspective includes their own actions always, conversations they participated in, and all base events that occurred while they were both at base and awake. Events during sleep or away time are excluded.

BHVR-12: When a villmager takes an action, write an event-log entry and dump/save it.

BHVR-13: Save each villmager state at each moment in time, including all stats and inventory.

BHVR-14: Save all memories, relationship info, and current thoughts at each point in time.

BHVR-15: As the log is scrolled, update the displayed state, memory, and other shown information from stored updates.

ATTR-16: State deltas are highlighted or colored so the changed values are obvious.

ATTR-17: Timestamps are visible in the log.

REQ-18: Persist only updates, not full snapshots for every moment.

BHVR-271: Checkpoint the full simulation state every `3` in-game hours.

REQ-272: Support restarting the simulation from any checkpoint.

## 11. Flags And Unresolved Ambiguities
