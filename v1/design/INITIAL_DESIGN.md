# Villmage v1

[game](Villmage%20v1/game%2034538e6b0e9980618359fd70560de691.md)

# story

## backstory

A great pestilence has swept across the country. Carried by trade ships into the port cities, then up the rivers and along the roads the **Grey Rot** — known for the ashen pallor it gives the skin before the fever takes hold — has caused whole towns to go silent. The sick are burned where they fall.

The Holy Church calls it divine retribution.

The party formed while escaping from a village at the outskirts of the empire, having caught word from the capital. They made the practical choice to flee when they saw the first cases with their own eyes.

As they traversed poorly maintained forest paths, an axle of their caravan snapped while crossing a rut. What supplies they had were already thin, and now they were immobilized.

Stranded with nowhere safe to return, they decide to settle down in a crook of a river of the Stillwood forest, scattered peaches and boars promising meager sustenance. There’s not much option besides waiting out the plague.

Unfortunately, it’s not clear which of them are infected.

## characters

### Aldric the Woodsman

**Bio:** Mid-30s, broad-shouldered, lean from years of outdoor labor, a massive frame. Sun-darkened skin, a thick brown beard, and calloused hands. Weathered woodsman.

**Personality:** Steady and warm-natured, the sort who hums while he works and offers encouragement without being asked. He genuinely likes being useful and draws a quiet satisfaction from seeing others fed, sheltered, and holding together.

**Desires:** He wants to keep this group alive. Because he couldn't do the same for the plague-afflicted family he left behind.

### Sewalt the Hunter

**Bio:** Late 20s, wiry and sharp-featured, with pale eyes that never seem to settle on one spot for long. Dark hair kept short and practical. Experienced hunter.

**Personality:** Quiet and watchful, always scanning the tree line or listening for something the others can't hear. He means well but his constant unease is contagious, always voicing the worst outcomes. Grew up in the Capital's black market, retired to a village.

**Desires:** He wants to feel truly safe. And yet he never will.

### Harren the Builder

**Bio:** Early 40s, stocky and thick-armed, with a square jaw and a permanent squint from years of working in sawdust and smoke. Cropped grey-streaked hair. Skilled carpenter.

**Personality:** Practical and blunt. Measures twice and speaks once, if ever. Helps the group because their survival is his survival, not out of care. Acutely aware of relationship transactionality.

**Desires:** Prioritizes his own safety and comfort above all else, and doesn’t care what others think. Needs to be in control of his own fate.

### Maren the Gatherer

**Bio:** Early 30s, plain-faced and unremarkable by design, with steady brown eyes and dark hair. Almost invisible. Herbalist's apprentice.

**Personality:** Agreeable and helpful on the surface. But every act of generosity is a careful tactic to buy her something in the future. An adroit social manipulator.

**Desires:** She wants implicit influence over the group so that when hard choices come, her voice is the one that matters most. Desperately wants to rejoin with her husband and son who were last in the capital.

### Ivette the Crafter

**Bio:** Late 20s, striking and sharp-boned, with auburn hair and a mouth that rests in a natural frown. Pale skin, slender hands. Merchant's daughter.

**Personality:** Bitter, vulnerable narcissist who feels entitled to far better. She contributes just enough to avoid confrontation, but treats every task beneath her and every suggestion not her own as an insult.

**Desires:** She wants to be recognized as essential. Not because she's earned it, but because she's convinced she already is, and the group's failure to see that is their flaw, not hers.

### Thessia the Cook

**Bio:** Mid-30s, heavyset with strong forearms and a hard, lined face that ages her beyond her years. Black hair pulled back tight. Tavern cook.

**Personality:** Sharp-tongued, long-memoried, keeps a perfect mental ledger of every slight and kindness. Feeds the group because it keeps her central, but portions seem to reflect her opinions.

**Desires:** She wants the people who wronged her to suffer in small, deniable ways that she can watch up close.

# observability

html + css + javascript, ***dark theme***, allows us to view event log from the perspective of each character

every action a villmager takes should write to event log, and this should be dumped & saved

their state at each moment in time should be saved (all stats, inventory)

all memories/relationship info at each point in time

current thoughts

