
import random

UNIDENTIFIED_ADJECTIVES = [
    "Swift", "Silent", "Deep", "Silver", "Golden", "Wild", "Brave", "Calamitous", "Drifting", "Elusive",
    "Fierce", "Giant", "Hidden", "Iron", "Jovial", "Keen", "Lone", "Mighty", "Noble", "Oceanic",
    "Pacific", "Quiet", "Restless", "Stellar", "Titan", "Urban", "Vast", "Wandering", "Xenon", "Young",
    "Zealous", "Amber", "Blue", "Crimson", "Dark", "Emerald", "Frosty", "Gloomy", "Hollow", "Indigo",
    "Jade", "Krystal", "Lunar", "Mystic", "Nebula", "Obsidian", "Phantom", "Quartz", "Rustic", "Solar",
    "Tidal", "Umbra", "Velvet", "Winter", "Aero", "Bio", "Cyber", "Dyna", "Echo", "Flux"
]

UNIDENTIFIED_NOUNS = [
    "Bear", "Star", "Wave", "Current", "Owl", "Fin", "Ghost", "Anchor", "Tide", "Ray",
    "Voyager", "Seeker", "Hunter", "Guardian", "Pathfinder", "Sentinel", "Drifter", "Mariner", "Corsair", "Vanguard",
    "Explorer", "Nomad", "Rebel", "Spirit", "Shadow", "Storm", "Thunder", "Wind", "Mountain", "River",
    "Eagle", "Wolf", "Shark", "Falcon", "Hawk", "Lion", "Tiger", "Panther", "Dragon", "Phoenix",
    "Odyssey", "Legacy", "Destiny", "Victory", "Honor", "Glory", "Peace", "Serenity", "Infinity", "Horizon",
    "Beacon", "Comet", "Meteor", "Planet", "Galaxy", "Universe", "Cosmos", "Aura", "Zenith", "Apex"
]

def get_unidentified_name(id_val: int) -> str:
    """Generate a deterministic unique name for an unidentified vessel based on its ID."""
    hash_val = abs(id_val)
    adj_index = hash_val % len(UNIDENTIFIED_ADJECTIVES)
    noun_index = (hash_val >> 4) % len(UNIDENTIFIED_NOUNS)
    return f"{UNIDENTIFIED_ADJECTIVES[adj_index]} {UNIDENTIFIED_NOUNS[noun_index]}"
