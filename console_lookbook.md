# The Console — Lookbook

What the Console Constitution asked for, what the deck actually does, and the measurement
behind each claim. Every number here was read off this machine on 25 September 2026; none of
it is typed from the specification. Where a claim is a *measurement* the harness and line are
named, so anything in this document can be re-run rather than believed.

Machine: Windows 11, Chrome on the real GPU, `python server.py` on 127.0.0.1:4700 serving
only `viewer/`. Run logs for this date, in the project root: `_pre.out` and `_pf.out`
(preflight, before and after the presence), `_conv.out`, `_deck.out`, `_voice.out`,
`_layout.out`, `_desk.out`, `_tools.out`, `_focus.out`. Each is the stdout of the harness of
the same name, and every harness can be re-run by name — **solo**, for the reason §16 gives.

Sections 1–9 were written first; **sections 10–16 were added the same day**, after the worlds,
the Mind, the deep field, the spoken dial and the Open Ear landed, and **§17 after the face**.
Where a later part falsified a sentence in an earlier one the sentence was **rewritten from a
new measurement** rather than left standing, and the rewrite says what it replaced.

---

## 1 · The telemetry top rail, and what it says right now

A 30px band across the very top, dark glass on the same blur as every other surface, mono
type throughout, uppercase, 10px — an instrument label rather than a sentence. It sits at
z-index 6, under the panel and under the countdown card, and it is `pointer-events: none`, so
it never takes a press meant for the sky behind it.

Its state as the deck stands, read out of the DOM rather than out of the source:

```
[ MODEL: OPUS 5 ]  [ VOICE: PIPER · JOE-MEDIUM ]  [ ARCHIVE: 36 FILES ]  [ WEB: READY ]
```

Four cells, left to right in the order the constitution names them, and every one painted
with a value rather than the markup's ellipsis:

| Cell | Reads | Where the value comes from | Light |
| --- | --- | --- | --- |
| MODEL | `OPUS 5` | the same reading the brain chip uses — one source, two places, no way for them to disagree | white type |
| VOICE | `piper · joe-medium` | `/health.say`: the engine **and** the model file the server is actually loading | gold — a voice on this disk is local material |
| ARCHIVE | `36 files` | what the server says is indexed, not what the folder looks like | gold |
| WEB | `ready` | the door this config actually has — searxng, ddg-lite, ddg-html, wikipedia | cyan when live |

It re-reads `/health` every 10 seconds, so an archive rebuilt in another window is a stale
readout for a few seconds and not for the session. That cell read `ryan-high` when this
section was written; it reads `joe-medium` now because the voice has since been recast **out
loud**, through the door §13 records — the readout followed the file, which is the whole point
of reading it off `/health` instead of printing a constant.

**The empty-archive state** (Part 4) was forced and measured rather than reasoned about: with
the server's count answered away, the cell reads `[ ARCHIVE: 0 FILES ]` in muted red —
`rgba(255, 107, 107, 0.72)`, measured off the browser — which reads as a fault without
becoming an alarm. The renderer did not flinch: 44 more frames of spin during the forced
state, no exception thrown, and one real reading put it back to `36 files`.

## 2 · Instrument nodes — no text on any crust, no Saturn rings

Thirty worlds for thirty notes, each built exactly once. The old text-textured spheres and the
Saturn rings are gone, and their absence is asserted from counters the page keeps for exactly
this purpose rather than from a glance at a screenshot.

**Two bullets here used to read "zero text canvases" and "no colour map on the crust at all",
and §10 has made both false.** There is a canvas per world again — thirty of them, painted at
index load — so the counter that carried the old claim now reads `textures: 30`. The claim it
was standing in for survives intact, and it is the one worth keeping:

- **zero characters drawn, on any world** — `{"count":30,"builds":30,"textures":30,"chars":0}`,
  and `chars: 0` again in each skin read one at a time. Thirty colour maps and not one glyph:
  what got onto those spheres before was *text*, and text is what is gone. A colour map was
  never the defect; a label baked into a planet was.
- **built once, and thirty different worlds**: `builds: 30` for 30 nodes — no rebuild per
  frame — over **30 distinct seeds for 30 worlds**, no two alike. The noise field and the
  frosted roughness map are still shared by the whole galaxy (`noise: 1, frost: 1`), so what
  is per-world is the painting and not the machinery that paints it.
- **matte rock, hazier gas, and nothing chromed**: measured off three real materials —
  rocky `metalness 0.05 / roughness 0.95`, gas `0.16 / 0.72`, ice `0.12 / 0.60`, `emissive
  0.08` at rest. This replaces a claim of `metalness 0.86, roughness 0.34, body #0c1218`: a
  dark metal housing was right for a shell with no skin on it, and wrong the moment the skin
  arrived. A world lit by §10's key light needs a surface that scatters rather than one that
  mirrors a light that is not in frame.
- **one equator ring per world, and it is an equator ring**: `ringed: 30`, all 30 a quarter
  turn about X and *exactly zero* about Z. That is the measurement that says "not Saturn".

The ring is the readout every instrument carries, not a badge a few of them earn — 30 rings
for 30 worlds.

**Ring thickness is connection density.** Four strictly increasing tiers, the thickest still a
hairline at 0.124 of a radius:

```
0.035  <  0.058  <  0.086  <  0.124        breakpoints at 2, 4, 8 links
inner radius 1.055 against a body of 1     so thickness grows outwards, never eating the world
```

All 30 widths are the tier their own recounted link total earns, and not one world with more
links wears a thinner ring than one with fewer. The ladder is genuinely in use —
`{"0.086": 26, "0.124": 4}` — so thickness carries information instead of being one value
thirty times.

**Ring colour is cluster.** Seven colours across seven folders, each folder one colour and no
colour in two folders, worn at 62% alpha — the one lit thing on a dark body, and still not
opaque:

```
#367dba  #ba9a36  #5b36ba  #36ba96  #ba3636  #baa936  #ba6636
saturation and lightness pinned at 0.55 / 0.47, measured off the material
```

Desaturated jewel tones by arithmetic, not by eye.

## 3 · Motion — the exact curve, and why nothing overshoots

```css
--spring: cubic-bezier(0.16, 1, 0.3, 1);
--spring-ms: .3s;
```

Both control-point y values are inside the unit square — `1` and `1`, never above — so every
entrance decelerates onto its mark and stops. Nothing travels past the value it is animating
to. The retired curve is named in the stylesheet's own comment so it cannot creep back:

> This deck used to overshoot on purpose — `cubic-bezier(.34,1.56,.64,1)`, a surface arriving,
> leaning past its mark and coming back. That is the motion language of a phone, not of an
> instrument: the y=1.56 control point means every entrance travels PAST the value it is
> animating to, and a readout that overshoots is a readout that displayed a wrong number for
> 80ms.

That string now appears in the file exactly once, inside that comment, and nowhere in a rule.

Measured on the live surfaces: the hyper-glass panel enters on `transform` alone at `0.3s` on
`cubic-bezier(0.16, 1, 0.3, 1)`; the command sheet enters on `opacity` **and** `transform`,
both capped at 300 ms, both on the same curve. No width, no top, no box-shadow — nothing that
costs a layout. The Yes/No gate is the one deliberate exception at `.09s linear`, which is the
harness law's sub-100ms door rather than a settle.

The only other curve in the stylesheet is the layout governor's `cubic-bezier(.22,.7,.25,1)`
at 220 ms, used sixteen times. That is a surface being *re-placed* when the window changes,
not an entrance, and its y values are 0.7 and 1 — inside the square, so it does not overshoot
either. There is no third curve.

Frame rate, since motion that settles is only worth having if it is cheap: **59.2 fps over 5
seconds idle** — 296 frames in 5002 ms, p95 17.1 ms, worst 83.3 ms, 2 of 296 frames over 20 ms
— against the 55 fps floor, and measured **with the microphone open**, thirty painted worlds
turning and the nebula behind them. The page's own monitor read 60 fps at the same moment, so
the guard below is watching the real frame rate rather than a number of its own.

The bloom was auditioned on this machine rather than assumed, and **this run dropped it**:
60.1 fps without the glow against 52.1 fps with it, floor 55, keep 90% of baseline. It was
kept when this section was first written (60.4 against 57.6) and the deck it was auditioned on
had bare spheres and no nebula on it. Nothing about the audition changed except the cost of the
frame, which is exactly the decision the guard exists to make — and it states its reason
arithmetically: *"audition: 52.1fps with the glow against 60.1fps without it (floor 55, keep
90% of baseline)"*.

## 4 · The organ rail

The five buttons that were already there, under the ids every other harness in this repo
already clicks: `#screen`, `#eye`, `#focusbtn`, `#mic`, `#reset`. Nothing was added and no id
moved. Each gained a state dot and a state line in its tooltip — the markup's own sentence
*plus* the state, two lines, so the designer's description of what the button is for is never
overwritten.

At rest: `screen=off · eye=off · focusbtn=off · mic=off · reset=held`, zero organs live, and
**nothing pulses**. The one thing that *is* true — a conversation there to forget — shows as a
still dot on `#reset`. The pulse is spent only on `data-organ="live"`, and a reader who asked
for less motion gets the dot without it.

## 5 · The command panel

A real Ctrl+K summons it — dispatched through the browser's key queue, not by calling the
handler — and a real Escape dismisses it. Dark glass at z-index 10: under the countdown card
at 12, and pressable while open. It hangs from the telemetry rail down the left wall and stops
short of the ask bar (bottom 388px, bar at 762px).

Five diegetic orders, each carrying a label in the reading type and a state line in mono:

```
focus     Start Focus          30 minutes · it will ask what for
lock      Lock Tab             no session · start focus first
links     Show Every Link      86 of 236 shown · the strongest
archive   Open Archive         36 files · nothing cited yet
cast      Voice Casting        piper · joe-medium · three candidates
```

They press the real controls. *Simplify Links* took the graph 86 → 236 → 86 links — the strong
subset, all of them, and back — and the order renames itself to what pressing it would do
next rather than naming the state it is already in. The sheet stays open across it, because
thinning a graph is something you look at.

**Parallax suspends while the sheet is open** (Part 4): the flag is written on every frame, so
a panel summoned by a key is honoured on the next frame and not on the next mouse move. The
pointer was taken to the opposite corner and neither camera counter moved — the camera is
frozen rather than eased, because WANTED is dragged up to NOW instead of being followed — while
the sky itself turned 85 more frames. A decision, not a dead page. The give comes back the
moment the sheet is gone.

## 6 · The voice

**The FIFO.** A 120-character line, read through the real AudioContext bus: queued 1, played
1, dropped 0, silent 0, decode failures 0 — and 15 queued / 15 played across the whole
session. 7.5 s of audio against the page's own estimate of 9.2 s, so the queue did not
"play" everything in milliseconds. Every chunk came from `/say` rather than a browser
utterance, decoded here, off the bus: a page that had quietly fallen back to an `<audio>` tag
would satisfy every count above and none of the requirement.

**A decode failure cannot lose a chunk.** With one `decodeAudioData` call sabotaged to refuse
mid-read: 4 queued, 4 played, **0 dropped**, one 10 ms silent buffer standing in at chunk 0 of
4 — and all 3 chunks after the hole read as real audio, to the last word. The tail never died.
The page says so in words, naming the chunk, the refusal to decode and the ten milliseconds.
One stumble is not a verdict: it takes two consecutive misses to fall back, because a browser
voice bought with one bad decode would cost the whole answer its voice.

**Prosody**: `length_scale 1.05`, `noise_scale 0.4`, read off `/health.say`. Never rushed.

**Chime ducking.** The chime bus drops to 0.03 from a ceiling of 0.15 — the 80% the
constitution asked for — for the whole sentence: 61 samples while speaking, not one of them
caught the chimes at full height, and the AudioContext was `running` for every sample, so
those numbers are a measurement and not a stopped clock. A chime fired into the middle of a
sentence still *sounds* — it is scheduled and recorded, not cancelled — and it sounds 80% down.
A chime never talks over the butler.

One note for whoever reads the duck next, because it cost an afternoon: `AudioParam.value` is
not the timeline. It is the number the audio thread last *computed*, and Chrome stops
computing for a node it has disabled — a GainNode whose inputs have all disconnected, which is
exactly what a chime's envelope does at its own `onended`. After a mid-sentence chime the bus
reads a frozen `0.03` while the 90 ms lift ramp sits on the timeline, correct, waiting for a
quantum with any reason to be rendered. Nothing is broken; the observer was. So the lift is
now measured the way an ear meets it — fire a real chime into the silence and watch the bus
carry it — and it reads **0.15 of 0.15**. Both the page and the harness carry that paragraph
in a comment.

**The casting test.** Three candidates, one line, three real auditions through the real bus:

```
en_US-ryan-high      heard · 2.7s    chimes ducked to 0.07
en_GB-alan-medium    heard · 4.1s    chimes ducked to 0.07
en_US-joe-medium     heard · 3.6s    chimes ducked to 0.07
```

Each read the server's own constant — *"The archive is online, and the hands are wired,
sir."* — printed by the panel rather than retyped in the harness. Every one was heard to the
end, the length reported from its own `onended` rather than hoped about, with the chimes ducked
under the audition as well: the casting booth is speech, and the same rule applies to it. An
audition begun in the middle of a sentence is refused in words — *"hold — he is speaking"* —
because the butler owns that bus.

**Nothing was kept — by the casting panel.** Pressing *keep* is what writes `config.json →
voice_model` from the audition room, and that press is yours. No harness has made it:
`config.json` ended the run byte-for-byte the decision it started as — `voice_model` unchanged
at `en_US-joe-medium`, 19 keys, digest of every other key `35b8224d`. That digest is how a file
holding credentials gets checked without being read. (It read `en_US-ryan-high` / `a7dac0ca`
when this section was written; the voice has been recast **out loud** since, and the digest is
of a file that has been edited by its owner's hand in the meantime — the number is a
before/after equality within one run, never a constant across days.)

There is now a **second** door onto that same key, and it is the only other one: the `set_voice`
hand, proposed and confirmed by voice, in §13. Both doors write the same field; neither writes
it without being told to twice.

## 7 · The refusal and edge matrix

| Case | Asked for | Measured |
| --- | --- | --- |
| Piper absent | casting panel reads "Piper Offline — Web Fallback", defaults to Windows natural voices, no crash | forced by answering `/voices` with a piper-less payload: the banner reads **"piper offline — web fallback · speaking as David"**, opening it threw nothing, all three candidates stay listed and every one is unpressable, and the voice already cast behind it is a real one off this machine (Microsoft David, by allowlist #5). The real `/voices` puts it back — the absence was a paint and nothing else. |
| Empty archive | `[ ARCHIVE: 0 FILES ]` in muted red, no renderer crash | exactly that, at `rgba(255,107,107,.72)`, with 44 more frames of spin during it and no exception |
| Panel open while the camera is moving | parallax suspends immediately | suspends on the next *frame*, camera frozen rather than eased, sky still turning; released when the sheet closes |

## 8 · The regression matrix

**The summary lines live in §16** and are not repeated here, because two copies of a matrix are
two numbers waiting to disagree. This section's block used to hold `deck_proof 147/147`,
`voice_proof 122/122`, `tools_live 35/35` and `desk_proof 37 checks`; every one of those
harnesses has since grown assertions for the worlds, the Mind, the deep field, the dial and the
Open Ear, and §16 is the current reading of all eight.

Zero failures anywhere, then and now. The three preflight warns are the two documented environmental ones:
no OpenRouter/Astra key in `config.json`, so the swapped brain's *answer* chain is unverified
here — the model id is right and the fallback is honest and visible on the card (warns 10 and
12) — and no Chrome-family browser on the DevTools port at that moment, so tab-level focus
locking degrades to the application only and says so in its own start line (warn 11). Only
`fail` judges the code, and there are none.

`deck_proof.mjs` carries the Part 1 assertions: instrument nodes, both rails, the exact curve,
and **59.2 fps** against the 55 fps floor, now with the textures, the nebula and the Open Ear
idling in the frame. `voice_proof.mjs` carries the FIFO, the casting
protocol and the ducking. `layout_proof.mjs` and `desk_proof.mjs` both assert the rails never
overlap the PiP card, at 1280×860 and squeezed to 1280×380, and in the page with a live
session — and they name the axis that separates them, because squeezed it is the column and not
the row: the bar ends at 362px, the card begins at 374px. Every DOM id the harnesses know is
unchanged; the organ rail is the same five buttons `tools_live.mjs` still clicks Yes/No
through.

Plates written by the deck proof, for the eye rather than the counters: `deck-planet.png` (one
world, close enough to read its surface), `deck-panel.png` (the hyper-glass panel over the
galaxy), `deck-command.png` (the order sheet under the telemetry rail), `deck-gate.png` (the
dimmed deck and the gold gate), `deck-galaxy.png` and `deck-galaxy-bloom.png`.

## 9 · What this document does not claim

- **The watch-capture gap stays documented, not rebuilt** — it is described in `README.md` and
  untouched here, as instructed.
- **The voice is not cast *by the audition room*.** Three candidates were auditioned there; the
  choice, and the one press that writes it to `config.json` from that panel, is yours. It *is*
  cast by the spoken dial, asked for out loud and confirmed out loud — §13.
- **Two checks are still by hand**: the Gmail app-password round trip and the two Calm Sky
  reads. Nothing in this run touched either.
- Nothing in the do-not-alter list was edited: the semantic retrieval path and its 0.60
  threshold, the Hands pipeline, the Web Gate fallbacks, the Backchannel / Third Door / PII
  vetoes, the server routes and `test_watch.py`'s in-process loop are as they were.

---

## 10 · True worlds

Thirty spheres became thirty *places*. Each crust is a canvas painted once at index load, 512
× 256, off a seed of its own — **30 distinct seeds for 30 worlds** — and the whole galaxy is
three kinds: `{"gas":10,"rocky":11,"ice":9}`. What the brushes laid down, counted across all
thirty: **102 latitude bands, 1272 craters, 318 cracks, 22 polar caps, and 0 characters.**

One skin of each kind, read out one at a time rather than in aggregate, because an aggregate
can hide a kind that is painting nothing:

```
gas    seed 287841048   512x256   bands 13  storms 3  craters 0   cracks 0   caps 0  chars 0  mean 0.2872
rocky  seed 904125740   512x256   bands 0   storms 0  craters 91  cracks 0   caps 2  chars 0  mean 0.3527
ice    seed 3750272928  512x256   bands 0   storms 0  craters 0   cracks 36  caps 0  chars 0  mean 0.4423
```

The bands belong to the gas giant and the craters to the rock: no kind is painting another
kind's brush, which is the whole difference between three procedures and one procedure with a
tint. `wrapS` and `wrapT` are both true on every skin, so the seam meets itself rather than
showing as a scar down a turning world.

**The key light is one light, off frame, and every world is in it.** The rig was retuned rather
than added to blindly — `{"found":2,"retuned":1,"added":1,"zeroed":0}`:

```
key      DirectionalLight   intensity 1.7   #fff3e2   at [-1539, 1010, 1539]
fill                        intensity 0.34  #2b3c60   at [ 1155, -758, -1155]   (exactly opposite)
ambient  AmbientLight       intensity 0.5
direction                   [-0.6414, 0.4209, 0.6414]
```

One warm key and one cold fill directly behind it: that is a day side, a terminator and a night
side, and nothing is lit from the camera. Every world carries a fresnel atmosphere shell at
`shellAlpha 0.34` which rims the lit limb, and the smooth kinds carry a faint specular the rock
does not — `spec: true` on gas and ice, `false` on rocky, which is the difference between an
atmosphere and a stone.

**They live without moving the viewer.** Four parts per world, one of them spinning; axial rate
`0.0013–0.0016` rad/frame, and a per-world orbital drift measured twice, four seconds apart:

```
drift  [0.04097, 0.01331, -0.02079]  ->  [0.04019, 0.01086, -0.02089]
```

Small, and not the same small number twice. The camera was untouched between those two
readings.

**Hover is an annotation, not a bubble.** Measured on one world with the pointer on it:

```
text   "Customer Feedback Log·7 connections·touched 8 days ago"
at     [585, 379]   side r   leader line: h 1px, w 46px, 26.55px drawn, rotated by a matrix
skin   background rgba(0,0,0,0) · border 0px · border-radius 0px · pointer-events none · z 6
type   "JetBrains Mono", ui-monospace …
tip    {"present": false}
```

Name, connections, last touched — the three things the spec names, in mono, over nothing: a
transparent background, no border and no corner radius is the measurement that says *HUD
annotation* rather than *tooltip*. The leader line is one pixel high and arrives at the world on
an angle. There is no tooltip node in the page at all, which is why the last row can be a
`false` rather than a paragraph.

Plates, the camera walked in to 3.1 radii of the world's own centre: `shots/world-gas.png` (latitude bands, a turbulent storm
in the lit third, the terminator falling away down the left limb, the equator ring edge-on),
`shots/world-rocky.png` (crater rims catching the key light, a polar cap at the top, no
specular anywhere), `shots/world-ice.png`, and `shots/world-hover.png` for the annotation. At
this range the key light at 1.7 washes the lit face toward white; the cluster tints read plainly
at galaxy distance, in `shots/deep-field.png`.