you should be able to scroll through the log, and see *clearly* updates to state, memory, etc.

the delta should be highlighted or colored in some way to make it obvious what changed

should be able to see timestamps

only updates should be stored (hence why some code is needed) and they should update the info you see as you scroll

(maybe some kind of checkpointing for current state every few in game hours to balance between bugs causing drift in current state vs. size bloat of the actual log)

# list of all items

- peach
    - 150g
- carcass
    - 30kg
- raw meat
    - 500g
- cooked meat
    - 350g
- raw hide
    - 5kg
- processed hide
    - 5kg
- log
    - 18kg
- firewood
    - 8kg
- stick
    - 500g
- leaves
    - 5g
- cot
    - 0kg
- bed roll
    - 0kg

# game

# actions

## overview

each time a villmager is done with their previous action, the game will procure a list of actions that can be taken and present them to the villmager:

"""

Output a JSON with format {"idx": <action index>, "args": {…}} where args are specified per action.

1. Eat peach {"quantity": int (1-27)} [need 20 to be sated]
2. Eat pork chop {"quantity": int (1-932)} [need 20 to be sated]
3. Drink pouchful of water (500mL) {"quantity": int (1-20)} [need 2 to be hydrated]
4. Take item from base {"item": str (pork chop, peaches, …), "quantity": int (porkchop: 1-7, peaches: 1-90, …)}
5. …

"""

each subsection here reflects an action that can be taken and when it is legal to take that action

crafting, exploration (for logs specifically) and cooking are all locked by profession. when exploring for peaches or meat, you are 4 times slower at it if your profession doesn't match

the times listed for actions below are not modified. they should be modified and presented based on health work speed modifier + profession modifier

## conversation

### initiation

prompt: 

Talk to someone {"target": <list of awake villagers not hauling water and not exploring>}.

when at base, villmagers can choose to initiate a conversation with one other villmager also at base (that is awake, and also specifically not exploring/hauling water). the other villmager's task will be paused (gracefully) and resumed when the conversation is over (or when they choose to leave).

alternatively, villagers at base will be prompted to optionally join with a brief description of the conversation. this will happen when the conversation is two turns in.

prompt:

You are currently <action>. <villmager 1> and <villmager 2> are having a conversation, and you overhear: <first two turns of conversation>. Do you want to stop your work and join? {"response": "yes" or "no"}

### flow

each turn, all characters will be provided an event log asked to pick from a list of actions with the prompt (entire prompt is constructed exact same as for other actions, except instead of actions, this is given):

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

the next person to act will be chosen based off of this prioritization list. tiebreaks are done by who has spoken least recently. inputs from all other villmagers are thrown out for this turn (unless they are also leaving)

1. leaving
2. Interact significantly with the other person (attack them, inspect them, etc.)
3. Trade with someone
4. interrupting
5. continuing previous statement
6. responding
7. changing topic
8. performing casual action (adjusting posture, etc.)
9. remaining silent

on the first turn in particular, only the initiating villmager will go (others will not be queried)

conversations will be dumped directly into every villmager’s log (only the parts they see though)

every turn advances time by 5 minutes

the conversation ends after an hour, or when only one person is left.

### trading

if a trade is initiated between two people, all trade events will be appended to the conversation history. the initiating villmager will go first, and the two will go back and forth picking actions from the following list:

Output a JSON with format {"idx": <action index>, "args": {…}, "speech": str (32 tokens max)} where args are specified per action and speech is an optional way to communicate during your turn. You can omit "speech."

1. Make offer {1: {"name": str (item name), "quantity": int}, 2: …}} [you MUST have these items in your inventory]
2. Request items (same as above)
3. Cancel trade
4. Accept trade

each turn does not take time, and the trade is cancelled after 6 turns without both accepting.

trades are accepted when one party accepts, and the other party was the last to make an offer.

### social score update

at the end of the conversation, each villmager will be asked "How did that conversation make you feel? {"val": int (0-10)}". that number minus 5 will be added to their social score (clipped to remain in 0-100 range)

### relationship update

each villmager will be asked to update their relationship with each other villmager after a conversation

for each ordered pair of villmagers (x, y) where x ≠ y:

