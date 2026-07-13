---
title: "False Summit: a game where you commit the fraud — and the database catches you"
published: false
tags: weekendchallenge, snowflake, ai, gamedev
---

*This is a submission for the [DEV Weekend Challenge: Passion Edition](https://dev.to/devteam).*

> *"Passion is the rivalry that pushes competitors to greatness."* — the challenge prompt

This is a game about the **shadow** of that sentence. The rivalry that pushes
someone one step *past* greatness — over the line, into the file, editing the
truth to win back the thing they can't earn on the road anymore.

## What I Built

**False Summit** is a narrative game where you play the cheater.

You and your rival, Dax, used to ride together. He took the segment crown that
mattered, and now you can't beat him on the road. But a Strava-style leaderboard
doesn't *see* the road — it sees a **GPS file you upload**. And a file can be edited.

So you doctor it. Trim the coffee stop out of the timestamps. "Digital-EPO" the
whole ride 8% faster. On a mountain, juice only the descent, where the physics
can't see you. By the final level you're fabricating rides you never rode.

After every upload, a **deterministic forensic audit** runs real checks against
your file — and if you got greedy, it catches you and tells you *exactly how*.
You learn what fraud detection catches by trying to beat it. That's the whole
idea: **red-teaming for data integrity, as a game.**

I've wanted to build a database-detective game — the kind you solve by *querying*
it — for years. The prompt's line about "the love that fuels late-night side
projects" was the push to finally do it. False Summit is that game — except I put
you in the criminal's seat instead of the detective's, because the question that
actually grips me was never *who did it*, but *how far someone would go* for the
thing they love.

## Demo

📺 **Walkthrough:** YOUR_VIDEO_LINK_HERE

💻 **Code:** https://github.com/PujaSridhar/false-summit

![The audit catches an over-juiced ride: Power-to-weight forensics, FAIL](SCREENSHOT_LINK_HERE)

## Why it's on theme — and why it's real

Passion here is the *motive*: devotion to a rivalry, curdled into fraud. And it
isn't invented — "digital doping" is a documented problem:

- A tool literally called **[Digital EPO](https://road.cc/content/news/84868-digital-epo-smash-your-strava-times%E2%80%A6-cheating)** lets you upload a ride and pick how much faster you'd like to have gone.
- **[Strava's own leaderboard guidelines](https://support.strava.com/hc/en-us/articles/216919507-Segment-Leaderboard-Guidelines)** address motor-assisted and doctored uploads.
- Community sleuths catch fakes with the exact tell my game uses — real GPS jitters; generated files are suspiciously smooth ([ScarletFire](https://www.scarletfire.co.uk/how-to-tell-if-someone-used-digital-epo-to-cheat-on-strava/)).

The forensics in the game are the ones the real world uses. I just put you on the
wrong side of them.

## Prize Categories

### 🏔️ Snowflake — Time Travel *as a game mechanic*

The evidence lives in Snowflake and the audit SQL runs in the warehouse. But the
finale is the real flex: on the last level, passing the audit triggers **manual
review**. You can stand pat — or **edit the file that's already on record**. If
you do, the audit diffs your upload against the table *as it existed at upload
time* using genuine **Time Travel** (`AT(TIMESTAMP => …)`), and the diff between
then and now *is* the confession: *"the database remembers."* I've never seen
Time Travel used as a gameplay mechanic — it turns a Snowflake feature into the
most dramatic moment in the game.

### 🤖 Google Gemini — the investigation report

As you play, the game builds a dossier of every cheat across all five segments.
At the end, **Gemini** synthesizes that dossier into a closing case file — a
clinical, damning investigator's report of your season-long crime spree.

### 🎙️ ElevenLabs — the voices of the chase

**ElevenLabs** voices your rival's smug taunts and the auditor reading the final
verdict. Click-to-play, so it's atmosphere you control, not noise.

## The forensic engine (the part I'm proud of)

Every ride — honest or fabricated — is generated from a **rider power model**
(`P = (Crr + grade)·m·g·v + ½ρCdA·v³`). Because detection *inverts the same
physics*, every check has a ground truth. The audit is a suite of SQL checks over
the trackpoints:

- **Power-to-weight forensics** — invert speed + gradient into watts. A weekend
  rider holding 5.8 W/kg is either a Grand Tour winner or lying.
- **Signal-noise analysis** — real devices jitter every second; fabricated files
  are too clean.
- **Cardiac coupling** — a heart rate that never responds to the climb.
- **Terrain cross-reference** — a track floating meters off the real mountain.
- **Rider-history consistency** — checks self-calibrate against *your own* past
  uploads, so "you've never been this strong before" becomes a flag.

The hardest design problem was fairness: each level has a **provably winnable
clean path** and a dozen ways to get caught, calibrated so greedy cheating trips
a specific check with a specific, human-readable explanation.

## Engineering notes

- **DuckDB ↔ Snowflake** behind one storage interface — dev runs offline on
  DuckDB; prod is Snowflake with a small SQL-dialect shim.
- **97 tests** (physics, cheats, every audit check, the state machine, the API,
  and edge cases) — fully offline, and they caught three real bugs.
- Graceful fallbacks everywhere: no API keys → canned narrative, silent voice,
  DuckDB. The game is always playable.

## What I Learned

That the most compelling way to teach detection is to make someone commit the
crime. Every threshold in this game is something a real anti-cheat system checks
— you just feel it from the inside, one `COMMIT` at a time.

Every record they chased was real once. Only the rider changed.