## 11 · The Mind, in all five states

The smiley is gone: bar-eyes, bar-mouth and every ghost of them. The selector sweep for
`.feye,.feyes,.fmouth,.fbarm,.fring,.fscan` finds **0 nodes**. What stands there now is a
gyroscopic lens — `{"gimbals":3,"lens":1,"iris":1,"core":1,"spokes":36}` — three rings on three
different axes at three different rates (9.4 s, 6.8 s and 4.3 s per turn, each divided by the
pose's `--spin`), one optical iris, and a 36-spoke waveform ring driven by the live speech
analyser. It renders in **two homes** (`homes: 2, lit: 2`): the focus card, and small in the
Command Panel header.

Five states, and each one measured as aperture, waveform amplitude and gimbal rate out of
*computed style* rather than taken on trust from the class name:

```
state       iris    waveform   gimbal rate     both homes
idle        0.72    0.13       1.0             mind idle          · mind mini idle
listening   1.16    0.52       1.5             mind listening     · mind mini listening
thinking    0.50    0.09       2.3             mind thinking      · mind mini thinking
speaking    0.94    0.70       1.2             mind speaking      · mind mini speaking
locked      0.60    0.05       0.42            mind locked        · mind mini locked
```

The iris **dilates to listen** (0.72 → 1.16) and **contracts to think** (→ 0.50); the waveform
is loudest while he speaks (0.70) and nearly flat when he is locked (0.05); the gimbals spin
fastest while thinking and slowest under a lock. `focus_probe.mjs` walks all five by name and
asserts each pose is unlike every other one on the list — five signatures, five distinct — so
"five states" is a fact about what is drawn and not about five class names that happen to
differ. Its own line for each: *"the Mind holds LISTENING: both homes wear the pose and it looks
like nothing else on the list."*

Plates: `shots/mind-idle.png`, `mind-listening.png`, `mind-thinking.png`, `mind-speaking.png`,
`mind-locked.png` — the card at 476 × 303 — and `shots/mind-panel.png`, the small Mind beside
the word COMMAND in the panel header, on its own gimbals.

## 12 · The deep field

```
nebula     3 ellipses · 6 colour stops · max alpha 0.06 · blur(40px)
grain      0.02
stars      three webgl shells: 690 / 495 / 315   sizes 5.4 / 7 / 8.6   opacity 0.547 / 0.684 / 0.760
parallax   depth factors 0.16 / 0.48 / 1.00
swing      9.42 / 28.27 / 58.91 world units, pointer far left to far right
sun        direction [-0.6414, 0.4209, 0.6414] — the key light's own vector, to the digit
```

Three radial ellipses in **two** hues — violet `rgba(139,92,246,.06)` and `rgba(124,88,230,.035)`,
teal `rgba(45,212,191,.05)` — **never above 6% opacity**, under `blur(40px)` so no edge of any of
them can be found by looking for it, with film grain over them at 0.02. The ceiling is measured
off the rule rather than eyeballed. Two hues and not three, because three reads as a gradient
mesh; violet and teal at this temperature read as one cloud lit from two sides.
Three star layers under real pointer parallax, and the nearest layer swings **six times as far**
as the farthest — 58.91 against 9.42 world units — which is what makes it depth instead of a
slide. The canvas fallback keeps the same idea in three bands (98 / 70 / 45 stars at parallax 3
/ 9 / 19) for a machine with no WebGL.

The distant sun sits on **exactly the key light's direction vector**, so the glow in frame and
the terminator on every world are the same light source; nothing is lit from two suns. Fog
stays, and the bloom audition guard stays and this time exercised its judgement (§3).

Plates: `shots/deep-field.png` — the wide shot: thirty tinted worlds, the violet and teal
washes, three star depths — and `shots/deep-sun.png`, the sun brought into frame with its
anamorphic streak drawn flat across it and the worlds in front of it going to silhouette.

## 13 · The spoken dial — a real recast, out loud, twice

The registry hand is `tools/set_voice.py`: stdin `{voice}`, nicknames resolved to model ids,
validated against the `./voices/*.onnx` actually on this disk (`en_GB-alan-medium`,
`en_US-joe-medium`, `en_US-ryan-high`), `config.json → voice_model` written atomically, and one
sentence on stdout. Asked for by voice, proposed by voice, confirmed by voice:

```
  EMPLOYER  [the voice in force is en_US-joe-medium]
  EMPLOYER  switch your voice to alan
  BUTLER    You are hearing Joe at the moment, sir. That would make it alan from the next
            word on. Shall I change the voice?   [Yes / No]
  EMPLOYER  yes, go ahead
  BUTLER    Speaking as Alan now, sir.
  EMPLOYER  speak with joe again
  BUTLER    You are hearing Alan at the moment, sir. That would make it joe from the next
            word on. Shall I change the voice?   [Yes / No]
  EMPLOYER  yes, go ahead
  BUTLER    Speaking as Joe now, sir.
```

`/health.say` either side of each confirmation, which is `config.json` read back off the disk by
the server rather than the page's opinion of it:

```
en_US-joe-medium   ->  en_GB-alan-medium   ->  en_US-joe-medium
```

That round was driven by hand rather than by a harness, and deliberately so: `tools_live.mjs`
recasts to the voice **already in force**, because which voice this machine speaks in is not a
harness's decision to change. Its two sentences are the whole recipe — say them, answer the
question, read `/health.say` — so it re-runs without a script.

The machine ends the round in the voice it began in, having genuinely spoken in another one in
between — 19 keys in `config.json` at the end, `voice_model en_US-joe-medium`, `voice_engine
piper`. **The announcement is read in the voice it announces**: `/say` re-reads the config per
chunk, and the write lands before the sentence is synthesised, so *"Speaking as Alan now, sir."*
arrives in Alan. That sentence is the script's own stdout, spoken — not a line the page composed
about what the script did.

Every gate around it, measured elsewhere and not repeated by hand:

- **Current beside requested, always** — `rows: {"voice":"alan","current":"Joe"}`; the *current*
  value is read off the disk by the server, so the card cannot flatter itself.
- **Proposed before written** — the question is spoken aloud before anything is written, and
  `tools_live.mjs` proves the same round leaves `config.json`'s other 18 keys digest-identical
  either side (`baf6e29d`), with the ledger moving by exactly one `ok` for `set_voice`.
- **Cancelling cancels** — preflight check 16(h) proposes a real recast and then *cancels* it:
  the slot empties, Joe stays, and `config.json` is unmoved to the byte (1770 bytes, sha256
  `bfd3392c` either side).
- **The three refusals name the thing that is wrong** — no voice given: *"I should need the
  voice before I could do that, sir"* (the field, by name). An unheard-of voice, confirmed out
  loud: refused **by the hand**, and the refusal names the voices that are installed. A voice
  not on this machine: told so plainly. The ledger records one more `failed` for `set_voice`
  each time (2 → 3 on the last run) and keeps no note of which voice was asked for.
- **And the file is where it was.** `preflight.py` weighs and digests `config.json` inside check
  16, and it ran on both sides of the recast round above: **1770 bytes, sha256 `bfd3392c`,
  `voice_model en_US-joe-medium`, before and after.** A dial that can be turned and turned back
  is the only kind that is safe to demonstrate on a file that holds credentials.
- The Third Door hears **switch · change · sound like · speak with · cast**, next to "voice" —
  both spoken sentences above went in through it, one with *switch*, one with *speak with*.
- The casting panel remains the audition room (§6). It auditions; the dial decides.

## 14 · The Open Ear — one click, three questions, and a goodbye

```
  EMPLOYER  [clicks the ear once]
  EMPLOYER  what is the web gate
  BUTLER    According to current web sources, the term most likely intended is a "secure web
            gateway" (SWG): per Microsoft Security, a cybersecurity solution t…
  EMPLOYER  and what does the third door do
  BUTLER    A third door is beyond my remit, sir; nothing in your notes describes one. They run
            to equipment loans, regulars, feedback, subscriber churn, whole…
  EMPLOYER  tell me about the antecedent memory
  EMPLOYER  [speaks over him] hold on, actually
  BUTLER    [stops mid-sentence, listening]
  EMPLOYER  thank you, goodbye
  BUTLER    A pleasure, sir. Goodbye.
  EMPLOYER  [clicks the ear again, and then says nothing at all]
  BUTLER    I'll let you work, sir.

  clicks in the three-turn conversation above: 1
```

**One.** The click counter is incremented by the one function in `conversation_proof.mjs` that
can dispatch a mouse event at all, so "one click" is arithmetic rather than a description of
what the harness meant to do. Three questions, three answers, and the ear re-armed itself
between them 400 ms after his voice ended — and the answers went through the ordinary funnel,
which is why the first one is a web answer with a citation and the second is a refusal to invent
a third door.

**The barge-in, in one frame.** Speech over the butler, and the same tick read back:

```
mid-answer  {"queue":1,"bus":1,"zeroed":false,"draining":true,"caption":true,"arms":3,"listening":false}
the instant  {"vad":{"level":0.25,"speech":true,"over":3,"bargeIns":1},"bus":0,"zeroed":true,
              "queue":0,"draining":false,"caption":false}
             notes: "speak: queue emptied by a barge-in (one of the three)"
             arms 3 → 4
```

The gain node reads **0**, not a fade and not a scheduled ramp: whatever syllable was in flight
is inaudible before it is gone. The rest of the answer is **cancelled** rather than waited out,
the subtitle goes with it — a caption for a sentence nobody heard is a caption for a sentence
that was not said — and the recogniser comes **up** in the same breath, because an interruption
is the start of the next thing he wants to say. Still one click: a barge-in is not a button
either. Note `listening: false` while he read the answer: the session is open, the microphone is
not being transcribed, which is how he avoids reading his own sentence back to himself.

*(That line cost a real bug. `earRearm`'s timer guarded only on `speakDraining`, so 400 ms after
a question was asked — while the machine was still **thinking** — the microphone came back up and
stayed up through the entire answer. The guard is now `busy || speakDraining || speakQueue.length`
at `viewer/index.html:9096`, which are the same three terms the watch asks about, because "is
this turn over" should have one answer and not two.)*

**The closers, the clock, and the seal.** Four closers, published as patterns and matched
against a normalised transcript, each with its own parting: *that's all* → "Very good, sir.";
*thank you, goodbye* → "A pleasure, sir. Goodbye."; *end conversation* → "The conversation is
closed, sir."; *good night* → "Good night, sir." A second session, with the courtesy clock
shortened to 4 s, closed itself on silence with the line the spec names — **"I'll let you work,
sir."** — and put the microphone down as completely as a closer does.

```
seal   at rest=ready → ear open=OPEN:listening → speaking=OPEN:speaking → closed=speaking → at rest again=ready
```

`EAR OPEN` for exactly as long as the session lasted, **including while he was talking**, and the
engine named beside it. The engine word has exactly one producer in the page and the only two
words in it are `browser` and `none` — so *"never claims to be local when it is not"* is a fact
about the source, not a promise about behaviour. The clock is the **server's** 45 s, read from
`/health` rather than kept as a literal in the viewer. Ambient always-on listening is published
as a refusal rather than left to be inferred.

**Nothing is kept.** `MediaRecorder` was replaced with a counting constructor before the first
click and **never constructed once** across two sessions, four turns and a barge-in — and the
page's own source never names it outside a comment. One microphone per session and not one more:
2 asks for 2 sessions. Nothing buffered, the transcript spent and cleared, and the page threw
nothing through the whole conversation.

## 15 · The vanishing input

There is **no standing textarea in the page** — the assertion is made against the DOM, not
against a screenshot. The bottom bar is the state seal on the left (`READY` / `LISTENING` /
`SPEAKING`, and `EAR OPEN` with the engine while a session is up), the organ rail centre-right —
the same five ids every harness already clicks — and a single `/` glyph on the right. It is
visible in every full-frame plate in this document — seal, then the five organs (screen, eye,
focus, mic, reset), then the slash — and no field anywhere along it.

Typing is summoned: a real `/` keypress through the browser's key queue raises the line, and
`tools_live.mjs` types through it rather than calling `typeLine.raise()`, because a proof that
used the door would stop proving the keyboard works. Answers stay subtitles — a caption above
the bar, gone 4 s after his voice ends — and a cancelled answer's caption goes with the answer
(§14).

## 16 · The summary lines

Every harness in the matrix, run **solo on a quiet machine**, on 25 September 2026, with the
presence docked and FACE mode live:

```
preflight.py            14 pass, 0 fail, 3 warn
conversation_proof.mjs  VERIFY 69/69 PASS        (the face docked through all of it, 60 fps)
deck_proof.mjs          VERIFY 195/195 PASS      (60.1 fps with FACE live; root dPos 0 · dQuat 0)
voice_proof.mjs         VERIFY 130/130 PASS      (mouth peak 0.8642, every moving frame analyser)
layout_proof.mjs        VERIFY 72/72 PASS        (the well never touches toast, card or panel)
desk_proof.mjs          44 checks, 0 failed      (the miniature mirrors across the PiP boundary)
tools_live.mjs          VERIFY 50/50 PASS
focus_probe.mjs         78 checks, 0 failed  ·  PROBE 26/26 PASS   (the Eyes Law, both ways)
```

Zero failures. The three preflight warns are the documented environmental ones (§8): warns 10
and 12 for the absent key, warn 11 for no Chrome-family browser on the DevTools port at that
moment. Only `fail` judges the code.

Two of those lines are worth a sentence, because they were failures first and the failures were
instructive. `deck_proof` read 53.4 fps and `voice_proof` a 2776 ms gap between chunks while
four stray Chromes from a killed run were still alive; solo, the same measurements read 59.2 fps
and 6 ms. **These harnesses share a camera, a screen share, a focus ledger and a PiP window, so
a number measured while another one is running is not a number.** And `voice_proof` failed
`15 queued / 14 played` because of its *own* `sleep(1500)` before it cleared the boot greeting:
on a slow synthesis the cancel discarded a queued chunk, and `speakCancel` does not adjust the
FIFO's cumulative counters, so the session-wide equality broke permanently. A harness with a
hard-coded sleep where a wait belongs can manufacture the exact defect the next assertion
detects; the fix was in the harness — wait for the queue to run dry — and not in the assertion.

**What §§10–17 do not claim.** The plates were captured headless on this GPU, so they are what
the renderer draws and not what a projector would. No claim is made here about how the voices
*sound* — only that the recast landed, was announced in the voice it named, and was put back.
The Open Ear's recognition is Chrome's, which is why the seal says `browser`: nothing in §14
claims local recognition, and the page cannot say the word. One explicit click per session
remains the privacy contract, by design.

## 17 · The face, the eyes, the still frame and the AGI card

### 17.1 · The presence, docked

There is a **reserved presence well** right-of-centre, and the hologram in it belongs to the
Layout Governor rather than to the stylesheet. The governor assigns a square, tells the renderer
the number rather than asking it to measure a box mid-transition, and publishes both the square
and its reason. Three widths, read off `layout_proof.mjs`:

```
1280x860   {"fits":false,"why":"no room: 12px of 168","side":12}     the well stands down
1600x860   {"fits":true,"why":"beside the toast","side":172}         canvas 1180 · midpoint 1068
1920x860   {"fits":true,"why":"beside the toast","side":259}         canvas 1500 · midpoint 1272
```

At both widths where it fits, the toast, the session card, the note panel, the telemetry rail and
the legend are each measured against it and none of them touches it — and the renderer took the
same 172 px and 259 px the governor assigned, at `dpr 1.5`, so the canvas is never a frame behind
its own width. **`fits:false` is the governor working, not failing:** a canvas with no `PRES_MIN`
square left in it after the card, the chips and the toast have been served has nowhere to put a
hologram, and four faint brackets around a cropped face would be worse than none.

`PRES_MIN` is **168** and not 176, and that number came from a measurement this pass. A 1600 px
window leaves the well 172 px once the toast has taken its column; standing the machine's face
down over four pixels is the governor being fussy rather than protective. 168 still has teeth —
1280 leaves 12 px and is refused.

Plate: `deck-presence.png`, the whole deck with the face docked in its well.

### 17.2 · Three modes, one Points object

```
face 10400 pts      ring 5092 pts      cube 8748 pts
objects 1 · materials 1 · shader true · capacity 10400 · three r183
```

Side by side at 2x from the well itself: `deck-presence-face.png`, `deck-presence-ring.png`,
`deck-presence-cube.png`. All three switch from the **Command Panel's own call**, and the counts
are measurements off the scene graph rather than claims — a second object added by a later edit
would read as a `2` here, and a `MeshStandardMaterial` that happened to draw something
face-shaped would pass every count and fail `shader`.

The expensive part is what is *not* there. `deck_proof` recorded 300 frames with FACE live and
then asked the buffer how many times it had been rewritten:

```
NO PER-FRAME GEOMETRY REBUILDS: the attributes were written 2 times for 2 mode switches
and not once during 300 frames
and each one cost EXACTLY ONE attribute write - 4 for the life of the page - while asking
for the mode already on the glass cost nothing at all
```

### 17.3 · The audition, and the two numbers in it

FACE auditions exactly as the bloom does: a baseline, a 3 s trial, a floor of 55 fps and 90 % of
baseline to keep.

```
the audition: baseline 40.8fps with the ring, trial 60.3fps with the face, verdict "kept"
THE DECK HOLDS 60.1fps WITH THE FACE LIVE, above the 55fps floor - 10400 points, a live
analyser tap and thirty textured worlds, on ANGLE (Intel(R) Arc(TM) 140V GPU, D3D11)
and IT RIDES THE ORBIT LOOP rather than a second one: the presence drew 300 frames while
the page drew 300 - one tick, not two
```

**The trial is the higher number, and that is not a paradox.** The ring's baseline is sampled
while the worlds are still being built at boot, so 40.8 fps is the cost of thirty textures
arriving, not the cost of a ring. The audition is deliberately left that way: it measures *this
machine at this moment*, which is the only question worth asking before putting ten thousand
points on the glass, and a baseline taken later would flatter the face.

It degrades for real, too. `voice_proof` — a run that also holds a synthesiser, an analyser and a
live microphone — was told `audition: 53.9fps with the face against 51.6fps with the ring (floor
55, keep 90% of baseline)`, the ring stood in, and the trace said so once. That harness then asked
for the face **by hand**, which is the one caller allowed to clear a degrade: you asked for it
after being told it would not hold, which is a decision and not a mistake.

### 17.4 · The mouth, in the same signal as the voice

`voice_proof.mjs`, sampling from inside the page every 60 ms through one real sentence:

```
at rest before the line: {"level":0.0095,"from":"rest","mode":"face","pose":"idle"}
the loop: 561 frames -> 622 frames in a second, level 0 through all of them
mouth: 63 samples · peak 0.8642 · 44 over 0.12 · sources {"analyser":61,"rest":2}
```

Plates: `voice-face-idle.png` (FACE mode, nothing speaking, the lips at rest) and
`voice-face-speaking.png` (mid-sentence, `level 0.2583` from `analyser`).

Two of those lines are there because of a defect in an earlier draft of the harness. **A frozen
level reads exactly like a shut mouth** — `presFrame()` early-returns while the well is standing
down, which freezes the published `level` at whatever it last painted — so "the mouth is shut
before a word is spoken" is asserted *with a frame count beside it*: 61 frames were drawn during
that second, and the mouth stayed at 0 through all of them. The mouth also moves only on real
samples: every moving frame named `analyser`, an `AnalyserNode` tapped off `speechBus`, which is
why a barge-in shuts this mouth for free rather than by a second piece of code remembering to.

### 17.5 · The Eyes Law — the same variable, twice

`focus_probe.mjs` drives Chrome's fake camera on the **real** page, and every assertion below is
made against a hologram that is on the glass (`THE HOLOGRAM IS ON THE GLASS on the real page, so
the eyelids below are geometry and not just a number`).

```
THE TABLE HAS THREE ROWS: shut 0, sampling a HALF, watching 1
CAMERA OFF: the variable says "shut", eyesLive() agrees, both EYES LIVE surfaces dark
AND THE FACE IS NOT LOOKING: the hologram was told lid 0 and its geometry eased to 0
CAMERA ON: the variable moved to "sampling" - the landmarkers are still waking, so the
   eyes are HALF open, which is the third state earning its keep
and the EYES LIVE seal lit in the same breath - one variable, two surfaces, asserted together
AND IT BLINKED ON WAKING: 1 open, 1 blink
THE INSTANT THE CAMERA RELEASES: state "shut", eyesLive() agreeing, the table's lid back
   to 0 and both seal surfaces dark - one call moved all four
and THE FACE WAS TOLD WITHIN ONE FRAME: the lid the shader is handed read 0 at the instant
   of the call and 0 one frame later, with the eased geometry at 0.2261 and still travelling
with a SLOW BLINK ON CLOSING too: 1 close, 2 blinks for one open and one close
```

Plates, side by side: `focus-eyes-shut.png` (camera off) and `focus-eyes-open.png` (camera on).

The distinction in the last three lines is the whole law. `sightSet()` is the only writer and it
moves the variable, the seal and the pure lid **synchronously**; the *geometry* eases over a blink
in the frame loop, one frame later. So the release is asserted twice — instantly on the variable,
and within one frame on the number the shader is handed. What is never true is a face that looks
while the camera is off: `conversation_proof` runs a whole session with a live microphone and no
camera, and the last thing it checks is that the eyes were **shut** through all of it — the Eyes
Law does not care that the ear is live.

### 17.6 · The still frame

The galaxy root does not travel. `deck_proof` holds the pointer still for 30 s and then reads the
watch that has been checking the root all along:

```
holding the pointer still for 30s - hands off the mouse
THIRTY SECONDS OF STILLNESS: the camera quaternion is unchanged to four decimals
still frame: world ancestor "Group" pinned at [0,0,0] · dPos 0 · dQuat 0 · 2791 holds, 0 corrections
AND OVER 30s OF IDLE IT NEVER TRANSLATED: the largest position deviation ever measured is 0
and it never turned either: largest quaternion deviation 0 - the root holds [0,0,0,1]
and the pin never had to FIGHT anyone for it: 0 corrections, so nothing in the page is
   writing to the root behind its back
and the watch was AWAKE for the hold: the pin checked the root 1800 times in those 30s -
   a sleeping watch would report a deviation of zero too
of 30 built worlds, 30 turned on their own axes and 30 moved along their micro-orbits
THE SKY IS STILL, NOT FROZEN: 30 of 30 worlds turned on their own axes (at least 24 required)
and 30 of 30 rode their micro-orbits: motion INSIDE the frame is what the still frame is for
```

Three of those assertions exist to stop the other four being cheap: **0 corrections** says nothing
else in the page is fighting the pin, **1800 checks** says the watch was awake, and **30 of 30
worlds turning** says the sky is alive. A frozen page would satisfy `dPos 0` perfectly.

### 17.7 · The AGI card

The focus card has shed its rounded-rect normalcy. Read off the live page rather than a
stylesheet:

```
cuts 4 · brackets 4 · traces 4 · scans 1 · cells 3 · cols 2 · radius 0px
clip-path polygon(15px 0, 100%-15px 0, 100% 15px, 100% 100%-15px, 100%-15px 100%,
                  15px 100%, 0 100%-15px, 0 15px)
framePE "none" · frameZ "-1" · aria-hidden "true"
sparklines sp-drift / sp-clean / sp-streak, each a 96x11 box · tv ["0.0","100%","2"]
mini {"w":30,"h":30,"tag":"CANVAS","hdr":"fh"} · 5 keyframe rules, none off transform/opacity
```

Close-up: `layout-agi-card.png`, at 2x and running.

Three of those numbers are laws rather than decoration. The frame is `pointer-events: none`, at
`z-index: -1` **under every character on the card**, and `aria-hidden` — so none of it can be
pressed or read aloud, and the text-inside-box law is untouched: 21 line boxes inside the padded
box, worst overhang 0 px, and the unbreakable 86-character intent did not widen the card past
460 px. The micro-telemetry digits are the **same numbers the card is running on** — `clean 100%`
and `streak 2` straight off `fx`, not off a second source. And all five animations are cheap.

The miniature in the header is the same hologram, not a second instrument. On the desk, inside the
PiP document:

```
THE MINIATURE PRESENCE IS ON THE DESK CARD: a 26px canvas in the header row, 26px of the 320
and it is a PICTURE of it: 369 lit pixels in the canvas out there (ring mode)
AND THE MIRROR IS LIVE ACROSS THE DOCUMENT BOUNDARY: wiped by hand, and 336 pixels came back
   within a second - 19 more frames of the well drawn into a canvas in another document, off
   the one canvas and no second renderer
the card's rows FIT the window they were given: 239.33px into 239.33px
the rows, in order: aframe 239.33 | fh 20 | aclock 40 | fbar 3+9px/8px | focus-stats 31 |
   frow flock 28+34.6667px | frow 28+10px
```

When there is no room for a well, the miniature is **correctly blank** and says why: `the governor
stood the hologram down (no room: 5px of 168)`. A miniature that kept drawing a face the main
window had stood down would be the metaphor lying in small print.

That row breakdown is in the log for a reason. `desk_proof` first read `253px into 240px` and the
obvious conclusion — the card has outgrown the PiP window — was wrong: `.aframe` is `inset: 0` and
out of flow, so a row-sum that counted it was measuring the whole card plus its own bottom
padding, and no window size could ever close the gap. The harness now sums the **rows**, skips
absolutely-positioned children, and prints them, so the next row added to this card is a number
someone can read rather than a shortfall to chase.

### 17.8 · The conversation, in front of it

`conversation_proof.mjs` — one click, three turns, a barge-in and a courtesy closer — now ends by
turning round and looking at the hologram:

```
the governor at the end of it: {"vw":1578,"vh":846,"panelOpen":true,"canvasW":1158,
  "toast":{"width":760,"left":199},"well":{"fits":true,"why":"above the toast","side":220}}
the audition: kept - 60.3fps with the face against 60.3fps with the ring
AND THE PRESENCE WAS DOCKED THROUGH ALL OF IT: a 220px well above the toast, 2396 frames at
  60fps in "face" mode (the audition said kept), and the conversation happened in front of it
with its eyes SHUT, because this room has a microphone open and no camera
```

That harness was given a **1600 x 1000 window** for this pass, and the reason is worth recording
because it is the governor being right. At 1280 x 880, with a long answer open, the band above the
toast is shallower than the 168 px floor and the strip beside it came to **one pixel** — so the
well stood down, exactly as §17.1 says it should. The spec asks for this conversation to happen in
front of the presence; the honest way to get that is to give the room a window big enough to hold
a face, not to assert around a governor that is telling the truth. The mode is reported and not
demanded, too: whichever mode the audition chose is the one asserted, and the probation verdict is
printed beside it so the line is never a shrug.

### 17.9 · What §17 does not claim

The plates are what this renderer draws on this GPU, headless, at 2x from the well — not what a
projector would. The face is **light and never a mesh**: `shader true`, one material, and the brow,
cheekbones and lips are readable in the *density* of 10,400 points, which is a thing to be looked
at in `deck-presence-face.png` rather than asserted by a counter. No claim is made that FACE mode
will hold 55 fps on any other machine — that is precisely why it auditions, degrades to RING and
says so once. And the Eyes Law is a claim about this page's own camera state: it says the face does
not look while the Eyes organ is off, which is a statement about the metaphor, not a statement
about anyone else's camera.

## 18 · Galaxy — the protected classes, the watchdog, the lock and the head

This section is written in the order the work was done, and it opens with research rather than with
results, because the mandate asks for the real mechanics of each Part before a line of that Part is
written. Every paragraph below is something that was **measured on this machine**, and several of
them contradict what I believed when the round started. Where a finding cost me a wrong edit, the
wrong edit is named too: a lookbook that only records the things that worked is a brochure.

### 18.0 · Research — the microphone, the echo canceller and the barge-in reference (Part C)

Chrome's echo canceller cancels audio *Chrome itself rendered*, and it does it well enough to be the
central fact of this Part. With the page's ear open, a fixture sentence played from inside the page
read **0.0256** on the page's own analyser against a **0.0269** silence floor — indistinguishable
from silence — while the identical wave played by an external `powershell` process read **0.1723**.
The render reference is what makes the difference: Chrome knows what it sent to the speakers and
subtracts it, and an external process is not in that reference. Two consequences follow, one for the
product and one for the harness. For the product: a naive barge-in gate that simply watches input
level would still be half-defensible, because the AEC already removes most of Galaxy's own voice —
but "most" is not "all", and the residue that survives cancellation rises with speaker volume, so a
fixed threshold is a volume-dependent bug waiting to be reported as "he interrupts himself". Hence
the mandate's ratio: input measured against the **live output RMS tapped off the speech bus**, 1.6×
sustained 250 ms, and nothing at all in the first 800 ms of an answer — a gate immune to both the
absolute volume and the transient at the start of a phrase. For the harness: a spoken fixture can
never play its own audio through the page, which is why `tools/mouth.mjs` spawns a player process.
It is also the honest simulation — a person in the chair is not in the AEC's render reference
either. Worth recording as a negative result: `echoCancellation: true, noiseSuppression: true,
autoGainControl: true` — exactly what Part C requires the ear to open with, and exactly the
processing one would expect to eat a far-field synthetic voice — transcribes as reliably as raw
capture. The noise suppressor was the prime suspect for a week and was innocent.

### 18.1 · Research — recognition restart semantics, and a finding that was not one (Part E)

Part E asks for recognition errors to auto-restart with backoff, which presumes one knows what the
errors are. The mechanic that matters most here is not in the specification of the API at all. **The
cloud speech service throttles silently and raises no error**: past some number of sessions it fires
`audiostart`, `soundstart` and `speechstart` into a room the analyser reads at 0.4, returns no
result, and reports no fault. The proof is one spike run unchanged three times inside forty
minutes — **6 of 6, then 1 of 6, then 1 of 6**. A watchdog built against that behaviour would be
built against a wall: there is no error event to count, no `error.error` to back off from, and the
seal would read `LISTENING` while the ear was functionally dead. That is the strongest argument for
the change this round made to the page — it now prefers **on-device recognition**
(`SpeechRecognition.available` / `install`, shipped in Chrome 138; this machine runs 153), which has
no quota behind it, punctuates and capitalises its results, and keeps the boss's words in the room,
which is the page's whole claim about itself. One trap on the way in, and it is a one-word bug with
a silent symptom: `available()` and `install()` are statics on **`SpeechRecognition`** and are *not*
on the `webkitSpeechRecognition` alias, so reading the alias first made the page report "this build
has no `SpeechRecognition.available()`" on a Chrome that has it, and go on posting the boss's speech
to the throttled service. The standard name is now read first and that order is load-bearing.

The cost of learning this is the part worth keeping. Under that throttle I measured, carefully and
repeatedly, that *a reused recogniser instance goes permanently deaf*: freshly constructed instances
heard, restarted ones fired every event and returned nothing, at 400 ms after the stop and at three
seconds alike. I believed it, wrote it into the spoken harness's header as finding 7, and **edited
`startListening()` to retire and rebuild the recogniser on every arm**. It was an artefact: the
quota was draining across the run, and the "fresh" instances were simply the ones that happened to
be early. Re-run on-device, reuse scores `fresh=true reuse=true reuse-far=true fresh-again=true`.
The edit is reverted, the comment at that site now records why reuse stays, and the rule is written
where the next person will meet it: **a platform finding taken during a throttle is not a finding.**
Everything else in that spike series was eliminated the same way, and the negatives are worth as
much as the positive — it is not the turn number, not the phrase, not the phrase length, not the
language, not stale or quiet cached waves (measured 0.167–0.214 RMS, all fine), and not transcript
capitalisation (`/chat` returns the same `kind` and the same node count for `who are you` and
`Who are you`).

One adjacent mechanic, established while proving the above and load-bearing for every spoken fixture
in Part H: **`listening === true` is not a promise that anything will be heard.** A session one tick
from its own no-speech timeout reports itself as listening, and speaking into it returns neither a
transcript nor an error — a silent false negative indistinguishable from a routing bug, which is
exactly the kind of test the mandate forbids. The fixtures therefore wait for `listening &&
analyser`, record *which* arm they are about to speak into, settle 1800 ms, and re-check that the
arm counter has not moved underneath them; the measured distances behind those numbers are ~150 ms
from `.start()` to `audiostart` and ~2 s to the first `soundstart` the engine will honour. Chrome
will also only transcribe for a page that has rendered audio itself at least once, so the room is
warmed with a half-second tone through a real user gesture before the ear is ever opened. And there
is exactly one recogniser per page: a second `start()` aborts the first.

### 18.2 · Two defects the spoken fixtures found before a line of Part A was written

The rule that every fixture must also run out loud earned itself on its first successful run, which
found two real bugs the typed pass cannot see.

The first is a routing defect, and it is the exact defect Part A exists to remove: spoken aloud into
the real microphone, **"can you listen to me" was answered from the web** — "According to current
web sources…" — rather than from live state. Whether the ear is open is not a question about the
world, and it must never cost a lookup.

The second is a bookkeeping defect the typed path hides. **One spoken utterance increments
`__galaxy.ear.turns` by two.** Measured at the wire with a `window.fetch` wrapper, exactly one
`/chat` leaves the page per utterance — so this is not a double question and not a double cost — but
`turns` is the number the Open Ear's own contract is stated in, and "one click, three questions"
reading `6` in the trace makes a true claim look like a false one. `flushThought()` has three
callers and two of them fire for a single phrase: `armFinishTimer`, `earSpeechEnd`'s end-of-speech
flush, and `r.onend`'s salvage flush, with both increments landing between 2.05 s and 2.56 s around
`.stop()` / `FINAL` / `end`. It is fixed where turn semantics belong rather than patched at the
counter.

### 18.3 · The watchdog, built and bitten (Part E)

**What was added.** Three things, all in `viewer/index.html`, and none of them visible until
something goes wrong — which is the point.

1. **The ear admits a fault.** `earFaultPaint(errors, why)` raises a fault after
   `EAR_FAULT_AFTER = 3` consecutive hard recogniser errors. The seal then reads
   `ear fault · retrying` (stored lowercase; `#seal` is `text-transform:uppercase`, so he sees
   **EAR FAULT · RETRYING**) with `data-state="fault"` and its own amber. The existing
   backoff — `EAR_REARM_MS * 2^hardErrors`, capped at `EAR_BACKOFF_MAX_MS` — was already
   correct and is untouched; what was missing was the admission. The fault clears itself in
   three places, all of them recoveries rather than clicks: a result arrives, a `no-speech`
   comes back (the recogniser ran a whole session and reported a quiet room — a *working*
   ear), or the session is closed.
2. **A heartbeat.** `setInterval(heartBeat, HEARTBEAT_MS)` at 500 ms, started above the probe
   fork so it is never conditional, published on `__galaxy.pulse`. `setInterval` and not
   `requestAnimationFrame`, and the reason is the whole value of the instrument: rAF is
   throttled to nothing when the window is occluded, so a missed rAF means *the window is
   behind another window* and nothing more. A late `setInterval` means the main thread could
   not get to it.
3. **A blocker, named in words.** Two or more missed periods count a stall; while the page is
   *idle* the stall is also written into the trace with a sentence saying who was holding the
   thread — read from counters other parts of the page were already keeping (the deck's frame
   count, the ear's analyser frames, the speech FIFO), so it costs nothing and cannot drift.

**The identifier that could not be called PULSE_MS.** The page already had
`const PULSE_MS = 1600` — the birth pulse of a newly captured note — and `__galaxy.capture`
publishes it, so a harness reads it. The heartbeat's constants are therefore `HEARTBEAT_MS`
and `HEARTBEAT_NOTE_MAX` while the public surface stays `__galaxy.pulse`, which is what the
mandate names. Chrome reported the collision honestly (`Identifier 'PULSE_MS' has already been
declared`) and the whole page died at parse — a reminder that in a single-scope page of fifteen
thousand lines, a new top-level `const` is a global.

**A rate, not a presence.** The first version of the blocker line asked only whether the
deck's frame counter had moved, and across a measured 1.6-second block of the main thread it
reported *"the deck kept drawing (31 frames), so whatever blocked this timer was not the
renderer"*. True as arithmetic and false as a bug report: 31 frames in 2.08 s is fifteen a
second, and the renderer was starved right along with the timer. It now compares what was
drawn against what the elapsed time was owed, and a third or less means the render loop was
inside the stall. **A stall named with the wrong culprit sends somebody to the wrong file.**

#### The fixture, and how a service is made to fail honestly

`conversation_proof.mjs` gained four sections (93 checks, all passing). The recognition service
cannot be unplugged on demand — pulling the interface down takes the server with it, and
Chrome's speech endpoint is not a URL this page requests — so the fixture replaces
`SpeechRecognition.prototype.start`: an *armed* attempt reports `network` through the page's
own `onerror` and then its own `onend`, which is the exact shape Chrome produces when it cannot
reach the service. Everything downstream — `hardErrors`, the doubling backoff, the seal, the
note — is the real code reached through the real event. The other half matters more: **"recovers
without a click" cannot be observed from a failure alone**, so when the fixture plugs the
service back in it gives the answer a working recogniser in a quiet room gives — `no-speech` —
and the page is left to do what it does with it.

The backoff is measured off the page's own timer, not polled from Node. The first attempt at
that assertion sampled `ear.rearmIn` from outside every 250 ms and **missed the 800 ms step
entirely** (it recorded 400 → 1600 → 3200 and failed); a CDP round trip plus a sleep is not a
clock. The injector now stamps `Date.now()` in the page each time it fires, and the intervals
between the stamps are the intervals the page chose.

```
  ·· 3b · the heartbeat across three turns
  note the conversation lasted 52s of heartbeat time; camera=true reading
       {"present":true,"headDown":false,"slouched":false} face=face at 60fps
       ear=true (3553 analyser frames)
  ok   NO STALL ACROSS THE THREE-TURN CONVERSATION with the eyes, the ear and the face all
       live: 104 beats, 0 stalls and 0 missed beats inside the window
  ok   and the beats account for the time: 104 of the 104 the wall clock owed
  ok   and this was measured with the room ACTUALLY OCCUPIED - camera live and reading a
       body, 3553 analyser frames, the presence drawing "face" at 60fps, and the ear still
       open on that one click

  ·· 3c · the ear fault and the recovery
  ok   THREE FAILURES IN A ROW AND THE SEAL SAYS SO: hardErrors=3, fault on
  ok   and the word is the admission the spec asks for - the bar reads EAR FAULT · RETRYING
       in its own amber state, not READY
  ok   and the SESSION IS STILL OPEN while it retries
  ok   THE RETRIES BACK OFF rather than hammering: the page waited 830ms then 1633ms between
       attempts and is now standing off 3200ms - 400 doubled, three times
  ok   AND IT RECOVERS WITH NO CLICK: the service answered once and the fault cleared itself,
       hardErrors back to 0
  ok   STILL ONE CLICK after a fault and a recovery: 1
  ok   and it was ONE episode rather than three - the fault is a state, not a per-error flash
  ok   and the trace names it in words: "pulse: the ear has failed 3 times in a row (network)
       · the seal reads EAR FAULT and the retry stands at 3200ms"

  ·· 8 · the watchdog, proved by stalling the page on purpose
  ok   A 1.6s BLOCK IS SEEN, and counted as one stall of 2 missed beats
  ok   IT IS NAMED IN THE TRACE while idle, in words, once: "pulse: MISSED 2 BEATS while idle
       (1745ms between beats, beat 151) · the blocker: the deck was starved with it (11 frames
       where 104 were due, 6fps) - a long task on the main thread · the speech queue is
       mid-flight (7/8 played)"
  ok   and the blocker NAMES THE MAIN THREAD rather than shrugging or blaming the renderer
  ok   and the heartbeat is still beating after the stall it reported
```

Section 8 comes last on purpose: it blocks the main thread for 1.6 seconds with the ear shut
and nothing being asked, because **a "no stall" result is worth exactly as much as the detector
behind it, and a detector nobody has ever seen fire is a comment.**

#### Two findings the watchdog produced the first time it ran

Both were found by the instrument, not by reading the code, and neither is fixed by Part E.

**1. Opening the camera can freeze the page for four seconds.** `eyes.on` goes true when the
*stream* is live; the landmark reader is built after that, and building it compiles the
MediaPipe vision bundle (`tasks-vision@0.10.14`, GPU delegate). The watchdog measured a
**4207 ms** gap at that moment and named it correctly — *"the deck was starved with it (5
frames where 252 were due, 1fps) — a long task on the main thread"*. It is a one-time cost at
the instant the camera opens and it is not what "no stall across three turns" is a claim about,
so the fixture waits it out before taking its baseline and reports it as a note. **The fix is a
worker**, which is a change to the eyes pipeline and not to this Part. Note also that the
cold-start stall is *counted* but not *named in the trace*: naming happens only while the page
is idle, and a camera opening inside an open ear is not idle.

**2. The audition can be poisoned by a transient, and it costs him the face.** The presence
mounts when the layout governor has a well for it — which is after the first answer — so the
audition and the camera's model compile land in the same few seconds no matter which is started
first. Twice, the audition measured **8–9 fps for the face against 59 for the ring** and stood
the face down for the whole session; once, with the compile finished first, it measured **60 fps
and kept it**. The guard is behaving exactly as written; what it timed on those two runs was a
four-second freeze belonging to a different organ. The audition guard is out of scope for this
round by instruction, so this is recorded rather than changed — **but it bears directly on Part
G**: a fourteen-thousand-point volumetric head will be auditioned in the same room, in the same
few seconds, against the same ring.

### 18.4 · Research — what CDP will and will not tell you about which tab you are on (Part F)

Part F asks for "real teeth via CDP", and the teeth turn on one question: **how does a process
outside the browser learn which tab you are looking at?** There is no event for it. `Target`
domain events fire on creation, destruction, navigation and title changes; none of them fire when
you press Ctrl+Tab. `Target.getTargets` reports a target's type, url, title and whether a debugger
is attached to it, and nothing about whether you can see it. So the answer has to be asked of the
pages themselves, and the property that answers is `document.visibilityState` — which is what
`focus.py` already rests on, and which I measured rather than trusted (`_partF.mjs`, a headed
Chrome on port 9271, two tabs in one window plus a second window):

| what was in front | the locked tab's `visibilityState` + `hasFocus()` |
| --- | --- |
| a *different tab* in the same window | `hidden`, no focus → bits **0** |
| the locked tab, its window frontmost | `visible`, focused → bits **3** |
| the locked tab, but **another window** in front | `visible`, **not** focused → bits **1** |

That middle row is the whole design. **Bit 1 is a pure statement about tabs** — it is set for the
active tab of *every* window, even with the entire browser in the background — and bit 2 is a
statement about windows. So the two organs divide cleanly and neither is asked a question it
cannot answer: **the operating system says which application is in front** (`GetForegroundWindow`,
which `TargetReader` already reads), **and the browser says which of its tabs is the live one**.
Reading tab-ness off bit 2 would have been the easy mistake: it reports a drift every time the
boss clicks on VS Code, which is a drift the app read already catches and would then double-count.

Three measurements decided the rest. **Latency:** after `/json/activate`, the outgoing tab reported
`hidden` and the incoming tab `visible` **13 ms** later — the flip is immediate, so the 1.5 s the
mandate allows is spent entirely on the poll interval and the grace, not on the browser. **Cost:**
one `Runtime.evaluate` of the expression costs **0–1 ms** on a warm socket and **1–2 ms** opening
and closing a fresh one each time, which is what `focus.py` does; at a 300 ms cadence that is under
1% of one core, so there was no case for holding a socket open. **Activation:** `/json/activate/<id>`
(i.e. `Target.activateTarget`) raised the *window* as well as re-ordering the tabs — the locked tab
went from bits 1 to bits 3 and the other window dropped from 3 to 1 — so the summon needs nothing
more, and `Page.bringToFront` is redundant on Windows. Finally, `attached` in `Target.getTargets`
was `true` for exactly as long as a socket was open and `false` within a second of closing it,
which is what lets "no CDP session left attached" be asserted rather than asserted-ish. Note what
that also means: because the watcher opens and closes a socket per question, *nothing is ever left
attached by construction*, and the leak actually worth testing for is a **watcher that keeps
polling a tab after the session ended** — a thread reading the boss's tabs on his behalf and
nobody's instruction. That is the failure mode `lock_proof` asserts against, not the attachment.

**And then the relaunch, where the research overturned the plan.** Part F specifies the no-port
path as a gated hand wrapping `launch-chrome.ps1`, "session restored", and I had assumed the
restoring would be a flag. It is not. `launch-chrome.ps1` opens with `taskkill /IM chrome.exe /F`,
and on this machine at the moment I ran it that would have killed **nineteen processes of the
boss's ordinary browsing** — his real windows, in the default profile, which the relaunch does not
even reopen. So I measured the flag that was supposed to repair that: after `Stop-Process -Force`,
a relaunch with `--restore-last-session` came back with **a new tab and nothing else**
(`_partF2.mjs`). A force kill is a crash; Chrome writes `Last Session` on a clean exit, and after
an unclean one it has a bubble to offer instead of a session. The promise was not keepable the way
it was written.

Two further measurements made it keepable, and both changed the code. First: with the default-profile
browser running, a second Chrome on its **own** `--user-data-dir` opened the DevTools port in
**332 ms and the nineteen processes were still there afterwards** (`_partF3.mjs`). The launcher's
kill is justified by a real hazard — a browser already running *on the same profile* swallows the
launch and exits — but that hazard is per-profile, and the launcher always uses a profile of its
own. So in the ordinary case the hand must **destroy nothing**, and "session restored" is kept for
free by never taking it away. Second, for the one case that does need the profile cleared — a
portless Chrome already running on the devtools profile — a **polite** close keeps the promise
where a kill does not: `CloseMainWindow()` (WM_CLOSE, which is what the X button sends) emptied the
profile in under 250 ms, and the relaunch with `--restore-last-session` came back with **both tabs
plus the viewer** (`_partF4.mjs`). That is now what the launcher does: close only the processes on
its own profile, politely, force only a straggler, and never speak to any other Chrome on the
machine.

### 18.5 · The lock, on a real port-launched Chrome (Part F)

`lock_proof.mjs`, **70 checks, 0 failed**, against a Chrome launched by the hand itself on its own
profile. The episode the mandate asks for, lifted out of the run with the harness's own clock on it:

```
   59.05s  ok   THE LOCK COMPLETED ITSELF on the tab he went to, with no second press:
                lockedTab="Example Domain"
   59.05s  ok   one press of the pill in this whole session: presses=1
   59.05s  ok   and the title on the card is at most 24 characters: 14
   59.06s  ok   the instrument shows one live watcher: watchers=1, watchState=on

   60.28s  ok   and the session is clean: drifts=0
   61.20s  ok   LEAVING THE LOCKED TAB IS NOTICED in 926 ms (budget 1500 ms)
   61.21s  ok   the locked tab really is behind: bits=0 (bit 1 clear is the whole signal)
   61.21s  ok   ONE callout for the episode, from the locked-tab pool:
                "The tab you asked me to hold you to is still open, sir. This is not it."
   61.61s  ok   returning to it resumes on target in 382 ms
   61.61s  ok   and says so ONCE: "Back. Thank you, sir."
   61.61s  ok   the drift is not refunded by coming back: drifts=1
   63.26s  ok   a second drift is noticed in 1606 ms
   63.67s  ok   called out again: "You have left the locked tab, sir - drift 2."
   63.67s  ok   and THEN it offers to fix it: "Shall I bring you back?"
   63.68s  ok   and again with no parameters: the locked tab lives in the session, not on the wire
   63.68s  YES - running tools/summon_tab.py
   63.91s  ok   and its stdout is the session's own sentence:
                "Here you are, sir - back where you said you would be."
   63.92s  ok   THE LOCKED TAB AND ITS WINDOW ARE IN FRONT AGAIN: bits=3
   63.93s  ok   and the record keeps BOTH drifts: drifts=2

   63.95s  ok   the session ends
   63.96s  ok   NOTHING IS LEFT WATCHING: watchers=0
   65.47s  ok   and the polling has stopped dead: watchPolls 19 -> 0 -> 0 over a second and a half
   65.48s  ok   and no debugger is still attached to the two work tabs
   65.49s  ok   a summon after the end refuses rather than moving a window:
                "There is no locked tab to bring you back to, sir."
```

Three things in there are assertions I would not have thought to write before the research in 18.4.
**`bits=0` rather than a title comparison**, because bit 1 is the only signal that means "another tab
of this window is in front" and a title check would have passed on a tab that was merely renamed.
**The drift is not refunded by coming back**, because a counter that heals itself turns the
sparkline into a record of how often he accepted help rather than how often he drifted. And
**`watchPolls` sampled three times across 1.5 s after the unlock**, because `watchers=0` is a
statement about a list and the failure worth fearing is a loop that is no longer in the list and is
still reading his tabs — which is the leak the per-question socket design makes impossible to see
any other way.

The no-port path runs in the same file and ends in a sentence rather than in a silence: `I cannot
lock a tab, sir - Chrome has no debugging port open.` → the gated ask `I need Chrome relaunched with
the debugging port to lock a tab, sir. Shall I?` → and on a refusal, `Tab-level locking is off,
then, sir: no debugging port, and you would rather I did not restart the browser. I shall watch the
application only.` No silent degradation anywhere on that path.

### 18.6 · Research — sampling a head out of points, and making depth read (Part G)

The face this Part replaces was a **relief**: a flat sheet cut to a head's outline with eight
Gaussians embossed on it. Before touching a fifteen-thousand-line page I rebuilt both the old field
and the proposed shell in Node (`_headmath.mjs`) and measured them against the mandate's own two
numeric criteria, because "it looks like a mask" is an opinion and the round needed an arithmetic.

|  | z-range ÷ width | nose above the face plane |
| --- | --- | --- |
| the old relief | **0.146** (0.55 asked) | **0.069** (0.18 asked) |
| the new shell, in Node | 1.13 | 0.22 |
| the new shell, live on the GPU | **1.132** | **0.219** |

A factor of 3.8 and a factor of 2.6 short: **no amount of taller Gaussians would have reached
either**, because both numbers are bounded by the emboss height of a sheet and the sheet has no back
to it. That is the whole case for a closed surface, and it is worth having as a number rather than
as a judgement — the emboss could be doubled and it would still fail.

**The shell is a surface of revolution by table, and it is deliberately asymmetric front-to-back.**
For a height *y* the ring has a half-width from the outline table, a forward half-depth from
`PRES_FRONT` and a rearward half-depth from `PRES_BACK` which is *larger* — 0.64 against 0.50 at its
deepest — and the deepest point of the back is not at the middle of the head but above it, at *y* =
+0.30, which is where an occiput actually is. An ellipsoid symmetric about the coronal plane is the
thing that reads as a balloon with a face drawn on it. The facial relief is then added to the
**front** half only, faded by how frontal the point is, so the brow, the recessed sockets, the
cheekbones, the lip mound and the chin displace a real surface instead of embossing a plane.

**A nose cannot be a term in a field.** It is built as its own cluster: a wedge from the bridge at
*y* = +0.16 down to a tip at −0.20 that overhangs the shell by `0.30 × (1 − f)^0.55 + 0.035` and
narrows toward the bridge, with a triangular cross-section (`u = rnd() + rnd() − 1`) so the flanks
fall away instead of ending. Two things follow that a Gaussian bump could not give: the nose has an
identity the harness can *measure* — criterion 2 is a statement about the 900 points tagged NOSE,
not about a box I drew where I thought a nose should be — and at yaw 90 it stands clear of the
silhouette, which is the only view in which a nose is a nose.

**Where the points go is a density field, and it is the part that does the drawing.** The shell is
filled by rejection sampling against a weight built out of the same Gaussians as the relief:
silhouette rim, brow, cheekbone, jawline, socket rim. Measured acceptance **0.282 — 3.54 draws per
accepted point** — which is the budget answer that mattered, because a field whose acceptance
collapsed would thin the face out silently rather than fail. Two findings came out of this and both
are in the code with their reason written beside them.

The first is the one the plates forced. The first yaw-90 plate came back **a uniform speckled blob
with a nose stuck on it**, and the reason is that the density field had a silhouette term measured
against the *coronal* great circle only: at yaw 0 that circle is the drawn edge of the head, and at
yaw 90 it is spread flat across the view and reads as even noise, while the edge you are actually
looking at — the sagittal midline — had nothing gathering on it at all. One term fixed it
(`w += 0.40 × G(|x|, 0.048)`): **a head needs a drawn edge from each direction it is ever seen
from**, and there are two.

The second is about additive blending, which is the deck's law and therefore a constraint on
density rather than on colour. The eyelids are surface patches over an ellipse of area 0.028; at 280
points each that is ~2.5× the shell's local density, and additively blended **a closed lid
photographed as a lamp** — brighter than the open eye it was covering, which is the precise opposite
of shut. Dropping to 200 points and the alpha ceiling from 0.92 to 0.74 fixed it. The general rule
worth keeping: with additive blending, **point count is luminance**, so any feature drawn by
gathering points has a brightness budget as well as a shape.

**The depth cue is read off local Z after the rotation and not off view space.** Size and alpha
attenuate with `near = clamp((p.z + 0.62) / 1.45)` — computed in the head's own coordinates, after
the yaw and pitch and before the camera — so the modelling owes nothing to `CAM_Z`, and moving the
camera later cannot silently change how the head reads. Attenuation is `a *= 0.26 + 0.74 × near`
and `size *= 0.70 + 0.48 × near`: the back of the skull is a quarter as bright and two-thirds the
size of the nose tip, which is what lets 12 000 undifferentiated points read as a solid.

**Two measurement mistakes, both the same mistake.** Criterion 2 failed on the first live probe at
**0.148** with a correct nose, because the width it divided by was **1.954** — the *shoulder* span.
Every ratio the mandate states is against head width, so the shoulder hint was inflating the
denominator; measured over head-only points (1.288) the same geometry scores 0.225. Then my own
socket-hollow assertion called a correct socket a failure by comparing the socket's mean Z (0.407)
to the *cheekbone's* (0.386) — the cheekbone sits further round the side of the head, so its surface
is less forward for reasons that have nothing to do with the socket. Against the **brow**, directly
above it at nearly the same azimuth, the hollow is 0.051. Both failures were one error: **measure
through the geometry's own regions, and pick the anatomically meaningful reference** — a ratio is
only as good as what it divides by, and a difference only as good as what it is a difference from.
Both wrong versions are written into `deck_proof.mjs` beside the right ones.

### 18.7 · The head, measured and photographed (Part G)

`deck_proof.mjs` section **2c**, off the live buffer on this machine's Intel Arc 140V, with the face
in the well at 60 fps:

```
  note regions: skull 4274 · nose 900 · cheek 263 · chin 1009 · brow 406 · socket 426 ·
                back 2202 · neck 1100 · lip 600 · iris 420 · lid 400
  note moving parts: skull 5654 · lip_up 300 · lip_low 300 · iris_l 210 · iris_r 210 ·
                lid_l 200 · lid_r 200 · jaw 3826 · neck 1100

  ok   CRITERION 1 - IT IS AS DEEP AS IT IS WIDE: the point cloud spans 1.457 in Z against
       1.288 of head width, a ratio of 1.132 where 0.55 is the floor. The relief this
       replaces scored 0.146 and no amount of taller Gaussians would have moved it
  ok   CRITERION 2 - THE NOSE STANDS OFF THE FACE: the 900-point nose wedge averages Z 0.674
       against the cheekbone plane at 0.392, 0.282 clear = 0.219 of head width where 0.18
       is asked
  ok   CRITERION 3 - THE PROFILE HAS A PROFILE: at the nose's height the frontmost points in
       the cloud are the nose's (0.821 against 0.452 for the cheek and 0.490 for the socket),
       and the chin stands clear of the throat behind it (0.407 against 0.173)
  ok   CRITERION 4 - THE LIDS ARE IN FRONT OF THE EYES: stored shut, the left lid sits 0.074
       and the right 0.071 nearer the viewer than the iris cluster each one covers, so a
       closed eye is a lit lid over a dark eye rather than two surfaces at the same depth
  ok   the eye sockets are HOLLOWS and not bumps: the socket floor lies 0.051 behind the brow
       ridge immediately above it (0.408 against 0.459)
  ok   THERE IS A BACK OF THE HEAD: 2202 points averaging Z -0.183
  ok   and the MANDIBLE IS A REAL PIECE of it: 3826 points carrying role JAW, cut out of the
       shell rather than strapped on, which is what the hinge below has to swing
  ok   a head TALLER THAN IT IS WIDE, neck included: 2.000 by 1.288
  ok   all of it inside the mandate's ceiling: 12000 points, cap 14000
  ok   AND THE HEAD HOLDS STILL TO BE PHOTOGRAPHED at every angle asked for:
       -30° (-0.5236 rad) · 0° (0.0000 rad) · 30° (0.5236 rad) · 90° (1.5708 rad)
  ok   and the pin comes out afterwards
```

**The plates.** `deck-head-yawm30.png`, `deck-head-yaw0.png`, `deck-head-yaw30.png`,
`deck-head-yaw90.png` — 2× from the presence well, taken with the attitude *pinned* by
`presence.yaw(deg)` and the uniform read back off the material each time, because four plates at four
unknown attitudes compare nothing and a plate taken mid-wobble is a plate of the wobble. The lids are
shut in all four and that is not a setting: `sight.state` starts `'shut'`, `SIGHT_LID.shut = 0`, and
with no camera on a headless page `uEye` is 0 — so **the plates are the lids-closed case the fourth
criterion measures**, taken in the state the page is actually in rather than with an override that
would have had to reach into the Eyes Law.

Read beside the holo-gesture reference board, what the plates now show: at **yaw 0** a brow line and
two cheekbone arcs carrying as density, the nose wedge standing in front of the face with its flanks
falling away, two lip arcs with the parting gap between them, lid patches reading as closed eyes over
dark sockets, and the neck fading out at the base. At **±30** the nose swings across the far cheek and
the far socket goes behind the cheekbone — which is the view a mask cannot survive, and the reason
those two angles are in the mandate. At **90** there is a drawn profile: forehead, brow, the nose in
clear air, the lip mark, the chin ahead of the throat, and the occiput bulging behind. The earlier
round of this plate was a speckled blob with a nose stuck on it; the midline seam in 18.6 is the
difference, and it was the plate that demanded it, not a criterion.

**Motion that proves volume** is in the shader rather than in the buffer: idle yaw ±5° and pitch ±2°
on slow sine, blinks by moving the lid geometry over the sockets, and a nod fired by a **rise** in
level rather than by a level — `lvl − prev > 0.16` with a 700 ms refractory gap, so he nods on
sentence stress instead of nodding continuously through a long answer. The jaw is the fifth criterion
and it is proved where real speech exists; see 18.10.

### 18.8 · The funnel, in the boss's own sentences — typed and spoken (Parts A and B)

`routing_proof.mjs` carries the boss's real sentences verbatim and runs each one twice: typed
straight at `/chat` for determinism, and **spoken out of the speakers into the real microphone**
through the Open Ear with on-device recognition. Each row asserts the `kind`, the route class, and
the **lookup count**, read off the server's own trace rather than inferred from the answer.

| the sentence | typed | spoken — what recognition posted | route |
| --- | --- | --- | --- |
| can you listen to me | `200 chat/meta/0` | "Can you listen to me" | chat/meta/**0** |
| can you listen to me *(ear shut)* | `200 chat/meta/0` | — | chat/meta/**0** |
| hey galaxy are you there | `200 chat/meta/0` | "Hey Galaxy are you there" | chat/meta/**0** |
| yes yes do it galaxy *(offer standing)* | `200 tool/-/–` | "Yes yes do it Galaxy" | tool, confirmation taken |
| yes yes do it galaxy *(nothing pending)* | `409 tool/confirmation/0` | "Yes yes do it Galaxy" | tool/confirmation/**0** |
| ok do it | `200 tool/-/–` | "Okay do it" | tool, confirmation taken |
| no no cancel that | `200 tool/-/–` | "No no cancel that" | tool, cancellation taken |
| switch your voice to joe | `200 tool/-/1` | "Switch your voice to Joe" | tool/-/1 |
| who are you | `200 chat/identity/0` | "Who are you" | chat/identity/**0** |
| who am i | `200 chat/identity/0` | "Who am I" | chat/identity/**0** |
| what's my name | `200 chat/identity/0` | "What's my name" | chat/identity/**0** |
| galaxy what can you do | `200 chat/identity/0` | "Galaxy what can you do" | chat/identity/**0** |
| tell me about the invoice importer | `200 notes/-/1` | "Tell me about the invoice importer" | notes/-/1 |
| what is react | `200 notes/-/1` | — | notes/-/1 *(see below)* |
| what is the web gate | `200 web/-/2` | "What is the web gate" | web/-/2 |

**Typed 37/37 · spoken 29/29 · the two together 65/65.** Every protected-class row asserts
`lookups=0`, which is the assertion that does the work: a class that answered correctly *after* a
retrieval would read identically in the answer and would be the bug Part A exists to remove.

What he actually said, out loud, on the spoken column:

```
  ·· spoken "can you listen to me"
   spoken aloud: "can you listen to me" (1.754s, into arm 1)
       posted     : "Can you listen to me"
       he answered: "I am here, Addi - the ear is shut just now, so I have this one message.
                     Open it and the room is yours."
       the wire   : ["200 kind=chat route=meta lookups=0 q=\"Can you listen to me\""]

  ·· spoken "yes yes do it galaxy" · with NOTHING pending
       posted     : "Yes yes do it Galaxy"
       he answered: "Nothing is pending, Addi - tell me what to do and I shall propose it."
       the wire   : ["409 kind=tool route=confirmation lookups=0 q=\"Yes yes do it Galaxy\""]

  ·· spoken "who am i"
       he answered: "You are Sir Aditya Singh, sir - Addi, when we are talking like this."
       the wire   : ["200 kind=chat route=identity lookups=0 q=\"Who am I\""]

  ok   AND ALL OF IT ON ONE CLICK: 13 spoken turns, 14 arms of the recogniser, 1 session
```

Two things in that column are worth naming because they only show up out loud. **Recognition
rewrites the sentence and the funnel has to survive it**: "ok do it" came back as *"Okay do it"* and
was still taken as a confirmation, which is precisely why the affirmative list is matched after
peeling rather than compared as a string. And **the whole spoken column is one click** — thirteen
utterances, fourteen arms of the recogniser, one session, no re-press — which is the Open Ear's
contract asserted rather than restated.

One row is an honest miss and it is not a routing failure: **"what is react" answers from the notes**,
because on this corpus a note about a React rewrite scores 0.614 against the 0.60 threshold and the
retrieval is doing exactly what it is specified to do. The Web Gate is not reached because notes
answered first, which is the funnel's stated order. It is listed as open in Part J rather than
papered over by lowering a threshold the mandate forbids touching.

### 18.9 · His name, and a capability he can name the day it is fitted (Part D)

`persona_proof.mjs` — **19/19**, and run three times because a proof about a brain's *register* that
passes once has proved nothing about the second time he is asked. The persona block lives in
`config.json`, which means **the boss owns his own name**: the fixture compares every answer against
the names the *server* publishes rather than against names typed into the harness, so a fixture
cannot agree with a typo.

```
  note /persona: "{salutation}, Addi. Galaxy here - {notes} indexed, all present and accounted for."
  note the line the page opened with:
       "Good afternoon, Addi. Galaxy here - 30 notes indexed, all present and accounted for."
  ok   AND SO DOES THE CHROME AROUND IT: the window title "Knowledge Galaxy", the heading and
       every visible word on the page are free of the old name - the rename reached the
       furniture, not only the answers
  ok   AND THE FLOATING CARD IS TITLED AFTER HIM: the PiP document is titled "Galaxy · focus"
```

The section that earns the Part is the one with **no protected class behind it**. Asked something
unscripted — route `undefined`, class `null`, straight through retrieval and the brain like any other
question — he answered *"I would say I keep a gentleman's notes in order, then change the subject
before 'traceability' gets loose…"*: in character, no "as an AI", and **not claiming any of the four
families of thing this machine has no hand for** — no car booked, no call placed, nothing bought, no
music played. That is the manifest reaching a free-form answer, which is what Part D asks for and
what a persona in front of only the hard classes would not give. Asked for a hand he has not got:
*"Still no, sir — no taxi-hailing hand among mine, and I shan't mime one at the kerb."*

The register rule holds in both directions and it is asserted as **one form of address per sentence**,
because deference sprayed on every line becomes a tic: an identity answer names both (*"You are Sir
Aditya Singh, sir - Addi, when we are talking like this."*), a warm line uses Addi only (*"I am here,
Addi - the ear is shut just now…"*), and a **consent gate keeps sir** (*"A self test, sir, carrying the
token persona-proof and touching nothing. Shall I run it?"*) — asking permission being the formal
moment the rule reserves it for.

On the old name, the distinction is between his ears and his mouth. *"jarvis who are you"* peels to an
address, reaches identity **at zero cost**, and comes back *"I am Galaxy, the personal assistant of
Sir Aditya Singh - Addi, to those he serves."* — **the rename took his name back without making him
deaf.** A source sweep across five server modules finds the old word surviving in exactly two live
string constants, and both are *recognition*: the assistant-name list the vocative peel matches
against, and the force-trigger alternation. The word is not banned, because *Build Your Own Jarvis* is
the title of one of his own PDFs and he is entitled to read it out.

**`capabilities_proof.mjs` — 16/16, and it is the one fixture in this round that edits real
configuration.** It fits a canary hand into `tools/registry.json` that exists on no machine
(`water_the_ferns`), restarts the server, asks, then removes it and restarts again. The arc of **one
unchanged sentence** across three registry states is the whole proof:

```
  before   "could you water the ferns on the landing for me"
           -> no proposal · "That is a hand I have not been given, sir - the ferns must wilt
              without me."
  fitted   the same sentence, unchanged
           -> PROPOSED water_the_ferns · "The ferns on the landing, sir - a full can each.
              Shall I?"
  removed  the same sentence, a third time
           -> no proposal · "That is a hand I have not been given, sir - my reach ends at the
              edge of this machine, and the ferns know it."
```

Nothing was retrained and no prose of mine was edited: **a line of JSON was added and he could name
it.** He counted it himself at start-up (`Galaxy knows 7 hands: … water_the_ferns`), offered it to the
boss by its human name — *"Water the ferns on the landing"*, a sentence no source in this repository
contains — and still **put it through the consent gate**, which is the one property of the Hands
pipeline that must not be reachable around. The direction that matters more is the third row: a
manifest which kept the sentence after the code went would have him promising the boss something
there is nothing left to run.

Two assertions in that file exist because of this machine rather than because of the spec. **Each
restart is proved to be a genuinely new process** (`pid 46880 → 48488, up 0s`), because on Windows a
second `server.py` exits 1 while the old process keeps answering port 4700 — every claim after a
restart that was not asserted would be a lie about a stale server. And the registry is restored
**byte-for-byte from memory in a `finally`** (7097 bytes, canary gone): a fixture that edits real
configuration owes that assertion more than it owes any of its others.

### 18.10 · The full read, the barge-in reference, and the silent nudge (Part C)

The mic opens with `echoCancellation: true, noiseSuppression: true`, and the barge-in gate is a
**ratio against the live output RMS tapped off the speech bus** — 1.6× sustained 250 ms, and deaf for
the first 800 ms of any answer. Every attempt is logged with the input beside the reference it was
measured against, taken or not, which is what makes the two halves distinguishable. The log from
`conversation_proof.mjs`, both cases, self-voice first:

```
  {"at":…604343, "input":0.09, "output":0.072, "reference":"calibrated", "ratio":1.25,
   "sustainedMs":0,   "intoAnswerMs":811,  "engine":"piper", "taken":false,
   "why":"not 1.6x the output reference · 0.090 against 0.072 (1.25x)"}

  {"at":…604748, "input":0.09, "output":0.072, "reference":"calibrated", "ratio":1.25,
   "sustainedMs":0,   "intoAnswerMs":1216, "engine":"piper", "taken":false,
   "why":"not 1.6x the output reference · 0.090 against 0.072 (1.25x)"}

  {"at":…605211, "input":0.28, "output":0.072, "reference":"calibrated", "ratio":3.89,
   "sustainedMs":269, "intoAnswerMs":1679, "engine":"piper", "taken":true,
   "why":"over the gate for 269ms, 1679ms into the answer · 0.280 against 0.072 (3.89x)"}

  ok   HE DOES NOT INTERRUPT HIMSELF: half a second of the answer's own leak, past the deaf
       window and well over the voice floor, and he is still reading - bus still at 1,
       0 barge-ins
  ok   still one click - a barge-in is not a button either
```

The middle entry is the one that matters. **0.09 is well over any voice floor** and it is 500 ms
*past* the deaf window, so every absolute test would have fired there — and it is his own voice
leaking back through a canceller that removed most but not all of it, exactly as 18.0 measured. The
ratio rejects it at 1.25× and accepts a real interruption at 3.89× sustained 269 ms. The unit case is
asserted separately: input equal to output → no barge-in; 2× → barge-in.

**The nudges.** `nudge_proof.mjs` — **21/21** — and the rule is that a posture or watch nudge is
caption-only during speech or an open ear, and spoken only when idle with the ear shut. Four nudges
were made: one spoken, three held, **and the gate names the reason for each**:

```
  idle, ear shut          {"spoke":true,  "why":""}                              -> SPOKEN
  the butler is reading   {"spoke":false, "why":"the butler is reading"}         -> caption
  the ear open, silent    {"spoke":false, "why":"the ear is open and the room is his"}
  an answer in flight     {"spoke":false, "why":"an answer is in flight"}        -> caption
```

Three of those four are only assertions because of what the fixture ruled out around them. The
spoken one is preceded by an unlocking click on empty canvas, *because without a live AudioContext
every "caption only" below it would pass for the wrong reason.* The open-ear case is taken **in a
silent room with the queue empty**, so it cannot be the speech rule wearing the ear's clothes — the
reason an open ear silences him is that the recogniser is armed between turns and a nudge spoken into
it is transcribed as his. And the fourth is the one a naive implementation gets wrong: **the gap
between the question and the reply is not a gap** — the speakers were silent, the ear was shut, every
audio test said go ahead, and the gate still said *"an answer is in flight"*, one second before the
answer arrived.

The held caption is deferred rather than dropped, and it takes its turn when the queue runs dry —
asserted, because a subtitle stolen from the words currently coming out of the speakers is the
failure that would make the caption rail untrustworthy. Both unasked sentences reach `nudgeSpeak()`
and **neither has a `speakLine()` anywhere near its call site**, so the gate cannot be walked around
by accident tomorrow.

### 18.11 · The silence a warm cache had been hiding (Part H, and a real defect)

`voice_proof.mjs` failed on the first full re-run of this round — **131/132**, on the one assertion
whose subject is what the boss would actually notice:

```
  FAIL NO SILENCE OVER 2s BETWEEN CHUNKS: worst was 2287ms (before chunk 4)
```

It would have been an easy failure to re-run away, and re-running it *would* have made it pass. It
is worth writing down why that would have been the wrong move, because the reason is not "tests
should be deterministic" — it is that the harness had caught a product defect that had been in the
page for as long as the piper path has existed, and a second run would have hidden it behind its own
first run's cache.

**The diagnosis, before the fix.** Two files of 422,956 bytes each had been written into `say-cache/`
*during* the failing run, so the run had taken a cache miss on chunk 4. `say.py::_key()` is a sha256
of model, length scale, noise scale and text, so the key was not drifting; what drifts is the
**cache's ~100 MB oldest-first prune**, which had evicted those entries since the previous run.
The cache is 97 MB at rest, so eviction is not an accident of this round — it is the steady state.
Then I measured the two paths directly rather than reasoning about them:

| `/say` for a novel 170-character sentence | wall |
| --- | --- |
| cold, model loaded, cache miss | **4337 ms** |
| the same text, immediately again | **104 ms** |

Cold synthesis costs about **0.45× the real time of the audio it renders**. Now the arithmetic. The
FIFO prefetched exactly **one** chunk ahead, so the cover available for chunk *k* is the playing time
of chunk *k−1*, and the queue is safe only while `0.45 × dur(k) < dur(k−1)` — that is, only while no
chunk is more than about twice its predecessor. The failing pair: chunk 3 played for **2.067 s**,
chunk 4 was 170 characters and **9.59 s** long. `4337 − 2067 = 2270 ms` of exposed silence, against
the 2287 ms the harness measured. The numbers close.

**The fix went into the product, not the ceiling.** `GAP_MAX_MS = 2000` is the spec's statement about
what the boss will tolerate mid-sentence; raising it would have been editing the requirement to match
the behaviour. Instead the lookahead is now measured **in seconds of audio rather than in chunks** —
`SPEAK_AHEAD_MS = 7000`, `SPEAK_AHEAD_CAP = 3` — so a long cold chunk is covered by the **sum** of the
chunks in front of it rather than by only the last one. The cap is there because the original
one-chunk comment was not wrong about its own concern: `/say` is effectively serial, and an unbounded
lookahead would put the synthesiser to work on the end of an answer while the beginning is still
being read. This chunk is still requested *first*; the lookahead follows within the same tick.

**And then the assertion was made unable to pass for the wrong reason.** A gap ceiling can be met by
a warm cache on a lucky run, so the page now publishes the lookahead's depth and the fixture asserts
it: `__galaxy.voice.AHEAD_MS`, `AHEAD_CAP`, and a live `ahead` — chunks in flight *in front of* the
chunk being played. `buffered` exists too and is deliberately **not** what is asserted: the buffer map
is cleared once per run and never per chunk, so its size only climbs, and it read **13 by the end of
a 13-chunk answer** — which a one-deep lookahead would also have reported. Only the live depth tells
the two apart.

The verification run was taken with **`say-cache/` deleted entirely**, which is the harshest case this
page can be given: every chunk of the greeting and all thirteen chunks of the long read synthesised
from cold.

```
  note chunks: 13 queued · 13 spoken · 0 skipped · 0 errored · worst gap 2ms (before chunk 2) · 0 stalls
  ok   NO SILENCE OVER 2s BETWEEN CHUNKS: worst was 2ms, measured in Node from the page’s own timestamps
  ok   and the page’s own arithmetic agrees (2ms vs 2ms), so the number in the instrument can be trusted next time
  note lookahead: 7000ms of audio, at most 3 chunks · deepest measured in front of the ear: 2 chunks (buffered 13 by the end)
  ok   THE LOOKAHEAD IS SECONDS OF AUDIO AND NOT ONE CHUNK: it holds 7000ms of estimated speech in
       front of the ear (cap 3 chunks) and was measured 2 chunks deep mid-read
  ok   IT READ THE WHOLE ANSWER: speakDone went up after 99.2s
```

**2 ms**, from 2287 ms, on a colder cache than the run that failed. Ninety-nine seconds of speech
with no join a listener could hear.

### 18.12 · The seal that could outlive its silence (Part E, found by the regression matrix)

Part E's spoken fixtures caught "one utterance, two turns" — Chrome delivering a final result it
was already holding while the recogniser was being torn down, which refilled the phrase buffer
*behind* the flush and sent the same sentence to the brain twice, 394 ms apart. The repair was a
seal: a thought that has gone to the brain closes the buffer, and words arriving before the
microphone opens again are the tail of a sentence already answered. It was cleared in exactly one
place — `r.onstart`, the browser's own word for "the microphone is open" — and the comment written
beside it claimed that this meant the seal could never outlive the silence it belongs to.

It could. `r.onstart` being the **only** release means that any session in which the recogniser does
not start again keeps the seal forever, and a sealed ear is the worst kind of broken: the ring is
lit, the organ rail says the ear is open, `ear.sealed` climbs, and he never answers again. **Part E's
own fault path is exactly such a session** — three failed restarts and the watchdog stops trying —
which is to say the seal had a failure mode that the Part it was written for creates.

`brain_live.mjs` found it, and found it the way a regression matrix is supposed to: **30 checks, 1
failed**, on the one step that speaks a second sentence.

```
   38.50s  FAIL the run itself: the page said nothing at all after "go back to your normal brain"
```

The sentence was never dropped by the server, which is what made it worth chasing rather than
re-running: asked over HTTP the same words answer correctly — `{"kind": "model", "restored": true,
"answer": "I am OPUS 5 already, sir."}`. A scratch probe injected two utterances into a headless tab
with no recogniser between them and showed the second one being swallowed with only `ear.sealed`
moving.

So the seal now **expires**, and the number is taken off the measurement rather than off a round
figure: the tail it exists to swallow was seen at 394 ms, so `EAR_SEAL_MS = 900` is a margin of
better than two over the only number anybody has. `r.onstart` is still the normal release and the
only one a live session ever uses; the clock is for the session whose recogniser does not come back,
and in that session every extra millisecond is a word of his that the page throws away.

**1500 ms was tried first and was wrong**, which is worth recording because it looked safe:
`brain_live`'s second spoken sentence arrives **1.3 s** after the first one's flush — a perfectly
ordinary gap between two turns — and a seal still shut at 1.3 s ate it. The harness failed again,
identically, and the second failure is what fixed the constant. `__galaxy.ear.sealExpired` and
`SEAL_MS` are published beside `sealed` so that "he stopped answering" and "he heard nothing" are
never again the same reading from outside the page.

```
  brain_live.mjs   before: 30 checks, 1 failed
                   after:  32 checks, 0 failed
```

The count goes up by two because the two assertions behind the failure had never run.

### 18.13 · The amend door that swallowed a change of subject (Part B, and a real defect)

Part B gave a standing offer three fates. A yes or a no answers it; a remark **about** it keeps it
alive and goes to the brain with the offer in front; anything else is a genuine new request, which
releases the slot with one sentence in front of the answer — *"You have changed the subject, sir, so
I have let that request go."* Silence is not consent and neither is a change of topic.

`tools_live.mjs` disagreed, twice, on the one section that walks away from an offer:

```
   ok   one more proposal, to walk away from
   FAIL changing the subject lets the proposal go, and says so: null
   ok   silence is not consent: the diary did not grow
   FAIL and nothing is pending in the page either
```

Read together those two lines describe something worse than either alone. The proposal was **not
run** — the diary is the witness — and it was **not released** either. No withdrawal was spoken. The
page was handed the same pending slot back in the reply and drew the card again. And the boss's
actual question was answered as a remark about a reminder.

The cause was one alternative in one regular expression. `_AMEND_RE` is the first door in
`about_the_proposal()`, above every other, because "send it to Bob instead" reads to the tool matcher
as a brand-new email and treating it as one would drop the offer being corrected. Among its
alternatives, to catch "say it warmer" and "just say sorry at the end", was `\bsay\s+` — the bare
verb, anywhere in the sentence. The fixture's change of subject is:

```
what do my notes say about coffee
```

`say about` matched. A question about coffee became an amendment to a calendar reminder.

The repair makes the verb **imperative**, which is the only form an amendment takes: at the head of
what he said once the vocative is off it, or pointing at the offer with its object —
`(?:^|,\s*|\band\s+|\balso\s+|\bjust\s+|\bplease\s+|\bcan\s+you\s+)say\b` or
`\bsay\s+(?:it|that|this)\b`. Nine amendments and pointed questions still hold the offer; five
changes of subject, each carrying a word the door has reached for at some point, now release it.

```
  tools_live.mjs   before: VERIFY 48/50 FAIL
                   after:  VERIFY 50/50 PASS
```

and the line the harness had been waiting sixty seconds for, in full:

> "You have changed the subject, sir, so I have let that request go. Coffee, sir, is rather the
> running theme — the notes are a café's in their entirety. In brief: six lots of green in store led
> by Ethiopia Guji at 6 bags, drip at $3."

One utterance. The withdrawal and the answer, in that order.

**Two things were added so this cannot come back quietly.** The fixture now carries a comment saying
why *that* sentence and not a tidier one — "what is react" would pass this section for ever without
touching the amend door, so the verb stays in. And `preflight.py` check 18 gained step **(f)**: Part
B's fork, both ways, on nine sentences that must keep the offer and five that must release it, plus
the same fourteen against an empty slot. It is three function calls and no browser, because the fork
is pure — `tools_live` needed a real Chrome, a real hand and ninety seconds to find this.

The one sentence in that probe that surprised me is worth writing down rather than fixing: **"who
said that react was simple" is held as talk about the offer**, and not by the amend door — "said" is
not "say" — but by the third door, the deictic. It is a question and it contains *that*, which is
exactly what door 3 tests for. The rule is doing what it says; the sentence is just unlucky in its
pronoun. Narrowing the deictic to catch it would cost "is that going to bob?", which is the case the
door exists for.

### 18.14 · The archive that claimed the world (Part H, measured, reported, not tuned)

Eleven assertions across two standing harnesses failed this round for **one** reason, and it is not
in any code this round wrote. `salutation_proof` was 26/34 and `followup_proof` 44/47, and every
failure traces to the semantic archive answering questions it cannot answer.

`archive/samples/Build-Your-Own-Jarvis-GPT-6-Astra-Prompt-Pack.pdf` is 372 KB dated 15 September and
contributes **22 of the vector store's 55 chunks** — two fifths of the collection, all of it about
building an assistant, which makes it the nearest thing in the store to any question about software,
AI, or an assistant of any kind. The server's own trace, from three questions asked over HTTP:

```
  recall: the notes door opened on MEANING alone - 0.613 (threshold 0.60) from Build-Your-Own-Jarvis-GPT-6-Astra-Prompt-Pack.pdf, ...
  recall: the notes door opened on MEANING alone - 0.652 (threshold 0.60) from Build-Your-Own-Jarvis-GPT-6-Astra-Prompt-Pack.pdf, ...
  recall: the notes door opened on MEANING alone - 0.621 (threshold 0.60) from Build-Your-Own-Jarvis-GPT-6-Astra-Prompt-Pack.pdf, ..., customer-feedback-log.md
```

0.613 is *"ok, what is closures in javascript"*. 0.652 is *"who is JARVIS in the movies?"*. 0.621 is
*"who is zqtask@example.invalid"*. Three questions with nothing in common except that the store held
no answer to any of them, all landing between 0.61 and 0.66 against a document that mentions none of
them. What he **says** is honest in every case — "JavaScript closures are not something the notes
touch on, sir", "A question for the cinema, sir, and my shelves hold only your own papers" — because
the notes branch reports what it found. What is lost is where the answer should have come from: the
door having opened, `confidence` is lifted to the same number, and a lifted confidence is not "thin",
so **the live web never opens on a question about the world**.

**Two of those eleven were repaired and nine are reported.** The difference is what the mandate
protects.

**Repaired — the PII shield's reach (three assertions in `followup_proof`).** Asked *"who is
zqtask@example.invalid"* with a previous question still in the session, the door opened at 0.621,
`kind` became `notes`, and the shield — gated on `kind != "notes"` for the good reason that a note
genuinely naming the correspondent should answer — was stepped over. Nothing leaked: the notes branch
asks no search engine, no lookup was spent on the address, and what he said was true. What was lost
was the **refusal, said out loud**, and the shield's own law is that a refusal the employer cannot
see is indistinguishable from a failure. Standalone the same sentence is held correctly; it takes a
prior in the session to make it "substantial" enough to reach the embedder at all, which is why this
only ever failed inside a fixture that asks something first.

The fix is a fourth veto on the semantic door, beside the backchannel, the vocative and the Third
Door: `semantic_holds_identifier()`. A question carrying a private identifier may be claimed by the
meaning search **only if the passages it found actually contain that identifier**. The test is
containment rather than a higher dial, because that is the one kind of evidence an identifier admits
— prose can mean the same thing in different words, an email address cannot — so the 0.60 threshold
is left exactly where it is. And it cannot cost a real notes answer: the door is only consulted when
the keyword half has already declined, so a note that shares the address with the question claimed it
two branches earlier and never arrives here.

```
  who is zqtask@example.invalid   before: kind=notes, cites 4, privateHeld absent
                                  after:  kind=chat,  cites 0, privateHeld true
                                          "Private identifiers never leave this machine, sir -
                                           I shall not ask the web about them."
  and a genuine notes question is untouched:
  what do my notes say about coffee  kind=notes, 6 nodes, 5 citations
```

**Reported — the two world questions (eight assertions in `salutation_proof`).** *"ok, what is
closures in javascript"* and *"who is JARVIS in the movies?"* should reach the live web and do not.
Every repair available is one the mandate forbids or one no engineer should take:

- move the 0.60 threshold, or change how recall scores — **DO-NOT-ALTER**, in those words, and
  rightly: the dial is correct for the prose it was set on;
- delete the prompt pack from `archive/samples/` and rebuild the store — it is **the boss's own
  document**, put there on 15 September, and making a harness green by deleting his file is not a
  repair;
- change the fixture's two probe questions — that hides a live behavioural regression he would meet
  the first time he asked his assistant about a film.

So it stands, named, with its numbers. The one-line change that would resolve it, on his word: a
world-question class that outranks a semantic match the way `REALWORLD_RE` already outranks a keyword
one. `REALWORLD_RE` is deliberately narrow — weather, scores, prices, "current" anything — and
neither of these two sentences is in it, by design, because every phrase in it is one somebody would
have to go and look up. Widening it to cover "what is X" is a decision about the web gate, and the
web gate is his.

### 18.15 · Two ways a green harness lies, both found this round

Neither of these is a defect in the product, and both cost real time, so they are written here rather
than remembered.

**A stale debugging browser makes the wrong tab the subject.** `eyes_live.mjs` came back **56 checks,
31 failed**, starting with `FAIL the EYE button opened a real camera` and an empty `trouble=`. The
organ was fine. `eyes_live` launches its own Chrome on port **9222** with
`--use-fake-device-for-media-stream`, and `port_proof.mjs` — which relaunches Chrome through
`launch-chrome.ps1` and deliberately leaves it open — uses the same port. Attaching to the leftover
browser gets a viewer tab that looks right in every way except that it has no camera and no
permission answer, so `getUserMedia` never settles and the organ reports no trouble because nothing
went wrong. Run alone on a clean machine: **56 checks, 0 failed**, no code changed. `port_proof` runs
last, alone, and eight seconds between harnesses on the same port is not enough.

**A frozen log makes every delta assertion vacuous.** Ten harnesses read `server-trace.log` for what
the server *did* — `lookups()` counts `web lookup` lines, `logSays()` tests for a trace — and they
take **differences** across a run. Restarting the server with its stderr going anywhere else leaves
that file on disk and stale, so `lookups()` returns the same number before and after and every "zero
lookups" assertion passes for the wrong reason. `followup_proof` caught it honestly, because it is
the one that asserts a count *going up*:

```
  FAIL EXACTLY TWO lookups across those four turns - the two that were questions
       before=46 after=46
```

Two questions had been asked and one of them had searched the web for "who created svelte". The
counter had not moved because the file had not been written since 14:18. It also explains a passing
assertion that had no right to pass: `logSays(/a private identifier was in the message/)` was true
during the very run in which the shield did **not** fire, because the line was in the log from an
earlier run. The server's stderr belongs in `server-trace.log`, appended, and every log-reading
harness in this round was re-run against a server that writes there.

### 18.16 · The watch that undid the backoff (Part E, and the third real defect of the round)

`conversation_proof` section 3c came back **102/103**, and the one red line was the backoff itself:

```
  FAIL THE RETRIES BACK OFF rather than hammering: the page waited 425ms then 1628ms between
       attempts and is now standing off 3200ms - 400 doubled, three times
         {"at":[1790413672195,1790413672620,1790413674248],"gaps":[425,1628],"rearmIn":3200}
  ok   AND IT RECOVERS WITH NO CLICK: the service answered once and the fault cleared itself
```

Everything else about the fault was right: three failures, `hardErrors=3`, the seal amber and
reading EAR FAULT · RETRYING, the session still open, and the recovery with nobody touching
anything. The specified intervals are 800 then 1600 — four hundred doubled once, then twice.
The second was 1628. The first was **425**, which is four hundred doubled *no* times.

**The shape of the number was the whole diagnosis.** 425 is not a slow 800 or a jittery
anything; it is `EAR_REARM_MS` exactly, the ordinary courtesy delay after his voice ends. So
the question was never "why is the backoff late" but "who re-armed this ear without knowing
there was a fault standing" — and the answer is in `earWatchUp()`:

```js
    ear.watch = setInterval(function () {
      if (!ear.open) return earWatchDown();
      if (listening || busy || speakDraining || speakQueue.length) return;
      earWatchDown();
      earRearm('nothing came back to be spoken');     // <- no ms: the default four hundred
    }, EAR_WATCH_MS);
```

The watch is the half-second interval that exists for answers which never speak — a muted
tab, a machine with no voice, an organ that renders a line and returns. It is put up by every
turn hold, and it comes down the moment it re-arms once. During the fault the page is not
listening and not busy, so the watch's four questions all said "the turn is over", it re-armed
with no argument, and `earRearm` wrote `ear.rearmIn = 400` straight over the 800 the error path
had chosen one tick earlier. Then it took itself down, which is exactly why only the **first**
interval was short and the second was a correct 1600: one firing, one skipped doubling.

**And one line down it is worse.** The re-arm timer's own callback ends with

```js
      if (busy || speakDraining || speakQueue.length) { earWatchUp(); return; }
```

— a backoff re-arm that lands while a turn is still in flight *drops itself* and hands the job
to that watch. So a recognition service that dies while an answer is being read is retried at
four hundred milliseconds with no backoff at all. That is the hammering the backoff was written
to refuse, in the one situation where the page is already busiest.

**The repair is a floor, in the one door all four callers come through.** The backoff got a
name of its own —

```js
  function earBackoffMs() {
    if (!ear.hardErrors) return 0;
    return Math.min(EAR_REARM_MS * Math.pow(2, ear.hardErrors), EAR_BACKOFF_MAX_MS);
  }
```

— the two inline copies in `onerror` now call it, and `earRearm` treats it as a minimum rather
than as one caller's private business:

```js
    ear.rearmIn = Math.max(ms > 0 ? ms : EAR_REARM_MS, earBackoffMs());
```

Why a floor and not a guard in the watch: there are four paths that re-arm this ear — the error
path, the `onend` self-heal, the watch, and `speakDone` — and three of them have no business
knowing what a backoff is. Fixing the watch alone would have left `speakDone` free to re-arm a
dead recogniser four hundred milliseconds after the answer, which is the same bug wearing a
different sleeve. `hardErrors` is put back to zero by any result at all and by `no-speech` and
`aborted`, so the floor is **zero in every ordinary moment** and the specified four hundred is
untouched: this cannot make the ear slower to come back in a working room.

**The assertion was rewritten too, because the arithmetic alone was luck.** The gaps caught
this only because the watch happened to fire between attempt one and attempt two; had it fired
a beat earlier or later the run would have been green with the page demonstrably hammering. So
the fixture now samples the invariant itself throughout the fault — `rearmIn < backoffMs` is
the defect, whoever caused it, and one sample convicts:

```
  ok   AND NOTHING SHORTENED THE STANDING BACKOFF: every re-arm scheduled inside the fault was
       at least the delay the failure count had bought (the re-arm watch was UP when the service
       went away, which is the case that used to skip the first doubling)
```

That parenthesis is read off the page (`__galaxy.ear.watch`, added with `backoffMs` for this),
not asserted, so the line says out loud whether the run exercised the hole or merely missed it.
In the run below it says UP.

**Measured, same machine, same fixture, only the page changed:**

| | first interval | second interval | standing off | result |
|---|---|---|---|---|
| before | **425 ms** | 1628 ms | 3200 ms | 102/103 FAIL |
| after | **837 ms** | 1641 ms | 3200 ms | **104/104 PASS** |


### 18.17 · The relaunch that shot the browser (Part F, and the fourth real defect of the round)

`lock_proof.mjs` is the only harness that exercises the whole no-port chain, and it put its
finger on the one line in it that cannot be checked by reading:

```
FAIL the relaunch restored his work tab: 
BROKE: Cannot read properties of undefined (reading 'id')   at lock_proof.mjs:638
FAILURE MODE: a hand that "relaunches Chrome" by killing it. --restore-last-session only
works on a browser that was closed, not shot.
```

The empty string after the colon is the whole story: the work tab was not in `/json/list` at
all, so the assertion had nothing to name and the next line crashed reaching for its id. The
hand, `tools/relaunch_chrome.py`, was innocent; so were the launcher's flags. The fault was
three deep in `launch-chrome.ps1`, in the twenty lines that close the profile politely before
relaunching it, and each of the three fails the same way — a close that Chrome never finished
is read as a close it refused, the force kill follows, and a force-killed Chrome writes no
session for `--restore-last-session` to restore.

**One: the wait counted processes that hold nothing.** The filter took every process whose
command line mentions the profile. A Chrome browser has a dozen of those, and one of them,
`--type=crashpad-handler`, outlives the browser it was started for. So the wait watched a
handler that was never going to exit, timed out, printed `something on this profile ignored
WM_CLOSE`, and shot everything — including a browser that had already gone quietly. Only the
browser process holds the profile lock, owns a window and writes the session, and it is the
only one the wait has any business watching: `Get-ProfileBrowsers` now excludes `--type=*`.

**Two: the match depended on how the path was spelled.** The old filter compared the whole
`--user-data-dir` string, so a browser launched with forward slashes, or a mixed-slash path of
the sort Node hands out, held the profile while being invisible to the launcher. The launcher
then started a second Chrome on a profile that was already owned; Chrome handed the URL to the
first browser and the second process exited — taking the `--remote-debugging-port` with it. The
port never answered and nothing said why. Matching is now on the profile **folder name**, which
is the same in every spelling of its path.

**Three, and the one a boss would actually meet: `CloseMainWindow()` asks one window.** It posts
WM_CLOSE to whichever window Windows currently calls main. Chrome exits when its **last** window
closes, and as each one goes it promotes the next. A browser with two windows open on this
profile — the boss with a second window, or any earlier run of this launcher that opened one —
was asked once, closed one window, sat there perfectly alive for the whole fifteen seconds of
patience, and was then shot with its tabs in it. Measured on a real two-window profile, over
`EnumWindows`:

```
pid 18280 top-level windows:
   23331160 :: Restore pages?
   24513884 :: Example Domain - Google Chrome
   14616420 :: Restore pages?
   22088368 :: Example Domain - Google Chrome
```

The wait now re-asks the newly promoted window about once a second until the process is gone. An
extra WM_CLOSE to a window that is already closing costs nothing, and the patience went from
eight seconds to fifteen.

**A regression I wrote into the repair, worth the paragraph because PowerShell will do it
again.** After the refactor the launcher reported `no chrome.exe browser on this profile - 11
helper process(es) of a closed one` while the identical filter inline matched the browser
perfectly. PowerShell unrolls a function's output: the `@()` written *inside*
`Get-ProfileBrowsers` is undone on the way out, so one match comes back as a bare `CimInstance`,
and `.Count` on a `CimInstance` is `$null`, not 1. `if ($mine.Count)` was therefore false in the
commonest case of all — exactly one browser on the profile. The `@()` belongs at the **call
sites**, and the same bug bit the scratch script written to measure the fix, which declared a
clean exit `after 0.25s` and relaunched into a browser that was still dying. A test harness gets
no exemption from the trap it was written to investigate.

**The measurement, end to end, on the real path.** Two windows on the profile, no debugging
port, a "Restore pages?" bubble on each, then `launch-chrome.ps1`:

```
  closing 1 chrome.exe browser process(es) on this profile - politely, so the tabs come back
  ok    the profile is free and its session was written
  ok    DevTools port 9222 is open - Chrome/153.0.8010.54
  ok    /health reports focus.cdp = true - a session can lock the SITE, not just the app
```

— no `warn`, where every run before the repair had one. And with two marked tabs open before the
launcher ran, `/json/list` afterwards:

```
   http://127.0.0.1:4700/
   https://example.com/launcher-mark-B
   https://example.com/launcher-mark-A
   ...
LAUNCHER MARKS RESTORED: 2 of 2
```

A control run settled that the flags were never the suspect: on a browser that exited cleanly,
the launcher's exact argument line restores two marked tabs of two and Chrome writes a fresh
`Default/Sessions/Session_13434895796847964`, 4006 bytes, at the moment of the close. Every
zero-restore run in this investigation had a force-killed browser somewhere behind it.

`lock_proof.mjs`: **70 checks, 0 failed** — the no-port press, the gated relaunch, the restored
work tab, drift inside 1.5 s with one callout, the resume, the second drift, the summon accepted
and the window in front again, and the unlock leaving zero watchers and no attached debugger.

**And the harness's own safety net, which was copying nothing.** The same run printed `copied 0
session file(s) aside` and, in teardown, `put 0 session file(s) back; the boss's tabs return on
his next launch`. Both lines were true and neither meant anything: `SESSION_FILES` listed
`Current Session` / `Last Session`, which is pre-M100 Chrome. On Chrome/153 the session lives in
`Default/Sessions/` as `Session_<timestamp>` and `Tabs_<timestamp>`, so the backup matched no
file and the teardown restored no file — while printing the sentence that says his tabs are
safe. That is the same defect class as a frozen level that reads like a shut mouth, in a harness
rather than in the product. It now matches on the pattern, keeps the legacy names for an older
Chrome, and — because Chrome picks the **newest** `Session_<timestamp>` and would therefore have
preferred the run's own session over the one restored beside it — clears what the run wrote
before putting his back:

```
    2.38s  copied 4 session file(s) aside; they go back in teardown
   71.19s  cleared 4 session file(s) this run wrote
   71.19s  put 4 session file(s) back; the boss's tabs return on his next launch
  70 checks, 0 failed
```

### 18.18 · The matrix, at the end of the round (Part H and Part I)

Every standing harness, run in the foreground — which is itself a finding of this round: a
harness launched from a backgrounded shell loses synthetic input and reds out on the product's
behalf (§18.15). Summary lines as they printed:

| harness | summary | what it stands over |
| --- | --- | --- |
| `routing_proof.mjs` | **65/65 PASS** | the funnel in the boss's own sentences, typed and spoken |
| `conversation_proof.mjs` | **104/104 PASS** | three turns with eyes, ear and face live; the pulse; the ear fault and its backoff |
| `persona_proof.mjs` | **19/19 PASS** | his name everywhere, no "Jarvis" left to a user's eye |
| `capabilities_proof.mjs` | **16/16 PASS** | a canary hand fitted in a temp registry and named after a restart |
| `nudge_proof.mjs` | **21/21 PASS** | posture and watch nudges caption-only while he is speaking or listening |
| `voice_proof.mjs` | **133/133 PASS** | the full read, the barge-in gate, self-voice rejected and a true interruption accepted |
| `deck_proof.mjs` | **208/208 PASS** | the deck, and the head's volume assertions |
| `lock_proof.mjs` | **70/70 PASS** | the whole Part F chain on a real port-launched Chrome |
| `eyes_live.mjs` | **56 checks, 0 failed** | posture, the relief valve, and no organ ever opening the microphone |
| `brain_live.mjs` | **33 checks, 0 failed** | the live brain, and the seal that may not outlive its silence |
| `tools_live.mjs` | **50/50 PASS** | the hands: gated, once, nothing kept |
| `focus_probe.mjs` | **78 checks, 0 failed** | the session on the server, leaking nothing |
| `desk_proof.mjs` | **44 checks, 0 failed** | the desk |
| `layout_proof.mjs` | **72/72 PASS** | the layout under every width |
| `followup_proof.mjs` | **47/47 PASS** | the antecedent memory |
| `port_proof.mjs` | **24 checks, 0 failed** | the launcher's own promises; run last and alone |
| `salutation_proof.mjs` | **26/34 FAIL** | red by decision, measured and reported in §18.14 — two world questions the archive answers from its prompt pack |
| `preflight.py` | **15 pass, 0 fail, 4 warn** | nineteen checks, including 18 (the routing chain) and 19 (the lock chain) |

The four preflight warns are the standing ones and none of them judges the code: no OpenRouter
key in `config.json`, so the swapped brain's answer chain and the Astra look are unverified here
(checks 10 and 12); no Chrome on the debugging port at that moment, so a session would degrade
to the application (check 11); and the screen watch standing down rather than reading somebody
else's cooldown, because check 12 had just spent a nudge (check 13). Only `fail` judges the code,
and it reads zero.

## 20 · The Silent Subprocess, the Echo Law and the Scribe

This section is the round's own record. One research paragraph per Part, written before the
code for that Part existed; the audit that found the defect; and the evidence each Part was
asked to produce. Nothing here is a plan — every number in it was measured on this machine.

### 20.1 · Part 0, the research — how a console window gets onto a desktop nobody asked

`CREATE_NO_WINDOW` does not mean "no console". It means *a console with no window*: Windows
still allocates a console object for the child and still starts a `conhost.exe` to host it,
and that host simply never shows itself. This matters because the obvious way to check the
repair — "assert no console host was created" — passes the bug and fails the fix. An A/B on
the real piper binary said so in the plainest possible terms:

```
MODE=old  (no creationflags)     windows: []   consoles: []
MODE=new  (CREATE_NO_WINDOW)     windows: []   consoles: [conhost(37184) <- piper(42260)]
```

The unflagged spawn allocated nothing because it **inherited** its parent's console. That is
the whole mechanism of the complaint. A console program started with the default flags gets a
usable console if one can be inherited, and a brand-new one otherwise — and when Windows has
to allocate a new console it opens the machine's *default terminal application* to host it.
On this box that arrives as a pair: a `CASCADIA_HOSTING_WINDOW_CLASS` window (Windows
Terminal) followed 80–320 ms later by a visible `PseudoConsoleWindow` owned by the child. That
pair is the black flash. It appears in the boss's ordinary use — where the shell that started
the server has long since gone, so there is no console left to inherit — and it does *not*
appear under a harness holding a live pty, which is exactly why the first control written for
this reported a clean desktop and why the field condition cannot be reproduced on demand
inside one terminal session. Two further consequences shaped the code. First, the window class
is `PseudoConsoleWindow`, not the famous `ConsoleWindowClass`, because the server is started
from a shell holding a ConPTY; a detector looking for the famous name sees nothing. Second, the
flag beats `STARTUPINFO`/`SW_HIDE`, which hides a window that has already been created — a
race the flash can win — and does nothing at all about a console the OS allocates on the
child's behalf. `CREATE_NO_WINDOW` removes the dependency on inheritance entirely: the child's
console never needs a window, so no terminal is opened to host one. And because the flag is a
property of the *call site* rather than of the feature, the policy had to become a module every
call site goes through, not a keyword typed into the one line that was flashing.

### 20.2 · Part 0, the audit — every spawn in the repository, before and after

Found by parsing, not by grepping: `hands.py`'s own module docstring explains the call it makes
by writing `subprocess.run([sys.executable, script], ...)` in prose, and the first regex-based
version of this audit read that sentence as a call and failed the very file it had just been
repaired in. `ast` sees a `Call` node or it sees a string constant and never confuses the two.

There is no `subprocess.Popen`, no `subprocess.call` and no `os.system` anywhere in the
repository — the audit looked for all of them. `focus.py`'s Windows reader is pure `ctypes`,
so it spawns nothing at all; its five sites are the mac and linux readers.

| call site | what it starts | creationflags before | after |
| --- | --- | --- | --- |
| `say.py:258` | **piper** — the voice | *(none — the defect)* | `_proc.run` → `CREATE_NO_WINDOW` |
| `hands.py:651` | **every registry hand** (`python.exe <script>`) | *(none)* | `_proc.run` → `CREATE_NO_WINDOW` |
| `focus.py:1035,1046,1057,1060` | `osascript` / `xdotool` — the mac and linux window readers | *(none)* | `_proc.run` → no-op off Windows, by design |
| `focus.py:1300` | the posture/idle reader's platform helper | *(none)* | `_proc.run` |
| `tools/relaunch_chrome.py:124` | `powershell launch-chrome.ps1` | *(none)* | `_proc.run` (imported as `import _proc`: a script inside `tools/` has that directory as `sys.path[0]`) |
| `preflight.py:603,3116` | `build.py` | *(none)* | `_proc.run` |
| `preflight.py:3913` | `console_watch.py`, for check 20(c) | — | `_proc.popen` (new this round) |
| `test_email_wiring.py:131` | the wiring probe's child | *(none)* | `_proc.run` |
| `tools/_proc.py:66,71` | `subprocess.run` / `subprocess.Popen` | — | **the policy itself — the one file allowed to reach subprocess** |

The measurement that named the defect, taken before a line was changed, with a tight `user32`
poll running while `POST /say` was in flight:

```
HIT +2,300ms  pid 45448  class PseudoConsoleWindow
      chain: piper.exe(45448) <- python.exe(42376)
```

And the same instrument after the migration, during a real 354,860-byte synthesis:

```
NEW VISIBLE CONSOLE WINDOWS: 0        (859 polls)
```

`console_watch.py` was then validated against a deliberately loud spawn — `CREATE_NEW_CONSOLE`
forced on — to prove it can still fail:

```json
{"root": 10072, "polls": 1168,
 "windows": [{"pid": 10120, "class": "PseudoConsoleWindow", "atMs": 3510,
              "chain": ["cmd.exe(10120)", "python.exe(10072)"]}],
 "bystanders": [{"pid": 45396, "class": "CASCADIA_HOSTING_WINDOW_CLASS", "atMs": 3428}],
 "hiddenConsoles": [{"pid": 32052, "image": "conhost.exe"}],
 "silent": false}
```

The CASCADIA bystander 82 ms before the hit is the same pair described in §20.1. A detector
that had only watched for `ConsoleWindowClass`, or that had failed on the presence of a
`conhost.exe`, would have got both of these backwards.

### 20.3 · Part 0, the four silent desktops (`console_proof.mjs` — 30/30 PASS)

Four real things, each watched at 8 ms from the moment before it started to the moment after
it finished, filtered by parent chain to the pid the server names for itself:

| case | how it was driven | spawns inside the watch | polls | verdict |
| --- | --- | --- | --- | --- |
| a short answer | **typed** — `/` summons the vanishing input, text inserted, Enter — then read aloud | 2 piper | 2,775 | **silent** |
| a long answer | typed, five or six sentences, one spawn per spoken chunk | 2–3 piper | 3,123 | **silent** |
| a voice recast | the casting panel's audition door, `__galaxy.cmd.cast.hear('en_US-ryan-high')` | 1 piper, cold | 492 | **silent** |
| a proposal | `propose` + `execute` on the hermetic `selftest` hand — `python.exe`, not the voice | 1 hand | 176 | **silent** |

```
  note A SHORT ANSWER: 2775 polls · 0 window(s) ours · 0 bystander(s) · 2 hidden console host(s)
  note A LONG ANSWER:  3123 polls · 0 window(s) ours · 0 bystander(s) · 3 hidden console host(s)
  note A VOICE RECAST:  492 polls · 0 window(s) ours · 0 bystander(s) · 1 hidden console host(s)
  note A PROPOSAL:      176 polls · 0 window(s) ours · 0 bystander(s) · 0 hidden console host(s)
```

Every one of those hidden console hosts is the policy working rather than failing — see §20.1.

Three things in that harness are there because of how this test could have lied:

**It cannot pass on a cache hit.** `say.py` writes its trace line on a synthesis and never on
a `say-cache/` read, so "piper really ran" is read out of `server-trace.log` rather than
assumed; and each case is made cold on purpose. The two answer cases speak one nonce sentence
through the page's own funnel, and the recast case has its `say-cache` entry *deleted* first —
addressed exactly as `say.py` addresses it, `sha256(model \0 lengthScale \0 noiseScale \0 text)`,
cross-checked against `say._key()` before it was trusted. Without that, an empty desktop is the
desktop of a machine that was asked to do nothing.

**It cannot pass without having looked.** `polls` is asserted above a floor per case. The first
version of `console_watch.py` treated end-of-input as a stop, so a watcher spawned without a
stdin pipe returned `polls: 0, silent: true` before examining the desktop once — a green light
for an unwatched screen. End of input is now explicitly *not* a stop; only a written `stop` is.

**It is headed and not muted.** The spawn under test only happens when a chunk is really
fetched and really played. A `?mute=1` tab would have reported four silent desktops with
nothing started behind any of them.

Two discretion decisions, recorded because the mandate words them differently. The filter is by
**window class, visible only**, not by image name: the visible window in the field measurement
was owned by `piper.exe` rather than by `conhost.exe`, and `conhost.exe` is what the repair
legitimately produces, so an image-name test would have passed the bug and failed the fix. And
the proposal case is raised through `/tools` + `/execute` on the hermetic hand rather than by
typing an instruction, because a harness that types and then clicks **Yes** on whatever comes
back is a harness that can click Yes on `send_email`; the spawn's parentage, which is the whole
subject, is identical either way.

### 20.4 · Part 0, preflight's new check

`preflight.py` gained **check 20, "nothing the server starts shows a console window"** — it
becomes check 21 when Part 5 inserts the Scribe chain ahead of it. Three parts, because no one
of them is evidence alone: **(a)** every `.py` in the repository parsed with `ast` and every
spawn attributed, one bare call anywhere being a failure; **(b)** the policy function exercised
in both directions, since a helper that overrode a caller's explicit `DETACHED_PROCESS` is how
a launcher stops launching; **(c)** a live watch on the running server while it really speaks.

```
  ✓  20. nothing the server starts shows a console window   2797 ms
        (a) 24 .py files parsed; 12 spawn call(s), all of them through the policy:
            focus.py(1035,1057,1060,1046,1300), hands.py(651), preflight.py(3116,3913,603),
            say.py(258), test_email_wiring.py(131), tools\relaunch_chrome.py(124)
        (b) the policy decides correctly both ways: nothing asked -> CREATE_NO_WINDOW
            0x08000000, DETACHED_PROCESS passed -> left untouched
        (c) 250924 bytes of real speech synthesised under pid 12036 while the desktop was
            polled 273 times: not one console window, and 1 hidden console host(s) - which is
            CREATE_NO_WINDOW working, since the flag means a console with no window rather
            than no console

  17 pass, 0 fail, 3 warn
```

The three warns are the standing ones and none of them judges the code: no OpenRouter key in
`config.json`, so the swapped brain's answer chain and the Astra look are unverified (checks 10
and 12), and no Chrome on the debugging port at that moment, so a session would degrade to the
application (check 11). Only `fail` judges the code, and it reads zero.

### 20.5 · Part 1, the research — edit distance on a recogniser's mistakes, and why the stream cannot be gated

**Why the metric is Levenshtein and not equality.** The transcript a microphone produces from a
loudspeaker is not the sentence the loudspeaker was given. It is that sentence with
*substitutions* in it — `roaster` → `roster`, `shelf` → `shell`, `warm` → `worm` — because a
recogniser under leaked audio is still doing acoustic modelling and still picking the nearest
word it knows. Substitution is exactly the operation Levenshtein counts, at a cost of one, which
is why edit distance is the right family of measure here and why a hash, an equality test or a
token-set overlap is not: the first two see a different string, and the third sees a different
bag of words. The implementation is the standard two-row dynamic program — `O(n·m)` time but
`O(m)` memory, two arrays swapped each row, because the full matrix is never needed when only the
last row is read. It is asserted against the textbook value, `levenshtein("kitten","sitting") === 3`,
since a function that merely returns small numbers for similar strings would pass a vaguer test
and still be wrong arithmetic.

**The part that plain distance gets backwards.** A recogniser does not hand back the whole
sentence. It hands back a *final* every time the room goes briefly quiet, so what arrives is a
fragment of what is being said. Measured plainly, a fragment is maximally *unlike* the paragraph
it came out of, because every character of the paragraph it does not cover counts as a deletion.
This was measured on the pair under test and it is the whole reason the law is not one line long:

```
  the fragment against the whole line: plain distance 125 (similarity about 0.25 if taken
  that way) but the law scores 1
```

A word-for-word piece of the butler's own sentence reads as **0.25 similar** — far under the
mandate's 0.70 — and a perfect echo would have been routed to the brain. So the distance is taken
against the best-matching **substring** of what is being spoken, by the free-ended form of the
same dynamic program: row 0 is all zeros, which lets the match *begin* anywhere in the spoken
text at no cost, and the answer is the minimum of the last row, which lets it *end* anywhere.
The same pair then scores **1.000**. The threshold still discriminates afterwards, which is the
other half of the research and the assertion most likely to be forgotten: the mangled fragment
scores **0.963** (the case exact matching cannot catch, and the only reason to be fuzzy at all)
while a different sentence of similar length scores **0.342** — *0.621 of daylight* between a
leak and a question. Without that second number every drop in the harness would be consistent
with a filter that drops everything.

**Web Audio, AEC, and the limitation this Part publishes rather than hides.** The mandate asked
for Layer 2 as a *stream* gate: feed the recogniser silence unless the room beats the output by
3×. That cannot be built on this page, and the reason is architectural rather than awkward.
`webkitSpeechRecognition` opens its **own** capture inside the browser; it accepts no
`MediaStream` argument and exposes no input node. This page's `getUserMedia` stream is a separate
capture that feeds an `AnalyserNode` and nothing else. There is therefore no node of ours between
the microphone and the recogniser to attenuate — inserting a `GainNode` would silence an analyser
that nobody listens to and leave the recogniser hearing the room exactly as before. Chrome's own
`echoCancellation: true` is already requested and is already insufficient: AEC models the path
from *this process's* output device to the mic, and it degrades badly on the delays, gain and
nonlinearity of real speakers in a real room — which is why the leak exists at all. So the 3.0×
decision is enforced at the only boundary this page actually controls, the transcript boundary,
and the page says so out loud in its own door rather than implying a mute that isn't there:

```js
streamGated: false,
transcriptGated: true,
gatedWhy: 'the Web Speech API opens its own capture; our getUserMedia stream feeds an ' +
          'AnalyserNode and nothing else, so there is no node of ours to mute'
```

The harness asserts those three fields. The effect the mandate wanted — his own voice never
reaches the brain — is delivered in full; the mechanism is one valve downstream of where the
mandate placed it, and the existing `earTurnHold()` still stops the recogniser outright while he
speaks, so this is a third layer behind two, not a replacement for either.

**The four discretion decisions, each with the failure it is a wager against.**

1. **The valve sits at the transcript boundary** (above). Cost of being wrong: none to
   behaviour, one paragraph of honesty owed — hence the published fields.
2. **`ECHO_GATE_RATIO = 3.0` is a new constant and `BARGE_RATIO = 1.6` is untouched.** They look
   like the same number and are two different wagers: 1.6 decides whether to *cut a sentence
   short*, which is cheap to get wrong and recoverable; 3.0 decides whether words *reach the
   brain*, which is not. `voice_proof.mjs` asserts the first, and echo_proof asserts it is still
   1.6, so neither can be tuned by way of the other.
3. **A finished line is still his voice for `ECHO_TAIL_MS = 1600`**, read off the existing
   `saidLines` ring under `SAID_TTL_MS` — no new bookkeeping and no new memory. A recogniser
   delivers a final up to a second after the audio that produced it, so a law that consulted only
   the live queue would let the last sentence of every answer through. The tail carries a
   `ECHO_TAIL_MIN_CHARS = 12` floor *in the tail only*: a short phrase turns up inside a long
   paragraph by coincidence, and once the engine is quiet a genuinely short reply is possible
   again.
4. **No reference means the gate stays shut** — the opposite of `bargeWatch`, which treats an
   unmeasurable reference as permission. The two are right in opposite directions because the
   cost of being wrong differs: there, a missed barge-in; here, a question nobody asked, answered
   out loud, on the record.

**And it is ahead of the interrupts on purpose.** `INTERRUPTS` catches barked words — `stop`,
`quiet`, `enough` — and the butler's own sentence contains *"I shall stop there"*. Placed behind
the interrupts, the law would be reached too late: a leaked `stop` empties the queue and he cuts
himself off mid-sentence. `echoDrop(raw)` therefore runs between the seal and the interrupt
lookup, and the harness asserts the queue is *still draining* after the leaked `stop` arrives.

### 20.6 · Part 1, the proof (`echo_proof.mjs` — 49/49 PASS)

Headed, **unmuted** Chrome on port 9248 with `--use-fake-ui-for-media-stream` — the *prompt* is
automated, the *device* stays real, because a fake device would be a signal the harness invented.
What the file does not claim is written in its own header: no audio is fed to the recogniser,
because the Web Speech API takes no `MediaStream` and Chrome's cloud service is throttled to
silence under a harness, so transcripts arrive through `__galaxy.speech.feedFinal`. The two
halves that matter are real — **real piper audio through the real graph**, and a **really open
microphone** — and Layer 2's output reference is post-gain RMS read off `speechBus` through the
analyser already tapped there for the mouth, never a number this harness handed in.

Three preconditions are assertions of their own, because each one is a way this file could pass
for the wrong reason: a real mouse gesture unlocks the `AudioContext`; the tab is **not muted**
(a muted tab gives a reference of zero and passes every gate claim); and the engine is **piper**
before a word is spoken, since `speakEngine` starts at `'web'` and only becomes `'piper'` on a
`/health` poll — the browser synthesiser never passes through this page's graph, so a harness
that speaks on the first tick measures an output of zero. A further wait — *a chunk is in flight
rather than queued behind a synthesis* — closes the ~1 s window in which the queue is live while
the bus is silent, which is a reference of zero wearing the clothes of a real measurement.

```
  ·· 4. LAYER 2 - the words got past the filter; the room did not
  note a quiet room against a live answer: input 0.01 against output 0.0118 from the bus (0.85x)
  ok   the output reference is REAL: 0.0118 RMS of post-gain samples read off speechBus through
       the analyser already tapped there for the mouth - not a number this harness handed in,
       which is what would make the whole of Layer 2 circular
  ok   and the gate is SHUT, because nothing in the room came to 3x that - the machine's own
       speakers leaking into the machine's own microphone measured 0.85x, which is the field
       condition this law exists for

  ·· 5. AND THE BARGE-IN REGISTERS - the assertion that stops Layer 2 being a mute button
  note a voice leaning in: 0.053 against 0.005 = 10.95x, held 228ms
  ok   and held there 228ms, over the 200ms asked - so one slammed door or one loud consonant
       is not a human being
  ok   THE GATE IS OPEN. Without this assertion every refusal above is consistent with a gate
       welded shut, which would be a page that had stopped listening rather than a page that
       had stopped answering itself
  ok   THE BARGE-IN REACHED THE BRAIN: exactly one new request to /chat, counted at the wire -
       one question in, one question through, and the law let it past on the loudness rather
       than on the words
```

**The self-recording rejection log**, the mandate's `kind: echo` ledger, printed by the page's own
`__galaxy.ear.echo.log` at the end of the run:

```
  note the law's ledger: 6 dropped (5 by the words, 1 by the room) and 2 passed
       drop  L1  sim 1      "The roaster on the second shelf is warm, sir, "
             word for word inside the chunk in flight and the queue behind it
       drop  L1  sim 1      "and I have set the table by the window"
             word for word inside the chunk in flight and the queue behind it
       drop  L1  sim 0.963  "the roster on the second shell is worm sir and"
             0.96 similar to the chunk in flight and the queue behind it (over 0.7)
       drop  L1  sim 1      "and I have set the table by the window"
             word for word inside the chunk in flight and the queue behind it
       drop  L1  sim 1      "stop"
             word for word inside the chunk in flight and the queue behind it
       drop  L2  sim 0.342  "What is the weather in Vancouver tomorrow afte"
             the acoustic gate is shut: nothing in the room reached 3x the output reference
             (0.010 against 0.012 from bus)
  note piper synthesised 0 chunk(s) inside this run; the other 2 came back out of say-cache/,
       which is the same bytes through the same bus
  ok   nothing was kept: no audio, no recorder, and an empty transcript buffer at the end of a
       run that put nine transcripts through the funnel

  VERIFY 49/49 PASS
```

**One assertion in that ledger was demoted to a note during Part 5's regression sweep, and the
demotion is a correction rather than a concession.** It was written as
`ok(n > 0, 'and piper really synthesised …')`, reasoning that a `say-cache/` hit would mean the
output reference had been measured from "a file being reread". That reasoning is wrong twice over.
It is wrong about the mechanism: `say.py` hands back the same WAV bytes either way, the page
decodes them and plays them through the same `speechBus`, and the analyser reads **post-gain**
samples off that bus — a cache hit is not a silent bus, and the run that first failed this
assertion measured **0.2449 RMS** on one. And it is wrong about itself: `LINE` is a fixed
sentence, so the cache is cold exactly **once per machine** — the assertion could only ever pass
on the first run on a given desktop and then fail for ever, which is an assertion that tests the
age of a directory. What it was reaching for is asserted properly at the Layer 2 gate above:
`reference === 'bus' && output > 0`, which is the measurement itself rather than a proxy for it.
The count stays as evidence, phrased as what it is.

**The mandate's own two claims, and two more the mandate did not ask for.** *The brain receives
zero inputs* is counted **at the wire** by CDP — `0 request(s) to /chat` across all five Layer 1
drops, and `0` thoughts formed — and not by asking the page whether it had behaved; *the barge-in
registers* is the same counter reading exactly one. The two extra claims are the ways this feature
fails without anybody noticing: a sentence scoring **0.342**, invisible to Layer 1, is dropped by
the gate anyway and counted against **Layer 2 specifically**, so the two layers cannot hide behind
one another; and **in a quiet room the law is inert** — after 2537 ms of silence, past the 1600 ms
tail, *his own sentence, verbatim*, is heard and reaches the brain, because the law is about a
leak in progress and not a blacklist of things the butler has ever said.

**Three traps this file fell into first, kept as notes because each is a way a later harness will
fail.** (a) A voice loud enough to clear 3.0× has *already* cleared the 1.6× barge gate, so the
answer is cancelled, the queue goes dry and `echoGateWatch` resets its own sustain — the gate's
evidence erased by the gate working. The loud pump therefore carries `maxSustainedMs` and
`maxRatio` out of its loop and breaks the moment the gate is open with sustain met. (b) `ask()`
begins `if (busy || ...) return;` and there is no `busy` door, so a question asked into a thinking
page leaves the wire still and looks exactly like a refusal; the file waits on
`Network.loadingFinished` versus `requestWillBeSent` plus `status.className !== 'thinking'`, and
asserts that wait as its own claim so the trap is on the record. (c) `heardFinal` *buffers* and
`flushThought` fires on the 900 ms pause, so a harness reading the wire on the next tick reads
zero and calls it a refusal.

**Regression, on the three harnesses most at risk** — the ear, the funnel and the routing:
`voice_proof.mjs` **133/133**, `conversation_proof.mjs` **104/104**, `routing_proof.mjs`
**65/65**. Preflight after the change: **`17 pass, 0 fail, 3 warn`**, the three standing warns.

### 20.7 · A harness-environment law found while proving Part 1 — the occluded window gets no frames

`voice_proof.mjs` failed **128/133** three times in a row, always on `__galaxy.presence.*`
reading zeros: *0 frames were drawn*, *0 points in FACE mode*, *uJaw never varied*. It was not a
regression. **A Chrome window that is behind another application is OCCLUDED, and an occluded
window is given no `requestAnimationFrame` at all** — measured on this machine at **61 frames a
second raised against 0 occluded**. The viewer's boot chain is a promise chain of frame-driven
stages,

```js
planetBoot().then(flowStart).then(deckBoot).then(stillPin).then(presBoot)
```

so without frames it **stalls before `presBoot()` ever runs**: `presence.built:false`,
`points:0`, `mode:""`, and — the tell that separates this from a real failure —
`trouble:""`, `why:""`, `three:""`, `notes:[]`. Nothing failed. Nothing ran. A harness reading
`built:false` and reporting a broken head would be reporting the desktop. With the window raised:
`built:true, points:12000`, and **133/133**.

The workaround was a scratch PowerShell raiser that walked `Win32_Process` for
`chrome.exe` command lines containing `remote-debugging-port` and called `ShowWindow` /
`SetWindowPos(HWND_TOPMOST)` / `SetForegroundWindow` on each, every 400 ms. It is **deleted
rather than promoted**, for a reason worth writing down: it steals focus while it runs, and a
harness with a *real* recogniser needs the room and the foreground to itself —
`routing_proof.mjs` read 62/65 with the raiser alive and **65/65** solo, which is the same lesson
the sweep rule already teaches. The law stays here as the thing to check first when a headed
harness reports a zero for something that should have been drawn: **raise the window, or expect
no frames.**

### 20.8 · Part 2, the research — how a call gets into a transcriber without going through the room

Four mechanics had to be settled before a line of the tap was written, and three of them are
counter-intuitive enough that getting them wrong produces a feature that *looks* finished.

**`getDisplayMedia` is the only door to system audio, and video is not optional.** Chrome will
not return an audio track for a display capture requested with `audio` alone; the picker itself
is a video picker, and `Share audio` is a tick *inside* it. So the Scribe asks for
`video: { frameRate: { ideal: 1, max: 4 } }` — a track nobody renders, floored so it costs
nothing — purely to be allowed to ask for the audio beside it. It also means the third refusal
exists at all: the picker can be **accepted with `Share audio` left unticked**, which returns a
perfectly healthy video track and no audio. Nothing throws. The button would light, the panel
would open, and every chunk would be three seconds of the room with none of the call in it. That
is the one way this feature fails while reporting success, so the whole capture is stopped and
the seal names the tick by its own label.

**The AEC split — the two tracks take opposite constraints, and the reason is which side of the
speaker each one sits on.** The microphone asks for `echoCancellation`, `noiseSuppression` and
`autoGainControl` **all true**: it is a real microphone in a real room and the room is noise. The
system-audio track takes **all three false**: echo cancellation on a signal that never went
through a room does not remove an echo, it removes consonants, and automatic gain applied to a
call that already has its own levelling pumps every pause. Same page, same graph, opposite
requests.

```js
sys = await navigator.mediaDevices.getDisplayMedia({
  video: { frameRate: { ideal: 1, max: 4 } },
  audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
mic = await navigator.mediaDevices.getUserMedia({
  audio: { echoCancellation: true,  noiseSuppression: true,  autoGainControl: true }, video: false });
```

**The zero-gain pull.** A Web Audio graph is pulled from the destination backwards. An
`AudioWorkletNode` whose output goes nowhere is **never called** — `process()` does not run, no
error is raised, and the tap looks exactly like a muted microphone. But connecting it to
`destination` plays the other side of the call back into the room at full volume and straight
into the echo law. The resolution is a gain node pinned at **0**:
`tap → gain(0) → destination`. The node is pulled because it reaches the destination; nothing is
heard because the gain is zero. It is three lines and it is the whole difference between a tap
that works and a tap that silently does nothing, which is why `scribe_proof` asserts *the worklet
is being PULLED* as a claim of its own rather than trusting that a graph was built.

**The `MediaRecorder` trap, which is why there is a worklet here at all.** The obvious design is
`new MediaRecorder(stream)` with `start(3000)` and one POST per `dataavailable` blob. It does not
work, and it fails in the way that costs a day: with a timeslice, **only the first blob carries
the WebM/EBML header**. Every later blob is a bare cluster, and PyAV — correctly — refuses it as
undecodable. A naive harness transcribes chunk 1, gets words, and passes. The repair is not to
re-glue headers; it is to stop using a container. The `AudioWorklet` takes raw `Float32Array`
frames, the page sums the two sources through one gain node, resamples to **16 kHz mono** (what
Whisper wants anyway), and writes its own **44-byte RIFF header** per chunk. Every chunk is then
a complete, independently decodable file — **94 KB each**, which is exactly what three seconds of
16 kHz mono 16-bit should weigh and is asserted as such. `scribe_proof` states the trap as a
number rather than a comment — *2 of 2 chunks came back with words* — because "more than one chunk
decoded" is the only assertion that distinguishes the worklet from the recorder.

### 20.9 · Part 3, the research — what a local transcriber actually costs, and the 3.13 hole under it

**faster-whisper, measured on this machine before the route was designed.** `import` is
**0.20 s**; the first `WhisperModel('base.en', device='cpu', compute_type='int8')` is the
expensive moment at **0.98–1.45 s** cold (**1664 ms** in the preflight run quoted below), and it
is paid **once** — so the model is held by the long-lived server and never constructed per
request. After that a **3 s** chunk costs roughly **0.5 s** of CPU, and the whole **5.14 s**
fixture came back in **894 ms**: comfortably real-time on four threads, which is what makes a 3 s
chunk cadence honest rather than a queue that grows for the length of the meeting.

Three behaviours decided three route decisions:

- **`BytesIO` decodes identically to a path.** Measured, not assumed — and it is the finding the
  privacy law rests on. There is no temporary file anywhere in the chain; the WAV arrives as a
  multipart part, is handed to the decoder as bytes, and is dropped. `keepsAudio: false` is
  published on `/health` as a boolean precisely so a harness can read the promise, and
  `scribe_proof` then checks it **from outside the process** by walking the project root for new
  audio files across the whole meeting.
- **Silence is not an error.** Three seconds of digital silence with `vad_filter=True` yields
  **zero segments** — no exception, no empty-string hallucination. So a pause in a meeting costs
  a `200` with no words rather than a red line in the panel. Without the VAD filter, Whisper
  reliably invents a sentence over silence; the filter is load-bearing, not a tuning.
- **Junk bytes raise `av.error.InvalidDataError`, and that must not be a 500.** A single corrupt
  chunk in a forty-minute meeting has to cost that chunk and nothing else, so an undecodable body
  is a **`200` with `ok:false`** and an English reason (*"that chunk was not audio this machine
  could decode"*) — the meeting keeps running. A malformed *request*, by contrast, is a real
  `400`, and a misnamed part gets told which name to use (*"Send the audio in a part named
  \"audio\"."*). Those are the three ways a chunk can be wrong, and preflight check 20(d)
  exercises all three.

**And the hole under all of it: `audioop` was removed in Python 3.13.** Preflight has to build a
16 kHz fixture to post, and `audioop.ratecv` — the one-line answer every example gives — no longer
exists in the interpreter this machine runs. `_wav16k()` therefore resamples by hand with `wave`
and `struct`, and it **interpolates linearly rather than dropping samples**. That is not
fastidiousness: piper renders at 22050 Hz, and decimating to 16 kHz by taking every *n*th sample
folds everything above 8 kHz back down into the speech band as aliasing — sibilants become buzzes
and the transcriber starts guessing. The difference is audible and it is measurable in the
transcript, which is why the method is named in the source rather than left to be inferred.

### 20.10 · Part 4, the research — a panel that outlives the meeting, and a hand that writes nothing

Part 4's mechanics are less exotic and its failure modes are worse, because each one loses work
that was already done.

**The panel stays open on stop.** The natural symmetry — press to start, press to close — takes
the only copy of the meeting off the screen at the exact moment it becomes useful, since
*stopping* is the moment the minutes can first be drafted. So `scribeStop()` releases both
captures (which is what turns the browser's own recording indicator off, and is asserted for that
reason), leaves the transcript where it is, and moves the organ to **HELD** — *something is true
and nothing is happening*. `scribe_proof` asserts the panel's survival as a named failure mode
rather than as an incidental.

**The minutes are drafted, never written.** `/scribe/minutes` returns text and touches no file;
the write is `tools/save_minutes.py` through the ordinary Hands gate, on the employer's Yes. Two
consequences are assertions: **the file does not exist before the Yes** — a hand that wrote on
`propose` rather than on `execute` would have written it by then, and no amount of correct UI
would undo that — and **the minutes shown on the card are the minutes that would be written**,
all four headings present, so what is approved is the artefact and not a promise about it.

**The `overwrite` flag is a visible row, not a hidden parameter.** Yes on an existing file means
*Replace*, and a decision that destructive has to be readable where it is taken. That makes the
card taller, which makes the third assertion necessary: **the `minutes` row is clamped and Yes is
still on the screen.** An unbounded value there pushes the one button that must never be
unreachable off the bottom of the window — a card that cannot be refused is worse than no card.
The harness finds that row by walking `#ask-rows` in label/value pairs and matching the `b` whose
text is `minutes`, having first tried `:last-of-type` and learnt that it silently depends on the
registry's field order.

### 20.11 · Part 4, a real defect the Scribe fixture found — a tooltip with two authors

`scribe_proof`'s offline-refusal case asked for something simple: with the transcriber down, the
button's tooltip should say what the button is **for** and why it cannot be pressed. It said only
this:

```
  Checking whether this machine has a transcriber…
```

Neither half. Not what it does, not why it is dead — and it said it permanently, long after the
check it described had finished. The mechanism is worth writing down because it will catch the
next organ too. `organsPaint()` sets every organ's title to `ORGAN_TIP[id] + '\n' + state.line`,
and **`ORGAN_TIP[id]` is captured lazily off the markup on the FIRST paint of that organ** and
never again. `organsUp()` runs at the end of boot; the Scribe's own section runs long before it.
So the boot line

```js
$('scribebtn').title = 'Checking whether this machine has a transcriber…';   /* deleted */
```

was not a placeholder that would be replaced — it was **adopted as the button's permanent base
description**, because it is what `.title` held when the first paint read it. And the three
*later* writes, in `scribeHealthFrom`, `scribeStart` and `scribeStop`, were the opposite error:
each lasted until the next paint, milliseconds, because the class change they accompanied is what
triggers the observer that repaints. Four title writes; one of them permanent and wrong, three of
them dead code that read like the authority.

The repair is one author for that attribute. All four writes are deleted; `organRead` owns the
sentence, off the markup; and because there genuinely is a second in which the answer is not back
yet, it gained a case for it rather than guessing:

```js
/* BEFORE THE FIRST /health there is no answer yet, and "unavailable" would be a
   guess. The button is disabled either way; only the sentence differs, and a man
   hovering it in the first second deserves the true one. */
if (!scribe.asked) {
  return { organ: 'off', line: 'checking whether this machine has a transcriber…' };
}
if (el.disabled) {
  return { organ: 'off', line: 'unavailable · the transcriber is offline · ' +
           (scribe.why || 'faster-whisper is not installed') };
}
```

`scribeHealthFrom` now sets the one thing it owns — whether the control can be pressed — and calls
`organsPaint()` **unconditionally**, because `why` can change while `installed` does not, and the
reason is the half of the tooltip worth reading. The assertion that caught it is phrased as the
law rather than as the symptom:

```
  ok   and the tooltip carries BOTH the markup’s sentence and the server’s own reason - it
       outlives the four seconds the seal gives it, and a tooltip written by two authors is a
       tooltip that shows whichever of them painted last
```

### 20.12 · Part 5, the meeting itself (`scribe_proof.mjs` — 58 checks · 58 pass · 0 fail)

Headless-new Chrome with `--auto-select-desktop-capture-source=Entire screen`,
`--use-fake-ui-for-media-stream`, `--use-fake-device-for-media-stream` and
`--use-file-for-fake-audio-capture=<fixture>`. **Nothing in the chain is mocked except the two
picker-return refusals**, which have no other way to be provoked: the dismissal and the
`Share audio`-unticked case. The rest is a real `getDisplayMedia`, a real worklet, real POSTs
counted at the wire off `Network.requestWillBeSent`, the real transcriber, the real brain, the
real Hands gate and a real file on disk.

**The fake-device finding, which is what makes the fixture possible.** Measured under all three
auto-accept flag sets, a display capture requested with `{video, audio}` comes back as

```json
{"audio":1,"video":1,"alabel":"Fake audio","vlabel":"screen:-3:0"}
```

— the video track is a real screen source and **the display capture's audio track *is* the fake
device**, so it reads the fixture WAV. That is the whole reason a scripted meeting can be spoken
at this feature at all. It has a consequence the fixture has to absorb: **both** capture devices
are the same fake device, so the display-audio track and the microphone track carry the *same
file*, and the page sums them through one gain node. Two identical signals added clip. The fixture
is therefore **peak-limited to 0.4** before it is written — a measured accommodation of the
harness environment, recorded here because a reader finding `0.4` in the source would otherwise
have to guess at it. The builder also **walks the RIFF chunk list instead of assuming data starts
at byte 44**, because piper's output does not always oblige.

**Typed and spoken, and the honest version of that rule for this Part.** The Scribe's *input* is
spoken — real piper speech through a real capture device, which is as spoken as a fixture gets —
and its *controls* are clicked. There is no spoken trigger for the Scribe and there will not be
one: `getDisplayMedia` requires **transient user activation**, so a voice command cannot legally
open the picker, and a butler who could start recording a room because he thought he heard his
name is not a feature. The typed half of the round's fixtures lives in Part 0's four desktop
cases (§20.3), which drive the vanishing input.

**The transcript, as the panel showed it:**

```
  | listening · system audio and your microphone · nothing is written to disk
  | 0:04  quarterly review is on Thursday at 10. We agree.
  | 0:07  to send the deck by Wednesday evening. The quarterly reading.
```

Spoken at it: *"The quarterly review is on Thursday at ten. We agreed to send the deck by
Wednesday evening."* The keywords asserted are **quarterly**, **thursday**, **wednesday**;
*"ten"* is deliberately **not** among them, because `base.en` writes it as **10** — an assertion
on the word would have been an assertion about a transcriber's formatting, which is not what this
file is for. The chunk boundary at 0:04/0:07 is visible in the output (*"We agree."* / *"to send
the deck"*), which is what three-second chunking looks like honestly reported rather than
stitched over.

**The minutes, drafted by the brain from that transcript and written after the Yes:**

```markdown
# Meeting-2026-09-26-2111

Minutes taken Saturday 26 September 2026 at 21:11 by the Scribe.

## Attendees
Not named in the recording.

## Key Decisions
- Quarterly review is on Thursday at 10.
- "to send the deck by Wednesday evening."

## Action Items
- Owner not stated - send the deck - by Wednesday evening.

## Raw Excerpts
> quarterly review is on Thursday at 10. We agree.

> to send the deck by Wednesday evening. The quarterly reading.
```

`Written to notes/Meeting-2026-09-26-2111.md - 65 words in 4 sections.` — the hand's own stdout,
asserted to be the answer the card shows, so the tool says where it put the file rather than the
page claiming it on the tool's behalf. Note *"Attendees: Not named in the recording"* and
*"Owner not stated"*: the draft declines to invent the two things a five-second fixture cannot
contain, which is the behaviour worth having. The harness writes **exactly one file**, prints it,
and deletes it on both the success and the failure path.

**The privacy law, measured from outside:** *not one audio file appeared anywhere under the
project root during the meeting*, and the server — asked afterwards — reported the chunk count it
transcribed while holding no audio and no text. Preflight check 20(g) makes the same measurement
server-side, counting audio files under the root before and after and asserting none grew, with
`say-cache/` excluded **by name and out loud**, because it holds the speech this machine
*produces* and because 20(b) deliberately puts the fixture there. An exemption nobody can see is
how a privacy sweep stops meaning anything.

### 20.13 · The matrix at the end of the round (Part 5), and what is left open

Every standing harness, run solo, the last leg against a server started fresh (`pid 15548`);
`port_proof.mjs` last, because it can leave a Chrome on 9222.

| harness | result | what it holds down |
| --- | --- | --- |
| `scribe_proof.mjs` | **58 checks · 58 pass · 0 fail** | the whole Scribe chain, the three refusals, the privacy law from outside |
| `console_proof.mjs` | **30/30 PASS** | four silent desktops, parentage-filtered, polled |
| `echo_proof.mjs` | **49/49 PASS** | the echo law, both layers: self-voice dropped, barge-in let past |
| `deck_proof.mjs` | **208/208 PASS** | the cinematic deck and the six-organ rail |
| `routing_proof.mjs` | **65/65 PASS** | the funnel |
| `voice_proof.mjs` | **133/133 PASS** | the full read, the barge-in gate, the head |
| `conversation_proof.mjs` | **104/104 PASS** | the turn, the amend door |
| `layout_proof.mjs` | **72/72 PASS** | the desk |
| `followup_proof.mjs` | **47/47 PASS** | the antecedent memory |
| `nudge_proof.mjs` | **21/21 PASS** | the purse and the callouts |
| `persona_proof.mjs` | **19/19 PASS** | the persona block |
| `capabilities_proof.mjs` | **16/16 PASS** | the injected capability list, counted not typed |
| `desk_proof.mjs` | **44 checks, 0 failed** | the still frame and the pin |
| `focus_probe.mjs` | **PROBE 26/26 · 78 checks, 0 failed** | the focus session's own instrument |
| `lock_proof.mjs` | **70 checks, 0 failed** | the lock with CDP teeth — see the note below |
| `brain_live.mjs` | **33 checks, 0 failed** | the live brain and the recogniser seal |
| `eyes_live.mjs` | **56 checks, 0 failed** | the eyes, and that no organ turns the microphone on |
| `tools_live.mjs` | **VERIFY 50/50 PASS** | the hands, end to end, calendar restored |
| `port_proof.mjs` | **24 checks, 0 failed** | the debugging-port launcher (run last) |
| `preflight.py` | **21 checks · 18 pass, 0 fail, 3 warn** | checks 20 and 21 are new this round |

**Open, named. (1) `salutation_proof.mjs` — 26/34, pre-existing and not caused by this round.**
The failing set is **byte-identical** to the one in `_runs/salutation_proof.txt` from 13:42, and
appears in five prior logs across the day — `diff` of the `FAILED:` lines is empty, including
against a run made on a freshly started server, which rules out long-lived process state. The
cause is corpus growth: the assertions want *"who is JARVIS in the movies?"* to fall through the
thin-score trigger and reach the web (`kind=web, searched=thin`), and the answer now comes back
`{"kind":"notes"}` — the archive PDF indexed in an earlier round scores well enough to keep the
web gate shut. **The web gate is on this mandate's DO-NOT-ALTER list**, so this is reported rather
than tuned. Either the harness's questions or the corpus would have to change, and both are
decisions above a regression sweep's pay grade.

**(2) `lock_proof.mjs` — a failure that was process state, not code.** It read **65 checks, 17
failed** during the sweep and reproduced identically solo after an eight-second settle
(`_runs/lock_proof.sweep.txt`, `_runs/lock_proof.solo2.txt`). Every premise and every step through
the relaunch passed — port 9222 answering, `cdp=true`, the work tab restored — and then the
deferred lock never completed inside the ~14 s the harness allows: `lockedTab=""`, `watchers=0`,
`watchPolls=0`, and every downstream timing check overrunning its budget by roughly **2×**
(*noticed in 2834 ms, budget 1500 ms*). The same file on the same code read **70 checks, 0 failed**
at 10:40 and reads **70 checks, 0 failed** now. The one variable that changed is the server
process: the failing runs were answered by a pid that had been up ~18 minutes through the entire
sweep, including a harness-driven Chrome relaunch; the passing runs by a pid started minutes
before. Nothing edited this round touches `focus.py`, and **the lock with CDP teeth is on the
DO-NOT-ALTER list**, so no repair was attempted. The shape — ticks arriving late rather than not at
all, since the session did eventually reach `running` — points at the **tick thread being starved**
in a process that has had a day of harnesses through it, and that is a hypothesis and not a
finding: the failing process was killed before it could be interrogated, and `/focus/diag`
publishes `tickAlive`, `ticks` and `tickAgeS` precisely for the next time (a healthy process
measured **1.25 ticks/s** here). **The rule that follows is operational and belongs beside the
sweep rule: a lock sweep gets a freshly started server**, and a lock failure seen against a
long-running one is not evidence until it survives a restart. The route's own docstring already
warned of this from the other end — *"a fresh interpreter passes every check while the one
actually holding your session sits on a tick thread that died forty minutes ago."*
