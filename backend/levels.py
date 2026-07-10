"""Level designs. Each level has a designed clean path (the intel hints at
it) and several ways to get caught. rival_factor is applied to the honest
ride's MOVING time to set the target, so every level is provably winnable."""

RIDER = {"mass": 78.0, "ftp": 231.0}

LEVELS = [
    {
        "id": 1,
        "title": "The Lunch Loop",
        "segment_name": "Lakeside Lunch Loop",
        "brief": ("Your local loop. Your crown — until Dax took it last Tuesday. "
                  "Your legs were good today, but you stopped for coffee mid-lap "
                  "and the clock didn't."),
        "intel": ("The auto-flagger on quiet segments only sanity-checks speed. "
                  "Nobody audits a ride that looks slow and boring."),
        "profile": [(800, 0.005), (700, 0.025), (800, 0.0), (700, -0.01)],
        "stop": (1400, 160),
        "rival_factor": 1.04,
        "tools": [
            {"name": "trim_stops", "label": "Trim stopped time",
             "hint": "Deletes stationary points and stitches the clock together.",
             "params": []},
        ],
        "checks": {
            "timestamps": {},
            "max_speed": {"limit": 16.0},
        },
    },
    {
        "id": 2,
        "title": "The Causeway",
        "segment_name": "Causeway Flat-Out",
        "brief": ("Dax's favourite segment — a dead-flat power drag across the "
                  "causeway. No coffee stop to blame this time. You're just not "
                  "fast enough. The GPX file doesn't know that yet."),
        "intel": ("Flats hide watts badly — the platform estimates power from "
                  "speed and physics. Modest juice slips under the model; "
                  "greedy juice lights it up like a flare."),
        "profile": [(3200, 0.002)],
        "stop": None,
        "rival_factor": 0.94,
        "tools": [
            {"name": "trim_stops", "label": "Trim stopped time",
             "hint": "Deletes stationary points and stitches the clock together.",
             "params": []},
            {"name": "scale_time", "label": "Juice the ride (Digital EPO)",
             "hint": "Compresses timestamps — everything gets N% faster.",
             "params": [{"name": "pct", "label": "% faster", "min": 0, "max": 30, "step": 1, "default": 0}]},
        ],
        "checks": {
            "timestamps": {},
            "max_speed": {"limit": 13.5},
            "power_wkg": {"limit": 4.0},
            "accel_spikes": {"limit": 4.5},
        },
    },
    {
        "id": 3,
        "title": "Col du Faux",
        "segment_name": "Col du Faux",
        "brief": ("The queen segment: 2.2 km of 6.5% up, then the long drop off "
                  "the back. Dax posted his time with a summit selfie. Gravity "
                  "doesn't negotiate — but the descent is another story."),
        "intel": ("Two things to know. The audit checks effort against YOUR "
                  "history now — a 10% stronger you is a flag, not a triumph. "
                  "And power forensics can't see descents: coasting and braking "
                  "make the estimates worthless below the summit. Speed sanity "
                  "still applies everywhere."),
        "profile": [(2200, 0.065), (800, 0.005), (2600, -0.055)],
        "stop": None,
        "rival_factor": 0.90,
        "tools": [
            {"name": "trim_stops", "label": "Trim stopped time",
             "hint": "Deletes stationary points and stitches the clock together.",
             "params": []},
            {"name": "scale_time", "label": "Overall juice",
             "hint": "Everything gets N% faster. Your history is watching.",
             "params": [{"name": "pct", "label": "% faster", "min": 0, "max": 15, "step": 1, "default": 0}]},
            {"name": "scale_time_range", "label": "Sector juice",
             "hint": "Juice only a slice of the ride. Choose the slice wisely.",
             "params": [
                 {"name": "pct", "label": "% faster", "min": 0, "max": 50, "step": 1, "default": 0},
                 {"name": "from_frac", "label": "from (0-1)", "min": 0, "max": 1, "step": 0.02, "default": 0.78},
                 {"name": "to_frac", "label": "to (0-1)", "min": 0, "max": 1, "step": 0.02, "default": 1.0},
             ]},
        ],
        "checks": {
            "timestamps": {},
            "max_speed": {"limit": 26.0},
            "power_wkg": {"limit": 4.6},
            "rider_baseline": {"margin": 1.12},
            "accel_spikes": {"limit": 4.5},
            "elevation_match": {"max_m": 6.0},
        },
    },
    {
        "id": 4,
        "title": "The Phantom Ride",
        "segment_name": "Ridgeline Rollers",
        "brief": ("Flu week. You haven't touched the bike, and Dax just took the "
                  "Rollers with a caption: 'some of us show up.' You can't ride. "
                  "The file doesn't know that. Build one from nothing."),
        "intel": ("Fabrications die three ways: constant pace up rolling hills "
                  "(nobody climbs at cruise control), signals too clean to be a "
                  "real device, and a heart that doesn't answer the hills. Fake "
                  "the physics, fake the noise, fake the physiology — all three."),
        "profile": [(1200, 0.04), (800, -0.02), (1000, 0.045), (600, -0.015), (900, 0.01)],
        "stop": None,
        "rival_factor": 0.96,
        "tools": [
            {"name": "synthesize", "label": "Fabricate ride (full synthesis)",
             "hint": "No ride happened. Generate the file from the route alone.",
             "params": [
                 {"name": "faster_pct", "label": "% faster than Dax", "min": 1, "max": 12, "step": 1, "default": 3},
                 {"name": "humanize", "label": "humanize noise", "min": 0, "max": 100, "step": 5, "default": 0},
                 {"name": "hr_mode", "label": "heart rate", "type": "select",
                  "options": ["flat", "modeled"], "default": "flat"},
                 {"name": "terrain_aware", "label": "terrain-aware pacing", "type": "checkbox",
                  "default": False},
             ]},
        ],
        "checks": {
            "timestamps": {},
            "max_speed": {"limit": 16.0},
            "power_wkg": {"limit": 4.6},
            "rider_baseline": {"margin": 1.12},
            "accel_spikes": {"limit": 4.5},
            "smoothness": {"min_mad": 0.05},
            "hr_flat": {"min_sd": 2.5},
            "hr_correlation": {"min_corr": 0.15},
            "elevation_match": {"max_m": 6.0},
        },
    },
    {
        "id": 5,
        "title": "The Crown",
        "segment_name": "Alto de la Corona",
        "brief": ("The one that matters. 4 km of climbing to the chapel, then "
                  "the drop everyone films. Dax's crown, three seasons running. "
                  "Your honest attempt died mid-climb — you cracked and sat on "
                  "the wall for a minute and a half. This is the last upload "
                  "that will ever matter to you."),
        "intel": ("Big segments get MANUAL REVIEW: pass the audit and a human "
                  "re-runs the sensory checks tighter. Two ways out of a review: "
                  "a file so conservative it survives the second look — or "
                  "editing the flagged file. Know this: the reviewer can see "
                  "the file as it was originally uploaded. The database "
                  "remembers everything."),
        "profile": [(1500, 0.03), (2500, 0.07), (500, 0.01), (2000, -0.045)],
        "stop": (2700, 90),
        "rival_factor": 0.93,
        "review": {"tighten": 0.90},
        "tools": [
            {"name": "trim_stops", "label": "Trim stopped time",
             "hint": "Deletes stationary points and stitches the clock together.",
             "params": []},
            {"name": "scale_time", "label": "Overall juice",
             "hint": "Everything gets N% faster. Your history is watching.",
             "params": [{"name": "pct", "label": "% faster", "min": 0, "max": 15, "step": 1, "default": 0}]},
            {"name": "scale_time_range", "label": "Sector juice",
             "hint": "Juice only a slice of the ride.",
             "params": [
                 {"name": "pct", "label": "% faster", "min": 0, "max": 50, "step": 1, "default": 0},
                 {"name": "from_frac", "label": "from (0-1)", "min": 0, "max": 1, "step": 0.02, "default": 0.88},
                 {"name": "to_frac", "label": "to (0-1)", "min": 0, "max": 1, "step": 0.02, "default": 1.0},
             ]},
        ],
        "checks": {
            "timestamps": {},
            "max_speed": {"limit": 25.0},
            "power_wkg": {"limit": 4.6},
            "rider_baseline": {"margin": 1.12},
            "accel_spikes": {"limit": 4.5},
            "smoothness": {"min_mad": 0.05},
            "hr_flat": {"min_sd": 2.5},
            "elevation_match": {"max_m": 6.0},
            "snapshot_diff": {},
        },
    },
]


def level_cfg(level_id):
    for lv in LEVELS:
        if lv["id"] == level_id:
            return lv
    return None
