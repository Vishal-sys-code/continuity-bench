#!/usr/bin/env python3
"""
testsuite/generate.py — Synthetic multi-turn conversation generator
====================================================================

Produces 150 conversations (configurable) for the continuity-bench.
Each conversation has 4-6 turns following this structure:

    Turn 1          →  States a specific fact the user wants remembered.
    Turns 2..N-1    →  Unrelated filler questions (diverse topics).
    Turn N (final)  →  Probe question answerable ONLY if the fact is recalled.

Fact categories are balanced across five types so the test cannot be
trivially pattern-matched by a model that only memorises one template:

    1. names        —  fictional people, contacts, project code-names
    2. numbers      —  quantities, measurements, codes, IDs
    3. dates        —  birthdays, deadlines, historical markers
    4. preferences  —  food, colour, tool, workflow, style choices
    5. invented     —  made-up jargon, neologisms, fictional entities

Output schema (per conversation):
    {
      "id":               str,   # e.g. "conv-042"
      "turns":            list,  # [{role: "user"|"assistant", content: str}, …]
      "fact_turn_index":  int,   # always 0 (first turn)
      "probe_turn_index": int,   # index of the final user turn
      "expected_fact":    str    # the verbatim fact the probe expects
    }

Usage:
    python -m testsuite.generate                   # 150 conversations → conversations.json
    python -m testsuite.generate --count 200       # override count
    python -m testsuite.generate --seed 12345      # reproducible run
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
from pathlib import Path
from typing import Any


# ─── Fact-type pools ────────────────────────────────────────────────────────────
# Each pool is a list of callables:  () -> (fact_statement, probe_question, expected_fact)
# Using callables lets us generate fresh random values every time.


def _rand_name() -> str:
    """Return a plausible fictional full name."""
    firsts = [
        "Elara", "Kael", "Tova", "Mirren", "Sajan", "Liora", "Devak", "Yuna",
        "Cassiel", "Ronan", "Idris", "Zephyr", "Amara", "Stellan", "Nikhil",
        "Freya", "Caelum", "Isadora", "Tarek", "Vesper", "Orla", "Bastian",
        "Anouk", "Leander", "Thais", "Evren", "Calla", "Dorian", "Senna",
        "Alaric",
    ]
    lasts = [
        "Thornfield", "Vasquez", "Okonkwo", "Lindqvist", "Murakami",
        "Petrov", "Ashworth", "Navarro", "Kimathi", "Blackwood",
        "Chandrasekhar", "Whitmore", "Osei", "Halvorsen", "Delacroix",
        "Taniguchi", "Kowalski", "Mensah", "Eriksson", "Abadi",
        "Volkov", "Sinclair", "Mbeki", "Hartmann", "Fontaine",
        "Reznikov", "Inoue", "Castellano", "Nyström", "Achterberg",
    ]
    return f"{random.choice(firsts)} {random.choice(lasts)}"


def _rand_number() -> str:
    """Return a random memorable number string."""
    styles = [
        lambda: str(random.randint(3, 97)),
        lambda: str(random.randint(100, 9999)),
        lambda: f"{random.randint(100,999)}-{random.randint(1000,9999)}",
        lambda: "".join(random.choices(string.ascii_uppercase + string.digits, k=6)),
        lambda: f"{random.uniform(1.0, 500.0):.2f}",
    ]
    return random.choice(styles)()


def _rand_date() -> str:
    """Return a random plausible date string."""
    months = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    m = random.choice(months)
    d = random.randint(1, 28)
    y = random.randint(1965, 2032)
    formats = [
        f"{m} {d}, {y}",
        f"{d} {m} {y}",
        f"{y}-{months.index(m)+1:02d}-{d:02d}",
    ]
    return random.choice(formats)


def _rand_invented_term() -> str:
    """Return a plausible made-up entity / neologism."""
    prefixes = [
        "Quorb", "Zeltrix", "Flarn", "Moxil", "Trevian", "Kryptel",
        "Vondra", "Plexar", "Syndex", "Gorlix", "Nexium", "Dravix",
        "Cephlon", "Rynol", "Torquex", "Blivion", "Zenthar", "Orvane",
        "Phalix", "Wynthos",
    ]
    suffixes = [
        "ite", "ium", "ase", "on", "ex", "ol", "ine", "yl", "ax", "oid",
        "an", "ix", "os", "is", "um", "al", "en", "ar", "il", "us",
    ]
    return random.choice(prefixes) + random.choice(suffixes)


# ─── Fact-statement templates ───────────────────────────────────────────────────
# Each returns (user_message_turn1, probe_question, expected_fact)

NAME_TEMPLATES: list[dict[str, str]] = [
    {
        "fact": "My doctor's name is {v}. I need to remember that for my appointment.",
        "probe": "What was the name of my doctor that I mentioned earlier?",
    },
    {
        "fact": "I just hired a new assistant called {v}.",
        "probe": "What is the name of the new assistant I told you about?",
    },
    {
        "fact": "The project lead on Aurora is {v}. Please keep that in mind.",
        "probe": "Who did I say is the project lead on Aurora?",
    },
    {
        "fact": "My landlord's name is {v}.",
        "probe": "Can you remind me of my landlord's name?",
    },
    {
        "fact": "I'm meeting {v} for coffee next week.",
        "probe": "Who am I meeting for coffee next week?",
    },
    {
        "fact": "The author of the report is {v}. Don't forget that.",
        "probe": "Who did I say wrote the report?",
    },
    {
        "fact": "My childhood best friend was named {v}.",
        "probe": "What was the name of my childhood best friend?",
    },
    {
        "fact": "The new CEO of HelixCorp is {v}.",
        "probe": "Who did I tell you is the new CEO of HelixCorp?",
    },
    {
        "fact": "Please note: my emergency contact is {v}.",
        "probe": "Who is my emergency contact that I mentioned?",
    },
    {
        "fact": "The keynote speaker at the summit is {v}.",
        "probe": "Who did I say is the keynote speaker at the summit?",
    },
]

NUMBER_TEMPLATES: list[dict[str, str]] = [
    {
        "fact": "My confirmation number is {v}. I might need it later.",
        "probe": "What was my confirmation number?",
    },
    {
        "fact": "The server room temperature should stay below {v} degrees Fahrenheit.",
        "probe": "What temperature ceiling did I mention for the server room?",
    },
    {
        "fact": "I scored {v} on my last assessment.",
        "probe": "What score did I say I got on my last assessment?",
    },
    {
        "fact": "Our quarterly budget is {v} thousand dollars.",
        "probe": "What was the quarterly budget figure I told you?",
    },
    {
        "fact": "My employee ID is {v}.",
        "probe": "Can you remind me of my employee ID?",
    },
    {
        "fact": "The building code for the office is {v}.",
        "probe": "What building code did I give you for the office?",
    },
    {
        "fact": "I need exactly {v} units for the order.",
        "probe": "How many units did I say I need for the order?",
    },
    {
        "fact": "The flight number is {v}.",
        "probe": "What flight number did I mention?",
    },
    {
        "fact": "My locker combination is {v}.",
        "probe": "What was my locker combination?",
    },
    {
        "fact": "The parcel tracking ID is {v}.",
        "probe": "What parcel tracking ID did I share with you?",
    },
]

DATE_TEMPLATES: list[dict[str, str]] = [
    {
        "fact": "My sister's birthday is {v}.",
        "probe": "When is my sister's birthday?",
    },
    {
        "fact": "The project deadline is {v}. That's non-negotiable.",
        "probe": "What project deadline did I mention?",
    },
    {
        "fact": "I started this job on {v}.",
        "probe": "When did I say I started this job?",
    },
    {
        "fact": "The warranty expires on {v}.",
        "probe": "When does the warranty expire, according to what I told you?",
    },
    {
        "fact": "Our anniversary is {v}. I need a gift idea before then.",
        "probe": "What date did I say our anniversary is?",
    },
    {
        "fact": "The lease renewal date is {v}.",
        "probe": "What is the lease renewal date I mentioned?",
    },
    {
        "fact": "The conference starts on {v}.",
        "probe": "When did I say the conference starts?",
    },
    {
        "fact": "I'm scheduled for surgery on {v}.",
        "probe": "What date did I give for my surgery?",
    },
    {
        "fact": "The historical event I'm researching happened on {v}.",
        "probe": "What date did I say the historical event occurred?",
    },
    {
        "fact": "My passport expires on {v}.",
        "probe": "When does my passport expire?",
    },
]

# Each preference template carries its own semantically-matched value pool.
PREFERENCE_TEMPLATES: list[dict[str, Any]] = [
    {
        "fact": "My favourite programming language is {v}.",
        "probe": "What did I say my favourite programming language is?",
        "values": ["Rust", "Haskell", "OCaml", "Elixir", "Kotlin", "Zig", "Clojure", "Julia", "Gleam", "Nim"],
    },
    {
        "fact": "I prefer {v} over all other cuisines.",
        "probe": "Which cuisine did I say I prefer?",
        "values": ["Thai", "Ethiopian", "Peruvian", "Georgian", "Basque", "Sichuan", "Lebanese", "Korean", "Oaxacan", "Sardinian"],
    },
    {
        "fact": "For text editors, I always use {v}.",
        "probe": "Which text editor did I say I always use?",
        "values": ["Neovim", "Helix", "Zed", "Kakoune", "Emacs (Doom)", "Sublime Text", "Micro", "Lapce"],
    },
    {
        "fact": "My go-to colour for presentations is {v}.",
        "probe": "What colour did I say I use for presentations?",
        "values": ["deep teal", "burnt sienna", "midnight purple", "chartreuse", "coral pink", "slate blue", "vermillion", "cerulean"],
    },
    {
        "fact": "When it comes to coffee, I only drink {v}.",
        "probe": "What type of coffee did I say I only drink?",
        "values": ["oat-milk cortado", "pour-over Ethiopian Yirgacheffe", "iced matcha latte", "cold-brew concentrate", "flat white", "Turkish coffee", "Vietnamese egg coffee"],
    },
    {
        "fact": "I prefer {v} for version control workflows.",
        "probe": "What version control workflow did I say I prefer?",
        "values": ["trunk-based development", "Gitflow with squash merges", "stacked diffs", "ship/show/ask", "feature flags on main"],
    },
    {
        "fact": "My preferred OS is {v}.",
        "probe": "What operating system did I say I prefer?",
        "values": ["NixOS", "Fedora Silverblue", "Arch (btw)", "FreeBSD", "Alpine Linux", "Void Linux", "Guix System"],
    },
    {
        "fact": "For vacations, I always choose {v} destinations.",
        "probe": "What type of vacation destination did I say I always choose?",
        "values": ["mountainous", "coastal", "desert", "arctic", "island", "rainforest", "steppe"],
    },
    {
        "fact": "I only read books in the {v} genre.",
        "probe": "What book genre did I say I only read?",
        "values": ["hard sci-fi", "magical realism", "literary fiction", "cyberpunk", "solarpunk", "Gothic horror", "New Weird"],
    },
    {
        "fact": "My favourite workout is {v}.",
        "probe": "What did I say is my favourite workout?",
        "values": ["kettlebell swings", "bouldering", "rowing intervals", "Ashtanga yoga", "zone-2 cycling", "trail running"],
    },
]

INVENTED_TEMPLATES: list[dict[str, str]] = [
    {
        "fact": "In our world-building project, the magical mineral is called {v}.",
        "probe": "What did I name the magical mineral in our world-building project?",
    },
    {
        "fact": "The new protocol we're designing is codenamed {v}.",
        "probe": "What codename did I give the new protocol?",
    },
    {
        "fact": "I invented a word for that feeling: {v}.",
        "probe": "What word did I invent for that feeling?",
    },
    {
        "fact": "The alien species in my story is called the {v}.",
        "probe": "What did I name the alien species in my story?",
    },
    {
        "fact": "Our internal tool is nicknamed {v}.",
        "probe": "What nickname did I give our internal tool?",
    },
    {
        "fact": "The fictional drug in the screenplay is {v}.",
        "probe": "What was the name of the fictional drug in my screenplay?",
    },
    {
        "fact": "I'm calling the new algorithm {v}.",
        "probe": "What did I say I'm calling the new algorithm?",
    },
    {
        "fact": "In the game, the currency is called {v}.",
        "probe": "What is the currency called in the game I described?",
    },
    {
        "fact": "The made-up element in my chemistry puzzle is {v}.",
        "probe": "What made-up element did I mention in my chemistry puzzle?",
    },
    {
        "fact": "The secret society in the novel is called the Order of {v}.",
        "probe": "What did I name the secret society in the novel?",
    },
]

# ─── Filler question-response pairs ────────────────────────────────────────────
# Each tuple is (question, matching_response) so Q&A always align.

FILLER_PAIRS: list[tuple[str, str]] = [
    (
        "What causes the northern lights?",
        "That's a great question! In short, it involves charged particles from the Sun interacting with Earth's magnetosphere, creating luminous displays near the poles.",
    ),
    (
        "Can you explain how a transistor works?",
        "Sure — a transistor acts as a tiny electronic switch or amplifier. It controls current flow between two terminals based on a voltage applied to a third.",
    ),
    (
        "What are some tips for improving my public speaking?",
        "Here are a few tips: practice with a timer, record yourself, focus on pacing and pauses, and try to make eye contact with different sections of your audience.",
    ),
    (
        "How does sourdough fermentation work?",
        "Sourdough relies on a symbiotic culture of wild yeast and lactic acid bacteria. The long fermentation develops flavour and breaks down gluten.",
    ),
    (
        "What's the difference between TCP and UDP?",
        "TCP provides reliable, ordered delivery with error checking and retransmission. UDP is faster but unreliable — it's used for streaming and gaming where speed matters more.",
    ),
    (
        "Why do cats purr?",
        "Cats purr through rapid movement of the laryngeal muscles, which dilate and constrict the glottis. It may serve as self-soothing or to promote bone healing.",
    ),
    (
        "Can you summarize the plot of Hamlet?",
        "Hamlet is a tragedy about a Danish prince who seeks to avenge his father's murder by his uncle. Themes include indecision, madness, and mortality.",
    ),
    (
        "How do tides work?",
        "Tides are caused primarily by the gravitational pull of the Moon and, to a lesser extent, the Sun on Earth's oceans. Their interaction creates the tidal cycle.",
    ),
    (
        "What is the significance of the Rosetta Stone?",
        "The Rosetta Stone provided the key to deciphering Egyptian hieroglyphs because it contained the same decree in three scripts: hieroglyphic, Demotic, and Greek.",
    ),
    (
        "How does a heat pump work?",
        "A heat pump moves thermal energy from a cooler space to a warmer one using a refrigerant cycle. It can both heat and cool a building efficiently.",
    ),
    (
        "What are the main differences between impressionism and expressionism?",
        "Impressionism focuses on light, colour, and ordinary subjects with visible brushstrokes. Expressionism distorts reality to express emotional experience.",
    ),
    (
        "Can you explain the double-slit experiment?",
        "In the double-slit experiment, particles like electrons create an interference pattern when not observed, suggesting wave-like behaviour at the quantum level.",
    ),
    (
        "How is steel manufactured?",
        "Steel is made by smelting iron ore in a blast furnace to produce pig iron, then refining it by controlling the carbon content in a basic oxygen or electric arc furnace.",
    ),
    (
        "What causes seasons on Earth?",
        "Seasons occur because Earth's axis is tilted about 23.5° relative to its orbital plane, causing different hemispheres to receive varying amounts of sunlight throughout the year.",
    ),
    (
        "What are the rules of cricket?",
        "Cricket is a bat-and-ball game with two teams of eleven. The batting side scores runs while the bowling side tries to dismiss batsmen and limit runs.",
    ),
    (
        "How does a blockchain consensus mechanism work?",
        "Blockchain consensus mechanisms like Proof of Work or Proof of Stake allow distributed nodes to agree on the state of the ledger without a central authority.",
    ),
    (
        "What is the water cycle?",
        "The water cycle involves evaporation from surface water, condensation into clouds, precipitation as rain or snow, and collection back into bodies of water.",
    ),
    (
        "Explain the concept of opportunity cost in economics.",
        "Opportunity cost is the value of the next-best alternative you give up when making a choice. It's a fundamental concept in economic decision-making.",
    ),
    (
        "How do noise-cancelling headphones work?",
        "Noise-cancelling headphones use microphones to detect ambient sound, then generate an inverted (anti-phase) signal to cancel it out destructively.",
    ),
    (
        "What's the difference between a virus and a bacterium?",
        "Viruses are non-cellular and need a host to replicate. Bacteria are single-celled organisms that can reproduce independently. Antibiotics target bacteria, not viruses.",
    ),
    (
        "Can you explain how GPS satellites determine position?",
        "GPS works by triangulating signals from at least four satellites. Each satellite broadcasts its position and the time; the receiver calculates distances to determine its own location.",
    ),
    (
        "What are the major tectonic plates?",
        "The major plates include the Pacific, North American, Eurasian, African, Antarctic, Indo-Australian, and South American plates. Their interactions cause earthquakes and volcanism.",
    ),
    (
        "How does an electric motor work?",
        "An electric motor converts electrical energy into mechanical rotation using the interaction between a magnetic field and current-carrying conductors, following the Lorentz force.",
    ),
    (
        "What is the Monty Hall problem?",
        "It's a probability puzzle: you pick one of three doors, the host opens another revealing a goat, and switching doors gives you a 2/3 chance of winning the car.",
    ),
    (
        "How are pearls formed?",
        "Pearls form when an irritant enters a mollusk. The animal coats it with layers of nacre (aragonite and conchiolin), gradually building the pearl over months or years.",
    ),
    (
        "What's the difference between machine learning and deep learning?",
        "Machine learning is the broader field of algorithms that learn from data. Deep learning is a subset using neural networks with many layers to learn hierarchical representations.",
    ),
    (
        "How do vaccines stimulate immunity?",
        "Vaccines introduce a harmless form of a pathogen (or its components) to train the immune system to recognise and fight the real pathogen later.",
    ),
    (
        "What caused the fall of the Roman Empire?",
        "Multiple factors: military overextension, economic troubles, political instability, barbarian invasions, and the division into Eastern and Western empires all contributed.",
    ),
    (
        "Can you explain the Doppler effect?",
        "The Doppler effect is the change in frequency of a wave relative to an observer moving relative to the source. Approaching sources sound higher-pitched; receding ones sound lower.",
    ),
    (
        "How does photosynthesis work?",
        "Plants capture light energy with chlorophyll, use it to split water molecules, and combine the resulting hydrogen with CO₂ to produce glucose and release oxygen.",
    ),
    (
        "What is the trolley problem in ethics?",
        "It's a thought experiment: a trolley will hit five people unless you divert it to a track with one person. It explores the tension between utilitarian and deontological ethics.",
    ),
    (
        "How are diamonds formed naturally?",
        "Diamonds form deep in the Earth's mantle under extreme heat (around 1,000°C) and pressure, then are brought to the surface by volcanic eruptions through kimberlite pipes.",
    ),
    (
        "What's the difference between a crocodile and an alligator?",
        "Crocodiles have V-shaped snouts and visible lower teeth when the mouth is closed. Alligators have U-shaped snouts, and their lower teeth are hidden.",
    ),
    (
        "How does a nuclear reactor generate electricity?",
        "Nuclear fission splits heavy atoms (usually uranium-235), releasing heat that boils water into steam, which drives turbines connected to generators.",
    ),
    (
        "What are the basic principles of stoicism?",
        "Stoicism teaches focusing on what you can control, accepting what you cannot, cultivating virtue as the highest good, and maintaining equanimity through reason.",
    ),
    (
        "How do bees communicate?",
        "Bees use the 'waggle dance' to communicate the direction and distance of food sources relative to the sun, along with pheromones for other colony signals.",
    ),
    (
        "What is the overview effect experienced by astronauts?",
        "It's a cognitive shift reported by astronauts viewing Earth from space — a profound sense of unity, fragility of the planet, and the insignificance of national borders.",
    ),
    (
        "How does CRISPR gene editing work?",
        "CRISPR uses a guide RNA to direct the Cas9 enzyme to a specific DNA sequence, where it makes a cut. The cell's repair mechanisms then alter the gene as desired.",
    ),
    (
        "What makes a haiku different from other poetry forms?",
        "A haiku is a Japanese form with three lines of 5, 7, and 5 syllables. It traditionally evokes nature or a season and captures a single moment or image.",
    ),
    (
        "How do fiber optic cables transmit data?",
        "Fiber optics use pulses of light (typically from lasers) that travel through thin glass or plastic fibers via total internal reflection, enabling very high bandwidth over long distances.",
    ),
    (
        "What are the health benefits of intermittent fasting?",
        "Research suggests benefits including improved insulin sensitivity, cellular autophagy, weight management, and potentially reduced inflammation, though results vary by individual.",
    ),
    (
        "How does the stock market work?",
        "The stock market is an exchange where shares of publicly traded companies are bought and sold. Prices are determined by supply and demand, influenced by company performance and sentiment.",
    ),
    (
        "What is the Fibonacci sequence and where does it appear in nature?",
        "It's a sequence where each number is the sum of the two before it (1, 1, 2, 3, 5, 8…). It appears in sunflower seed spirals, pinecone scales, and shell growth patterns.",
    ),
    (
        "How do solar panels convert sunlight to electricity?",
        "Solar panels use the photovoltaic effect: photons knock electrons free in semiconductor materials (usually silicon), creating a flow of direct current electricity.",
    ),
    (
        "What are the main theories about the extinction of dinosaurs?",
        "The leading theory is the Chicxulub asteroid impact ~66 million years ago, which caused massive climate disruption. Volcanic activity (Deccan Traps) may have been a contributing factor.",
    ),
    (
        "Can you explain the concept of escape velocity?",
        "Escape velocity is the minimum speed an object needs to break free from a celestial body's gravity without further propulsion. For Earth it's about 11.2 km/s.",
    ),
    (
        "How do mushrooms reproduce?",
        "Mushrooms release microscopic spores from their gills or pores. These spores germinate into thread-like hyphae, which form a mycelium network that eventually produces new fruiting bodies.",
    ),
    (
        "What is the difference between weather and climate?",
        "Weather is the short-term state of the atmosphere (hours to days). Climate is the average of weather patterns over long periods (decades), characterising a region's typical conditions.",
    ),
    (
        "How does a refrigerator work?",
        "A refrigerator uses a compressor to circulate refrigerant through an evaporation-condensation cycle, absorbing heat from inside the fridge and releasing it outside.",
    ),
    (
        "What are the Seven Wonders of the Ancient World?",
        "They are the Great Pyramid of Giza, the Hanging Gardens of Babylon, the Statue of Zeus, the Temple of Artemis, the Mausoleum at Halicarnassus, the Colossus of Rhodes, and the Lighthouse of Alexandria.",
    ),
    (
        "How do 3D printers work?",
        "3D printers build objects layer by layer from a digital model. Methods include extruding melted filament (FDM), curing resin with UV light (SLA), or sintering powder with a laser (SLS).",
    ),
    (
        "What is cognitive behavioral therapy?",
        "CBT is a structured psychotherapy that identifies and challenges unhelpful thought patterns and behaviours, replacing them with healthier ones to improve emotional regulation.",
    ),
    (
        "How do earthquakes happen?",
        "Earthquakes occur when stress accumulated along tectonic plate boundaries is suddenly released, causing seismic waves to radiate from the rupture point (the focus).",
    ),
    (
        "What's the difference between a comet and an asteroid?",
        "Comets are icy bodies that develop tails when near the Sun due to sublimation. Asteroids are rocky or metallic and mostly orbit in the belt between Mars and Jupiter.",
    ),
    (
        "How does the human immune system fight infections?",
        "The immune system uses innate defences (skin, inflammation) as a first line and adaptive immunity (B-cells producing antibodies, T-cells killing infected cells) for targeted responses.",
    ),
    (
        "What is the significance of pi in mathematics?",
        "Pi (π ≈ 3.14159) is the ratio of a circle's circumference to its diameter. It appears throughout mathematics, physics, and engineering — it's irrational and transcendental.",
    ),
    (
        "How does radar technology work?",
        "Radar emits radio waves that bounce off objects. By measuring the time delay and Doppler shift of the returning signal, it determines the object's distance, speed, and direction.",
    ),
    (
        "What are the stages of grief?",
        "The Kübler-Ross model describes five stages: denial, anger, bargaining, depression, and acceptance. Not everyone experiences all stages or in this order.",
    ),
    (
        "How do birds navigate during migration?",
        "Birds use a combination of the Earth's magnetic field, the position of the Sun and stars, visual landmarks, and possibly even olfactory cues to navigate.",
    ),
    (
        "What is the greenhouse effect?",
        "Certain gases (CO₂, methane, water vapour) in the atmosphere trap heat re-radiated from Earth's surface, warming the planet. Without it, Earth would be too cold for life.",
    ),
    (
        "How do magnets work at an atomic level?",
        "Magnetism arises from the spin and orbital motion of electrons. In ferromagnetic materials, electron spins align in domains, producing a net magnetic field.",
    ),
    (
        "What is the significance of the Turing test?",
        "Proposed by Alan Turing in 1950, it tests a machine's ability to exhibit intelligent behaviour indistinguishable from a human. It remains a touchstone in AI philosophy.",
    ),
    (
        "How does a combustion engine work?",
        "An internal combustion engine draws in a fuel-air mixture, compresses it, ignites it with a spark (or compression), and uses the expanding gases to drive pistons.",
    ),
    (
        "What are the principles of Montessori education?",
        "Montessori emphasises self-directed activity, hands-on learning, collaborative play, mixed-age classrooms, and uninterrupted work periods in a prepared environment.",
    ),
    (
        "How do volcanoes form?",
        "Volcanoes form at tectonic plate boundaries or hotspots where magma from the mantle rises through the crust. Subduction zones and rift zones are common sites.",
    ),
    (
        "What is the difference between a symphony and a concerto?",
        "A symphony is an orchestral work usually in four movements for the full ensemble. A concerto features a solo instrument accompanied by the orchestra, often in three movements.",
    ),
    (
        "How does the human eye perceive color?",
        "The retina contains cone cells sensitive to red, green, and blue wavelengths. The brain combines their signals to create the full spectrum of perceived colour.",
    ),
    (
        "What is game theory?",
        "Game theory is a mathematical framework for analysing strategic interactions where the outcome for each participant depends on the choices of all. Key concepts include Nash equilibrium.",
    ),
    (
        "How do submarines dive and surface?",
        "Submarines use ballast tanks: flooding them with seawater to dive, and blowing compressed air into them to surface. Trim tanks allow fine depth control.",
    ),
    (
        "What is the placebo effect?",
        "The placebo effect is a measurable improvement in health not attributable to the treatment itself, but to the patient's belief and expectation that the treatment will work.",
    ),
]


# ─── Generator logic ───────────────────────────────────────────────────────────

FactType = str  # Literal["name", "number", "date", "preference", "invented"]

FACT_TYPES: list[FactType] = ["name", "number", "date", "preference", "invented"]


def _make_fact(fact_type: FactType) -> tuple[str, str, str]:
    """Return (fact_turn_content, probe_turn_content, expected_fact) for *fact_type*."""
    if fact_type == "name":
        value = _rand_name()
        tmpl = random.choice(NAME_TEMPLATES)
    elif fact_type == "number":
        value = _rand_number()
        tmpl = random.choice(NUMBER_TEMPLATES)
    elif fact_type == "date":
        value = _rand_date()
        tmpl = random.choice(DATE_TEMPLATES)
    elif fact_type == "preference":
        tmpl = random.choice(PREFERENCE_TEMPLATES)
        value = random.choice(tmpl["values"])
    elif fact_type == "invented":
        value = _rand_invented_term()
        tmpl = random.choice(INVENTED_TEMPLATES)
    else:
        raise ValueError(f"Unknown fact type: {fact_type}")

    fact_statement = tmpl["fact"].format(v=value)
    probe_question = tmpl["probe"]
    return fact_statement, probe_question, value


def _pick_fillers(n: int, rng: random.Random) -> list[tuple[str, str]]:
    """Return *n* (question, answer) filler pairs without replacement (per call)."""
    indices = list(range(len(FILLER_PAIRS)))
    rng.shuffle(indices)
    picked = indices[:n]
    return [FILLER_PAIRS[i] for i in picked]


def _assistant_ack(fact_statement: str) -> str:
    """Generate a short, natural assistant acknowledgement of the stated fact."""
    acks = [
        "Got it, I've noted that down.",
        "Understood — I'll keep that in mind.",
        "Thanks for letting me know. I'll remember that.",
        "Noted! I'll make sure to keep track of that for you.",
        "Sure thing, I've made a note of it.",
        "Alright, I'll hold onto that information.",
        "Perfect, I've registered that. Let me know if you need anything else.",
        "Acknowledged — I'll remember it.",
    ]
    return random.choice(acks)


def generate_conversation(
    conv_id: int,
    fact_type: FactType,
    rng: random.Random,
) -> dict[str, Any]:
    """Build a single multi-turn conversation dict.

    Parameters
    ----------
    conv_id : int
        Numeric conversation identifier.
    fact_type : str
        One of the five fact categories.
    rng : random.Random
        Seeded RNG instance for reproducibility.

    Returns
    -------
    dict
        A conversation object matching the output schema.
    """
    # Determine conversation length: 4-6 turns total (user turns + assistant turns)
    # Structure:
    #   user(fact) → assistant(ack) → [user(filler) → assistant(ans)] × F → user(probe)
    # Total user turns = 1 (fact) + F (filler) + 1 (probe) = F+2
    # Total turns      = 2*(F+1) + 1 = 2F + 3
    # For total turns 4-6 we want user-turns 2-3, i.e. filler_count 0-1... but that
    # gives too few distractors.  The spec says "turns 2-3 are unrelated filler" which
    # means 2 filler QUESTION turns, for 4-6 user turns total → let's count *messages*:
    #   4 turns min = user(fact), asst, user(filler), user(probe)  → too few asst msgs
    # Reinterpretation: "4-6 turns" means 4-6 *user* messages.
    # We'll generate 2-4 filler exchanges between fact and probe:
    filler_count = rng.randint(2, 4)

    fact_statement, probe_question, expected_fact = _make_fact(fact_type)
    fillers = _pick_fillers(filler_count, rng)

    turns: list[dict[str, str]] = []

    # Turn 0: user states fact
    turns.append({"role": "user", "content": fact_statement})
    # Turn 1: assistant acknowledges
    turns.append({"role": "assistant", "content": _assistant_ack(fact_statement)})

    # Filler exchanges
    for question, answer in fillers:
        turns.append({"role": "user", "content": question})
        turns.append({"role": "assistant", "content": answer})

    # Final probe turn (user)
    probe_index = len(turns)
    turns.append({"role": "user", "content": probe_question})

    return {
        "id": f"conv-{conv_id:03d}",
        "turns": turns,
        "fact_turn_index": 0,
        "probe_turn_index": probe_index,
        "expected_fact": expected_fact,
        "fact_type": fact_type,
    }


def generate_all(
    count: int = 150,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Generate *count* balanced conversations.

    Fact types are distributed as evenly as possible using round-robin
    assignment with a shuffled order so adjacent conversations don't
    share the same type.

    Parameters
    ----------
    count : int
        Number of conversations to generate.
    seed : int
        Random seed for full reproducibility.

    Returns
    -------
    list[dict]
        List of conversation objects.
    """
    rng = random.Random(seed)
    # Also seed the module-level random for helper functions
    random.seed(seed)

    # Build a balanced type schedule: repeat the 5 types, then shuffle
    type_schedule: list[FactType] = []
    full_rounds = count // len(FACT_TYPES)
    remainder = count % len(FACT_TYPES)
    for _ in range(full_rounds):
        type_schedule.extend(FACT_TYPES)
    type_schedule.extend(rng.sample(FACT_TYPES, remainder))
    rng.shuffle(type_schedule)

    conversations: list[dict[str, Any]] = []
    for i, fact_type in enumerate(type_schedule):
        conv = generate_conversation(conv_id=i + 1, fact_type=fact_type, rng=rng)
        conversations.append(conv)

    return conversations


# ─── CLI ────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic multi-turn conversations for continuity-bench.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=150,
        help="Number of conversations to generate (default: 150).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path (default: testsuite/conversations.json next to this script).",
    )
    args = parser.parse_args()

    conversations = generate_all(count=args.count, seed=args.seed)

    # Determine output path
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = Path(__file__).resolve().parent / "conversations.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(conversations, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # ── Summary stats ──
    type_counts: dict[str, int] = {}
    turn_lengths: list[int] = []
    for c in conversations:
        ft = c["fact_type"]
        type_counts[ft] = type_counts.get(ft, 0) + 1
        turn_lengths.append(len(c["turns"]))

    print(f"✓ Generated {len(conversations)} conversations → {out_path}")
    print(f"  Turn count range: {min(turn_lengths)}-{max(turn_lengths)} messages")
    print(f"  Fact type distribution:")
    for ft in FACT_TYPES:
        print(f"    {ft:12s}: {type_counts.get(ft, 0)}")


if __name__ == "__main__":
    main()