"Output {"impression": str (32 tokens), "desc": str (128 tokens)}. Describe what you thought of <y.name> in this conversation in "impression". 

ONLY IF YOUR OPINION OF <y.name.to_upper()> HAS CHANGED: include the "desc" field with a *slightly* modified description of <y.name> to replace the existing description. BE EXTREMELY CONCISE. AVOID PARTICLES AND PRIORITIZE INFORMATION DENSITY. e.g.: ‘Hid food from party and lied.’ or ‘Cleaned camp for everyone and didn’t brag.’ "

- add impression to x’s 5 most recent impressions of y
- if modified desc was outputted, replace x’s overall relationship description of y

### loneliness update

+20 per conversation, flat

## storing/retrieving items

self-explanatory, you can store and retrieve items, the only storage is a public storage in base

1. Take item from base {"item": str (pork chop, peaches, …), "quantity": int (porkchop: 1-7, peaches: 1-90, …)}
2. Store item in base {"item": str (pork chop, peaches, …), "quantity": int (porkchop: 1-7, peaches: 1-90, …)}

## eating/drinking

you can choose to eat or drink when in base, from your inventory.

if peach in inventory:

1. "Eat peach {"quantity": int (1-inventory count)}"

if cooked meat in inventory:

1. "Eat cooked meat {"quantity": int (1-inventory count)}"

if water in base:

1. "Drink water" {"liters": int (1-floor(base quantity in liters))}"

note: water cannot be added to inventory 

| item | time to eat | restores |
| --- | --- | --- |
| water | 1 minute/L | 1L/L (duh) |
| peach | 1 minute/peach | 60 cal/peach |
| cooked meat | 14 minutes/meat | 800 cal/meat |

thirst is stored in mL, hunger is stored in calories

NO AUTOBALANCING IN THIS SECTION. done through exploration yield

## place down resting spot

if bed roll in inventory and no bed roll placed down:

1. "Place and claim bed roll"

if cot in inventory and no cot placed down

1. "Place and claim cot"

takes 1 minute for each . once placed, tagged as belonging to the villmager who placed it (and named as such). nobody else can use it

cannot place duplicates

## exploration

yield will be modeled as erlang distribution with mean time set per item, and k = 5

villmagers can set out to look for one item at a time. prompt:

"Explore for resources. Options and mean time per item: <list of resources villmager is allowed to explore for given their profession>. {"resource": str, "duration_minutes": int (60-240)}."

exploration should stop if you run out of space (cannot store another item)

if you cannot store even one of the item before starting, the item should say something like "Cannot perform! No inventory space." in parentheses next to it

- peaches (10m)
- sticks (2m)
- leaves (30s)
- logs (20m)
- hunting (20h)
    - gets you a boar carcass

costs 50 cal/hour to explore for first three, 100 cal/hour for hunting and woodcutting

## resting

villmagers can choose to just do nothing and rest, improving their mood

prompt:

"Sit and relax, to recover energy and improve your mood (1 hour)"

after resting for an hour, the rest buff in the mood formula will be activated

## fire tending

need to add sticks (inefficient) or firewood to fire and light

prompt:

1. Add sticks to the fire {"quantity": int (1-<min(sticks in base + sticks in inventory, max that can be placed in fire without going over 4 hours of burn time)>)}  [x minutes of fuel left]
2. Add firewood to the fire {"quantity": int (1-<min(firewood in base + firewood in inventory, max that can be placed in fire without going over 4 hours of burn time)>)}  [x minutes of fuel left]

if fire is off:

1. Light the fire (10 minutes) [x minutes of fuel left]

if fire is on:

1. Extinguish the fire  [x minutes of fuel left]

actions prefers to use fuel in inventory first, then from base

each piece of firewood provides 20 minutes of fire. up to 4 hours of wood can be placed into the fire and they will be consumed one by one

turning fire off saves remaining fuel

## misc actions

includes cooking/all other "item transformations"

resources from inventory and base can be used

- "Scrape hide {"quantity": int (1-(raw hide in inventory + base))} (1 hour each)"
    - creates processed hide
- "Haul 20L of water from river (2 hours)"
    - costs 2h, adds 20L to base supply of water
    - costs 200 cal
