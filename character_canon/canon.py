# pyre-strict

"""Static authored canon data and read-only accessors."""

from character_canon.types import Profession, VillagerCanon, VillagerId, WorldBackstory


_VILLAGERS: tuple[VillagerCanon, ...] = (
    VillagerCanon(
        id=VillagerId("aldric"),
        name="Aldric the Woodsman",
        bio=(
            "Mid-30s, broad-shouldered, lean from years of outdoor labor, a "
            "massive frame. Sun-darkened skin, a thick brown beard, and "
            "calloused hands. Weathered woodsman."
        ),
        personality=(
            "Steady and warm-natured, the sort who hums while he works and "
            "offers encouragement without being asked. He genuinely likes "
            "being useful and draws a quiet satisfaction from seeing others "
            "fed, sheltered, and holding together."
        ),
        desires=(
            "He wants to keep this group alive. Because he couldn't do the "
            "same for the plague-afflicted family he left behind."
        ),
        profession=Profession.WOODCUTTER,
    ),
    VillagerCanon(
        id=VillagerId("sewalt"),
        name="Sewalt the Hunter",
        bio=(
            "Late 20s, wiry and sharp-featured, with pale eyes that never seem "
            "to settle on one spot for long. Dark hair kept short and "
            "practical. Experienced hunter."
        ),
        personality=(
            "Quiet and watchful, always scanning the tree line or listening "
            "for something the others can't hear. He means well but his "
            "constant unease is contagious, always voicing the worst outcomes. "
            "Grew up in the Capital's black market, retired to a village."
        ),
        desires="He wants to feel truly safe. And yet he never will.",
        profession=Profession.HUNTER,
    ),
    VillagerCanon(
        id=VillagerId("harren"),
        name="Harren the Builder",
        bio=(
            "Early 40s, stocky and thick-armed, with a square jaw and a "
            "permanent squint from years of working in sawdust and smoke. "
            "Cropped grey-streaked hair. Skilled carpenter."
        ),
        personality=(
            "Practical and blunt. Measures twice and speaks once, if ever. "
            "Helps the group because their survival is his survival, not out "
            "of care. Acutely aware of relationship transactionality."
        ),
        desires=(
            "Prioritizes his own safety and comfort above all else, and "
            "doesn’t care what others think. Needs to be in control of his "
            "own fate."
        ),
        profession=Profession.BUILDER,
    ),
    VillagerCanon(
        id=VillagerId("maren"),
        name="Maren the Gatherer",
        bio=(
            "Early 30s, plain-faced and unremarkable by design, with steady "
            "brown eyes and dark hair. Almost invisible. Herbalist's "
            "apprentice."
        ),
        personality=(
            "Agreeable and helpful on the surface. But every act of generosity "
            "is a careful tactic to buy her something in the future. An "
            "adroit social manipulator."
        ),
        desires=(
            "She wants implicit influence over the group so that when hard "
            "choices come, her voice is the one that matters most. Desperately "
            "wants to rejoin with her husband and son who were last in the "
            "capital."
        ),
        profession=Profession.GATHERER,
    ),
    VillagerCanon(
        id=VillagerId("ivette"),
        name="Ivette the Crafter",
        bio=(
            "Late 20s, striking and sharp-boned, with auburn hair and a mouth "
            "that rests in a natural frown. Pale skin, slender hands. "
            "Merchant's daughter."
        ),
        personality=(
            "Bitter, vulnerable narcissist who feels entitled to far better. "
            "She contributes just enough to avoid confrontation, but treats "
            "every task beneath her and every suggestion not her own as an "
            "insult."
        ),
        desires=(
            "She wants to be recognized as essential. Not because she's earned "
            "it, but because she's convinced she already is, and the group's "
            "failure to see that is their flaw, not hers."
        ),
        profession=Profession.CRAFTER,
    ),
    VillagerCanon(
        id=VillagerId("thessia"),
        name="Thessia the Cook",
        bio=(
            "Mid-30s, heavyset with strong forearms and a hard, lined face "
            "that ages her beyond her years. Black hair pulled back tight. "
            "Tavern cook."
        ),
        personality=(
            "Sharp-tongued, long-memoried, keeps a perfect mental ledger of "
            "every slight and kindness. Feeds the group because it keeps her "
            "central, but portions seem to reflect her opinions."
        ),
        desires=(
            "She wants the people who wronged her to suffer in small, "
            "deniable ways that she can watch up close."
        ),
        profession=Profession.COOK,
    ),
)

_BACKSTORY = WorldBackstory(
    text=(
        "A great pestilence has swept across the country. Carried by trade "
        "ships into the port cities, then up the rivers and along the roads "
        "the Grey Rot — known for the ashen pallor it gives the skin before "
        "the fever takes hold — has caused whole towns to go silent. The sick "
        "are burned where they fall.\n\n"
        "The Holy Church calls it divine retribution.\n\n"
        "The party formed while escaping from a village at the outskirts of "
        "the empire, having caught word from the capital. They made the "
        "practical choice to flee when they saw the first cases with their own "
        "eyes.\n\n"
        "As they traversed poorly maintained forest paths, an axle of their "
        "caravan snapped while crossing a rut. What supplies they had were "
        "already thin, and now they were immobilized.\n\n"
        "Stranded with nowhere safe to return, they decide to settle down in a "
        "crook of a river of the Stillwood forest, scattered peaches and boars "
        "promising meager sustenance. There’s not much option besides waiting "
        "out the plague.\n\n"
        "Unfortunately, it’s not clear which of them are infected."
    )
)


class CharacterCanon:
    """Read-only accessor for authored villager and world canon."""

    def __init__(self) -> None:
        """Build the villager lookup table from the authored records."""

        self._villagers_by_id: dict[VillagerId, VillagerCanon] = {
            villager.id: villager for villager in _VILLAGERS
        }

    def get_villager(self, villager_id: VillagerId) -> VillagerCanon:
        """Return the authored canon for one villager by stable id."""

        return self._villagers_by_id[villager_id]

    def get_all_villagers(self) -> tuple[VillagerCanon, ...]:
        """Return all authored villager records in authoring order."""

        return _VILLAGERS

    def get_backstory(self) -> WorldBackstory:
        """Return the shared world backstory prose."""

        return _BACKSTORY