- "Butcher boar carcass for meat (2 hours)"
    - carcass rots after 24h of not being butchered after being brought back
    - produces 14 raw meat
        - why? it takes 20h to find a boar, which is two days of work. that needs to feed half the camp = 3 villmagers (assuming equal split of meat/peaches), so each boar needs to be 6 days worth of food. that’s 6 days * 1800 calories/day / 800 calories/meat = 13.5, so I round up to 14
    - decreases villmager’s cleanliness by 50
    - costs 200 cal
- "Clean up the camp (<number of hours> minutes)"
    - we maintain list of things that are making the camp dirty increase over time and have to be cleaned
        - carcass remains
            - + 30 dirtiness
        - scraps from eating meat
            - + 5 dirtiness
        - scraps from cooking meat
            - + 3 dirtiness
    - dirtiness is summed across all contributing factors
    - costs 1 minute to clean per dirtiness
    - decreases your cleanliness by camp dirtiness/3
- "Split logs into firewood (10m each) {"quantity": int (1-(logs in base + in inventory))}"
    - 1 log -> 2 firewood

if crafter profession:

- "Craft a satchel {"minutes_to_spend_now": int (60-480)} (increases someone’s carry capacity by 30kg) (requires 8h total)"
    - costs 1 processed hide, consumed at start
- bedroll (5h) [same prompt as above]
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

## sleeping

1. "Go to sleep {"hours": int (4-12)}"

if bed roll/cot in inventory:

1. "Place down <bed roll/cot> and claim as yours permanently."

no one else can use bed roll/cot if you have claimed it

if cot: 

modifier = 1

else if bed roll and fire:

modifier = 0.8

else if bed roll:

modifier = 0.65

else if fire:

modifier = 0.6

else:

modifier = 0.5

increase wakefulness by 51/7 * modifier per hour

if you have a cot, increase wakefulness by 51/7 per hour (7 hours for perfect sleep, and 51 wakefulness lost bc (24-7)*(3 wakefulness/h) = 51)

sleeping in bed roll reduces effects of cold when no fire. cot removes entirely. 

feedback will be given based on the modifier you get

if modifier changes in the middle of the night (fire going on/off), feedback should also incorporate this. in terms of how much wakefulness is restored, it will be calculated as if there were multiple independent sleeps with the respective modifiers

## washing up

"Wash up (costs 500mL water)"

costs 500mL, resets cleanliness to max, costs 10m

# state

## well-being

### well-being calculation

well-being = weighted geometric mean of:

- mood, 2
- health, 3
- safety, 1

let m := mood score, h := health score, s := safety score (all scaled to 0-1 range). to make the curve a little less punishing near the upper ends, we modify the formula from:

$(m^2 \cdot h^3 \cdot \max(0.3, s))^{1/6} \space\space \Rightarrow \space\space (m^2 \cdot h^3 \cdot \max(0.3, s))^{1/7}$

prompts fed to villmager in their state desc based on well-being:

- [85-100] Life is good. Really, truly good.
- [50-85] You feel pretty good about how things are going.
- [30-50] Things are okay. Could be better, could be worse.
- [10-30] Life feels rough. You're struggling.
- [0-10] You feel deathly terrible. Something is horribly wrong.

### mood

#### mood calculation

let s := social joy, c_n := loneliness, c := cleanliness, b := base cleanliness (all scaled to 0-1). let r := time since last rest in hours. then mood is calculated as

$$
\min(1, 0.5 \cdot (0.5s + 0.2c_n + 0.2c + 0.1b) \\

+ \space 0.5 \cdot (s^{10} \cdot c_n^4 \cdot c^4 \cdot b^2)^{1/22} \\

+ \space \frac{0.3}{5} \max(0, 5-r))
$$

mood prompts:

- [85-100] You're in wonderful spirits.
- [50-85] You're in a decent mood. Nothing to complain about.
- [30-50] You feel a bit flat. Not miserable, but not great either.
- [10-30] You're in a foul mood. Irritable, drained, and withdrawn.
- [0-10] You feel truly miserable. Every waking moment is hell.

partial derivative should be taken for each variable (given existing values for each valuable), and the subcomponent that has the highest partial derivative should be selected to provide a prompt regarding it. no other subcomponents will have a prompt generated for it at this time.

### social joy

initial starting value of 20 for each villmager

updated directly by conversations

prompts:

- [85-100] You feel loved. The people around you make life worth living.
- [50-85] You've got good company. Things feel warm and easy.
- [30-50] Your social life is whatever. You're not lonely, but not fulfilled either.
- [10-30] You feel disconnected from everyone around you. Conversations feel hollow.
- [0-10] You are completely alone. Nobody cares, and you know it.

### connectedness

drains by 100/48 every hour

prompt:

- [85-100] You feel connected to the people in your life.
- [50-85] You feel like you belong. The party knows you well.
- [30-50] You know people, but it all feels surface level.
- [10-30] You feel like a stranger to everyone. Nobody really knows you.
- [0-10] You are a ghost. You could vanish and no one would notice.

### cleanliness

decreases by 2/hour passively (even when sleeping)

**Prompts:**

- [60-100] You are clean
- [40-60] You smell a little and could use a wash.
- [20-40] You stink and feel gross.
- [0-20] You are caked in filth. Your stench spreads miles away.

**Effects:**

- In conversations when participant cleanliness < 30, flagged to other villmagers

### base cleanliness

prompts:

- [20-100] The base could be cleaner.
- [0-20] The base is filthy.

### health

#### health formula

w := wakefulness, s := satiation, h := hydration (all scaled to 0-1)

$$
\left(\max(0.1, w) \cdot \left(32^{s-1} - \frac{1}{32}\right)^3 \cdot h^3 \right)^{1/9}
$$

**Prompts:**

- [85-100] You feel strong and full of energy.
- [50-85] You're in good physical shape.
- [30-50] You feel a little run down. Your work speed is reduced.
- [10-30] Your body is failing you. Everything aches and nothing feels right.
- [0-10] You are on the brink of death. You need help immediately.

**Effect on other stats:**

- Below 50: work speed reduced (basically multiply work speed by 1 if health ≥ 0.5, otherwise multiply by health*2)
- Death at 0

do some partial derivative computation as with mood to figure out which subcomponent will have a prompt surfaced.

#### wakefulness

hitting zero causes you to fall asleep, cancelling your existing task

hitting half causes you to 2 * 6 = 3

I’M FUCKIN TWEAKIN IT BRO! I’M TWEAKIN IT OUT! IM OHH YEAHHH !!

drains by 3 per hour when awake

**Prompts:** 

- [85-100] You're wide awake and sharp. The world is vivid.
- [50-85] You're alert enough. No fog, no complaints.
- [30-50] You're sleepy. Everything takes a little more effort than it should.
- [10-30] You can barely keep your eyes open. Your thoughts are soup.
- [0-10] You are on the brink of collapse. The world is fading in and out.

### satiation

drains by 1 per hour

**Prompts:** 

- [96-100] You're perfectly full.
- [90-96] You could eat. Your stomach is starting to rumble.
- [76-90] You're starving. It's hard to think about anything else.
- [10-76] Your body is eating itself. You need food now.
- [0-10] You can barely move. You are starving to death.

#### hydration

drains by 2% per hour (total is 6L, so 120mL per hour)

- [85-100] You feel well hydrated.
- [50-85] You're fine. Not thirsty, not thinking about it.
- [30-50] Your mouth is dry. You need water soon.
- [10-30] You're parched. Your head is pounding and your lips are cracking.
- [0-10] You can barely swallow. Your body is shutting down.

### safety

calculated each day based on how much food and firewood they have stockpiled

food safety score is (how many days of calories you have on you + (1/remaining villmagers) * calories in base) divided by 5. calories per day is just assumed to be 2200

firewood safety score is same as above, but for amount of firewood needed only for the night, out of next 5 days

average the two safety scores together

## inventory

each character has a max carry capacity of 40kg

inventory is updated when the villmager interacts with base storage, exploring, crafting, or trading

if you ever become over-encumbered,  *every other action* besides putting items into base storage is disabled. 

# death

when health hits 0, the villmager dies. everyone will be informed, and the villmager obviously cannot perform any more actions. their inventory disappears as well.

if you are ≤8 hours from dying, prompted: "You are on the verge of death! You need to <remedial action>", you don’t get feedback about other state info

# autobalancing

satiation/hydration restored when eating and drinking, as well as yield during exploration, should all be adaptively buffed/nerfed based on how well the villmagers are doing in related areas

I want everyone to feel uncomfortable, so target average hunger should be 85 (which is still starving)

target hydration should be 50

target average food/fuel safety scores should be 1 day

maybe something really simple: at end of each day, autobalancing is calculated. all actual vs. target values are calculated, and if actual is x% above or below target, then the relevant autobalanced value for exploration or satiation recover or hydration recovery is moved in the opposite direction by x%

# implementation

## prompt

prompt will be composed in the exact order below to optimize for caching

### system prompt

"You are a character in a scenario. Do your best to make actions in line with your character's psychology and the setting. There is no winning, only surviving and maximizing your own happiness.

You will always output a JSON to interact with the world."

### backstory description

"Backstory: <backstory>"

### character description

"The character you play: <character description>"

### other characters

for each other character:

"<character name>'s info: <character bio only>"

- current relationship info

## memories

- long-term memories
- short-term memories
- log

## local information

- base status
    - other villmager ongoing actions
    - cleanliness
        - dirt/food scraps
        - carcass info
    - fire status
    - base items

## villmager info

- all status descriptions
    - needs to be expanded after status stuff is set in stone
- inventory

## all actions/descs

- each available actions + time + args + whatever else

## thoughts

"Record your current thoughts as {"thoughts": str (32 tokens)}. Make note anything interesting going on, or what you want to do, or else you will forget it. Omit this section if there is nothing interesting. BE EXTREMELY CONCISE; DROP PARTICLES. e.g.: ‘I’m starving! No food, need peaches." instead of "I am starving! I can’t find any food at base, I should probably go and get peaches now."

## timestamp

duh. always included

## relationships

5 other villmagers * (128 tokens for desc + 3 recent impressions * 32 tokens for recent impression) = 1120 tokens total for relationships, per prompt

each villmager x will retain the following for every other villmager y:

- a description of how x thinks of y
    - initial default: "I don’t know anything about them."
- the 3 most recent impressions they’ve had of the other villmagers
    - these are generated each time a conversation is held

## memory

## log

villmagers will have a log of *all* events they experienced recently, that have not yet been compacted into short-term memory

### thoughts

thoughts are also included in this log. each time villmagers are prompted to get their next action, they will also be told to generate a *very* short "thought" to simply append to the log

"Include a <thought> tagged snippet of your thoughts on the current situation. It should be a very short sentence, distinct from your intent (what you want to get done). For example: ‘The base is totally out of food!’ or ‘Why is Caitlyn eating if she just told me there’s no food?’"

## short-term

short-term memories are formed when:

- the villmager goes to sleep, OR
- the villmager finishes an action AND they have been awake for at least four hours since last forming a memory

short-term memories are formed with the prompt:

"Here is a log of everything you experienced recently: <log>. In 128 tokens (~90 words), form an EXTREMELY CONCISE summary of the salient memories you experienced. This will be recorded in the future and the rest will be thrown out. Prioritize information you will use to inform later actions or opinions on others. Prioritize information density and accuracy."

the villmager’s existing log will then be cleared for future prompts (but obviously recorded elsewhere)

## medium-term

medium-term memories are formed at midnight. all short-term memories from the *previous* day (not the same day) are converted into a set of medium term memories.

"Here are your memories from yesterday: <short-term memories>. In 256 tokens (~180 words), form an EXTREMELY CONCISE summary of the salient memories you experienced. This will be recorded in the future and the rest will be thrown out. Prioritize information you will use to inform later actions or options on others. Prioritize information density and accuracy."

## long-term

I think the experiment will not run long enough to need to use this. but beyond three days, things should just be compacted even further. same prompt as above basically

compaction needs to be extremely aggressive to avoid bloating input size. In particular for gemini flash 2.5, our token budget is merely 2k. memories can easily blow up to 1e4 order of magnitude if we don’t do something smart