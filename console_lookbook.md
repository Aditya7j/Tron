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

> **CORRECTED BY §21.7.** The hypothesis in the paragraph above — a starved tick thread in a
> long-lived server — was tested with the reading it asked for and **is wrong.** The tick thread
> was healthy (`ticks 759->760`, `tickAgeS=1` against `TICK_S=1.0`) while the drift went
> uncounted, because a second *headless* viewer was claiming **home base**, and home base
> outranks every drift by design. The operational rule this section drew from it — a lock sweep
> gets a freshly started server — is still good practice, but it was not the cause. See §21.7.

## 21 · The Room Knows the Hour — the compact head, the working sky, the gaze, and a lie the instrument was telling

This section is this round's own record, in §20's shape: the research for each Part written
against what the code actually did beforehand, the numbers chosen with the reason each was
chosen, and the measurement that settled it. It is **additive to §17–20 and replaces none of
it**, with one exception stated plainly and early: **§20.13's closing hypothesis was wrong, and
§21.7 disproves it with the reading it asked the next round to take.**

### 21.0 · The baseline, and why it was taken the long way

Every standing harness and `preflight.py`, solo and sequential, on a machine with no stray
Chrome and one server (`pid 18140`), `port_proof.mjs` last. This is slow and it is not
optional: §18.15 already proved that a shared debugging port or a stale `server-trace.log`
makes a harness lie **in both directions**, so a baseline taken any other way is not a
baseline, it is a coincidence. The table is at §21.11, baseline beside after, because a round
that cannot show what it found is indistinguishable from a round that broke something quietly.

One thing the baseline caught immediately, and it is the reason the rule exists: **`lock_proof.mjs`
read `33 checks, 2 failed` on runs 1, 2 and 3, `2/2` on run 4, and `70 checks, 0 failed` only on
run 5.** Run 5 is the number in §20.13's matrix. A green reached on the fifth attempt is not a
green, it is a race that happened to land, and §21.9 names what was actually rotten.

### 21.1 · Part 1, the research — a floor that refuses is not a floor, it is a cliff

§17.1 measured `PRES_MIN=168` and reported, honestly, *"no room: 12px of 168"* at 1280×860. The
honesty was never the problem. The problem is what the honesty was describing: the head that
took a whole Part of §17 to build **does not render at all on the single most common laptop
width**, and a single floor can only ever answer yes or no. So the governor gains a **second**
floor and a **tier** between them, and the failure mode changes from absence to reduced
density.

The well, measured at 860px tall with the note panel open, is not a matter of opinion:

| width | well side | tier |
| --- | --- | --- |
| 1280 | **12px** | stands down — see below |
| 1366 | 55px | stands down |
| 1440 | 92px | stands down |
| 1536 | **140px** | **compact** |
| 1600 | 172px | full |
| 1920 | 235px | full |

`PRES_MIN_COMPACT = 120`, and **120 rather than 100** because `PRES_LIP.gap = 0.013`: at 120px
and dpr 1 the lip is 1.56 device pixels, at 100px it is 1.3, and below about 76px it is under
one — a lip that cannot be drawn is a lip that is not there, and the head stops being the same
head. `COMPACT_DENSITY = 0.45`, and **0.45 rather than the 0.22 that area scaling would
suggest** (140²/300²), because constant per-pixel density at a third of the size gives a
silhouette that reads as soft rather than as sparse; the points are dropped with
`setDrawRange`, so it is fewer of the same vertices and not a second geometry.

**And the finding Part 1 was told to report rather than hide: 1280×860 with the note panel open
still stands down, and no floor can rescue it.** 12px of room is not a rendering problem, it is
an absence of room; a floor of 12 would draw a head nobody could identify and would be a lie
told to make a check pass. The repair for 1280 is a layout decision about the note panel, which
is not this round's to make.

### 21.2 · Part 1, the evidence (`deck_proof.mjs`)

Measured at a width chosen to force the tier, and audited by **the mechanism that already
exists** — the same probation that FACE-vs-RING has used since §17.3, with RING as the fallback
if compact cannot hold the floor either:

```
ok  at 1920x860 the well is 235px, clear of the 168px full floor, and the head is at full density: 12,000 points
    the tier ladder at 860 tall: 1600→172px full   1536→140px compact
ok  THE COMPACT TIER ENGAGES AT 1536x860: 140px of room, under the 168px full floor and over the 120px compact one
ok  and it AUDITIONS ITSELF on the mechanism that already exists: "kept" - 60.4fps compact against 60.3fps with the ring, floor 55, keep-ratio 90%
ok  AND IT IS THE SAME HEAD WITH FEWER POINTS: 5,401 points at 45% density against 12,000 full - 45% of the vertices for 60% of the width
ok  still one object, one material and a real shader at the compact tier - the density changed and nothing else did
ok  and the tier is not a one-way door: the window comes back and so does the full density - 12,000 points again
```

So the answer to the question Part 5 asked to be answered as a finding if it went the other way:
**compact holds the floor on this GPU comfortably — 60.4fps at 5,401 points**, and the §17.2
claim survives the tier intact (one object, one material, `shader:true`). The audition is not
decorative: on one earlier run the ring baseline read **39.3fps** because resize churn was still
settling when probation started, which depresses the number the trial is compared against and
would have kept compact for the wrong reason. It is recorded because a probation that can be
biased by the harness's own resizing is worth knowing about even when its verdict is right.

### 21.3 · Part 2, the research — the room, not the card

A focus session tinted the countdown card. That is a badge, not a mood: the one element already
telling you a session is running was the only element that changed. The session's
`public_state()` is **already** on the wire over SSE — *"the whole session state, as booleans and
counters"* — so nothing is added to that payload and no second channel is opened. The DEEP FIELD
(§12) and the world materials (§2, §10) simply become **subscribers to the stream that was
already there**, through one scalar.

That scalar is `work.k`, eased by `workEase()` — which solves the `cubic-bezier(0.16,1,0.3,1)`
already declared for entrances in §3 by twenty bisections rather than approximating it — with
`workSet()` as the single subscriber called from `fxApply`, and `workFrame()` writing nothing
but an opacity and a number, repainting only on 2% steps. The working sky is a **second layer**
(`#nebula-work`, `z-index:1`, `pointer-events:none`, invisible at rest) rather than a repaint of
the first, so §12's ink ceiling is never in question: the work layer's loudest channel peaks at
**5% alpha**, under §12's 6%, and because the idle nebula falls to 30% at the same time the
**total ink in the frame goes down**, not up.

The five numbers, declared where they can be argued with — which is the whole argument §12 made
once already about 6% and 0.16/0.48/1.00:

| number | value | why this value |
| --- | --- | --- |
| `WORK.MS` | **900** | three times `--spring-ms`; long enough to read as a room changing, short enough not to be a wait |
| `WORK.NEB_IDLE` | **1** | the room at rest is exactly the room §12 shipped — the identity, written down so it can be asserted |
| `WORK.NEB_WORK` | **0.30** | the nebula **dims** rather than vanishing, so the cloud keeps its shape and the cooler band reads as a shift and not a swap |
| `WORK.SWAY` | **0.45** | `DECK.STAR_SWAY`'s 34 units of lean become 15.3 — the sky stops leaning about as much as the work asks you to stop leaning |
| `WORK.DESAT` | **0.45** | world emissive is pulled 45% toward its **own** luminance, so each world dims into its own grey rather than toward a shared one |

Reduced motion gets `work.ms = 0`: the destination, never the journey. And the reversal is the
same curve run backwards on pause, abort and end — never a cut, in either direction.

### 21.4 · Part 2, the evidence

The mandate asked for an intermediate frame proving a crossfade rather than an instant swap, so
the ramp is sampled rather than described:

```
    the ramp up:   0 → 0.5378 → 0.8154 → 0.9263 → 0.9721 → 0.991 → 0.998 → 0.9998 → 1 …
ok  THE ROOM CROSSFADES RATHER THAN CUTTING: 7 of 16 samples caught it strictly between the two ends
ok  and it takes 935ms of wall clock to arrive, against the 900ms declared - one --spring curve, not a step
ok  AND ALL THREE ORGANS ANSWERED: the nebula fell to 0.3 with the cooler band up at 1, the star parallax from 34 to 15.3 units, and the world emissive desaturated by 45%
    the ramp down: 1 → 1 → 0.4988 → 0.1988 → 0.0796 → 0.0303 → 0.0099 → 0.0023 → 0.0002 → 0 …
ok  THE ROOM WARMS BACK UP THE SAME WAY IT COOLED: 7 intermediate samples on the way home, and it settles exactly back on the room it started from - k=0, nebula 1, swing 34
ok  two turns for one session, and not one per SSE push: turns=4
```

**935ms against 900 declared** is the curve, not a step; seven intermediate samples each way is
the proof that no frame jumps; and `turns=4` — two per session, not one per SSE push — is what
keeps a per-second state broadcast from restarting the crossfade sixty times.

### 21.5 · Part 3, the research — aliveness as attention, on the driver that exists

§18.7 gave the head idle yaw/pitch drift and a stress-nod: aliveness as **physics**. What it
could not do is look at anything. The addition is aliveness as **attention**, and it is
deliberately not a new animation system — it is a change to the **target** the existing sine
driver orbits. `focus.py` already computes drift; the page **reads** that rather than
recomputing it, so there is no second copy of the server's "counted AND running" to fall out of
step:

```
ok  THE GAZE NAMES ITS SIGNAL EXACTLY: "focus.public_state().drifting" - one field of focus.py's own public_state, read rather than recomputed
ok  its three numbers are bounded the way a gaze has to be: at most 0.2618 radians of turn (15°, a glance rather than a head-turn), a 260ms time constant, and a deadband of 0.02175 under the turn it measures
ok  AND THE GPU WAS TOLD THE SAME THING: uGazeY=0, uGazeP=0, read back off the material rather than off the bookkeeping beside it - the gaze is a target on the existing idle driver, not a second animation
```

`GAZE_MAX = 0.2618` (15°) is three times the idle yaw's 5°, so a glance is legible against the
wobble it rides on but is still a glance and not a head-turn. `GAZE_TAU = 260` is a time
constant used as `1 - e^(-dt/tau)`: frame-rate independent and incapable of overshoot, which a
spring would not be. `GAZE_EPS = PRES.YAW_IDLE / 4 = 0.02175` exists so that **the idle wobble
alone cannot trip the departure frame count** — without a deadband the harness would measure the
sine, not the gaze. The aim is taken on the drift's edges and then twice a second
(`GAZE_AIM_EVERY = 30`), because a target recomputed every frame is a tremor.

**And the deviation Part 4's assignment forced, named rather than smoothed over.** The mandate
asked for the gaze measured on a real drift driven the way `lock_proof.mjs` already drives one
(§18.5) rather than a synthetic state push — which is right, and is what was done. But a real
drift **cannot be measured in a headless page**, and the reason is §21.7's finding: the drift
detection is gated on not being at home base, and a headless page is permanently at home base.
So the gaze assertions live in `lock_proof.mjs`, which is headed and already owns a real
relaunch, with `focus_probe.mjs` asserting the signal name, the three bounds and the at-rest
uniforms. No parallel harness naming scheme was created, as instructed.

### 21.6 · Part 3, the evidence, on a real drift

`lock_proof.mjs`, headed, with a real locked tab actually left behind:

```
ok  LEAVING THE LOCKED TAB IS NOTICED in 1316 ms (budget 1500 ms)
ok  THE HEAD TURNS TOWARDS THE CHANGE on a real drift: the gaze left centre on frame 191 (8803ms on the page's own clock), aiming at [-0.12444,0.04446] radians because "focus.public_state().drifting" went true
ok  AND THE HEAD COMES BACK TO CENTRE when the drift ends: frame 261 (9969ms), 70 frames and 1166ms after it left - one departure for one drift, not a head that stayed turned
```

Twice, on two runs: departure frame **169 (8698ms)** → return frame **221 (9581ms)**, 52 frames
and 883ms; and departure frame **191 (8803ms)** → return frame **261 (9969ms)**, 70 frames and
1166ms. The target is `[-0.12444, 0.04446]` radians — a reach of **0.1038 rad**, past the
0.02175 deadband and well inside the 0.2618 ceiling — and `departures === 1` for one drift,
which is the assertion that catches a head that turns and then stays turned.

### 21.7 · The correction to §20.13 — the instrument was not being starved, it was standing in front of the watcher

§20.13 closed on a hypothesis: `lock_proof.mjs` failing at *"noticed in 2834 ms, budget 1500 ms"*
looked like **a starved tick thread** in a long-lived server, and the section said so while
labelling it a hypothesis and not a finding, and named the fields `/focus/diag` publishes
*"precisely for the next time."* This is the next time, the reading was taken, and **the
hypothesis was wrong.**

The reading is worth the space because the two candidate causes have the same symptom and
opposite repairs — a starved watcher wants to be fed, an excused one wants its excuse taken
away — so the rate was sampled instead of guessed. Two reads of the manager's own tick counter a
second and a half apart, taken **after** the stopwatch so they cost the measurement nothing:

```
ticks 759->760 = 0.67/s against TICK_S=1.0, tickAgeS=1, watchPolls advancing,
watchState=off, inGrace=false, and by now drifting=false drifts=0
```

Nothing was late. `tickAgeS=1` on a `TICK_S=1.0` loop is a heart beating on time, and
`drifting=false` **1500ms after the budget had already been overrun** says the drift was never
going to be counted at all. It was being **excused**.

The excuse is `?nohome=1`'s whole reason for existing. Every viewer beats `fxFetch(true)` →
`/focus?home=1` → `note_home_hint()` while a session is live and `document.hasFocus()` is true,
and `Session.tick()` computes `at_home = self._home_hint_fresh(now) or bool(verdict["home"])`
and only reaches `_tab_drifted()` when `not at_home`. **Home base outranks every drift by
design** — "coming back to talk to me is never a drift" is correct behaviour and stays. But
**under `--headless=new`, `document.hasFocus()` is permanently true**: there is no other window
for the page to lose the keyboard to. This round opens a second, headless viewer as an observer,
so that the head can be watched while a real drift happens in a browser that is not the
observer's own — and that observer beat *"I am home base"* every `FOCUS_HOME_BEAT_MS` for the
entire run. A locked-tab drift on the machine was therefore silently excused by an instrument.

Measured, **twice each way**, because a claim this embarrassing should not rest on one run:

| condition | drift noticed | `drifts` | watcher |
| --- | --- | --- | --- |
| observer open | still uncounted at **2861 ms**, and again 1500ms later | **0** | `watchState=off`, `inGrace=false`, ticks advancing |
| observer skipped (`LOCK_AB=1`), nothing else changed | **937 ms** | **1** | callout spoken |

The repair is one suppressed beat and nothing else about the page changed:
`if (probeRunning || NOHOME) return;`. **`?focusprobe=1` was considered and rejected** for the
job: `PROBE_ON` makes the page hermetic — no greeting, no brain read, and crucially **no session
stream** — and the session stream is the one stream the gaze reads, so the flag that made the
drift measurable would have made the gaze unmeasurable. `preflight.py` check 22 part (d) asserts
both the flag and the exact guard line, so removing it fails preflight rather than quietly
reintroducing a lying harness.

`lock_proof.mjs` went **72 checks / 15 failed → 77 checks / 0 failed**, drift noticed in 778ms.

### 21.8 · A repair that was measured and did nothing, kept on the record

The starvation theory produced `gazeStandBack()`: PowerShell setting `PriorityClass =
'BelowNormal'` on every `chrome.exe` whose CommandLine matches the observer's own `mkdtemp`
leaf. With **twelve of the observer's processes confirmed at BelowNormal**, the check still read
**2856 ms** — against 2861 without it. The priority drop is kept, on the narrower claim it can
actually support (an observer that yields is a better neighbour than one that does not, and 778
of 1500ms is measured with it in place), and its comment was **rewritten to stop claiming a fix
it did not make.** A function whose docstring describes a repair it never achieved is worse than
no function, because the next reader stops looking.

### 21.9 · Two harness faults this round found that were not this round's doing

**(a) The launcher profile poisons itself, and the §18 prevention did not prevent it.**
`lock_proof.mjs` read `33 checks, 2 failed` twice consecutively — *"the relaunch restored his
work tab: "* empty, then *"Cannot read properties of undefined (reading 'id')"*. The profile's
`Default/Sessions/` held its newest `Session_<ts>` at **01:27** while a `Tabs_` had been written
at **08:58**, with `exit_type: Crashed`: Chrome had stopped writing the session it is asked to
restore. **The `SESSION_DIRS` prevention added in the previous round did not prevent
recurrence.** The documented repair worked on the first try — confirm zero Chromes on the
profile with the **profile-scoped** filter, then move the profile aside — and the very next run
read `77 checks, 0 failed`. Two `devtools-profile-chrome.broken-*` folders are now on disk
(`…-20260927` and `…-20260927-0910`) and are left there deliberately as evidence. **This 33/2
signature is exactly what §21.0's baseline recorded for runs 1–3**, which retroactively explains
the baseline's own flakiness: it was a poisoned profile, not a flaky lock.

**(b) `layout_proof.mjs` Section 3 was asserting the graph's ordering, not the layout.** It
focused `__galaxy.nodes[0]`, and Section 3 asserts that the spoken report's toast does not bury
the panel's CONNECTED chips — but **a note with no links has no chips to bury.** At baseline
`nodes[0]` was *"Customer Feedback Log"* with seven neighbours and the check passed; after a
brain rebuild (the one preflight's own canary provokes every time it runs) `nodes[0]` was a
loose *"Meeting 2026-09-26-2132"* of degree zero, and the same check read *"every one of the 0
CONNECTED chips is legible"* and failed. **Nothing about the layout had moved.** The node is now
**chosen** by the property the section needs — a degree table built from `strongLinks` falling
back to `allLinks`, reading both the id and the object shape of `source`/`target` because
force-graph rewrites them once it has run — and named in the assertion line, with `nodes[0]`
still the fallback so a graph with no links at all fails on the chip count itself rather than on
an undefined id. Now **72/72**, *"the best-connected of 32 notes, degree 11"*.

### 21.10 · Preflight check 22 — "the room knows the hour, and the instrument does not lie"

The next integer after the 21 the repo's HEAD ended on, read rather than guessed. It is static
analysis plus one live read, in four parts, and it exists because every number above is only
worth what it is worth if it cannot be silently deleted:

- **(a)** the two floors read off the `LAYOUT` literal — FAIL if `PRES_MIN_COMPACT` is absent, is
  not below `PRES_MIN`, or is declared and **never read** via `LAYOUT.PRES_MIN_COMPACT`;
- **(b)** the `const WORK = {…}` block parsed — FAIL on a missing key, on `MS <= 0` (*a crossfade
  of zero milliseconds is a CUT*), on `NEB_WORK >= NEB_IDLE`, or on `SWAY`/`DESAT` outside
  `0 < x < 1`;
- **(c)** the literal string `focus.public_state().drifting` present, `GAZE_MAX`/`GAZE_TAU`/`GAZE_EPS`
  all declared, and **no** `presence.gaze.(want|at) =` setter — the gaze may be read from outside
  and never driven from outside;
- **(d)** `nohome=1` present **and** the exact guard `if (probeRunning || NOHOME) return;` present;
- then a live `/focus` read that **FAILs if any session-payload key matches
  `neb|gaze|presence|emissive|parallax|compact`** — the room subscribes to the session's state,
  and the session must never learn that the room exists. WARN, not FAIL, when the server is down.

It runs in **53 ms** and the fifteen original checks are untouched, as instructed.

### 21.11 · The matrix at the end of the round (Part 5) — baseline beside after

Baseline solo/sequential against `pid 18140`; after-column solo, foreground, `port_proof.mjs`
last on a quiet machine.

| harness | baseline | after |
| --- | --- | --- |
| `lock_proof.mjs` | **70 checks, 0 failed** — but green only on run 5; runs 1–3 read 33/2 | **77 checks, 0 failed** |
| `deck_proof.mjs` | **208/208 PASS** | **224/224 PASS** |
| `focus_probe.mjs` | **PROBE 26/26 · 78 checks, 0 failed** | **PROBE 26/26 · 85 checks, 0 failed** |
| `layout_proof.mjs` | **72/72 PASS** | **72/72 PASS** (71/72 before §21.9b's repair) |
| `desk_proof.mjs` | **44 checks, 0 failed** | **44 checks, 0 failed** |
| `persona_proof.mjs` | **19/19 PASS** | **19/19 PASS** |
| `capabilities_proof.mjs` | **16/16 PASS** | **16/16 PASS** |
| `nudge_proof.mjs` | **21/21 PASS** | **21/21 PASS** |
| `voice_proof.mjs` | **133/133 PASS** | **133/133 PASS** |
| `echo_proof.mjs` | **49/49 PASS** | **49/49 PASS** |
| `console_proof.mjs` | **30/30 PASS** | **30/30 PASS** |
| `conversation_proof.mjs` | **RED** (ear/network) | **104/104 PASS** |
| `scribe_proof.mjs` | **58 checks · 58 pass · 0 fail** | **58 checks · 58 pass · 0 fail** |
| `brain_live.mjs` | **33 checks, 0 failed** | **33 checks, 0 failed** |
| `eyes_live.mjs` | **56 checks, 0 failed** | **56 checks, 0 failed** |
| `tools_live.mjs` | **50/50 PASS** | **50/50 PASS** |
| `port_proof.mjs` | **24 checks, 0 failed** (last) | **24 checks, 0 failed** (last) |
| `preflight.py` | **21 checks · 16 pass, 0 fail, 5 warn** (6,10,11,12,17) | **22 checks · 19 pass, 0 fail, 3 warn** (10,11,12) |
| `followup_proof.mjs` | **47/47 PASS** | **42/47 FAIL** — corpus, see §21.12 |
| `routing_proof.mjs` | **RED** (*the ear has failed 3 times in a row (network)*) | **RED** — recogniser, see §21.12 |
| `salutation_proof.mjs` | **26/34 FAIL** (pre-existing) | **26/34 FAIL** (unchanged) |

Preflight's warns went **5 → 3**, and the two that cleared are worth naming because they were
misread once: warns 6 and 17 were **residue counts** from earlier preflight runs — *"after
cleanup the brain holds 32 notes, not the 30 it started with"* and *"the store holds 38 files,
not the 36 it started with"* — and not, as was previously recorded, a count of the two loose
`notes/Meeting-*.md` files. Both passed cleanly this round with those two files still on disk.

**A backgrounded sweep is not a sweep, and this round re-proved it.** `_runs/final_sweep.sh`
run in the background produced **eight** reds — layout 71/72, followup 42/47, nudge 12/21, voice
broken with **0 audio chunks**, echo 28/49, eyes_live 56/31, tools_live 2/3, lock_proof 17/6,
port_proof 24/7 — and `lock_proof.mjs` diagnosed it in English without being asked: *"FAILED to
raise chrome 576; front is 47024"* and *"front at the end of the press was Code (47024)"*.
Windows only lets a process set the foreground if it already owns it or has just launched, so a
harness launched from a backgrounded shell cannot raise its own Chrome, and every audio and
click harness fails that way. Re-run one at a time as blocking foreground calls: nudge 21/21,
voice 133/133, echo 49/49, eyes_live 56/0, tools_live 50/50. **All headed and audio harnesses
run one at a time, blocking, never inside a backgrounded sweep.** The sweep's greens stay valid;
its reds were about the shell.

### 21.12 · Open, named

**(1) `followup_proof.mjs` — 42/47, and it is the corpus, not the code.** The harness's first
question is *"what is react"* and it now comes back `kind=notes` where the baseline had
`kind=web`. The only file in the whole store that mentions React is
`notes/Meeting-2026-09-26-2135.md` — a **Scribe-round test artefact** whose Raw Excerpts
literally contain the line `> What is react?`, which scores well enough to keep the web gate
shut on a question about React. Two remedies exist and **neither was taken**: delete the two
test minutes, or change the harness's question. The web gate is on the DO-NOT-ALTER list, and
the notes are the boss's data — a regression sweep does not get to delete either.

**(2) `routing_proof.mjs` — the recogniser, not the funnel.** Every failing case is a *spoken*
one and every one reads the same way: `the funnel was asked "" · 0 asks · kind=undefined`, with
the ear's own record beside it — `{"transcript":[],"attempts":3,"wire":[]}`. The speech
recogniser returned nothing at all, three attempts deep, so the funnel was never asked a
question and had nothing to route; a second solo re-run on a quiet machine got further and then
**aborted outright** at `Error: the ear closed; there is nothing to speak into`. The typed cases
pass except one web-gate case, which is item (1)'s cause again. It was **RED at baseline too**,
for the ear's own stated reason (*"the ear has failed 3 times in a row (network)"*), so this
round did not cause it. The known mechanism is the cloud recogniser's silent throttle, which
returns empty results rather than an error and which no amount of local correctness can fix from
inside the page.

**(3) 1280×860 with the note panel open still has no head**, and §21.1 explains why no floor can
rescue 12px of room. The repair is a layout decision about the note panel.

**(4) The `SESSION_DIRS` prevention does not prevent profile poisoning** (§21.9a). The repair is
documented and fast, but it is a repair and not a prevention, and the next round should expect
to make it again.

**(5) Two `devtools-profile-chrome.broken-*` folders are on disk** (`…-20260927`,
`…-20260927-0910`), left deliberately as evidence. They are inert and can be deleted whenever
the profile fault stops being interesting.

One thing checked and found **not** to be open: the eight-clusters-versus-palette question reads
`8 colours across 8 folders, each folder one colour and no colour in two folders`, so no colour
wraps and no cluster shares.

---

## 22 · The Road Outside the House — a real calendar, a real mailbox, and an answer that stays in the glass

Two hands stopped pretending this round. `add_calendar_event` used to append a line to
`calendar.json`, a file nobody but this project has ever opened; `send_email` used to log in to
`smtp.gmail.com` with an app password. They now speak to Google Calendar v3 and Gmail v1 over an
OAuth grant the employer authorises once, in his own browser, from a Command Panel row. The long
answers that used to push the document sideways now scroll inside the glass. And the harness that
had been quietly seeding the semantic corpus was stopped, then made incapable of doing it again.

What follows is the whole round: what was read before anything was written, every number with its
reason, what was proved, what was deliberately not proved, and what is still open.

### 22.1 · What was read first

**The loopback flow, RFC 8252 and Google's own installed-app guidance.** A desktop application has
nowhere safe to keep a secret and no server to receive a redirect, so the authorisation code comes
back to a small HTTP server the application itself runs on `127.0.0.1` — a loopback redirect, which
RFC 8252 prefers over the older custom-scheme and out-of-band methods because the operating system
guarantees that only a process on this machine can bind that port, and the browser will not send
the code anywhere else. The flow is therefore: build a consent URL at
`https://accounts.google.com/o/oauth2/v2/auth` carrying the client id, the redirect URI, the scope
list, `response_type=code`, a PKCE challenge (`code_challenge` with `S256`), a random `state`, and
— because this application must keep working tomorrow without asking again —
`access_type=offline` together with `prompt=consent`, which is what makes Google return a refresh
token rather than an access token alone. The user consents in a browser they already trust; Google
redirects to `http://127.0.0.1:<port>/?code=…&state=…`; the loopback server reads the code, checks
`state`, and POSTs the code with the `code_verifier` to `https://oauth2.googleapis.com/token` to
exchange it for an access token (an hour's life) and a refresh token (no expiry of its own). The
client secret for an installed application is, by Google's own documentation and by RFC 8252's
reasoning, **not** treated as confidential — it cannot be kept secret in a binary a user can read —
which is why PKCE, not the secret, is what actually protects this exchange.

**Calendar v3, `events.insert`.** One authenticated `POST` to
`https://www.googleapis.com/calendar/v3/calendars/primary/events` with a JSON body carrying
`summary`, `start` and `end` (and `description` if there is one). The shape of `start`/`end` is the
part worth reading twice: each is an object, not a string, and it is either
`{"dateTime": "2026-09-28T16:00:00+05:30"}` for a timed event or `{"date": "2026-09-28"}` for an
all-day one, and the two kinds may not be mixed within one event. For an all-day event the `end`
date is **exclusive** — a one-day event on the 1st ends on the 2nd — which is the single most
likely place for an off-by-one to become a meeting on the wrong day. The response is the created
event, and `id` on it is Google's own identifier, which is what the receipt quotes back so the
employer has something to search for. `primary` is a reserved calendar id meaning "the signed-in
account's own calendar", so no calendar list needs reading, and `calendar.events` is a scope that
can write events without being able to read the rest of the calendar's settings.

**Gmail v1, `users.messages.send` and the draft that stands in for it.** Gmail does not take fields;
it takes a whole RFC 822 message. The body of the request is `{"raw": "<base64url>"}` where the
payload is the complete message — `To`, `From`, `Subject`, `Date`, `Message-ID`, the MIME headers
and the body — encoded with the URL-safe alphabet and the padding stripped, `POST`ed to
`https://gmail.googleapis.com/gmail/v1/users/me/messages/send`. `me` is the reserved id for the
authenticated account, so the `From` address is the account's own and is taken from the token
rather than from anything a caller supplied. The important discovery for a test suite is
`users.drafts.create`: same body, wrapped one level deeper as `{"message": {"raw": …}}`, `POST`ed
to `…/users/me/drafts`, and deletable with `DELETE …/users/me/drafts/{id}`. Gmail parses the raw
field on the way in and rejects a malformed message, so a draft that comes back with an id is a
message that **would** have flown — which is how the authenticated path gets proved without a
letter leaving the building.

### 22.2 · The scopes, in full

    https://www.googleapis.com/auth/gmail.send
    https://www.googleapis.com/auth/gmail.compose
    https://www.googleapis.com/auth/calendar.events

Three, all of them write scopes with no read. This grant **cannot** list a message, cannot read a
thread, cannot see the mailbox it sends from, and cannot read a calendar it did not put an event
into. `gmail.compose` is present for exactly one reason — `drafts.create` is the narrowest method
that proves auth and serialization without sending, and it also permits `users.getProfile`, which is
how the panel learns which account is connected. Deliberately absent: `gmail.readonly`,
`gmail.modify`, `https://mail.google.com/` (total control of the mailbox), and plain `calendar`. A
wider scope is one edit away and would never fail a test, because a broader scope never refuses —
it only permits. That is why the list is asserted by **equality** in preflight check 23(a), from
the source and again from the running server, and why the same check greps for the wide scopes by
string literal.

### 22.3 · Every number, and why it is that number

| Number | Where | Why this one |
|---|---|---|
| **4731** | `LOOPBACK_PORT` | Its own port, not the server's. 4700 is the house and 9222–9254 are the harnesses' debugging ports, one of them watched by `focus.py`; a consent server landing there would fight a debugger. Fixed rather than ephemeral because a fixed port can be allowed through a firewall once, where an ephemeral one asks the question again every time. |
| **300 s** | `CONSENT_TIMEOUT` | How long the loopback server waits for a human to choose an account and read a consent screen. Five minutes is generous for a person and short enough that a forgotten window does not leave a listening socket open all day. |
| **120 s** | `REFRESH_SKEW` | The access token is refreshed two minutes *before* Google says it expires, not after. Refreshing on expiry means the first request after the hour is the one that fails, and the employer sees a refusal caused by arithmetic. |
| **30 min** | `DEFAULT_MINUTES` | "Remind me to call the client at four" names a start and no end; a calendar event must have both. The brain is told never to invent a time, so the default lives in one place in code and is **rendered onto the card** as part of the duration before anybody presses Yes. An invented end nobody saw would be the same mistake as an invented address. |
| **45 s** | both hands' `timeout_s` | Was shorter when these hands were local. A round trip to Google over a domestic connection, with one token refresh possible inside it, needs room; 45 s is long enough to survive a refresh and short enough that a wedged request does not hold the consent slot past its own TTL. |
| **min(46vh, 560px)** | `--answermax` | The answer panel's height clamp. 46vh keeps the prose under half the glass so the Yes/No pair and the caption stay in view on a short window; the 560px ceiling stops a very tall monitor from rendering a paragraph the reader has to stand up to finish. |
| **2 s / 310 s** | panel poll | The Google state line polls every 2 s while the sheet is open, and stops after 310 s. Two seconds is fast enough that pressing Connect and returning from the browser shows CONNECTED without a second thought; the ceiling is `CONSENT_TIMEOUT` plus ten seconds, so the poll outlives the thing it is waiting for by exactly one breath and then stops rather than running all day. |
| **5,000 / 400 / 300** | `layout_proof` 2f | The injected answer, its unbroken token and its URL. 5,000 characters is longer than any real answer this machine has produced; 400 characters with no space in it is far wider than any viewport at any of the three widths, so nothing but `overflow-wrap` can save the layout; 300 characters of URL is a realistic hostile citation. |
| **2099-01-01 / 2028-03-07** | probe stamps | The refusal probes use 2099 so that a stamp which somehow reached a calendar would be unmistakably a test; the live probe event uses 2028 because Google rejects some far-future recurrences and the point of that one is to be accepted, read back, and deleted. |
| **200** | *removed* | A 200-character body preview was written into the spoken proposal and then taken out again. See §22.7. |

### 22.4 · Part 0 — the corpus, and the harness that was seeding it

Two files were deleted:

    notes/Meeting-2026-09-26-2132.md
    notes/Meeting-2026-09-26-2135.md

They were minutes drafted by `scribe_proof.mjs` during acceptance runs that were killed before
their cleanup could run. They were real notes in a real folder, and `build.py` embeds that folder,
so a harness had been quietly adding documents to the corpus the retrieval tests are measured
against. `followup_proof.mjs` was failing 42/47 because of them.

The store was rebuilt with `python build.py`, and the counts moved as they should:

| | before | after |
|---|---|---|
| notes (`.md` under `notes/`) | 32 | **30** |
| note groups (folders) | 8 | **7** |
| vector-store files | 38 | **36** |
| embedded chunks | 57 | **55** |

`followup_proof.mjs` then returned **47/47 PASS** and has stayed there.

The repair matters less than the guard. `scribe_proof.mjs` now deletes its artefact **the moment it
has been read** — the assertion that the minutes are on disk, and the assertion of what they say,
both happen first, and then the file is unlinked; `cleanup()` runs on the normal exit and on the
throwing one. The harness gained a check for exactly that, which is why its count went 58 → **59**.
A harness may prove the Scribe writes notes; it may not leave one in the corpus it is measured
against. `notes/` was empty of `Meeting-*` before this round's run and empty of them after it.

### 22.5 · Part 1 — the connect flow

`Connect Google` is the sixth row of the Command Panel, keyboard **G**, between *archive* and
*cast*. Pressing it builds the consent URL, opens it in the employer's own browser, and starts a
loopback server on **127.0.0.1:4731**. The code comes back to that server, is exchanged with PKCE,
and the token and refresh token are written to `secrets/google_token.json` — a folder already
gitignored, and already denied to me by tooling. The panel's state line reads one of:

    GOOGLE: CONNECTED · <account email>          action: Disconnect
    GOOGLE: NOT CONNECTED                        action: Connect
    GOOGLE: RECONNECT NEEDED                     action: Reconnect

Disconnect deletes the token file, asks Google to forget the grant, and says which of those two it
managed: *"The token is deleted, sir, and Google has been told to forget it as well"*, or *"The
token is deleted, sir. Google could not be reached to revoke it, so do that from your account page
if it matters"*, or — with nothing to remove — *"There was nothing to disconnect, sir."* The
telemetry rail gained no cell; the panel carries this, as instructed.

`GET /google` is the only Google route the page can read, and it carries six facts: whether a client
file exists, a truncated client id, the scope list, the port and redirect URI, the state word with
its reason, and — when connected — the account address, a **digest** of the refresh token, and the
seconds left on the access token. It carries no access token, no refresh token, no authorization
code and no client secret. Preflight check 23(b) asserts that by field name **and** by searching the
payload for the client secret's own 35 characters, because a field with an innocent name is still a
leak; it also asks the server for `secrets/google_token.json`, `secrets/google_client.json` and one
directory traversal at them, and requires all three to refuse. They 404.

### 22.6 · Part 2 — the calendar, for real

`add_calendar_event` now calls `events.insert` on `primary`. `calendar.json` is retired as a
backend: the hand neither reads nor writes it, which preflight check 23(e) proves from the hand's
own source with its docstrings stripped out — a hand that wrote to Google and *also* appended
locally would let a failed send look like a success. The file is still on disk, inert, for the boss
to delete when he likes.

The card shows the human reading of the stamp, and this is where a small mechanism earned its keep.
The registry's sentence carries two **derived blanks**, `{when}` and `{duration}`, which `hands.py`
composes from the validated parameters using the same `event_times()` the script uses, and which
**never enter `params`** — so the rows underneath stay verbatim, carrying the exact ISO stamp that
will travel, while the sentence says *"Thursday 1 January at 9:00 am, 30 minutes (the default, since
no end was given)"*. The card and the wire cannot disagree, because both are computed from the same
validated values by the same code.

Refusals: not connected → *"I have no road to your calendar yet, Addi - Connect Google, and I
shall."* Refresh failure → the reconnect line. A Google 4xx/5xx → the failure named plainly, the
ledger records **failed**, and nothing is retried silently. One retry exists and only one: a 401 is
treated as a possibly-stale access token, the token is refreshed once and the request repeated
once, because a 401 on a token that was just refreshed is a revocation and not a race.

An unreadable time is now refused **at the gate**, with nothing left pending. That was a decision,
not an accident: the first version filled the card with a literal `{when}` and asked the employer to
approve it, and the alternative — carrying the nonsense to Google to be told no — spends a click and
a round trip to reach a refusal that was already knowable. So `readings()` returns a refusal, the
slot is dropped, and the answer is *"I cannot put that in the calendar, sir: that start time is not
a date I can read - it wants 2026-09-28T16:00 or 2026-09-28."* The script keeps its own identical
check, because it can be run by hand and defence in depth costs nothing here.

### 22.7 · Part 3 — the mail, for real, and the canary that stopped a leak

`send_email` builds a complete RFC 822 message with `email.message.EmailMessage` — `To`, `From`,
`Subject`, `Date`, `Message-ID`, the body set as UTF-8 quoted-printable — and sends it with
`users.messages.send`. The `From` is the connected account's own address, read from the token and
never from a parameter, so this hand cannot be asked to forge a sender. Attachments are refused by
name in v1 rather than failing: *"I cannot attach a file to an email yet - the message itself can
go, but nothing can travel with it…"*, and the refusal is checked **first**, before the recipient is
even validated, because the worst outcome is not an error — it is the letter going anyway, without
the file, while the sender believes it went with it.

**And then the canary caught me.** The mandate asks the proposal card to show `to · subject · first
200 chars of body`, so I put a `{preview}` blank in the registry's proposal sentence and a
200-character preview into `hands.py`. Preflight check 16(f) failed within the hour:

    (f) THE CANARY WAS SPOKEN. The proposal template renders a parameter the employer
        never asked to hear read out in a room

That clause plants a fresh clock-derived string in `send_email`'s body and fails if it appears in
`pending.line`. `line` is not a caption — `speakLine()` says it **out loud**. An email body is the
one parameter in this project that can be entirely somebody else's business, and a machine that
reads your correspondence aloud to whoever is standing in the room has taken the wrong half of a
trade nobody offered it. The standing check wins: `{preview}` is gone, the sentence now reads *"I
have an email ready for `<to>`, sir, under the subject '`<subject>`'. The card carries what it says.
Shall I send it?"*, and the body is shown **on the card, in the rows, in full and verbatim** — which
is more than a 200-character preview and is the copy that actually travels. `hands.py` carries the
whole story as a comment where the preview used to be, so the next person to think of this reads
why it is not there before writing it again. Check 16 now passes with the canary *"absent from every
file under the project root and from every one of the 96 responses this run, save the parameters the
page renders for the human to read."*

The proof does not send. `google_hands_proof.mjs` exercises `users.drafts.create` and then deletes
the draft. **The one real send remains the employer's** — the reserved Gmail round trip, now against
the real API.

### 22.8 · Part 4 — the contained page, measured

`--answermax: min(46vh, 560px)` clamps the answer's prose; `overflow-y: auto` scrolls it;
`overflow-wrap: break-word` on body text and `overflow-wrap: anywhere` on code, citation chips,
captions and the ask-rows break the unbreakable; `pre` scrolls internally rather than widening its
parent. The clamp went on `#answer .a` — the prose — and **not** on `#answer` itself, for three
reasons: the Yes/No gate must never scroll out of view; `#answer.tool::after` is an
absolutely-positioned ring at `inset:-1px` that a scroll container would clip and then scroll away
from the buttons it surrounds; and the whole 5,000-character payload lands in `.a` anyway.

`answerReach()` grants the panel a tab stop and `role="region"` **only when it actually overflows**,
measured (`scrollHeight - clientHeight > 1`) after the text is typed, and removes both when it does
not — a permanent tab stop on a two-line answer is a keyboard trap that announces nothing.

`layout_proof.mjs` section 2f injects 5,000 characters containing one 400-character unbroken token
and one 300-character URL, and asserts the injection is what it claims to be (both hostile tokens
present, neither containing whitespace) before measuring anything — an earlier version padded the
filler first and silently sliced the URL to 214 characters while a length-only self-check passed.
Measured, at each width:

| width | body text box | body scroll height / clamp | document | wrap | tab stop | PageDown |
|---|---|---|---|---|---|---|
| 1280 | 265 ≤ 265 | 3364 / 396 px (max 395.6) | 1280 ≤ 1280 | break-word | `"0"` | 0 → 345.3 px |
| 1600 | 425 ≤ 425 | 2088 / 396 px | 1600 ≤ 1600 | break-word | `"0"` | 0 → 345.3 px |
| 1920 | 585 ≤ 585 | 1531 / 396 px | 1920 ≤ 1920 | break-word | `"0"` | 0 → 345.3 px |

The card around the text overflows nothing either (311 ≤ 311, 471 ≤ 471, 631 ≤ 631), the document
never scrolls sideways at any of the three widths, the scrollbar is reachable by keyboard — a real
`Input.dispatchKeyEvent` PageDown moves `scrollTop` — and a short answer afterwards carries **no**
tab stop and **no** region role. `layout_proof` went 72 → **95 checks, all green**.

### 22.9 · Part 5 — the regression matrix

Solo, sequential, foreground, quiet, `port_proof` last. The baseline is the §21 end-of-round solo
sweep, taken minutes before this round began with no code changed in between.

| harness | baseline (§21, solo) | after | |
|---|---|---|---|
| `desk_proof` | 44 checks, 0 failed | 44 checks, 0 failed | ✅ |
| `layout_proof` | 72/72 PASS | **95/95 PASS** | ✅ +23 (Part 4) |
| `followup_proof` | 42/47 FAIL | **47/47 PASS** | ✅ Part 0 |
| `salutation_proof` | 26/34 FAIL | 26/34 FAIL | ◽ named, pre-existing |
| `capabilities_proof` | 16/16 PASS | 16/16 PASS | ✅ |
| `persona_proof` | 19/19 PASS | 19/19 PASS | ✅ |
| `nudge_proof` | 21/21 PASS | 21/21 PASS | ✅ |
| `deck_proof` | 224/224 PASS | **224/224 PASS** | ✅ 2nd attempt, see below |
| `focus_probe` | PROBE 26/26 · 85 checks, 0 failed | PROBE 26/26 · 85 checks, 0 failed | ✅ |
| `voice_proof` | 133/133 PASS | 133/133 PASS | ✅ |
| `conversation_proof` | 104/104 PASS | 104/104 PASS | ✅ |
| `routing_proof` | 38/65 FAIL (crashed on the ear) | **64/65 FAIL** | ◽ one ear-throttle red |
| `echo_proof` | 49/49 PASS | 49/49 PASS | ✅ |
| `console_proof` | 30/30 PASS | 30/30 PASS | ✅ |
| `scribe_proof` | 58 checks, 0 fail | **59 checks, 0 fail** | ✅ +1 artefact guard |
| `brain_live` | 33 checks, 0 failed | 33 checks, 0 failed | ✅ |
| `eyes_live` | 56 checks, 0 failed | 56 checks, 0 failed | ✅ |
| `tools_live` | 50/50 PASS | **54/54 PASS** | ✅ +4 |
| `lock_proof` | 77 checks, 0 failed (3rd attempt) | **77 checks, 0 failed** (4th attempt) | ✅ see below |
| `preflight.py` | 22 checks · 19 pass, 0 fail, 3 warn | **23 checks · 20 pass, 0 fail, 3 warn** | ✅ +check 23 |
| `port_proof` | 24 checks, 0 failed | 24 checks, 0 failed | ✅ |
| `google_hands_proof` | — | **27/27 PASS (2 skipped)** | 🆕 |

The three preflight warns are **10, 11, 12** — the same three as the baseline, with the same known
causes. Nothing regressed.

**Two reds that came and went, named rather than hidden.** `deck_proof` failed three assertions on
its first run of the sweep: the compact tier's frame-rate audition measured 52 fps against its own
55 fps floor, dropped to the ring as the existing law says it should, and the two density
assertions that follow were then reading a perturbed room — the harness narrates this itself
(*"the compact tier could not hold 55fps on this GPU"*). Re-run alone after a pause: **224/224**,
with the audition reading 60.2 fps and the verdict *kept*. `lock_proof` needed four attempts, as its
own baseline needed three. Attempts one and two died at 56 s on *"the relaunch restored his work
tab"* — Chrome's `--restore-last-session` brought back the viewer but not the work tab — attempt
three restored **two** `example.com` tabs where one was expected, which is residue from the two
attempts before it, and attempt four was clean at 77/0. Both failures live in Chrome's session
restore and window foreground, and nothing this round touched either; the residue sat in the
employer's own default Chrome profile, which the standing law forbids me to close.

**`routing_proof` and `salutation_proof` remain red, untouched and named.** `salutation_proof` is
26/34, identical to baseline — the pre-existing 0.60-threshold red. `routing_proof` improved from a
crash at 38/65 to **64/65**: its single remaining failure is the ear-throttle, one spoken utterance
coming back as `""` because the cloud recogniser silently returns an empty transcript under load.
Environmental, pre-existing, and deliberately not chased.

**`preflight.py` check 23 — *the road to Google is narrow, and it refuses politely*** — reads from
HEAD and has five clauses: (a) the scopes are exactly the three, by equality, from the source **and**
from the running server, with a literal-scan for the wide ones; (b) nothing secret on the wire, the
client secret checked by value, `secrets/` unreachable over HTTP; (c) the refusal chain end to end
through `propose` → `execute` for both hands, requiring the English sentence, the named remedy, no
status code quoted at a human, and exactly one **failed** ledger run each; (d) the stamps read
before the network is; (e) `calendar.json` retired, proved from source, with the registry's four
parameters asserted. Clause (c) does **not** run on a machine that has a grant — proving a refusal
would mean creating a real event to be refused about — and says so rather than passing quietly. Its
live output:

    ✓  23. the road to Google is narrow, and it refuses politely    395 ms
          three write-only scopes, declared and matched exactly: send, compose, calendar.events
          the running server agrees, and reads state 'absent' on port 4731
          and the client secret's 35 characters appear nowhere in the payload, checked by value
          and secrets/ is unreachable over HTTP: the token file, the client file and one traversal
          calendar.json is named nowhere in the hand's code, and the schema is the four it reads
          an unparseable start is refused at the gate, naming the shape it wants, nothing pending
          with no grant, the chain propose -> confirm -> run ends in the hand's own sentence,
            'The tool failed, sir: I have no road to your calendar yet, Addi - Connect Google…'
          and the mail hand refuses in the same shape, at the same door

### 22.10 · The two probes, and the transcript that does not exist yet

`google_hands_proof.mjs` is new: no browser, no CDP port, every claim an HTTP claim or a subprocess
claim, so unlike the headed harnesses it is safe to run beside another. Its probes go through the
project's own `google_api` module — the identical functions the hands call — because a harness that
spoke to Google with its own fetch and its own token handling would be testing a second
implementation and reporting on the first. It never opens `secrets/`. It prints no token, no code,
no secret, and not the account address either: accounts appear as an eight-character digest.

**Sections 6 and 7 SKIPPED, and the skips are counted separately from the passes.** There is no
grant on this machine — `GET /google` reads `absent` — so Gmail and Calendar cannot be reached, and
the two transcripts the mandate asks for do not exist. I will not invent them. What ran instead:

    6. the draft that proves the send without sending
      SKIP a draft is created from a real RFC822 message and then deleted
           there is no grant on this machine (state "absent"), so Gmail cannot be reached.
      ok   and the draft probe this machine would have run is valid python

    7. the event that is created, seen, and taken back
      SKIP a probe event is created, read back with events.get, deleted, and 404s
           there is no grant on this machine (state "absent"), so Calendar cannot be reached.
      ok   and the calendar probe this machine would have run is valid python

Those two `ok` lines are the round's one genuinely new idea about testing. A section that skips is a
section whose code is never parsed, so a typo inside it would sit unnoticed until the one run that
finally had a token — the moment somebody was trying to prove the feature worked. So both probe
sources are built by functions, and when a section skips, the source it *would* have run is handed
to Python's own `compile()` and asserted to parse. Compiling is not running: no import executes, no
request is made, and a missing comma does not need a credential to be found.

What the two probes will do, on the employer's machine, after one press of Connect Google:

- **The draft probe.** Build a real message with `send_email.build()`, `drafts.create` it, assert an
  id came back and that the serialized message was more than 100 bytes of real headers, fetch it
  back with `?format=raw`, base64url-decode it and assert the subject and recipient survived the
  round trip, `drafts.delete` it, and assert a fetch of the same id **404s**. It also asserts that
  nothing in the section called `messages.send`.
- **The calendar probe.** `event_times("2028-03-07T11:00", "")` → `events.insert` → assert Google's
  id came back → `events.get` and assert the summary is the title that was sent and that
  `start.dateTime` still begins `2028-03-07T11:00` (a timezone dropped in transit is a meeting five
  and a half hours out) → `events.delete` → `events.get` again and assert **404**. Created and
  destroyed inside one run, so the diary ends the run exactly as it started it.

What did run, token-free, is the half that is true on most machines: both hands refuse in their own
English at the same door a human uses, naming the remedy, without quoting a status code or a token
at anybody, and each refusal is recorded as one **failed** ledger run rather than swallowed; an
unknown `POST /google` command is refused naming the two that exist; disconnect with nothing to
disconnect says so; an unreadable stamp never reaches the network; and an attachment is refused by
name. **27/27, two skipped.**

### 22.11 · Discretion exercised, with reasons

1. **The §21 sweep is this round's baseline.** Taken solo, sequential, foreground, quiet, with
   `port_proof` last, minutes before this round began, with no code changed in between. Re-running
   twenty-one harnesses to produce an identical table would have cost an hour and proved the same
   thing.
2. **The consent click is the employer's, and the skip is honest.** Everything token-free is
   proved; the two token-only sections skip with the reason printed, are counted separately, and
   their sources are compile-checked. I did not connect his Google account on his behalf.
3. **The height clamp went on `#answer .a`, not `#answer`.** The gate must not scroll away, the
   `::after` ring at `inset:-1px` would be clipped by a scroll container, and the payload lands in
   `.a` regardless.
4. **`tools_live`'s witness moved from `calendar.json`'s length to the ledger's `ok + failed`.** The
   old witness was a fossil once the file was retired; the ledger is a strictly better one and
   always was — it distinguishes ok from failed from refused, and it cannot be satisfied by a script
   that wrote a file without being asked.
5. **`tools_live` does not delete the events it creates on a connected machine.** Sections 3 and 4
   each create a real event, approved by a real click. Those are the employer's. A test that reached
   into somebody's calendar to tidy up after itself would hold a wider licence than the feature it
   tests. The disposable probe event belongs to `google_hands_proof.mjs`, which creates and destroys
   its own.
6. **`deck_proof`'s panel assertion went from six ids to seven** — a sanctioned same-commit selector
   update, with the reading rationale extended to match.
7. **The derived-blank mechanism is keyed on parameter names and never enters the slot**, so the
   rows stay verbatim and `tools_live`'s verbatim assertion stays true while the sentence carries a
   human reading.
8. **`{preview}` was removed rather than the check being weakened.** §22.7. The standing privacy
   law outranks the mandate's phrasing of a card detail, and the body is still shown in full where
   it belongs — on the card, not in the room.
9. **The unreadable-stamp case became an outright refusal** rather than a card with a blank in it.
10. **`calendar.json` was left on disk.** Retired as a backend, named nowhere in the hand's code,
    and the mandate says the boss may delete it — so that is his to do.

### 22.12 · Left open

- **The consent click.** One press of `Connect Google` in the Command Panel, one account chosen, one
  consent screen read. Everything downstream is built and proved as far as it can be without it.
- **The two probe transcripts**, §22.10, which arrive with that click.
- **The one real send.** The reserved Gmail round trip, now against the real API rather than an app
  password, is still the employer's to make by hand.
- **The two by-hand Calm Sky checks**, unchanged.
- **The documented watch-capture gap** in `README.md`, still documented.
- **`routing_proof`'s ear-throttle red** and **`salutation_proof`'s 0.60-threshold red**, both named
  environmental/pre-existing and untouched by instruction.
- **`calendar.json`** sitting inert in the project root, for deletion whenever he likes.
- **The client secret is in this session's transcript on disk.** It was pasted into the conversation,
  and that transcript is a file on this machine. For an installed-app client, Google's own
  documentation and RFC 8252 both decline to treat that secret as confidential — PKCE is what
  protects the exchange — so rotation is optional rather than urgent. It is recorded here because a
  thing like that should be written down by whoever noticed it, not discovered later by somebody
  else. The separate and older matter stands unchanged: **`config.json` is in the Trone git
  history**, untracked now but never purged, and those keys want rotating before that repository is
  ever shared.

---

## 23. The ear that keeps listening, the quiet tongue, and the stack that fits

Four pieces of work, and they are not equal. Two of them cured something. One of them looked for
something and did not find it, and says so. One of them is a hardening that was asked for rather
than diagnosed, and it is labelled as such here rather than dressed up as a repair.

The order below is the order the mandate set, because the mandate had the order right: the dump
comes before the cure, and no line of the cure was written until the dump had been read.

### PART 0 — The state dump: what the ear actually did

**The instrument.** `ear_dump.mjs` drives one Open Ear session on a headed browser with a real
room, one click, no refresh, while `utter.py` speaks six sentences of four to eleven words into
the microphone. It logs, per turn: the recognition lifecycle in wall-clock offsets, the count of
finals and interims, the VAD floor at the arm and at its highest, the acoustic gate's output-RMS
reference at the arm and at its loudest, every gate open and shut edge, and the words spoken
against the words heard. It also keeps one flat timeline of every event the recogniser emitted for
the whole session, in order, which turned out to be the most useful thing in the file.

**The dump.**

```
turn  said  heard     %  arms  fin  int  sentence
 1       4      5  125%     1    1    9  tell me about coffee
 2       7      7  100%     1    1   13  what do you know about the roaster
 3       9      9  100%     1    1   22  and what did i write about the grinder exactly
 4       5      5  100%     1    1    9  and who exactly am i
 5      11     11  100%     1    1   21  tell me everything the notes say about brewing coffee at home
 6       8      8  100%     1    0   14  what else is in there about the beans
```

```
the shape        : opened 1 · turns 6 · arms 6 · rearms 4 · sealed 8 · sealExpired 0
                   hardErrors 0 · bargeIns 1
the floor at end : 0.00882 over 6556 frames        (VAD_OFF 0.018, VAD_ON 0.035)
the gate at end  : open false · opens 0 · ratio 0.56 · input 0.0134 · output 0.0048
the echo law     : dropped 0 · passed 85 · layer1 0 · layer2 0
the browser's own: built 1 · starts 6 · stops 6 · aborts 0 · live 1 · finals 5 · interims 88
                   errors []
```

**THE VERDICT: NOT REPRODUCED.** Six turns for six, in one session, no refresh, every turn at or
above its whole word count. The collapse the mandate sent me to find is not in this dump, and
there is therefore no "before and after" for it — the before is the after. That is the finding,
and it is reported as a finding rather than converted into a repair, because a fix applied to this
table would have been a guess with a table stapled to it as cover.

The mandate named four candidate mechanisms and asked for each to be checked. Each is cleared by a
specific line of the dump, not by the pass count:

**(a) A stale output-RMS reference or a stuck `speakDraining` leaving the Echo gate half-closed —
CLEARED.** `flags@arm` reads `draining=false queued=0 busy=false sealed=false` at all six arms; the
gate's output reference reads `0 at the arm (from none)` at every arm, with `0 frame(s) with the
engine speaking`; `gate edges : 0 open, 0 shut` on all six turns. The gate was neither half-closed
nor closed. There was nothing stale to be stale, because the reference was being zeroed and
re-provenanced at each arm.

**(b) VAD noise-floor drift firing speech-end after the first word — CLEARED, and with room to
spare.** The floor at the arm ran 0, 0.00586, 0.00408, 0.00215, 0.00161, 0.00415, and at its
highest within a turn never exceeded 0.01221. `VAD_OFF` is 0.018 and `VAD_ON` is 0.035, so the
measured floor stayed below the *lower* gate on every frame of every turn — a factor of roughly
1.5 to 11 of headroom. `VAD : 1 speech start(s), 1 end(s)` per turn: one start and one end, not the
several ends that a floor riding up into the gate would produce. The input peak on turn 1 was
0.39338 against that floor, which is the margin the design assumes.

**(c) A recognition stop/start restart race handing the new instance only the tail — CLEARED,
decisively.** `built 1` for the whole session: one `SpeechRecognition` object served all six turns.
`starts 6, stops 6, aborts 0`. The flat timeline shows the full cycle every time, in order and
never overlapping — `.start()` → `start` → `audiostart` → `soundstart` → `speechstart` → interims →
`.stop()` → `speechend` → `soundend` → `audioend` → `FINAL` → `end` → `.start()`. There is no point
in the file where a `.start()` appears before the previous `end`. A race needs two instances or an
overlap, and the dump has neither.

**(d) Interim/final handling stopping at the first final — CLEARED, and the opposite is what
happens.** Turn 3 shows `1 final, 22 interim · 3 late word(s) sealed off`; turn 5 shows an interim
arriving *after* `audioend` and then the final after that, and both were kept. Turn 6 is the sharp
case: `0 final, 14 interim`, `flushed by : the room went quiet carrying 8 word(s)` — eight words
out of eight, with no final ever arriving. Far from stopping at the first final, the ear does not
require a final at all. `sealed 8, sealExpired 0` across the session: eight late words sealed, none
lost to the seal timing out.

**Two corrections the instrument needed before its output could be believed.** Both were defects in
my own measurement, and both are the kind that produce a confident wrong answer rather than an
error:

- *The 16-second patience limit in `mouth.settledArm`.* The first version waited a fixed interval
  for the arm to settle and then reported what it found. On a turn where the answer ran long, that
  interval expired while the page was still legitimately busy, and the dump recorded "did not
  re-arm" for a turn that re-armed a second later. The instrument was measuring its own patience
  and printing the result as a property of the ear.
- *Reading `__galaxy.ear.dump` mid-session rather than after it.* The per-turn block is read after
  the session for a reason: read mid-session, the arm being described is the one currently open, so
  its `end`, its final and its seal have not happened yet, and every turn reports as though it had
  been cut short. The first run produced exactly that shape — a clean session that looked like six
  truncations — and it would have been very easy to name a mechanism from it.

**Two observations left unexplained, and left visible.**

- *Turn 1 heard five words for a four-word sentence — 125%.* The timeline says what happened: the
  recogniser's cold start emitted `interim "Honey"` before the speaker had said anything, and every
  subsequent interim carried it — `"Honey tell me about coffee"`. The **final for that turn was
  clean**: `FINAL "Tell me about coffee"`, four words, exactly right. The page kept the longer
  accumulated interim text, which is correct behaviour for turn 6 (where no final ever came) and
  wrong here. It is not word loss; it is a hallucinated leading word surviving a mechanism built to
  rescue trailing ones. It costs nothing in this dump — the vocative peel would eat a leading
  "Honey" anyway, which is very likely why nobody has noticed — but the asymmetry is real and it is
  written down here rather than smoothed over.
- *`bargeIns: 1` with `gate opens: 0`.* One barge-in was counted in a session where the acoustic
  gate never opened, and where `echo law : dropped 0, layer1 0, layer2 0` says nothing was refused.
  Nothing was lost to it: `hardErrors 0`, every turn at 100%, no audio discarded. But the barge-in
  counter and the gate's own ledger disagree about whether a barge-in occurred, and exactly one of
  them is right. Not chased, because chasing it was not the mandate and it cost the session nothing;
  named, because a counter that can disagree with its own gate is how a future dump gets misread.

### PART 1 — The reset contract

`armReset()` is one function, called at every re-arm path, and a comment above it names its
callers. At each arm it zeroes the acoustic gate's reference **and its provenance**, re-reads the
funnel's draining and queue flags and clears them if they are stale, opens a fresh 300 ms window in
which the VAD floor is re-sampled from silence, makes the recognition lifecycle explicit, and
leaves `arm.state` to exactly one writer, `armSet()`. Preflight check 24 holds all seven of those
clauses, including that `armReset()` writes neither the gate's hold nor the funnel's flags
(`echo.gateAt`, `echo.gateOpens`, `speakDraining`, `speakQueue` are read-only to the contract — the
hold in particular must survive, because `echoGateWatch` deliberately does not clear it when TTS
stops), and that the sampled floor stays a *measurement*: `VAD_OFF` and `VAD_ON` are read as
literals and neither is derived from it.

**This is a prescribed hardening and not a repair, and it should be recorded as one.** The dump
cleared mechanisms (a), (b) and (c) by evidence. Nothing in PART 0 says the ear was failing to
reset. What PART 1 buys is that the six-turn claim in PART 2 is now structural rather than lucky:
before it, "the flags happened to be clean at all six arms" was an observation about one session;
after it, it is a contract with a check behind it. That is worth having. It is not a cure, because
there was no disease in evidence.

**One thing in this part *is* evidence-named, and it was found in PART 2's own output.**
`conversation_proof`'s reset-contract note printed `recogStarts: 12, recogEnds: 15` — ends leading
starts by three. `armRead()` derived its `'stopping'` state from `recogStarts > recogEnds`, and
section 3c of that harness drives three hard network faults; a session that never reaches `onstart`
still fires `onend`, so the two counters drift permanently by one per fault. With ends ahead of
starts the subtraction can never be positive again, `'stopping'` becomes unreachable for the rest
of the tab's life, and `arm.races` is pinned at zero **by arithmetic instead of by conduct**. A
restart race after a fault — precisely when a restart race is most likely — would have been
invisible, and the harness would have printed "0 restart races" as though it had looked.

The fix is a per-instance boolean, `ear.recogLive`, set after `recogniser.start()` returns and
cleared in `onend`. One edge sets it, one edge clears it, neither counts, so it cannot drift.
`recogStarts` and `recogEnds` stay in the probe as what they always were — a record, not a state
machine. It is set *after* `start()` returns rather than before, so that the `InvalidStateError`
throw leaves the flag reading what it already read, which in that case is `true`, because the reason
`start()` threw is that the previous session has not ended yet.

### PART 2 — The longevity proof

`conversation_proof.mjs` section 9: six turns, one session, one click, no refresh.

```
turn  said  heard    %   arm  reset  why the turn ended     the sentence
1     5     5      100%  1    1      the recogniser's own pause   what is the web gate
2     8     8      100%  1    1      the recogniser's own pause   and what does the third door actually do
3     7     7      100%  1    1      the recogniser's own pause   tell me about the antecedent memory again
4     4     4      100%  1    1      the recogniser's own pause   and who am i
5     13    13     100%  1    1      the recogniser's own pause   tell me everything you know about how the web gate scores a source
6     8     8      100%  1    1      the recogniser's own pause   what else is worth knowing about the doors
--------------------------------------------------------------------------
6 turns   45 words in   45 words kept   100%
```

Against a 90% floor per turn, and a three-word floor for any sentence of four or more: the smallest
turn arrived with four words out of four. `ONE RESET PER ARM ACROSS ALL SIX TURNS: 6 arms, 6
resets` — the contract runs once per arm and not once per *request* to arm, which is a different
number and the one that would betray a double-reset. `0 restart races` and `0 arms that found the
funnel still draining after its own cancel` — and those two zeros now mean something, per PART 1.
`armRead()` and the stored `arm.state` agree on the word `"live"`; two answers there would mean a
second writer, which is what preflight 24 forbids.

The end-of-session contract reads
`{resets 7, races 0, staleFlags 0, floor 0, floorSamples 6, floorVoids 0, loudRoom false}`. Seven
resets to six arms because the session's opening arm is one of them. The acoustic half of the
longevity claim is `ear_dump.mjs` and stays there; this section is the word-count half and says so
in its own footer, so that nobody reads a 100% here as a statement about microphones.

### PART 3 — The quiet tongue

One normalization function, `tongueNormalize`, on the audio bus only. Three rules:

1. Markdown `*`, `_`, `#` and single backticks come out; the words behind them are untouched.
2. An unspeakable token — a run of 12 or more letters-and-digits — is replaced in the **spoken**
   line by the plain phrase *"the reference is in the card"*.
3. Two such tokens in one breath collapse to one phrase rather than saying it twice.

The eight strings, straight from the harness:

```
min: 12 · line: "the reference is in the card"
bold  : "Yes sir, that is quite right."
marks : "A heading with code and italics."
id    : "The event is the reference is in the card, sir."
words : "Your understanding of the extraordinary transcription."
many  : "Ids the reference is in the card."
digits: "The number the reference is in the card is in there."
short : "Short ones like abc123 stay."
```

**The before and after, out loud.** The fixture is 257 characters over three sentences, deliberately
long enough that the funnel cuts it in two and the id lands on a chunk the lookahead fetches before
the pump reaches it:

```
queued : Yes sir, that is *quite* right, and I have put the whole of it on the card for you. The
         reading is deliberately plain, because an identifier spelled out loud is nine seconds
         nobody wanted. The event id is 7s0h4k9m2n3p5q6r8t1v, and it is on the card in full.
spoken : Yes sir, that is quite right, and I have put the whole of it on the card for you. The
         reading is deliberately plain, because an identifier spelled out loud is nine seconds
         nobody wanted. The event id is the reference is in the card, and it is on the card in full.
caption: Yes sir, that is *quite* right, ... 7s0h4k9m2n3p5q6r8t1v, and it is on the card in full.
ledger : Yes sir, that is *quite* right, ... 7s0h4k9m2n3p5q6r8t1v, and it is on the card in full.
```

One string in, two different strings out, on purpose — and that is the whole claim, because either
half alone is easy. Zero asterisks reached the engine; not one character of the twenty-character id
is in what was spoken; the caption is the raw line character for character with `up === true`; the
ledger (`__galaxy.speech.said`) records what the page was *asked* to say, so the brain, the scribe
and every harness reading it still see the id.

**Where the function sits, and why it is not a line in the pump.** `speakPiper` prefetches — up to
`SPEAK_AHEAD_CAP = 3` chunks the pump has not reached. Normalizing in the pump would have left
every prefetched chunk raw, which is exactly the chunk an id tends to land on. So it is a memoised
accessor at the engine/fetch boundary: `spoken` is `null` until a chunk is first about to become
audio, and the assertion "every one of the 2 chunk(s) carries a spoken form" is a statement about
that seam and not about the text.

**The discretion decision in this part, and the reason.** The mandate's literal rule is
"alphanumeric tokens of 12+ characters". Taken literally, the butler says *"the reference is in the
card"* in place of *understanding*, *extraordinary* and *transcription*. The implemented rule
therefore requires a digit as well as the length, and that guard carries its **own** assertion in
`voice_proof` rather than riding along inside rule 2 — because it is the case a future edit is most
likely to break by "simplifying" the rule back to the mandate's words. A 12+ character English word
is common; a 12+ character mixed-case-and-digits token is an identifier.

**One reading problem this part does not solve.** The phrase reads well in the middle of a sentence
and less well at a clause boundary — *"The event id is the reference is in the card, and it is on
the card in full"* has two "is"es doing different jobs. It is still enormously better than nine
seconds of spelling, and the card carries the truth, so it ships. Naming it because the next person
to touch this will hear it too.

### PART 4 — The stack that fits

The Layout Governor already owned the well; now it owns vertical space on the same terms. Its
declared numbers:

```
STRIP_H  34    the collapsed minutes strip's floor
GATE_MAX 560   the gate card's ceiling, matching the 560 in --answermax
GATE_MIN 180   a guard against a viewport nobody has measured
```

**Why height was never governed before.** `#brain` is anchored at the **bottom**, so the column
grows upward. Overflow is therefore lost off the **top** of the window, behind the telemetry rail,
where nothing scrolls and no scrollbar ever appears to admit that anything is missing. A question
with Yes and No on it can be entirely off screen while the page looks composed. That is the defect
this part was written for, and at 1280×860 the instrument reproduces it as a number: the column
*wanted* 826px in a 792px budget.

**The precedence order is the design contribution.** With three transient surfaces live, they yield
in this order, and the order is the point:

1. **The caption, first and unconditionally**, because it is the only surface here whose content is
   duplicated somewhere else on screen — the gate's spoken line is already on the card. Saying it
   twice is noise that costs a line the card needs. It goes `display:none` and not `opacity:0`,
   because the whole point is the height.
2. **The minutes, second, down to their head** — a transcript is a record being taken, and a record
   can be read afterwards, whereas a gate expires. The strip *is* the panel with two children
   hidden, so there is no second markup to drift out of step; `display:none` and not
   `visibility:hidden`, because a scroll container that is merely invisible still takes the wheel.
3. **The gate card, last and only then**, and it yields by **scrolling**, never by losing its
   buttons.

Capping the gate first would have been the easy implementation and it is the wrong machine: it makes
a human scroll inside a card to read parameters they are about to approve, while a caption repeating
a sentence they can already see holds the room the card wanted.

**The existing law this was reconciled with rather than overridden.** `viewer/index.html:749-757`
deliberately clamps the prose and *not* the card, on the grounds that "a confirmation gate you have
to scroll down inside a panel to find is a worse defect than a tall panel." Both hold: the **card**
takes the max-height, the **prose and `#ask-rows`** take the internal scroll, and `.pair` is
`flex:0 0 auto` so Yes/No are the last thing in the card that can ever lose room. Every link in the
flex chain carries `min-height:0`, because one missing one silently voids the cap.

The governor measures the column **uncapped first**, so `wanted` is its true demand; reading it with
last frame's cap still on would hand the card back its own clamp and the number would never widen
again. And it caps when the column overflows whether or not a gate is open, because "nothing clipped
above or below" is not a promise that only holds during a proposal.

**The triple-surface plates.** Gate open (a six-parameter calendar proposal with a three-sentence
description), minutes panel live with a rolling transcript, caption active — at three viewports.
Plates: `layout-triple-1280x860.png`, `layout-triple-1600x900.png`, `layout-triple-1920x1080.png`.

```
viewport     budget  wanted  height  gate top  rail  gate h  cap bound  strip   transcript→strip
1280 x  860     792     826     711       123    30     560   yes (=560)   34    146 → 34  (112px)
1600 x  900     832     596     596       279    30     463   no           34    260 → 34  (226px)
1920 x 1080    1012     521     521       533    30     388   no           34    251 → 34  (217px)
```

At every width: the gate's top edge is ≥ 0 and ≥ the telemetry rail's bottom; Yes and No are fully
on screen **and hit-testable** — `elementFromPoint` at each button's own centre returns the button
and not the vignette over it, and neither is disabled (Yes/No at [101,648], [261,706], [421,886]);
none of the ten surfaces in the column has a top < 0 or a bottom > `innerHeight`; and the document
does not scroll vertically — `scrollHeight` equals `clientHeight` and a real `scrollTo(0,400)` left
it at 0. Closing the gate restores all three: strip back to 240 / 260 / 251 px of column, the
caption regains a rectangle, and `vbudget.gateOpen === false && captionOff === false`, so the budget
is a state and not a one-way door.

**The strip is `min-height` and not `height`, and the first measurement earned that choice twice
over.** It came back **49px** at 1280 and 1600 against 34 at 1920. A flat `height: 34px` would have
clipped the word MINUTES. But the assertion behind it read `h > 0` against "a declared floor of 34",
and a floor is satisfied by anything above it — so a strip that was quietly **two lines** at every
width where the note panel narrows the column (which is every width the fixture actually cares
about) was reported green. Nothing was wrapping at the flex level; `nowrap` is already the default.
The *text inside* the two children was wrapping, because a flex item may shrink below its content
width and then break, and at 312px the label and the meta together want about 350.

So in strip mode both children refuse to break, and the one that gives way if something must is the
**label** — the panel it labels is visibly the minutes panel, whereas the timer, the chunk count and
the word count are the three things on it that cannot be got from anywhere else and are the reason
it stays on screen at all. The letter-spacing comes off too: `.2em` over eighteen characters is
about 38px of pure air. The numbers are never the ones that go. The strip now measures **34px at
all three viewports**, still carrying `"0:00 · 0 chunks · 38 words"`, and the assertion reads
`h <= STRIP_H + 1` so that a second row can never again pass as one.

**Three probe seams were added, each with its limit written into its comment**, because the
alternative — driving a real model at three viewports — is a layout proof that fails on a slow
afternoon. `__galaxy.hands.paint` calls the real `showProposal`, so the rows, the label, the amber
card, the vignette and the countdown are production's; but a proposal painted this way carries no
slot the server issued, so Yes on it has nothing to execute. What is exposed is a way to draw the
question. `__galaxy.scribe.up/append` open no stream and leave `scribe.on` false, so the Scribe's
privacy law is untouched because there was never any audio.

### PART 5 — Regression, and the two defects the round found in its own instruments

Every standing harness, against `_runs/after/BASELINE_23.txt`. Sequential, solo, quiet, `port_proof`
last.

```
harness              baseline (round start)        now                          verdict
desk_proof           44 checks, 0 failed           44 checks, 0 failed          at baseline
layout_proof         95/95 PASS                    150/150 PASS                 +55  (PART 4)
followup_proof       47/47 PASS                    47/47 PASS                   at baseline
salutation_proof     26/34 FAIL (named)            26/34 FAIL (same 8)          unchanged, named
capabilities_proof   16/16 PASS                    16/16 PASS                   at baseline
persona_proof        19/19 PASS                    19/19 PASS                   at baseline
nudge_proof          21/21 PASS                    21/21 PASS                   at baseline
deck_proof           224/224 PASS                  224/224 PASS                 at baseline
focus_probe          PROBE 26/26 + 85, 0 failed    PROBE 26/26 + 85, 0 failed   at baseline
voice_proof          133/133 PASS                  145/145 PASS                 +12  (PART 3)
conversation_proof   104/104 PASS                  114/114 PASS                 +10  (PART 2)
routing_proof        64/65 FAIL (throttle, named)  65/65 PASS                   better than baseline
echo_proof           49/49 PASS                    49/49 PASS                   at baseline
console_proof        30/30 PASS                    30/30 PASS                   at baseline
scribe_proof         59 checks, 0 fail             59/59, 0 fail                at baseline
brain_live           33 checks, 0 failed           33 checks, 0 failed          at baseline
eyes_live            56 checks, 0 failed           56 checks, 0 failed          at baseline
tools_live           54/54 PASS                    54/54 PASS                   at baseline
lock_proof           77 checks, 0 failed           77 checks, 0 failed          at baseline (1st try)
google_hands_proof   27/27 PASS, 2 skipped         24/24 PASS, 2 skipped        different branch
preflight            20 pass, 0 fail, 3 warn       21 pass, 0 fail, 3 warn      +1  (check 24)
port_proof           24 checks, 0 failed           24 checks, 0 failed          at baseline, last
```

`echo_proof` at 49/49 is the re-run the mandate asked for specifically: the acoustic gate changed in
PART 1, and self-hearing must not come back with it. It did not.

`routing_proof` came in **better** than baseline — 65/65 against a recorded 64/65. The baseline
failure was the cloud recognition throttle, which is a property of the afternoon and not of the
code. An improvement that nobody engineered is not evidence of anything and is recorded as such.

**`google_hands_proof`'s counts are not comparable, and the reason matters.** The baseline row was
recorded on a machine with no Google grant, so the harness took its refusal branch — "absent", "no
road to the calendar yet", "nothing to disconnect". This machine now has a grant, so sections 6 and
7 take the **real API** branch instead: insert, get and delete a real Calendar event, create, read
and delete a real Gmail draft. Different assertions, hence 24 rather than 27. Both runs skip 2, and
a skip is not a pass.

**Defect 1, found by PART 3 and fixed: a probe getter is an interface.** The first version of
`__galaxy.voice.chunks` returned the six fields the tongue fixture needed. That quietly took
`start`, `end`, `source`, `silent`, `secs` and `bytes` away from every **other** reader, and sixteen
assertions with nothing to do with normalization failed at once — reporting "0 chunks" for a read
that had in fact played 93 seconds of correct audio, with the concatenation matching the input
character for character and 13 `/say` requests for 13 chunks. They were not wrong; they were reading
`undefined` off a row that used to carry the timings. `spoken` is now an **addition** to that row
and never a substitution for it. The failure mode to keep: a probe getter has existing callers, so a
field is added, never swapped in.

**Defect 2, found by this round's regression sweep and fixed: an assertion that was wrong about
Google rather than about the code.** `google_hands_proof` demanded a 404 from `events.get` after
deleting the probe event. It was written beside the Gmail draft check, where a deleted draft really
does 404, and the shape was carried across to Calendar, where it does not hold. Measured directly on
this machine: insert 200, delete 204, and then `events.get` answers **200 with `status: "cancelled"`
and a full body**, because a deleted event stays retrievable as a tombstone so that subscribers can
learn it was cancelled. Demanding a 404 there asserts a promise Calendar never made — and it failed
the first time a machine had a grant to reach the real API with, which is exactly the moment a
harness is being trusted. The assertion now accepts 404, 410, **or** a 200 whose state word is
`cancelled`, and it reads that word rather than inferring it from the code — because the failure
mode the old line caught and must not lose is an event left **live** in the diary, a 200 still
reading `confirmed`. A 200 with no state word at all is refused.

`preflight.py` gained check 24, *a turn resets once, and one hand writes the arm*, with seven
clauses: the four functions are declared; `arm.state` is assigned exactly once in the file and
inside `armSet()`; `armRead()` assigns nothing so it stays safe to call from anywhere; there is one
`recogniser.start()` and one `armReset()`, and the reset runs first inside `startListening()`;
`armReset()` zeroes the gate reference and its provenance, clears the over-window and opens a fresh
floor window; it writes neither the gate's hold nor the funnel's flags; and the floor stays a
measurement, sampled over 300 ms, with `VAD_OFF` and `VAD_ON` read as literals. Mutation-tested in
both directions. `21 pass, 0 fail, 3 warn`, exit 0 — the three warns are the known routine ones.

### The discretion decisions of this round, with reasons

- **PART 0 was reported and not repaired.** The dump cleared all four named mechanisms by evidence.
  The mandate's own instruction — *"if none, report the dump as a finding — no guess-fixes"* —
  covers this exactly, and it is the decision I am most confident of.
- **The two unexplained observations were written down rather than chased or dropped.** The turn-1
  leading "Honey" and the `bargeIns: 1` against `gate opens: 0` each cost this session nothing, and
  neither was the mandate. Both are the kind of thing that causes a future dump to be misread, so
  they are named above with their evidence lines.
- **PART 1 is labelled a hardening, not a cure.** It would have been easy and flattering to present
  the reset contract as the fix for PART 0. It is not, and the record says so.
- **The `recogLive` change was made even though nothing asked for it**, because it came out of PART
  2's own printed output and it meant a zero in my own instrument was arithmetic rather than
  conduct. An instrument that cannot fail is not evidence.
- **The id rule requires a digit as well as a length**, against the mandate's literal wording, so
  the butler does not read "understanding" as an identifier — and that guard carries its own
  assertion so a later simplification cannot quietly undo it.
- **Three paint-only probe seams** rather than driving a real model at three viewports, each with
  its limit in its comment, because a layout proof that depends on a model is a layout proof that
  fails on a slow afternoon.
- **The gate takes the cap and the prose takes the scroll**, honouring both the mandate's
  max-height and the older law at `viewer/index.html:749-757`, rather than overriding one with the
  other.
- **The strip's assertion was tightened after it had already passed.** Reporting 49px beside "a
  declared floor of 34" and calling it green was the round's own near-miss; the fix was to the CSS
  *and* to the assertion, because the first without the second leaves the next regression invisible.
- **One extra Calendar tombstone exists in the diary** from the direct probe that diagnosed Defect
  2 — created and deleted inside that probe, and cancelled like the harness's own. Named because
  anything that touches a real account should be said out loud.

## 24 · The doorman at the door, worlds that travel, and a mouth that only cites what it read

Three pieces of work and one sweep. The doorman is new law: the house learns a voice and then
declines to take orders from any other. The orrery is motion that had to be made *visible without
being busy*, and its story is mostly the story of a number that was wrong in the declaration and
wrong again in the first calibration, in opposite directions. The plain mouth is two queued nits.
The sweep found two reds that were not flakes, and both of them were the new law meeting an old
instrument.

The order below is the mandate's. Research first, because the mandate asked for research first and
because two of the three paragraphs changed what got built.

### The research, before the code

**Speaker verification on this machine.** The question was whether a voiceprint is affordable per
turn without a new dependency, and the answer is yes by a wide margin. `onnxruntime` 1.30.0 was
already installed; the model is an ECAPA-TDNN-class embedder run on CPU, producing a **192-float**
embedding. A downloaded `.onnx` file is an asset, not a pip dependency, which is the only reason
this was reachable under the standing no-new-dependencies rule. Cost, measured over twelve
fixture clips of 4.2–6.6 seconds: **46–162 ms per utterance**, which is 24×–93× realtime — the
first call pays 218 ms of warm-up and every call after it pays about 60. Separation, measured over
all pairs of three voices: same voice **0.8182 min, 0.9382 max, mean 0.8880 (n=18)**; different
voices **0.0244 min, 0.2954 max, mean 0.1659 (n=48)**; five seconds of generated noise against
each voice centre **−0.0216 to 0.0430**. The gap between the worst same-voice pair and the best
different-voice pair is **0.5228**, and its midpoint is 0.557. The threshold shipped at **0.50** —
below the midpoint on purpose, because the two errors are not the same size: a boss refused on a
hoarse morning costs one keystroke, and a stranger admitted costs a sent email. Cosine on
length-normalised embeddings, one embedding per turn, in RAM, discarded.

**Whisper fidelity.** Measured on `faster_whisper` 1.2.1 against 180 words of known script:
**3 errors, WER 1.67%**, and all three were numeral rendering — "four" for "4" and the like — so
the **semantic error rate was 0%**. Throughput **9.9× realtime**. The conclusion that mattered for
this round is negative and worth writing down: Whisper is accurate enough that it is *not* the
weak link in the spoken column. The weak link is the browser's own recogniser, and PART 4 below
had to be built around that rather than around transcription quality.

**Orbital motion that keeps links and hover glued.** Worlds travel on per-world ellipses, each
world given its own period seeded from its id, with the offset written as a *displacement from a
fixed base* rather than integrated into the position. That distinction is the whole of the
correctness argument: an accumulated offset drifts without bound and the still-frame law and the
root pin both die with it, whereas a displacement is bounded by its own amplitude every frame and
the base never moves. Links follow for free because the graph library samples its own endpoints'
live coordinates each frame — measured, twelve sampled link midpoints sit on the segment between
their endpoints' live coordinates to within **0.001 units** on links 112+ units long. Hover
annotations do *not* follow for free; the annotation anchors to a projection, so the projection has
to be recomputed per frame rather than latched at hover time. The collision question is arithmetic:
worst-case closure between two worlds is both at full excursion straight at each other, which for
the shipped per-axis envelope is **1.4456 × (A₁ + A₂)**, and that has to stay under the tightest
base gap minus both radii.

### PART 1 — THE DOORMAN

**Enrolment.** Three spoken sentences through the ear that is already open, from the Command
Panel's *Learn a voice* row, which is the keyboard's row and unreachable from the funnel. It
refuses rather than opening a microphone itself, because a control that starts recording from a
list of orders inverts the transparency law — the seal must be lit *before* anything is heard. The
transcript of a successful enrolment and the four refusals, from `speaker_proof`:

```
ok   a hands-privileged voiceprint enrolled from three recorded sentences: 3 sentences,
     14.93s of speech, 321ms
ok   and the route says it kept none of the 14.93 seconds it was given - the samples arrive
     as an argument, are read once by embed(), and the only thing that leaves is 192 floats
ok   a second voice enrolled WITHOUT the hands, so the seal has a third reading to give:
     a name, for somebody this house knows and takes no orders from
ok   the store went from 1 row(s) to 3 - two enrolments, two rows, and no row invented
ok   the same larynx under a second name is refused AS A DUPLICATE and the refusal names the
     row it already has: "That is already enrolled, as Proof Hands. One voice, one row, sir."
ok   three sentences totalling four and a half seconds are refused with the SECONDS still
     missing named: "That was 4.5 seconds of speech and I need 8.0 - another 3.5 seconds, sir."
ok   and one long clip is refused for the SENTENCES rather than the seconds: "I have 1 usable
     sentence and I need 3 - say another 2, each a full breath long."
ok   an enrolment that admits it came in through the ear is refused by name: "Enrolling a
     voice is done from the Command Panel, not by asking out loud."
ok   and a re-learning that succeeds comes back WITH the hands it had, though the body never
     asked for them - a boss re-enrolling after a cold must not return as a hands-less row
```

The first enrolment on this machine is the boss, with `hands: true`, taken from three sentences —
the transcript above is the fixture pair, which is why the names in it are `Proof Hands` and
`Proof Plain` rather than anybody's. `speaker-store/` is gitignored and Read-denied
like `secrets/`, holds JSON rows only, and the leak-scan battery and the preflight store-hygiene
check both name it.

**The match table**, one embedding per turn, discarded after:

```
utterance                  | cosine | seal            | hands | ms
---------------------------+--------+-----------------+-------+-----
the hands voice (joe-3)    | 0.9069 | BOSS            | yes   | 92
the plain voice (ryan-3)   | 0.8989 | Proof Plain     | no    | 87
a third voice (alan-3)     | 0.1961 | GUEST           | no    | 122
the noise floor            | 0.0390 | GUEST           | no    | 100
the threshold is 0.50; measured same-voice floor 0.8182 (n=18),
different-voice ceiling 0.2954 (n=48)
```

The seal has **three** readings, not two, and the middle one is the one worth defending: an
enrolled person without the hands reads as *their own name*, because a house that knows who you are
and will not take your orders owes you the first fact even while it declines the second. Through
the page's own microphone graph — echo cancellation, noise suppression and automatic gain all on —
the same recordings read **BOSS at 0.7617** and **GUEST at 0.1686**, and the glass says so: the
seal cell reads `speaker: BOSS` while the ear is open, live only, never written to ledger, lookbook
or log beyond counts. The server's own tally: **133.96 seconds of audio through RAM cumulatively,
none of it kept**, and 33 audio files under the project root before the run and the same 33 after.

**The guest's refusal, spoken, and the law's shape.** One function at three doors — `/chat`,
`/execute`, and `/tools cmd=cancel` — because a law written at one of them is a law with two ways
round it.

```
ok   a spoken yes carrying a hands-privileged turn EXECUTES: "Self test passed, token SPEAKER"
ok   the same turn, used once, executed once
ok   and the SAME turn number a second time is refused: an honoured word spends its slot, so
     one measured utterance cannot consent twice
ok   a spoken yes from an ENROLLED voice without the hands is refused with the mandate's line,
     verbatim: "I take orders from one voice in this house, and it is not speaking just now."
ok   and the refusal names NO NAME - neither the privileged row nor the refused one
ok   a yes carrying a GUEST turn is refused the same way, and the seal reads "GUEST"
ok   turn 0 - a number this process never issued - is refused exactly as a guest is
ok   turn 99999 - likewise, so a spoken yes whose speaker could not be established fails CLOSED
ok   a spoken NO from a voice without the hands is refused at /tools cmd=cancel as well
ok   and the keyboard executes THAT SAME proposal with no speaker block at all
```

Four properties of that block are worth naming because each closes a specific hole. The page
carries **a number and nothing else** — no name, no privilege, no score — so the worst a stale or
hostile tab can do is quote a verdict this process already reached from real audio. A turn is
**spent** when honoured, which closes the barked interrupt that reaches the page before the
detector has ended the utterance and therefore travels with the *previous* turn's number. It
**fails closed**, and the page sends `turn 0` rather than omitting the block, because an omitted
block reads as a keystroke and a hung identification would otherwise be a promotion. And the **no**
is guarded as well as the yes: a stranger who can say no can cancel the email the boss asked for
three seconds before it goes, which is the same hole pointed the other way.

With zero enrolments the law stands down silently — no sentence, no seal, no mention — and the ring
is never even built, because there is nobody to recognise and taking a recording to discover that
would be a cost with no answer at the end of it.

### PART 2 — THE ORRERY

**The declared numbers, old and new**, in the form §12 used:

```
amplitude multiplier   0      ->  1.25 x the world's own radius, with a floor of 8.80
                                  world units   (drafted at 0.55, then 1.00)
period, per world      none   ->  60 s .. 100 s, one period each, seeded by id
                                  (drafted at 70 .. 190, then 60 .. 120)
screen-space speed     0      ->  6 .. 30 px/minute at the default camera
                                  (declared 9.99 .. 41.03 in the draft; see below)
```

**And the number in that draft was wrong twice, in opposite directions.** The declaration said
"1.064 px per world unit". It was read off a projection of the *layout span*, which is not the
scale. The true figure, taken by projecting `(0,0,0)` and `(100,0,0)` and dividing, is **0.3919 px
per world unit** at the camera that settles at z ≈ 2304 with a 50° vertical field. Then the first
calibration made the matching mistake in the other direction and reported "9.99 .. 41.03
px/minute", which is 11.27 .. 41.08 **world units** per minute — the same measurement with the
wrong unit on it. Two reproducible reds in `deck_proof` are what forced the arithmetic to be done
properly, and the argument that had licensed AMP 1.00 turned out to be the argument that rejected
it.

The fix was not the one I had planned. I had intended a per-world minimum amplitude as *the* cure;
measurement showed the px/min spread is driven mostly by period and projection phase rather than by
radius spread — the amplitude range across 31 worlds is only 2× — so a floor alone could not have
worked. It was still needed, but for exactly **one** world. `AMP_MIN` is **8.80** rather than a
rounder number because one relation buys r 7.15 → amp 8.94, making 8.80 the highest floor that
binds only on degree-0 worlds; 8.00 was discarded because the single unlinked world travels 36
world units a minute at that amplitude and projects only 7.9 pixels of them, its ellipse happening
to lie along the view axis. This deck's slowest world on the glass is not its slowest world in
space.

**The collision bound was re-derived and the page's own comment was stale.** It named worlds 4/15
at 49.1 units as the closest pair; recomputing over all 465 pairs from live bases gives **16/29 at
47.2 units** surface-to-surface. The pair the comment named stopped being the closest pair when the
layout last moved and nothing said so — which is why `deck_proof` now recomputes the guarantee
every run instead of carrying a hard-coded bar that would have been wrong in the safe direction
today and wrong in the unsafe direction eventually.

**Measured, at 1400×940 (1378×842 css):**

```
orrery: travelling · 31 worlds · 3152 frames · amp 1.25 x radius, floor 8.8u
        periods 60-100s · declared 6-30 px/minute
slowest world "0" (period 85s)  7.9 px/minute
fastest world "1" (period 73s) 19.6 px/minute   = 0.33 px in a second
the amplitude floor lifted 1 of 31 worlds, and it is of the smallest radius on the deck (4.54u)
mesh against coordinate, 21 samples x 31 worlds: worst gap 0.00000 units
offsets never left the per-axis envelope A x [1, 0.62, 0.84]: worst 1.0000 of the allowance
tightest clearance guarantee over all pairs: 18.7 world units (16/29)
twelve link midpoints against live endpoints: worst perpendicular offset 0.001 units
hover glue over 30s: world ran 7.8px, annotation ran 8.1px, worst slip 1.14px/s,
        against a 2.0px bar DERIVED from the declared 6 px/minute
```

The hover-glue bar deserves its own line because it was the round's second near-miss. It used to
be `annRan > 2 && worldRan > 2` over twelve seconds — and the declared 6 px/minute only guarantees
1.2 px in twelve seconds, so a bar of 2 px was quietly asserting 10 px/minute, a number nothing
declared. It duly failed the run the real pixel scale came to light in. It is now 30 seconds, which
costs nothing because that sleep was already owed before the second plate, and the bar is computed
from `ORRERY.PX_MIN`.

**The plates.** `orrery-wide-A.png` and `orrery-wide-B.png`, **60.3 s apart**, and they were
checked numerically rather than merely asserted. With no PIL on this machine the diff was done with
a hand-rolled stdlib decoder over `zlib` and `struct` handling all five PNG filter types:
**8584 pixels changed by more than 12/255** (0.79% of the frame), **3688 by more than 48/255**, and
**27.2% of every lit pixel changed**. The worlds are elsewhere and nothing else is.

The root stays pinned at dPos 0 · dQuat 0, there is no global spin, parallax and the still-frame
law are untouched, and a reader who asks for less motion gets today's amplitudes exactly as before.

### PART 3 — THE PLAIN MOUTH

Connection-state questions joined the identity/capabilities class, answered from live `/google`
state with zero lookups, naming the Command Panel row and its current reading. From the fixture
table, typed and spoken:

```
how do i connect google              | 200 chat/identity/0
is my calendar connected             | 200 chat/identity/0  · spoken, same
why is it not connected (noun pos.)  | 200 chat/identity/0
why is it not connected (with offer) | 200 chat/proposal/0
```

The last row is the one that makes the class honest: the same sentence with a proposal standing is
a *question about the proposal*, not about Google, and it routes differently.

**Citation honesty.** `DRAWN FROM` / `CITED` chips render only where the answer text actually
consumed those sources, and the gate is one function called after the answer exists, with the chips
coming off in three places all of which are `strip_citations()`:

```
sentence                                   | chips | row      | label
-------------------------------------------+-------+----------+-----------
who are you                                | 0     | hidden   | Drawn from
galaxy what can you do                     | 0     | hidden   | Drawn from
is my calendar connected                   | 0     | hidden   | Drawn from
ok got it                                  | 0     | hidden   | Drawn from
good morning galaxy                        | 0     | hidden   | Drawn from
what do my notes say about coffee churn    | 2     | shown    | Drawn from   <- THE CONTROL
```

The control is the only thing that makes the five zeros mean anything. A blanket that hid every
chip would score five out of five above and be a regression, not a fix.

### PART 4 — THE SWEEP, AND THE TWO REDS THAT WERE NOT FLAKES

**The spoken column learned a third outcome.** Four runs of `routing_proof`'s thirteen-sentence
spoken column failed once each, on a *different* sentence every run: `switch your voice to joe`,
then `no no cancel that`, then `what is the web gate`, with mishearings including "Is my phone",
"My calendar connected", "Sorry pap", "Hey can you take a video for me", and three empty
transcripts in a row. The per-attempt hit rate of the on-device recogniser is about 0.6, so three
attempts leave a thirteen-sentence column red better than half the time and five attempts put it
near 1% per sentence. The retry budget went to five and the file gained **UNPROVEN** beside pass
and fail: a sentence the room never delivered produced no routing decision to judge, so blaming the
funnel for it would be a lie in the other direction. Unproven is not a pass — it is counted,
printed on its own line, named in the verdict, and **budgeted at two of thirteen**, with a
`heardRows` floor besides, so a muted microphone or a dead recogniser still fails, once, with a
count instead of thirteen times. The closing run delivered **14 of 14 with 0 unproven**.

**A red the old test had been hiding.** Confirmation fixtures compared the heard sentence to the
spoken one by *containment*, and containment has a hole the comment above it did not cover: a
recogniser that adds a word has all the same letters and some more. Measured — `no no cancel that`
came back as **"No no cancel that Why"**, which routed `kind=web lookups=2`. The room stapled a
word on the end, containment waved it through as the boss's sentence, and the fixture was passing a
confirmation class for answering a question he never asked. It is now compared by **equality**,
which keeps every accident the paragraph was written for — a swallowed space, "okay" for "ok" — and
refuses the one it was not.

**RED 1: `tools_live`, 54/54 → 46/54.** Not a flake and not a regression in the code: the doorman
correctly refusing an instrument that has no larynx. `tools_live`'s `say()` is `__galaxy.ask()`,
which is marked `via: voice` exactly as a dictated sentence is, but no audio was ever measured, so
the turn number is 0 and the gate fails closed on it. That is the law working. The harness now
**forks on the one switch the law itself uses**: with an empty store the spoken yes runs the hand
and every assertion is the one it made before the doorman existed; with a guarded store the spoken
yes is refused in the mandate's words, the ledger is asserted to have stood still, the card is
asserted to have **survived** — the refusal carries the pending proposal back, so a guest saying
yes cannot take the employer's question off his screen, which is the quiet denial of service a
refusal that merely hid the card would be — and the same proposal is then confirmed at the
keyboard, where the hand runs. Both branches require the hand to have run exactly once by the end
of the round. `tools_live` is now **62/62**, eight assertions above its baseline, and it proves the
tool door in both worlds instead of one.

**RED 2: `lock_proof`, 77/0 → 33 checks with 2 failed, four times identically.** Four identical
failures is not a flake, and the file's own comment named a failure mode that turned out not to be
the one. Section 3's chain is: a portless Chrome on the launcher's profile, a hand that closes it
politely and relaunches it with the port, and `--restore-last-session` handing the work tab back.
It came back with nothing. Running the launcher by hand without `-Quiet` showed the close was
genuinely polite — *"the profile is free and its session was written"*, no WM_CLOSE warning, no
force kill — and yet **no `Session_<ts>` file appeared in either `Sessions/` or
`Sessions_Encrypted/`**; the newest was hours old, from the morning this harness was last green.

The mechanism: Chrome writes `profile.exit_type = "Crashed"` when it opens a profile and flips it to
`"Normal"` on a clean shutdown. Read `"Crashed"` at startup and it offers the **restore bubble**
instead of restoring, and while it is in that state it commits no session file at all — so the next
clean close has nothing to write and **the mark never clears itself**. A wedge that holds. And the
thing that put this profile in it is `lock_proof`'s own teardown, which force-kills whatever is left
so the next run starts from nothing. A force kill is the right teardown — a run that leaves a
browser behind poisons the next harness, not just the next lock run — but it is also, precisely, a
crash. Every red run of section 3 was caused by the previous run of the same file, which is exactly
why re-running it four times produced four identical failures rather than one eventual pass.

Proved by the one field and nothing else: `exit_type: "Crashed"` → clean close, **no** session
file, relaunch returns only the launcher's own `--new-window` tab. The same cycle with the field set
to `"Normal"` first → `Session_13434987390668745` written within the cycle, and the relaunch hands
back **both** tabs, the viewer and `https://example.com/`. Section 1a — which already borrows the
profile's session files and puts them back — now clears the crash mark before the chain begins and
prints what it found. Two consecutive runs afterwards: **78/0 and 78/0, first attempt each**, where
this file previously wanted up to four. The extra check is a new assertion that asks for the session
file **by name**, because "no tabs came back" has two causes wanting different repairs, and a bar on
the tab count alone reports the symptom both times.

What was deliberately *not* done: teaching `launch-chrome.ps1` to clear the mark. For a browser that
really did crash the mark is true and the bubble is Chrome's own answer, and a launcher that quietly
rewrote it would hide a real crash from the person it happened to. So the gap stays open and stays
named — ask for the port after a genuine Chrome crash and the relaunch restores nothing, because
there is nothing committed to restore. That is Chrome's behaviour for everybody and it is not this
hand's to fake.

**Baseline and after.** Solo, sequential, quiet, `port_proof` last, both times.

```
harness              | baseline (round start)       | after
---------------------+------------------------------+------------------------------
desk_proof           | 44 checks, 0 failed          | 44 checks, 0 failed
layout_proof         | 150/150 PASS                 | 150/150 PASS
followup_proof       | 47/47 PASS                   | 47/47 PASS
salutation_proof     | 26/34 FAIL (pre-existing)    | 26/34 FAIL (identical)
capabilities_proof   | 16/16 PASS                   | 16/16 PASS
persona_proof        | 19/19 PASS                   | 19/19 PASS
nudge_proof          | 21/21 PASS                   | 21/21 PASS
deck_proof           | 224/224 PASS                 | 238/238 PASS      (+14)
focus_probe          | PROBE 26/26 + 85 checks 0 f  | PROBE 26/26 + 85 checks 0 f
voice_proof          | 145/145 PASS                 | 145/145 PASS
conversation_proof   | 114/114 PASS                 | 114/114 PASS
routing_proof        | 65/65 PASS                   | 91/91 PASS        (+26)
echo_proof           | 49/49 PASS                   | 49/49 PASS        (re-run)
console_proof        | 30/30 PASS                   | 30/30 PASS
scribe_proof         | 59 checks, 0 fail            | 59 checks, 0 fail
brain_live           | 33 checks, 0 failed          | 33 checks, 0 failed
eyes_live            | 56 checks, 0 failed          | 56 checks, 0 failed
tools_live           | 54/54 PASS                   | 62/62 PASS        (+8, RED 1)
lock_proof           | 77 checks, 0 failed          | 78 checks, 0 failed (+1, RED 2)
google_hands_proof   | 24/24 PASS, 2 skipped        | 24/24 PASS, 2 skipped
speaker_proof        | did not exist                | 61/61 PASS        (new)
preflight            | 21 pass, 0 fail, 3 warn (24) | 23 pass, 0 fail, 3 warn (26)
port_proof           | 24 checks, 0 failed (last)   | 24 checks, 0 failed (last)
```

`salutation_proof` is the named pre-existing FAIL, byte-identical to baseline. The three preflight
warns are checks 10, 11 and 12, the routine ones with known causes. Preflight's two new integers —
**25, speaker-store hygiene** (gitignored, denied, embeddings-only, no wav/mp3/ogg inside) and
**26, citation honesty** (five conversational, identity, capability and connection-state sentences
answer with nought nodes and nought citations; a real notes question still lights its chips) —
are both green, read from HEAD. Zero unexplained reds.

### What is left open

- **A guest asking "who am I" is still told the boss's name.** The identity class answers from the
  persona block, which is DO-NOT-ALTER, and the vocative peel takes addresses *off* rather than
  changing what a sentence knows.
- **`deaddress()` cannot peel an uncommaed terminal call-name.** Asserted in both directions; the
  limit is named where it lives.
- **The *Learn a voice* row enrols the boss only**, and refuses rather than opening a microphone,
  for the transparency reason above.
- **A bark sliced across two voices scores as neither** and fails closed, which is the right
  direction and still a gap.
- **`speaker_proof`'s third-larynx assertion is adaptive**, because the harness will not empty the
  boss's store to arrange a cleaner fixture.
- **A ~5% model flake at the tool/compose boundary on `switch your voice to joe`.** Isolated rather
  than assumed: 8/8 typed with no speaker block gave `tool`; 3/3 each with a bogus voice turn and
  with a keyboard speaker gave `tool`; 5/5 with the column's own session history gave `tool`. So
  19/20. Left alone because the fixture's own note says that registry-hand layer is out of scope.
- **`"no no cancel that Why"` routes to web** — a confirmation does not survive a stapled-on word.
  Left alone because the funnel's protected classes are DO-NOT-ALTER.
- **The spoken column's irreducible ~1-sentence-per-run recognition loss**, now reported as
  UNPROVEN under a budget of two rather than as a failure of the funnel.
- **`routing_proof`'s spoken confirmations are now 403'd by the doorman**, because the harness
  speaks through speakers as an unenrolled voice. They pass because they assert the door and the
  price — `kind`, `route`, `lookups` — rather than the outcome. The same fact broke `tools_live`,
  which *did* assert the outcome; see RED 1.
- **A genuine Chrome crash leaves the relaunch with nothing to restore**, deliberately. See RED 2.
- **Reserved for the employer:** the Gmail real-API send, the single OAuth consent click, the two
  by-hand Calm Sky checks, and the documented watch-capture gap in `README.md`.

### The discretion decisions of this round, with reasons

- **The threshold is 0.50 and not the 0.557 midpoint**, because the two errors are not the same
  size and the cheap one should be the one that happens.
- **The seal has three readings rather than two.** An enrolled person without the hands is owed
  their name even while they are refused the gate; only a stranger gets no name at all.
- **The refusal names no name — not the boss's, not the guest's.** A refusal is not the place to
  tell a stranger who is allowed to give this house orders.
- **The `no` is guarded as well as the `yes`**, which looks like caution and is not: a stranger who
  can veto is the same hole as one who can consent, pointed the other way.
- **A turn is spent when honoured.** A verdict is worth 45 seconds to `/chat`, which only uses it to
  decide what to call somebody; at the gate it authorises an action, and a number that authorises
  twice is a number worth stealing.
- **`T_MAX` came down to 100 rather than `PX_MIN` coming down to 5.** Both would have bought the
  same green; lowering the declared floor would have bought it by moving the declaration to
  wherever the code happened to land, which is how a declared number becomes decoration.
- **The old px ceiling of 70 was decoration** and is now 30. Nothing on the deck came within a
  factor of three of 70, so it could not have failed and therefore was not an assertion.
- **`deck_proof` recomputes the collision guarantee from live bases every run** rather than reading
  it out of the page's comment — which is the whole point, because the pair that comment named
  stopped being the closest pair and nothing would have said so.
- **The hover-glue bar is derived from the declared floor, with one judgement named**: two-thirds,
  because net displacement over 30 s is not path length averaged over 20 s, and the factor is
  written down as a judgement rather than dressed up as a derivation.
- **The spoken column got a third outcome instead of a wider assertion.** The budget buys more
  chances at the microphone and no latitude at all in what counts as heard.
- **Equality replaced containment**, which is a correction of that paragraph rather than an addition
  to it.
- **`tools_live` forks rather than skipping.** The lazy version — skip the spoken round when the
  store is guarded — would have gone green by asserting less, and a machine with an enrolled boss
  would have quietly stopped proving that consent ever runs a hand at all.
- **The crash mark is cleared in the harness and not in the launcher**, because the harness is
  clearing its own litter and the launcher would be hiding somebody's real crash.
- **`lock_proof` now names its own abort.** Without it the chain died on `Cannot read properties of
  undefined (reading 'id')` and stopped at 33 checks of 78 — two reds and forty-five assertions that
  were never asked, which reads like a far smaller failure than it is.

## 25 · Two things asked for, one word given, and where it stops

One piece of work in four parts, and the parts are not independent: the planner is worthless
without the card, the card is a lie without the halt, and the halt is unprovable without a hand
that can be made to fail on purpose. The shape that fell out of the research is the one sentence
worth remembering from this round — **a chain is not a second gate, it is a second thing behind the
same gate.** Every law already written at that gate covers it because nothing about the gate
changed: one `_pending` slot under one lock, one TTL, one voiceprint check, one pair of buttons.

The round found two real defects and both were in this machine's own voice rather than in the new
code. It also found one red in the sweep that was a fixture failing to keep up with a contract that
had grown, which is the honest kind of red.

The order below is the mandate's.

### PART 0 — The research, before the code

**Structured brain output, and the terminator that never arrives.** The mandate asks for a JSON
array of `{hand, params}` steps, and the obvious way to read one out of a model's answer is the way
the single tool tag is read: a regex. That is the one thing `chain_tag()` is not, and it is a
measurement rather than a taste. The tag opens `[[chain:` and closes `]]`; a JSON array closes `]`.
A model asked for `[[chain: [ {...}, {...} ]]]` writes **`}}]]`** — its own array bracket doing
double duty as the first of the tag's pair — and a pattern demanding three closing brackets reads
nothing at all. The first probe scored **0 chains out of 5** for exactly that reason. Replacing the
pattern with `json.JSONDecoder().raw_decode`, which is the authority on where an array ends, and
then asking only that the leftover *begin* with a `]`, scored **6 out of 6** on the same five
prompts plus one, and **every one of the six had written a single `]`**. The leniency costs nothing
because nothing in the parsed array is trusted: every step is looked up with `find()` exactly and
validated against that tool's own schema in `propose_chain()`. The safety is in the lookup and the
schema, never in the bracket count. The second finding was negative and shaped the prompt: without
an explicit *ONE INTENT IS NOT A CHAIN* sentence a model that has just been handed a new toy
reaches for it, so the sentence is in the protocol, and with it **6 single-intent directives out of
6 still came back as ordinary `[[tool: ]]` tags and none as a chain of one**.

**UI composition for stacked proposals.** The question was whether a plan of four needs its own
card, and the answer is no — it needs one more *surface* inside the card there already is. The
existing gate card is a label, a rows grid, two buttons, a countdown and a vignette; the chain card
is the same card with `<ol class="steps">` filled and the rows grid emptied, and `showProposal()`
fills exactly one of the two and empties the other. Two measurements decided the details. First,
**an empty `display:grid` still generates a box**: the unused rows grid contributed a 0-pixel-high
rectangle *and* its 13px margin between the label and step one, so both surfaces got a
`:empty{display:none;margin:0}` rule and an unused list now costs nothing. Second, **the height cap
is a chain of flex parents and one missing link anywhere silently does nothing** — the
`#answer.capped` rule had to name `#ask-steps` beside `#ask-rows` and pin `.pair` at
`flex:0 0 auto`, or a four-step plan pushed the Yes button off the bottom of a short window with no
scrollbar to say so. The numbering is `counter-reset`/`counter-increment` on the list itself rather
than digits written into the markup, which is what makes the rendered order the document's own
order; the cost of that choice is recorded under *What is left open*.

**State passing between registry hands.** This is the single deliberate exception to the oldest rule
in `hands.py` — *the parameters come from the slot, never from the request that confirms it; no door
may substitute a recipient between the asking and the doing* — because a `{{step1}}` is precisely a
substitution between the asking and the doing. So it is bounded four ways, and the first bound is
the one that makes the rest cheap. **A placeholder may land only in a `text` field.** Across the
whole registry the `text` fields are exactly `body`, `description` and `minutes`; every address,
subject, title, time, token and voice name is a `string`. So *"a placeholder may only land in a
text field"* and *"a recipient can never be substituted"* are the same sentence, and the second one
is checkable by reading the schema rather than by trusting a function. **Backwards only:** step 2
may quote step 1, and a step quoting itself or a later step is refused while a human is still
reading the card rather than halfway through with one hand already run. **Visible before the yes:**
the placeholder is *not* expanded at proposal time, so the card shows `{{step1}}` in the field it
will land in and the employer can see that a value they have not read yet will be pasted there — a
silent expansion at run time would be this machine editing a letter after it was approved. And
**capped at `CHAIN_PASTE_MAX = 200` characters**, because a letter that is mostly another program's
stdout is not a letter the employer wrote. The `text`-only rule is checked twice, at proposal time
and again in `_paste()`; the cheap check is what tells the employer early, the second is what makes
it true.

### PART 1 — THE PLANNER

`chain_protocol()` is appended by `prompt_block()`, never typed into the persona constants, and it
is generated from the same registry the executor reads so a capability sentence cannot drift out of
date. This is the whole of what the brain is told about plans, rendered live:

```
  AND A DIRECTIVE MAY CONTAIN MORE THAN ONE. "add a meeting and email the team", "put it in the
  calendar then write to Tom" name TWO of the things above in one breath. When, and only when,
  the one message genuinely asks for more than one of them, reply with nothing but a chain tag:
  a JSON array of steps, in the order they must happen, using "hand" for the id and "params"
  for the details.
  [[chain: [{"hand": "add_calendar_event", "params": {"title": "Vendor call", "start":
  "2026-09-27T16:00"}}, {"hand": "send_email", "params": {"to": "team@example.com", "subject":
  "Vendor call", "body": "I have put the vendor call in the diary. {{step1}}"}}]]
  Every id must be one of the ids above, at most 4 steps, and the same rules apply to each step
  as to a single one: fill in only what they told you, and if a required detail for ANY step is
  genuinely missing, ask for that one thing in prose instead of guessing it.
  ONE INTENT IS NOT A CHAIN. A message that asks for a single thing gets the ordinary
  [[tool: ...]] tag, never this one.
  STEP N MAY USE STEP N-1. Write {{stepN}} where an earlier step's result belongs - only ever
  inside a long text field such as a body or a description, and never in an address, a subject,
  a title or a time. The server fills it in after that step has actually succeeded, and shows
  them the placeholder before they say yes.
  NOTHING HAPPENS WHEN YOU DO THIS EITHER. They are shown the numbered plan and asked once for
  the whole of it.
```

Four things about that block are deliberate. The clock in the example is real, for the same reason
the single tag's example carries one: a calendar hand that takes ISO stamps cannot be filled in by
a model that does not know what day it is. The step cap is interpolated from `CHAIN_MAX_STEPS`
rather than typed, so the number asked for and the number enforced cannot differ — preflight 27
asserts that sentence against the constant. The placeholder restriction is *taught* rather than
left to be discovered, because `propose_chain()` refuses a placeholder in an address by name and a
refusal the model could have avoided is a turn wasted on both sides. And the block says nothing
about the Chain Card, the halt law or the ledger: the model is being asked for a plan, not for a
user interface, and every sentence about what the server will do with a plan is a sentence it can
get wrong out loud.

**The funnel did not change.** `hands_wanted()` is still a door and not a decision, the routing is
untouched, and the chain path opens only when the brain's answer carries a chain tag. A plan of one
falls through to `propose()` — the mandate's own rule, and also the only way the ordinary card,
receipt and ledger row stay the normal case rather than a special case of a bigger thing.

Measured live, through the real box and the real brain, with two instructions in one breath:

```
plan: ["1 Write 'Vendor call' into your Google calendar, Monday 28 September at 4:00 pm,
        30 minutes (the default, since no end was given).",
       "2 Send an email to team@acme.com under the subject 'Vendor call tomorrow at 16:00'."]
```

Two steps, in the order they must happen — the calendar before the email that refers to it.

### PART 2 — THE CHAIN CARD

The card is a **fork of one card, not a second card**, and that is the safety argument rather than
a tidiness one. Same slot id, same label position, same two buttons, same countdown, same vignette;
`params` and `fields` travel **empty** on a chain so that any surface still rendering the
single-proposal rows shows nothing at all rather than step one's parameters passed off as the whole
plan. `tool` on the slot stays the first step's real registry id rather than the word "chain",
which is load-bearing in three places that know nothing about chains: `_record()` drops an outcome
for an id the registry does not have, the page's status strip reads it, and `about_the_proposal()`
logs it.

Each step shows the **server's** sentence for that action, filled from that tool's `step` template
in the registry, never the model's prose about it — a model that paraphrases one action can
understate it, and a model paraphrasing two has twice the room. The step lines carry no `body`, no
`minutes` and no `description`, enforced in `_clean_tool()`, because the plan is read out loud and
a step line that interpolated the employer's correspondence would read it to whoever is in the
room. The exact values sit under each sentence in mono, because those are read with the eyes by the
one person entitled to read them.

**Measured, three-step plan, 1280×860 window:**

| surface | rectangle |
|---|---|
| the card (`#a-ask`) | **722 × 311** |
| the steps list (`#ask-steps`) | **722 × 221** |
| the single-proposal rows (`#ask-rows`) | **no rectangle at all** |
| Yes button, bottom edge | **635** |
| the organ rail, top edge | **684** |

The Yes button clears the rail by 49px with three steps up, the list sits above the buttons in
reading order, and the empty rows grid takes no room — which it did before the `:empty` rule, both
the zero-height box and its 13px margin.

**The spoken proposal is one sentence for the whole plan**, ordered aloud because a listener has no
numbers to look at:

> "I have a two-step plan, sir. First, write 'Vendor call' into your Google calendar, Monday 28
> September at 4:00 pm, 30 minutes (the default, since no end was given). Second, send an email to
> team@acme.com under the subject 'Vendor call tomorrow at 16:00'. Shall I execute the chain?"

**THE FIRST REAL DEFECT OF THIS ROUND WAS IN THAT SENTENCE, and it was this machine's own voice.**
Round 1 of `chain_proof` failed twice on "the plan was never heard". The first hypothesis was audio
autoplay, and it was half right: a throwaway probe established that only a **trusted** mouse event
unlocks speech — `page.evaluate('el.click()')` does not, `Input.dispatchMouseEvent` does — before
the gesture `speak()` returns false, `unlocked:false`, the line is recorded `aloud:false` and no
`speakLine` event fires; after it the held line is released. So the harness now clicks for real.
That alone did not fix it. The true cause was `spokenForm()`'s `SPOKEN_MAX_CHARS = 260`: it packs
whole sentences up to the cap and drops the rest, **and a two-step plan whose first step is a
calendar entry runs to about 270 characters.** The twelve characters over the cap were *"Shall I
execute the chain?"*. The butler read out a plan and never asked for the word, while the card sat
there waiting for one. `spokenForm()` now rescues a trailing question: if the last sentence ends in
a question mark and the packed form does not already contain it, the question is appended. The
harness assertion was rewritten to the truth rather than to the symptom — the spoken line must
**end** with "Shall I execute the chain?", must open "I have a two-step plan", must carry First and
Second, and the card must carry the server's sentence in full, cap or no cap, so that reading it
and hearing it agree.

**THE DOORMAN'S CHAIN.** Nothing was written for this. Because the chain reuses the one `_pending`
slot and `/chain/execute` is a *name* for `/execute`'s path, the voiceprint law, the TTL, the
withdrawal rule and the supersede rule all apply unchanged. Proved on a genuinely guarded store: a
guest's spoken yes at a two-step gate was refused in the same words as at a single one —

> "I take orders from one voice in this house, and it is not speaking just now."

— **zero hands executed**, which is the half a per-step gate would have got wrong; the card
survived the stranger, because a guest's word must not be able to take the employer's own question
off his screen; and the keyboard Yes then ran the plan the room's voice could not.

### PART 3 — SEQUENTIAL EXECUTION AND THE HALT LAW

`/chain/execute` runs the approved steps in order through the same registry hands, pasting each
step's evidence forward. **If step N fails, step N+1 is never attempted.** Measured, with a
three-step plan whose middle step is a self test carrying a token that makes it exit 1 on purpose:

> "Self test passed, token HALT-ONE. Step 2 of 3 — test the hands themselves — failed: The tool
> failed, sir: Self test failed on purpose, token FAIL-TWO. I have stopped the chain, so step 3 was
> not attempted."

Four things in one receipt, in this order: what **did** happen, with step one's own evidence; where
it stopped, **by number**; why, in the script's own words; and what was abandoned, so nobody is
left assuming the rest went through.

**The proof of the halt is a number that does not move.** Saying "step 3 was skipped" is a claim
about an absence, so it is asserted three ways: `save_minutes`' ledger row is **unchanged**, the
file step 3 would have written **does not exist**, and the ledger's chain row names the index. Step
one *and* step two both really started — two runs counted against the hand that touches nothing —
and step two is recorded as **failed** rather than **refused**, because the subprocess did start.
That distinction is the one a single failure taxonomy in `_spawn()` exists to keep honest.

**The ledger records a chain as one transaction**, in its own `chains` array, keyed by a
`chain_id` minted once at proposal time:

```json
{"id":"c6ab92c6a-22","status":"ok",     "steps":["selftest","save_minutes"],           "ran":2,"stopped":0,"at":"2026-09-27T20:17:06"}
{"id":"c6ab92c6b-23","status":"halted", "steps":["selftest","selftest","save_minutes"],"ran":1,"stopped":2,"at":"2026-09-27T20:17:07"}
{"id":"c6ab92c69-21","status":"refused","steps":["add_calendar_event","send_email"],   "ran":0,"stopped":1,"at":"2026-09-27T20:17:05"}
```

Three statuses, `ok` / `halted` / `refused`, the count that ran and the index it stopped at. It
keeps **none** of what the hands were given — no token, no address, no title — which is asserted
rather than intended. A refused plan is one refused transaction, not two refused tools.

**State passing, proved end to end.** Before the yes the card showed `{{step1}}` in the `minutes`
field, in the field it will land in, exactly as it will be sent, and said so in English beside the
number — *"quoting what step 1 returns"* — while step one quoted nothing, having nothing behind it.
After the yes, `notes/Chain proof.md` contained **`CHAIN-ONE`**, which is step one's own stdout, and
the literal `{{step1}}` was **gone**, not left in the file as this machine's markup.

### PART 4 — REGRESSION

**`chain_proof.mjs` — VERIFY 57/57 PASS.** Four rounds. (1) A two-intent directive **typed through
the real box and answered by the real brain**, asserted on screen and out loud, then declined. (2) A
two-step plan injected as **model-shaped text** closing with `}}]]`, accepted with a real click,
proving state passing into a real file. (3) A three-step plan whose middle step fails for real,
proving the Halt Law and the unmoved row, and carrying the layout measurements. (4) The Doorman's
chain: a guest's spoken yes refused, zero hands run, card intact, keyboard Yes then settling it.

The injection door is `/tools {"cmd":"chain"}` and it reads **`said` before `steps`** on purpose:
`chain_tag()` is the part of this feature a regression test cannot reach any other way, and it is
the part that was measured wrong first. A harness posting a ready-made array would prove
`propose_chain()` and leave the scanner — which is where the bug lived — untested for ever. The
`cmd == "chain"` door is the exact sibling of `cmd == "propose"`: it asks for a proposal and it
cannot run one; consent is still only ever given at `/execute` or `/chain/execute`, under the
doorman.

**preflight check 27 — "a plan of two is a schema, and a plan that breaks it never pends."** 73 ms,
no brain call, three clauses. (a) The protocol is *called* rather than grepped — its source is a
Python string full of escaped quotes, so a grep for `"hand"` finds nothing — and it must teach
`"hand"`, `"params"`, `[[chain:`, `{{step`, the one-intent sentence and the cap **in the number the
server enforces**; `chain_tag()` must use a JSON scanner and must not be matching three closing
brackets again. (b) **Seven malformed plans, each refused by its documented key, each naming its
step, and each leaving nothing pending** — `chain-empty`, `chain-too-long`, `chain-bad-step`,
`chain-unknown-tool`, `chain-step-missing`, `chain-ref-field` (a placeholder aimed at an address),
`chain-ref-order` (a placeholder pointing forwards). The *nothing pending* half is the one that
matters: a refusal that left a half-read plan in the slot is a plan a later yes could confirm. (c)
And the gate is not simply shut — a good plan **is** accepted, in the shape a model really writes
it, with the placeholder still visible and step two declaring `uses:[1]`; a plan of one falls
through to an ordinary single proposal rather than becoming a numbered list of one item; and the
check puts the proposal down again afterwards, so the next thing to say yes in this house does not
find this one waiting. Finally, **every run count in the ledger is identical either side of the
check** — it only ever proposed.

**THE ONE RED IN THE SWEEP THAT WAS NOT A FLAKE.** `capabilities_proof` fell from 16/16 to 11/16,
and all five failures were in its fitted state: the server restarted, read the registry, and
reported **7 hands, not 8**. The canary had been silently dropped. The cause is this round's own
work — `_clean_tool()` now **requires** a `step` template, because a tool with no imperative
sentence of its own could only be described in a numbered plan by its filename or by the model's
prose, and the second is the one voice this module will not use. An entry that does not validate
does not exist; it is not repaired, defaulted or guessed at, and the server said so on stderr, tool
by tool. Two fixes were available. Defaulting `step` from `proposal` would have gone green by
having a design decision quietly reversed to suit an old fixture. Instead the **fixture** gained
the field it now owes: the canary stands in for a real hand somebody fits by editing JSON, so it
must satisfy exactly what a real hand must satisfy. 16/16 on the re-run.

`lock_proof` failed once on drift being noticed in **1643 ms against a 1500 ms budget**, and passed
alone at **764 ms** — a timing flake of the known kind, re-run solo before being believed, as the
standing rule for this machine requires.

**Baseline and after.** Solo, sequential, quiet, `port_proof` last.

| harness | baseline (round start) | after §25 |
|---|---|---|
| desk_proof | 44 checks, 0 failed | **44 checks, 0 failed** |
| layout_proof | 150/150 PASS | **150/150 PASS** |
| followup_proof | 47/47 PASS | **47/47 PASS** |
| salutation_proof | 26/34 FAIL (named, pre-existing) | **26/34 FAIL — identical, same four assertions** |
| capabilities_proof | 16/16 PASS | **16/16 PASS** (11/16 first, see above) |
| persona_proof | 19/19 PASS | **19/19 PASS** |
| nudge_proof | 21/21 PASS | **21/21 PASS** |
| deck_proof | 238/238 PASS | **238/238 PASS** |
| focus_probe | PROBE 26/26 + 85 checks, 0 failed | **PROBE 26/26 + 85 checks, 0 failed** |
| voice_proof | 145/145 PASS | **145/145 PASS** |
| conversation_proof | 114/114 PASS | **114/114 PASS** |
| routing_proof | 91/91 PASS | **91/91 PASS** |
| echo_proof | 49/49 PASS | **49/49 PASS** |
| console_proof | 30/30 PASS | **30/30 PASS** |
| scribe_proof | 59 checks, 0 fail | **59 checks · 59 pass · 0 fail · PASS** |
| brain_live | 33 checks, 0 failed | **33 checks, 0 failed** |
| eyes_live | 56 checks, 0 failed | **56 checks, 0 failed** |
| tools_live | 62/62 PASS | **62/62 PASS** |
| **chain_proof** | *(did not exist)* | **57/57 PASS** |
| google_hands_proof | 24/24 PASS, 2 skipped | **24/24 PASS, 2 skipped** (grant present, real-API branch reserved) |
| speaker_proof | 61/61 PASS | **61/61 PASS** |
| lock_proof | 78 checks, 0 failed | **78 checks, 0 failed** (one timing flake, re-run solo) |
| preflight | 23 pass, 0 fail, 3 warn (26 checks) | **24 pass, 0 fail, 3 warn (27 checks)** |
| port_proof | 24 checks, 0 failed (last) | **24 checks, 0 failed (last)** |

`speaker_proof` and `google_hands_proof` were re-run specifically to show the chain wrapper did not
break the hands underneath it, and neither moved. The three preflight warns are the standing ones —
`/model`, the focus session and the eyes report — with causes already recorded.

### What is left open

New this round:

- **The spoken cap ate a question, and it may still eat other things.** `SPOKEN_MAX_CHARS = 260`
  now rescues a trailing question mark, which is the case that was measured and the case that
  matters at a gate. It does not rescue anything else. A long line whose last sentence is an
  *imperative* rather than a question is still dropped silently, and nothing asserts that it is not.
- **The rendered list number cannot be read back by any API.** `getComputedStyle(li, ':before')
  .content` returns the rule — `counter(step) "."` — with the counter unresolved, and there is no
  interface that returns the digit the user sees. So `chain_proof` asserts the strongest available
  proxy: the list is an `OL` of `LI`s, every marker is literally `counter(step)`, and the children's
  order and text match the server's steps. A CSS rule that shipped a *wrong* counter would still
  pass. The probe surface reports `n` as the DOM position and says so in its own comment rather
  than pretending to have read the glyph.
- **A chain of four has never been proposed by a model.** The cap is 4, the harness exercises 2 and
  3, and preflight exercises 5-refused. Nothing has yet measured whether a real directive naming
  four intents comes back as four steps or as prose.
- **Placeholders are proved only into `minutes`.** The `text` fields are `body`, `description` and
  `minutes`; state passing has been proved end to end into the third. Into an email `body` it is
  proved at proposal time only, because proving it further means sending real mail.

Carried forward, unchanged, from §24 and before: a guest asking *who am I* is told the boss's name;
`deaddress`'s uncommaed-terminal-call-name limit; *Learn a voice* enrols only the boss; a bark
sliced across two voices scores as neither; `speaker_proof`'s adaptive third-larynx assertion; the
~5% tool→compose flake on *"switch your voice to joe"*; `"no no cancel that Why"` routing to the
web; the spoken column's ~1-sentence recognition loss, still reported as UNPROVEN against a budget
of 2; `routing_proof`'s spoken confirmations 403'd by the doorman; and a genuine Chrome crash
leaving the relaunch nothing to restore. Reserved for the employer: the Gmail real-API send, the
single OAuth consent click, and the two by-hand Calm Sky checks. The watch-capture gap stays
documented in `README.md`.

### The discretion decisions of this round, with reasons

- **The chain reuses the one `_pending` slot rather than getting its own.** A second gate for
  multi-step work would have been a second gate to forget to guard, and the guard is the whole
  point of that file. This is why the Doorman's Chain needed no new code — and why it needed a
  test anyway.
- **`/chain/execute` is a name for `/execute`'s path, not a second executor.** There is exactly one
  route in this server that can start a subprocess, and duplicating it to serve a nicer URL would
  have doubled the number of places consent is checked. The cost of the alias is that a mislabelled
  post costs a trace line rather than an unapproved hand, which is the right way round.
- **The spoken sentence says "sir", not "Addi" as the mandate's example does.** Every registry line
  in this file says "sir"; threading a live speaker's `address_form` into `hands.py` would fork the
  persona's addressing rule, and the persona block is protected. The sentence's *shape* is the
  mandate's — "I have a two-step plan… First… Second… Shall I execute the chain?" — and only the
  vocative follows the house.
- **`step` is required rather than defaulted from `proposal`.** It cost a red in the sweep and it is
  still right: a question and an imperative are different sentences, and a registry that silently
  invents the one it lacks is a source of surprises. The fixture moved instead.
- **The step line is allowed to name LESS than the card shows.** `{body}`, `{minutes}` and
  `{description}` are refused in a step template at load time, because the plan is spoken aloud and
  the rows below it are not. The same leak preflight 16(f) plants a canary for.
- **A bad time at step 2 refuses the whole plan rather than proposing it.** The employer would
  otherwise be approving a first step that runs and a second that was never going to.
- **A refusal names its step number.** A plan is the one refusal where *"that would not work"* is
  genuinely ambiguous about which part, and the model is owed the same specificity so it can fix
  one field instead of guessing again.
- **The tool id a model sent is never echoed back or logged** when the registry does not have it.
  It came from a language model, and this file's standing habit is that model text does not reach
  disk.
- **`chain_proof` injects the model's TEXT rather than an array.** Posting a ready-made array would
  have been simpler and would have left the scanner — the one place the bug actually was —
  permanently untested.
- **Preflight 27 calls `chain_protocol()` instead of grepping `hands.py` for it.** The rendered
  string is both what the model receives and the thing the escaped source hides; a grep for `"hand"`
  against `\"hand\"` on disk finds nothing and would have passed by accident in the other direction.
- **Preflight 27 cancels what it proposes.** A check that leaves a live gate standing hands the next
  spoken *yes* in the house something it never asked about.
- **`spokenForm()` rescues the question rather than raising the cap.** Raising 260 would have hidden
  this instance and left the class; rescuing the interrogative fixes the case where the dropped
  words are the *request for consent*, which is the only case where the omission changes what the
  employer does.

## 26 · The lie was in the history, and four instruments were reading the shutter

Section 25 closed with a machine that could be asked for two things at once. Section 26 began with a
worse complaint: over a long conversation it started *making things up*. At turn 17 of a real session it
said, in its own voice and with no hedge, that the first thing it had been asked that day was where the
employer lived — a question from turn 9 — and that the barista plan had come second, which was turn 14.
Confident, fluent and wrong.

The mandate was to **name the layer before curing it**: instrument a session, log every turn, and let
the evidence say which of four mechanisms was at work — the ear lying to the brain, the brain losing its
grounding to truncation, the chain protocol bleeding into ordinary answers, or a referent resolving to
the wrong object. Fix what the evidence names and nothing else.

### PART 0 · The hunt, and the mechanism it named

`session_proof.mjs` runs twenty typed turns — note questions, web questions, identity, single-intent
directives, two-intent directives, a refusal, follow-ups carried by *it* and *that* — and logs, per
turn: the sentence that arrived, the sentence uttered, the routing kind, the retrieval scores with their
cited passages, the chain-tag, the prompt's assembly size and order with anything evicted, and the
model's raw output. Turn 2 and turn 20 are deliberately the same question. Turn 17 is the eviction
probe. Turn 19 is the staleness probe.

**The mechanism is (b), and it is a particular kind of (b): the model invented nothing.** Every raw
output was faithful to the prompt it was given. What was wrong was the prompt: a four-pair history
window with *nothing anywhere in it saying there had been eight earlier turns*. Asked what came first,
the model answered honestly from the oldest thing it could see — and the oldest thing it could see was
turn 9. It was not hallucinating. It was being lied to by omission, and the liar was the assembler.

The other three suspects were checked, and one of them could not be cleared honestly:

- **(a) transcript ≠ utterance.** `heard` and `asked` are recorded separately by `turn_begin()` and never
  reconciled, precisely so this question can be asked. No turn was answered against a sentence other
  than the one that arrived. But on a typed turn there is no ear, and `heard` is empty by design — so
  the wide claim is reported **UNPROVEN by construction** rather than passed. A harness that prints a
  tick there is lying about what it measured.
- **(c) chain-protocol bleed.** The protocol is in the prompt on every turn, and no ordinary answer came
  back wearing a plan structure.
- **(d) antecedent staleness.** Turn 19's *it* resolved to the object from turn 18, not to an older one.

### PART 1 · The context budget

| what | value |
| --- | --- |
| `MAX_CONTEXT` | 48 000 characters, declared on the wire, not only in a comment |
| `CONTEXT_FLOOR` | 29 000 |
| largest prompt in twenty turns | 26 712 characters — **44% headroom at the worst turn** |
| `HISTORY_TURNS` | 4 pairs held in full |
| `OLDER_KEEP` / `OLDER_MAX` / `SUMMARY_PAIR_MAX` | 8 / 4 000 / 200 |

The order is **persona → manifest → chain-protocol → guest → standing-offer → retrieval → recent-turns →
older-turns → question**, one assembly order for the whole session, and seven of the nine blocks can
never be evicted: persona, manifest, chain-protocol, guest, standing-offer, retrieval and the question
itself. Only `recent-turns` and `older-turns` are droppable.

**The eviction rule, which is the actual repair.** Turns beyond the window are no longer dropped; they
are *summarised by rule* into a block headed `EARLIER IN THIS CONVERSATION` that says in plain words
that it is a summary and holds the gist. Turn 1 is pinned. No line is cut mid-sentence. At turn 20 the
window held **8 recent messages and a 2 109-character summary of what was dropped**, and the answer
cited `cold-brew-recipe.md` — the same passage turn 2 cited, from 44% less room. Asked at turn 17 what
came first, it now says the first thing was a good morning, and does not name turn 9. Preflight's own
reading of the same machinery: sixteen pairs leave a four-pair window and a **1 733-character summary**,
with the middle counted but not quoted.

`accounted` is true on every assembled turn: an assembly of 5 928 characters is charged to the character
against the nine blocks, so nothing rides on the wire uncounted. The hands block is a composition —
manifest 3 609 + protocol 1 470 = the 5 080 bytes it always was.

### PART 3 · The grounding audit

Every answer carries one of six declared classes — `notes · web · persona · state · refusal · chain` —
asserted against what the answer actually has behind it.

| turn | class | what stands behind it |
| --- | --- | --- |
| 2, 3, 14, 15, 18, 19, 20 | `notes` | a real passage at or above threshold, shown |
| 7, 8 | `web` | 3 fetched sources each |
| 4, 5 | `persona` | cites nothing, fetched nothing — **no chip can render** |
| 6 | `state` | a live reading, nothing cited |
| 10, 12 | `chain` | really did propose hands from the registry |

Six turns the server would not classify went to a **separate judge process**, and it called all six
grounded: turn 1 `persona` ("its own greeting and offer of service, nothing reported from elsewhere");
turn 9 `notes` ("reports absence of the address in the employer's notes without inventing content");
turn 11 `refusal` ("it stands down and asserts no action taken, claiming nothing"); turn 13 `state`;
turn 16 `persona` ("the assistant's own translation, composed rather than reported"); turn 17 `state`
("it recalls earlier turns, which the summary and recent turns in the prompt support"). No answer in the
session wore `notes` or `web` with nothing behind it. Five conversational, identity, capability and
connection-state sentences render **nought chips and nought citations**, while a real notes question
still lights five — the gate is a judgement and not a blanket.

### PART 4 · The sure door

**The length ladder.** Measured in `tools/ladder.py` against a one-row roster built in memory from
piper's voices — nothing written to `speaker-store/`, no vector printed, only cosines.

| rung | the employer | strangers (worst of six readings) |
| --- | --- | --- |
| 13 words | 0.9079 | — |
| 30 words | 0.8950 | — |
| 47 words | 0.9166 | 0.1969 |

**No decay with length.** The floor is 0.50 and the near band 0.35; the worst stranger reading is under
both. Windowing gains the employer **+0.0000 on every rung** — and that is not the feature failing, it is
the fixture having no defect to cure: a piper clip is wall-to-wall speech with no room and nobody else in
it, and windowing exists to throw away exactly those things. So the two cases it *is* for were built:

| case | whole clip | best window | gain |
| --- | --- | --- | --- |
| he speaks, then eight seconds of room | **−0.0532** | **0.8662** | **+0.9194** |
| a guest talks over the middle of his sentence | 0.8157 | 0.8858 | +0.0701 |

The first is decisive: on the whole-clip reading the employer scores *worse than any stranger ever
measured* and is refused outright. The second **closes §24's open item, "a bark sliced across two voices
scores as neither."**

**The near band is reachable, and by the right input.** His own voice buried by degrees: 0.8950, 0.7765,
0.7133, 0.6357, **0.4756 → UNVERIFIED at −6 dB SNR**, 0.2911, 0.0975, 0.0232. Monotone. So 0.35 is not
dead code, and what reaches it is the employer in a very loud room — not a stranger. `seal_for()` gained
a fourth word, and the server refuses in its own sentence: *"I could not be sure that was you, so I have
not acted on it. Say it once more, a little longer, or press Yes on the card."* Never a silent GUEST for
the boss.

**Longevity is the one claim this round does not get to make, and the reason is the room.** Four
twelve-turn spoken sessions were run. Every one of them held the *structural* claims: one open, one arm
per turn, zero hard errors, zero barge-ins, the on-device engine taken every time, and — importantly —
**no positional decay**, the soft turns scattered across the session rather than clustering at the end.
What varied, wildly, was how many of his words came back:

| run | soft turns of 12 | aggregate | room, per turn | note |
| --- | --- | --- | --- | --- |
| A | **2** (86%, 31%) | ~93% | 0.28 – 0.41 | ten of twelve word-perfect; **at budget** |
| B (`session_proof`) | 6 | 83.5% (76 of 91) | 0.19 – 0.44 | reds at turns 1, 4, 5, 12 |
| C | 10 | — | 0.16 – 0.41 | bad from turn 1 |
| D | 6 | — | 0.28 – 0.38, **then 0.014 / 0.006** | perfect through turn 6, then the room blacked out |

Run D is the one that explains the rest. Turns 1–6 came back **100% each**. Turn 7 delivered nothing and
turn 8 delivered nothing, and their input peaks read **0.014 and 0.006** — sitting between turns that
read 0.38, and below `VAD_OFF` (0.018), so the page was right not to hear anything. Turns 9–12 recovered
the level and never recovered the accuracy. **The room intermittently collapses to four percent of its
level, mid-session, and comes back.** That is in the machine's audio path, not in the ear and not in the
funnel, and it is now recorded per turn so that nobody reads it as either.

So `SHORT_BUDGET` stays at **2** and `session_proof SPOKEN` is reported **RED: 80/83**, failing exactly
the three longevity claims. Lowering the budget to ten would buy a green by agreeing that a butler need
only hear a third of what is said to him, which is not a repair. The table above is the evidence; run A
is the only one taken in a room that behaved for twelve consecutive turns.

### The room was turned down, and it took most of the evening to see it

Before any of that, every spoken sentence in the house was returning empty — twelve-turn sessions with
nothing delivered, and `routing_proof` reporting **0 of 14** sentences reaching the funnel. The first
three hypotheses were all wrong, and they are worth listing because each one *fit*:

1. **The background-shell law.** A harness launched from a backgrounded shell cannot raise its Chrome, so
   `routing_proof` was re-run in the foreground. Identical: fourteen empty transcripts. **Cleared.**
2. **The cloud recogniser's silent throttle** — the documented failure that produces exactly this
   symptom. Cleared by the instrument itself: `__galaxy.ear.local` read `on: true, state: available,
   tries: 7`. The words were staying in the room the whole time. **Cleared.**
3. **Windows communications ducking**, which reduces other sounds by 80% while a microphone is open. The
   fit was almost too good: the best reading of the evening was 0.034, and the known-good level times
   0.2 is 0.034 exactly. `HKCU\Software\Microsoft\Multimedia\Audio\UserDuckingPreference` was absent, so
   the 80% default applied; it was set to 3 ("do nothing") and the room was measured again. **0.0444.
   Disconfirmed** — a hypothesis retired by measurement rather than by argument.

The cause was that **the machine's output volume had been turned down**. Raising it moved the page's own
analyser from 0.007–0.044 to **0.375–0.400**, and the same twelve sentences that had returned nothing
came back word-perfect on a single arm each. Trimmed toward the recipe's documented 0.17–0.23, a
three-turn control read **100% / 100% / 100%, one arm each, zero collapsed**.

Which is worth being blunt about: for several hours the suspects were the recogniser, the page, the
harness and the operating system's mixer policy, and the answer was the volume knob. The earlier
reading of *"0.23 → 0.16 → 0.04 → 0.00 across consecutive runs on an idle machine"*, written up in the
previous round as a mysterious environmental decay, was this all along, and the residual intermittent
collapse in run D is the same path still misbehaving.

### Four instruments that were measuring the wrong thing

This round found four defects of one family — the harness measuring itself rather than the thing — and
that is a pattern, not a coincidence.

**(1) `heardWords` was not a recall.** It counted *words the room delivered*, so a turn read 250% and a
session read 113.2% — 103 words against 91 spoken — and the mandate's "heard ≥ 90% of spoken" was
meaningless in both directions at once: turn 4 read 0% and turn 1 read 250% in the same run. A count of
delivered words can clear 90% while carrying *none of his words*, because the butler's own answer and the
neighbouring turn's late final land in the same window. `recalled()` now matches his words against the
delivered ones as a **multiset** — each spoken word struck off against one unused heard word, so a
doubled word is not scored twice and a dropped one is not forgiven. Both numbers are kept and printed
side by side, because the delivered count is still the right *diagnosis* column: a turn reading 250% is a
turn where something else was in the microphone, and a human wants to see that. Only the recall is
asserted on. The first two-turn run after the change earned its keep immediately: 7 words delivered, 6 of
them his — the ear had returned *rooster* for *roaster*, which the old measure scored 100%.

**(2) The last turn was photographed before its final landed.** Every turn's wait ends when the page's
turn counter moves. For turns 1..n−1 that is late enough by accident, because the next turn's `say()`
spends seconds arming and speaking and the final lands during it. For turn *n* there is no next turn, so
the dump was read the instant the counter moved — and this file's own header already says why that is too
early: **the final arrives after the flush that ends the turn.** Turn 12 read 0 of 6 words with nothing
delivered while the browser tap showed its interims still arriving one line above the table. There is now
a bounded fifteen-second wait for the last turn, and it reports which happened — a turn that truly
delivered nothing must still be able to read as nothing.

**(3) The engine verdict was read before the engine was chosen.** The page publishes
`__galaxy.ear.local` so a spoken harness can say whether the words stayed in the room or went to a
service. `ear_dump` read it **immediately after the ear opened** — and the engine is chosen at the *arm*,
which is later. So `on` was false for every run that will ever exist, and the first version of that read
called it a verdict: it printed THESE WORDS ARE GOING TO A SERVICE against a page that had simply not
armed yet. Most of a diagnosis was written on top of it — the cloud recogniser's documented silent
throttle, which fits the symptom perfectly — before `tries: 0` in the same line gave it away. The reading
is now taken after the last turn, where it exists, and the same session that had "proved" the cloud was
answering reported `on: true, tries: 6`. `session_proof` now asserts the engine as a red of its own,
before the recall claims, so a cloud run fails by name rather than being mistaken for an ear that
degrades over a long session.

**(4) The chain ledger is a ring, and `chain_proof` had forgotten it.** The proof that a refused plan is
recorded as ONE transaction and not one row per tool was written as arithmetic:
`chains().length === chainsBefore + 1`. `hands.py` caps the file at `CHAIN_LEDGER_MAX = 50` on the read
*and* on the write, so the fifty-first append pushes the oldest row out and **the length never moves
again**. The harness scored 78/78 the day before this was found purely because the ring had not filled
yet; it then failed twice identically, with a ledger row that was visibly correct — `status: refused`,
both steps, one row. A latent red with a date on it, and one that reads as a regression in the server
rather than as arithmetic in the harness. It now asserts **identity, not length**: the row is new if its
id was not in the ledger before, and "one and not two" is the claim that exactly one id appeared. True at
any ring position, and it now says so out loud — *"1 new row(s) in a ledger of 50 (the ring holds 50, so
this counts ids and not rows)"*.

### The page fix underneath it: an engine chosen once, and a flag that could lie

`processLocally` was only ever set inside `buildRecogniser()`, and the recogniser is built **once** —
`if (!recogniser)` at the arm. So whatever the pack's state was at the first arm decided the whole
conversation, and the comment promising that "the pack can land between two turns" was never implemented
for a reused instance. `earLocalTake()` now runs at every arm. It also cannot lie in either direction: on
a fresh instance it recomputes from nothing, and on one that has already taken the property it returns
early and keeps the answer, because re-writing `processLocally` on a recogniser that has already run a
session and reading it back is a question the browser need not answer the same way twice — and a false
read-back there would say *the cloud has him* about a recogniser that is still local. Under-claiming and
over-claiming are both lies. It also now says **which** of the two things happened when it fails, because
an empty `why` beside `on: false` was ambiguous between "the pack was not ready at this arm" and "the
browser refused the write" — opposite faults with opposite repairs, and both used to read as silence.

`ear_dump.mjs` gained `EAR_DUMP_CLOUD=1`, which stubs the one static the page reads before it decides —
over CDP, before navigation, so the page itself is unmodified, because a knob added to the page for a
question outlives the question. It exists because both engines answer through one API and neither says
which it is, so "the on-device model hears this room worse than the service" cannot be settled by
argument: only by the same sentences, the same speakers and the same minutes, twice.

### PART 2 · The orchestrator's checks, re-asserted

`chain_proof.mjs` stands at **78/78** against a 57/57 baseline. Seven malformed plans are refused, each
naming the documented key it broke, with nothing left pending; a good plan is accepted in the shape a
model writes it; a plan of one falls through to a single proposal — **one intent is not a chain** — over a
precision fixture set producing zero chain cards. Step N failing halts the chain, N+1 never runs, the
ledger row names the stop index and the receipt names what succeeded and where it stopped. A guest's
spoken *yes* is refused in the same words with zero hands run and the card intact; the keyboard *yes*
settles it. `{{stepN}}` substitutes end to end into minutes and into a **draft**, never a real send, and
the placeholder never reaches the spoken line or a card title.

**The fuzz set**, seven shapes — truncated JSON, missing and doubled terminators, a tag without its array,
an array without its tag — leaves **no `{{`, no `}}`, no `"hand":`, no tag and no bracket array on any
answer surface**, while the control answer *about* JSON is byte-identical with its braces intact.

**The spoken summary** is generated and never truncated: a four-step plan whose sentence runs to 365
characters — over the 260-character spoken cap — still ends with *"Shall I execute the chain?"*, announces
*"and two more steps on the card"*, and the number it announces is the number it dropped: 2 lost, 2 owned
up to. Nothing under the cap is touched.

### PART 5 · Baseline and after

| harness | baseline (§26 start) | after |
| --- | --- | --- |
| session_proof (typed) | *(new)* | **75/75 PASS** |
| session_proof (`SPOKEN=1`) | *(new)* | **80/83 FAIL** — the three longevity claims, named to the room |
| chain_proof | 57/57 PASS | **78/78 PASS** (after the ring fix) |
| speaker_proof | 61/61 PASS | **70/70 PASS** |
| routing_proof | 91/91 PASS | **89/89 PASS · 1 UNPROVEN** (13 of 14 sentences delivered, budget 2) |
| preflight | 24 pass, 0 fail, 3 warn (27) | **26 pass, 0 fail, 3 warn (29)** |
| persona_proof | 19/19 PASS | 19/19 PASS |
| capabilities_proof | 16/16 PASS | 16/16 PASS |
| nudge_proof | 21/21 PASS | 21/21 PASS |
| console_proof | 30/30 PASS | 30/30 PASS |
| echo_proof | 49/49 PASS | 49/49 PASS |
| followup_proof | 47/47 PASS | 47/47 PASS |
| salutation_proof | 26/34 FAIL (named) | 26/34 FAIL (unchanged, named) |
| desk_proof | 44 checks, 0 failed | 44 checks, 0 failed |
| layout_proof | 150/150 PASS | 150/150 PASS |
| deck_proof | 238/238 PASS | 238/238 PASS |
| tools_live | 62/62 PASS | 62/62 PASS |
| brain_live | 33 checks, 0 failed | 33 checks, 0 failed |
| eyes_live | 56 checks, 0 failed | 56 checks, 0 failed *(3 reds batched, 0 solo)* |
| scribe_proof | 59 pass, 0 fail, PASS | 59 pass, 0 fail, PASS |
| voice_proof | 145/145 PASS | 145/145 PASS |
| conversation_proof | 114/114 PASS | 114/114 PASS |
| focus_probe | PROBE 26/26 · 85 checks, 0 failed | **PROBE 26/26 · 85 checks, 0 failed** (2 reds batched, 0 on a clean server) |
| google_hands_proof | 24/24 PASS, 2 skipped | 24/24 PASS, 2 skipped |
| lock_proof | 78 checks, 0 failed | **78 checks, 0 failed** (third attempt; timing flake) |
| port_proof | 24 checks, 0 failed (last) | 24 checks, 0 failed (last) |

The two new preflight integers are **28, the prompt has a cap, an order, and a memory of what it
dropped** and **29, every answer carries a grounding class, and a class is not a route**. The three warns
are the routine 10, 11 and 12.

**Three reds in this sweep were the sweep's own fault, and saying so is the point.**

- **Eleven phantom reds in `routing_proof`**, all of the form *"THE TRACE NAMES THE CLASS: a line reading
  route: identity"*. The server had been restarted with its stderr going to `_runs/server-trace.log`,
  and every harness reads `server-trace.log` in the project root — so eleven assertions were reading a
  frozen file. Restarted to the right path, the same run scored 89/89. The house rule exists for exactly
  this and was still broken by hand.
- **Two reds in `focus_probe`**, both of the form *"the room is the ordinary room: k=0 … with no
  session"*. The server was holding a **leftover `state: "ended"` session** with `drifts: 2` and
  `locked: true` still on it, and the at-rest assertions require no session at all. On a freshly started
  server: 85 checks, 0 failed. `lock_proof` was contaminated by the same thing — 73 checks with 17
  failures cascading from one root, *"THE LOCK COMPLETED ITSELF … lockedTab=''"* — and came back to its
  full 78 checks once the server was clean, then needed a third attempt for the documented 1500 ms
  drift-notice budget, missed at 1690 ms.

### Discretion decisions, with reasons

- **`CONTEXT_ORDER` is the precedence ladder; `where` is the geometry.** Retrieval rides in the final
  user turn — a declared deviation, so the two ideas are not silently conflated in one list.
- **Summarising by rule, not by model.** `summarise_pairs()` makes no model call: a summary generated by
  the thing being audited is not evidence about it, and it would cost a call per turn.
- **`/session/dump` is a kill switch rather than an opt-in.** A dump that has to be asked for is a dump
  nobody takes on the run that mattered.
- **The judge is a separate process that bypasses `call_model`.** THE COSTUME — `wear_persona()` runs on
  every list `call_model` is handed, so a judge would be asked to rule while dressed as the butler; and
  THE METER — `call_model` also completes the open turn's budget plan and files a model call, so judging
  a session would change the session it was judging.
- **The transcript-vs-utterance claim is reported UNPROVEN in the typed half** rather than passed. There
  is no ear on a typed turn, and a tick there would be a lie about coverage.
- **The length ladder lives in `tools/ladder.py`, not in the harness.** Rungs defined in *words* need a
  synthesiser, and the stranger half needs a roster with one row in it — against the live store the
  strangers have rows of their own and `identify()` would correctly answer about the wrong pair of
  voices. The first draft made exactly that mistake and reported a guest as admitted when the doorman had
  been right; the mistake is recorded in the file.
- **`ear_dump.mjs` was extended to twelve turns rather than a second ear grown inside `session_proof`.**
  One ear, one no-retry rule; the default stays six so the by-hand photograph is unchanged.
- **The longevity 90% rule carries a measured budget; the collapse rule and the aggregate carry none.** A
  session allowed two soft turns and nothing else cannot pass by degrading quietly across all twelve.
- **Both word counts are kept, and only one is asserted on.** The delivered count is a diagnosis and the
  recall is the claim; deleting the first would have thrown away the column that explains the second.
- **`SHORT_BUDGET` was left at 2 with the harness red**, rather than raised to fit the room. A budget
  fitted to the worst room on record is not a budget.
- **The engine A/B is a harness env knob, not a page knob.** A switch added to the page to answer a
  question outlives the question.
- **The ducking hypothesis was tested by changing one machine setting, and it is still changed.**
  `HKCU\Software\Microsoft\Multimedia\Audio\UserDuckingPreference` was absent and is now `3` ("do
  nothing"). It did not fix anything and it is outside the application; it is recorded here by its exact
  key so it can be undone in one line, because an undocumented change to the test rig is worse than the
  hypothesis it failed to prove.
- **The premature engine verdict was withdrawn in public rather than quietly deleted.** The wrong
  diagnosis was well-evidenced and wrong, and the reason it was wrong — an instrument read before the
  thing it measures exists — is the same class of defect as the recall bug, the shutter bug and the ring
  bug. Four in one round is a pattern worth leaving on the page.

### Left open

- **The room's render level intermittently collapses to ~4% mid-session and recovers** (run D, turns 7–8
  at 0.014 and 0.006 between turns at 0.38, on an idle machine with 11.8 GB free). Ducking is
  disconfirmed; the mechanism is unnamed and is outside the application. **The twelve-turn longevity
  claim is blocked on it**, and `session_proof SPOKEN` stays red until a room holds for twelve
  consecutive turns.
- **`SHORT_BUDGET = 2` is met by one of four runs.** Run A met it; B, C and D did not, at verified room
  levels. The budget is not yet earned.
- The spoken 260-character cap still drops a trailing **imperative** silently; only the interrogative is
  rescued.
- The rendered list number cannot be read back by any API.
- **A chain of four has never been proposed by a model**; `chain_proof` round 6 executes the page's own
  bytes for that reason.
- `what can you do` is classed `identity` rather than `capability` (pre-existing).
- Three of `chain_proof` round 5's six single-intent fixtures raise no card at all.
- **Windowing buys the employer nothing on TTS fixtures.** Its benefit can only be measured in a real
  room; the two constructed cases stand in for that.
- **The near band's end-to-end refusal through a live spoken turn is not yet asserted** — only the seal
  and the curve are.
- `lock_proof`'s 1500 ms drift-notice budget is met on roughly one attempt in three on this machine
  (1690 ms, 1643 ms recorded).
- `focus_probe` and `lock_proof` both require a server with no session on it, and nothing enforces that
  but the operator.
- Everything carried from §24: a guest asking *who am I* is told the employer's name; `deaddress`'s
  uncommaed terminal-call-name limit; *Learn a voice* enrols only the employer; `speaker_proof`'s
  adaptive third-larynx assertion; the ~5% tool→compose flake on *switch your voice to joe*, seen again
  this round; `"no no cancel that Why"` → web; a genuine Chrome crash leaving the relaunch nothing to
  restore.
- **`routing_proof`'s spoken confirmations are still 403'd by the doorman**, and the room being fixed did
  not change it: with an offer standing, the wire still reads
  `403 kind=tool route=confirmation lookups=0 q="Yes yes do it Galaxy"`. The harness is green there
  because it asserts the *route*, not the outcome — worth knowing before anyone reads 89/89 as this being
  settled.
- **Closed this round:** §24's "a bark sliced across two voices scores as neither".

## 27 · A clock that costs nothing, and the island that proves it

### Why this part existed at all

Before this round, *"what time is it in Tokyo"* was **a web search**. A round trip, a rate limit, a
citation chip under the answer, and a latency the employer could hear — all spent computing a
subtraction. The whole of PART 7 is an answer to that: a table on this disk, read in microseconds,
citing nothing because it read nothing.

### The diagnosis that shaped the design

`zoneinfo` is in the Python standard library. **Its data is not on Windows.**

```
>>> from zoneinfo import ZoneInfo          # imports fine
>>> ZoneInfo("Asia/Tokyo")
ModuleNotFoundError: No module named 'tzdata'
>>> len(available_timezones())
0
```

The import succeeding is the trap. A module that tested `import zoneinfo` and then fell back to a
hand-written offset table would have read **identically right for six months** and been an hour out
every March and October, silently, in both directions. So `worldclock.py` has two doors and it
**proves the first one with a real key before adopting it**:

```python
if viastdlib("Asia/Tokyo") is not None:     # not `if zoneinfo:`
```

The second door is `dateutil.zoneinfo`, already installed, carrying **598 bundled IANA zones** — no
new pip dependency. The route names which door answered, and that naming is the check: a silent
fallback is invisible until spring.

### The fixtures

**Three cities, checked against a database this harness did not read from.** Node's V8 ships its own
full ICU copy of the IANA rules — a different database, a different project, a different process. A
harness that asked `worldclock.py` what time it ought to be would have proved only that Python is
deterministic.

| place | server (`dateutil.zoneinfo`) | Node ICU | offset handed to the page | ICU offset |
|---|---|---|---|---|
| London | `07:49` | `07:49` | `60` | `60` |
| New York | `02:49` | `02:49` | `-240` | `-240` |
| Tokyo | `15:49` | `15:49` | `540` | `540` |

The offset is asserted **separately from the time**, because the board ticks its tiles from that
number: a reading that is right on open and 60 minutes out thereafter passes a time-only check and
is wrong for as long as anybody watches it.

**The date line — the pair that proves the day is computed.** Apia and Pago Pago are about a hundred
miles apart at `+13:00` and `-11:00`. They read the same minute on different days, always.

```
It is 7:49 in the evening in Apia, Addi - today, against your clock.
It is 7:49 in the evening in Pago Pago, Addi - yesterday, against your clock.
```

```
offsets   Apia +780   Pago Pago -660     opposite signs
minute    19:49       19:49              the same
date      2026-09-28  2026-09-27         different days
```

A day offset derived from the hour difference collapses these two into one reading, and the tile
that says *tomorrow* then says it about the wrong island. **Tokyo is the same lesson quietly:** four
and a half hours from his clock is nought days by any arithmetic on the offset, and is still
tomorrow at nine in the evening. So the day is a **difference of calendar dates**, on the server and
on the page, and the clause is always present — *"against your clock"* — because *tomorrow* alone
leaves it open whether it means tomorrow in Samoa.

**A place that is not a place.**

```
I do not know where Narnia is, Addi, so I will not guess at its clock.
I do not know where Zanzibar On Sea is, Addi, so I will not guess at its clock.
I do not know where Upper Fenwickshire is, Addi, so I will not guess at its clock.
```

No time in the refusal, no nearest match, no *did you mean*. A guess reads exactly like a right
answer, and a clock confidently in the wrong hemisphere is worse than no clock. The place is handed
back **capitalised** even though the funnel's vocative peel lower-cases everything, because *"I do
not know where narnia is"* makes a second and untrue claim on top of the true one — that the word
was not recognised as a place name.

**Zero chips, through the real page.**

```
It is 3:49 in the afternoon in Tokyo, Addi - today, against your clock.
chips 0 · #a-src display:none · #panel not open · web lookups in server-trace.log 0 -> 0
```

The sources row is `display:none` rather than shown-and-empty — a *Drawn from* heading over nothing
is a claim about a source that does not exist.

**The board.** Seven tiles, his own marked, and the day word only where it is earned:

```
Here 12:19   London 07:49   New York 02:49   San Francisco 23:49 yesterday
Tokyo 15:49  Dubai 10:49    Sydney 16:49
7 rendered against 7 computed · repaints 2 -> 4 while open · 0 tiles after close · timer stopped
```

`CLOCK_DAY_WORD['0']` is the empty string on purpose. *today* on six tiles out of seven is noise;
its **absence** is the information.

### Two bugs the fixtures found before the employer could

**`re.VERBOSE` strips the space inside an alternation.** `(?:'s| is)?` compiled to `(?:'s|is)?`, so
*"what is the time in Sydney"* silently fell out of the clock class while *"what time is it in
Sydney"* worked. A class that works on the phrasing I happened to type first. The repair extracts
`_WHAT` / `_NOW` / `_ASKS` with explicit `\s`, and the harness now carries ten phrasings:

```
what time is it in Sydney · what is the time in Sydney · what's the time in Sydney
whats the time in sydney · time in sydney · what is the time in sydney right now
sydney time · what day is it in auckland · how late is it in berlin · time in tokyo japan
```

**`"what is the time"` returned nothing.** The loose possessive pattern matched first, read the
place as `"what is the"`, failed to resolve it, and returned a flat refusal instead of falling
through — three of his most ordinary phrasings out of the class. Fixed by ordering `asked()` so the
anchored *here* forms are tried before the possessive.

Two more caught by ear rather than by assertion: `"It is 3 30 in the afternoon"` — a bare number
pair, which a neural voice reads as *three, thirty* — and `"It is 12 o'clock in the afternoon"`.
Both are now asserted (`%d:%02d`, and `twelve noon` / `midnight` as special cases).

### The class is not a dragnet

The opposite failure to a miss, and the harder one to notice: a protected class that grew until it
caught *"what time is it in Tokyo"* can grow one word further and catch *"what time did I write that
note"*, which has an answer in his notes. Ten sentences are asserted to route **elsewhere**:

```
what did I write about Tokyo · what time did I write that note · how much time is left
set a timer for ten minutes · what is the difference between Tokyo and London
schedule a meeting in Tokyo · what is the weather in Tokyo · who are you (identity)
are you there (meta) · what can you do (identity)
```

`PROTECTED_CLASSES` is untouched — still `("confirmation", "meta", "identity", "directive")`. The
clock stands beside them in `UNPAID_CLASSES` and is tried only after all four decline. Check 30
asserts that structurally, because the cheap way to add a fifth class is to append it to the four.

### Verdicts

```
clock_proof.mjs      VERIFY 95/95 PASS
preflight.py         27 pass, 0 fail, 3 warn        (30 checks; warns are the routine 10, 11, 12)
```

Check 30 — *the clock costs nothing and knows what day it is there*:

```
the clock reads dateutil.zoneinfo, knows 215 places, and the route costs nothing
the four protected classes are as the mandate wrote them and the clock is tried after them
a clock question answers from a table on this disk: 0 nodes, 0 lookups, 0 sources
the date line holds: Apia is today and Pago Pago is yesterday, against his own clock
a place it cannot find is refused plainly, with no time in the refusal and nothing spent on it
and it declines the three sentences that only look like clock questions
```

### The Connectors board · six readings, the hands from a file, and one absence

The Command Panel gains a row, **Connectors**, and behind it a grid of nine tiles. Every value on it
is read from something else: the first six from `/google`, `/tools` and the page's own live state,
and the rest from `tools/registry.json` itself. Nothing on this board holds a fact of its own.

```
  TILE                              VALUE            SMALL PRINT                                  ACTION
  ------------------------------------------------------------------------------------------------------
  Calendar                          CONNECTED        can write events · <account email>           -
  Gmail                             CONNECTED        can send mail · <account email>              -
  Notion                            NOT CONFIGURED   no hand in the registry and no client here   Connect (disabled)
  Voice                             PIPER            joe-medium                                   Recast
  Eyes                              CLOSED           the eye button is the only control           -
  Scribe                            READY            base.en · can write minutes on a yes         -
  Relaunch Chrome with the debug…   HAND             3 capabilities · 0 parameters                 -
  Test the hands themselves         HAND             1 capability · 1 parameter                    -
  Bring you back to the locked tab  HAND             1 capability · 0 parameters                   -

  head: Read from /google and 7 hands in the registry. A hand runs when you ask for it and
        say yes — never by pressing a tile here.
  row : Connectors | 6 connectors · 7 hands · google connected
```

The account name is `<account email>` here and in every log this round, as it has been since the
Google row first existed. The board shows it on his own glass, which is where it belongs; a lookbook
is a document that leaves the machine.

### The one law this board could have broken

A grid of nine tiles next to an executor is a second door. The Halt Law gives the registry exactly
one: a proposal, a spoken yes, one run. So **no hand tile carries a button** — not a disabled one,
none — and the head says so in the place a human reads rather than only in a comment. The only verbs
on the whole board are Notion's disabled *Connect* and the Voice *Recast*, which is a control that
already existed one row above.

Eyes and Scribe are verbless for a narrower reason. The Eyes Law names **one variable and one
control**; a second button here could be pressed in the half-second `#eye` disagreed with it.

**And a connected grant carries no verb either.** The first plate of this board read `CONNECTED`
beside a disabled button saying `Connect`, which a reader takes as a broken button rather than as a
state. *Disconnect* is not the missing word: the Google row already owns it, and a second revoke door
is the thing Eyes and Scribe are kept quiet to prevent. Connected is a readout; anything else is a
button with a reason under it. That is the decorative thing this part cut.

### Notion is an absence, reported

```
Notion   NOT CONFIGURED   no hand in the registry and no client on this machine   [Connect] disabled
```

No route, no stub, no placeholder waiting for a key — the honest reading of a service this house does
not have, which is the reading he needs in order to ask for it. The harness asserts the registry
holds no `notion` hand, so the tile is a reading of the absence rather than scaffolding for it.

### The canary

The mandate asks for a fake registry connector that surfaces a tile and leaves no ghost. The entry
planted names a script **that does not exist**, asserted before it is written, so a tile can appear
for something that could never execute:

```
  planted   id canary_connector · script canary_connector_does_not_exist.py (asserted absent)
  /tools    carries it without a restart, on registry.json's own st_mtime rule
  grid      9 -> 10 tiles · keyed "hand:canary_connector" · act "" (no verb, like every hand)
  removed   /tools drops it · grid back to 9 · the name is nowhere in document.body at all
  file      tools/registry.json byte-for-byte what it was, asserted in `finally`
```

The restoration is written twice on purpose — inline and again in `finally`, where the equality is a
check rather than a hope. A harness that plants a row in a real file and throws halfway is a harness
that edits the employer's registry.

### Three reds, and only one of them was the page

The first run read `56/59`. Two of the three were a real bug and one was the harness lying to itself.

**The row under a full grid said it had not read anything yet.** `boardOpen()` painted the grid when
the read landed and nothing repainted the order sheet, and the row's own reading arrives from the
same fetch. So the employer would have seen nine live tiles above a line saying `not read yet`. One
line in `boardOpen` fixes it for every board there will ever be.

**Two boards shared one reading slot.** `board.read` was a single variable, so opening Connectors
over the World Clock left the clock row reporting `0 tiles · 0 places known` about an organ that was
working perfectly. It is now `boardRead[name]`, with `board.read` a getter that can only read, and
check 31 asserts `board.read` is never assigned.

**And the third red was mine.** The harness gated its assertions on "`/health` has landed", proved by
the rail's model cell carrying text — and the markup ships every rail cell with an ellipsis
placeholder:

```html
<div class="rl" id="rail-model"><span class="rk">model:</span><b class="rv">…</b></div>
```

`"…"` is truthy. The gate passed in the first frame, and worse, the model value also arrives on a
*second* route — `loadBrains()` reads `/brains` and paints the chip, and `/brains` answers long before
`/health`, which probes piper, whisper, the index and the web door on its way. So the harness read a
page mid-boot and reported the Voice tile as `BROWSER` and the Scribe tile as `ASKING`: both correct
for a page that had not been told otherwise yet, and both indistinguishable from a bug in the tiles.

A throwaway diagnostic settled it in one run, by asking the page rather than the code:

```
visibilityState  "visible"        voice.engine     "piper"
console.log      speak: engine is piper, en_US-joe-medium, locally
scribe.installed true             rail model text  "OPUS 5"
```

The page was never wrong. The gate is now the **archive** cell, matched against the four shapes
`railFrom()` can write into it — `off`, `building`, `N file`, `N files` — never against "not the
placeholder", because an empty string would pass that. The archive is on `/health` and nowhere else
in the page, and it is not one of the facts the sections below it assert, so waiting on it is not
waiting for the answer.

### Verdicts

```
connectors_proof.mjs   VERIFY 61/61 PASS
preflight.py           28 pass, 0 fail, 3 warn        (31 checks; warns are the routine 10, 11, 12)
```

Check 31 — *the connectors board reads two routes and cannot run a hand*:

```
the board's two routes answer and neither carries a token or a secret to the browser (7 hands, grant 'connected')
and /tools still publishes no script path and no trigger word
each of the 4 named tiles speaks for a hand the registry actually validates: add_calendar_event, send_email, set_voice, save_minutes
and not one hand tile carries a verb, so the grid cannot become a second door into the executor
each board writes its own reading by name and board.read only reads, so the World Clock row cannot report the Connectors board's answer
and the row behind a board is repainted from the same reading as the grid
and POST /tools runs nothing (400)
```

Each of the three source-level clauses was tested against a doctored copy of `index.html` before it
was trusted: a planted `act:` on a hand tile, a planted write to `board.read`, and `cmdPaint()` taken
out of `boardOpen`. All three fail when they should, which is the only thing that makes them checks.

### One voice, one surface · what stands down, and what may never

While the butler is reading an answer the sentence is in the speakers, on the transient caption and —
until this part — on the card as well. Three copies of one sentence, and the employer's eye is asked
to pick which one to read. So the card's answer paragraph now stands down for exactly as long as the
subtitle is carrying **the same sentence**, and comes back the moment it is not.

```
  ---- one voice, one surface ---------------------------------------------
  caption: "It is 4:48 in the afternoon in Tokyo, Addi — today, against your clock."
  card   : ""   (textContent kept: "It is 4:48 in the afternoon in Tokyo, Ad"…)
  -------------------------------------------------------------------------
```

The second line is the whole of the design. `card` is empty because nothing on the glass carries the
words; `textContent` is intact because the paragraph was **hidden, never written**. The card is the
record. Eleven harnesses read `#a-text`, the Scribe quotes it, and a law implemented by emptying it
would have destroyed the thing it was tidying.

The proof is a clock question, chosen deliberately: it answers from a table on this disk, spends no
model and consumes no sources, and still renders a real card and speaks through the real funnel. It is
the cheapest honest way to have one sentence on two surfaces at one instant.

### What could NOT stand down, and why the rule is one child deep

The mandate retires "the quoted-utterance block and the repeated toast". Both turned out to name
something load-bearing, and saying so is part of the work:

**`#a-q` is the antecedent-memory law made visible.** `followup_proof` asserts it three times — *"the
card still quotes them, rewrite or no rewrite"* — because the only way to see that *"and what about
his?"* was resolved against the right question is to read the question the card is quoting. The
antecedent memory is on the DO-NOT-ALTER list. So `#a-q` stays, and the rule reaches `> .a` and
nothing above it: the question is not what is in the speakers.

**"The repeated toast" is this page's own name for `#brain`** — `const toast = layoutMine('brain')` —
the telemetry surface, not a second copy of the answer. There was no duplicate toast to retire.

And the paragraph stands down **only for its own sentence**, which is the clause that keeps the rest
of the deck honest. A capped answer, a plan whose tail is *"and two more steps on the card"*, an error
softened for the ear — all of those are a caption that is deliberately *not* the paragraph, and hiding
the card under them would hide text the voice is pointing at. The harness asserts the inverse directly:
a different line spoken over the same card puts the paragraph straight back.

```js
const same = !!held && capCollapse(line) === held &&
             body.scrollHeight <= body.clientHeight + 1;
```

The second clause is a belt on a brace. `layout_proof` focuses `#a-text` and drives it with a real
Page Down, and a `display:none` element takes neither focus nor a scroll — so a paragraph that is
currently a scroller never yields. A long answer never matches its own spoken form anyway (the voice
is capped at 260 characters), so the guard costs nothing and removes the whole class of collision.

> **Amended by the boot plates, later in this section.** Equality alone missed the one screen every
> session starts with: the autoplay law joins held lines into one breath, so the caption carries
> *salutation + readiness line* while the card holds the salutation alone, and the greeting stood on
> both surfaces. A `startsWith` clause was added — the safe direction — and a `bare` rule for a
> yielded card with nothing left to show. See *The boot ceremony · what the plates caught*.

### The four ways down, and the frame that must not exist

`answerYield()` is called from four places, and the reason is a frame rather than a tidiness:

```
captionShow    the subtitle takes the sentence      -> the card stands down
captionFade    four seconds after his voice ends    -> the card takes it back, same tick
captionClear   a cancelled subtitle                 -> the card takes it back at once
renderAnswer   a new answer under an old caption    -> the decision is re-taken, both ways
```

A missing one of those leaves a blank paragraph with nothing speaking — invisible in a screenshot
taken a second too early, and exactly the kind of defect that ships. `captionFade` gives the
paragraph back inside the same timer callback that drops the `.up` class, so there is never a frame
with the sentence on neither surface.

`renderAnswer` matters in both directions: it releases the card when the new answer has drifted from
the caption still on screen, and it yields again the moment the caption for *this* answer arrives —
whichever of the two lands first.

### Verdicts

```
voice_proof.mjs   VERIFY 162/162 PASS      (was 156/156 — six new checks, headed, out loud)
preflight.py      29 pass, 0 fail, 3 warn  (32 checks; warns are the routine 10, 11, 12)
layout_proof.mjs  VERIFY 150/150 PASS      the focus-and-Page-Down scroller, untouched
followup_proof    VERIFY  47/47  PASS      "the card still quotes them", untouched
clock_proof.mjs   VERIFY  94/94  PASS      chain_proof 78/78 PASS
```

Check 32 — *an answer being read is on one surface, and the card keeps the record*:

```
the card stands down by one CSS rule on one child (display:none), so the yield costs no frame and moves nothing
and answerYield() writes that class and nothing else - no textContent, no innerHTML, no removal: the record survives being hidden
and all four state changes tell the card: raised, faded, cancelled, and a new answer painted under an old subtitle
while the quoted utterance stays on the card: the yield reaches the answer paragraph and nothing above it
```

Nine doctored copies of `index.html` were run through it before it was trusted — the rule deleted; the
paragraph hidden by `opacity:0` instead; a `transition` added to a rule that fires on every sentence
of a streamed read; `answerYield` made to empty the paragraph; the fade, the cancel and the re-take
each removed in turn; the quoted utterance retired; and a rule reaching `#answer.yield #a-q`. All nine
fail, the untouched control passes, and no doctored copy ever reached `viewer/`: the check was pointed
at a temporary `ROOT` instead.

### And one red that was real

`deck_proof` asserts the order sheet **whole** rather than by length, so that a row appearing,
vanishing or moving is a failure with a name in it. The Connectors and World Clock rows made it eight
against ten, and it failed as designed. Updated to the ten, in the reading the sheet has always had:
`connectors` under `google`, because the grant is one reach and the board is every reach; `clock`
under `cast`, because it is the only row that reports a fact about the world rather than this machine;
and `voice` still last, because the boss-only order does not move. `VERIFY 236/238`.

The two remaining are this desktop, not the deck: three consecutive runs each failed a *different*
pair of frame-rate clauses — the face's point count read mid-rebuild, then the bloom's own floor, then
`IDLE GALAXY HOLDS 48.2fps` against a 55 fps floor. Named in the open list rather than explained away.

### The boot ceremony · he reports for duty, once

On the first **healthy** `/health` of a session the butler says one sentence, over about three seconds
of music this machine makes for itself:

> I am ready, Addi. Fully functional — every feature live.

Declarative and unhedged, and the trigger is the reason it is allowed to be. `/health` is the route
that probes piper, the transcriber, the index, the Google grant and the web door, so *"fully
functional"* is read off a reading rather than off optimism — which is why the ceremony rides the
health poll and not `DOMContentLoaded`, a thing that knows nothing about any of them. A butler who
reports for duty with *"I think most things are working"* has told you to go and check.

### Nine oscillators and no asset

```js
put(130.81, 0,    2.90, 0.10, 'sine');      // C3, the room
put(196.00, 0.06, 2.84, 0.09, 'sine');      // G3, under it
[261.63, 329.63, 392.00, 493.88, 523.25]    // C4 E4 G4 B4 C5, walking up
put(659.25, 2.48, 0.62, 0.12, 'sine');      // E5 and B5, the landing
put(987.77, 2.54, 0.56, 0.09, 'sine');
```

Nine notes, **3.10 s**, scheduled on the audio clock ahead of time and stopping themselves. There is
no file: an `.mp3` would have been four lines shorter and a network request, a decode, a cache entry
and a thing to forget to ship — and a sound this page's mute law does not cover.

It plays through the **existing** `toneNote()` on the chime bus, and that is not tidiness either: the
pump already ducks the whole tone bus to a fifth of itself the moment speech starts and lifts it 90 ms
after the queue runs dry. So the jingle opens, the sentence lands on top of it, and the tail comes back
up when he has finished — *"ducked 80% beneath"* with no new code. A private gain node for the flourish
would have been a second thing to duck and a second thing to get wrong. Worst-case sum at any instant
is 0.57 of a bus whose ceiling is 0.15, so the ceremony cannot be louder than the room's own
vocabulary.

### Three ways of being quiet, which are not the same thing

```
a MUTED tab          {fired:1, said:false, spoke:false, jingle:{played:false}}
                     why: "muted: a tab that cannot make a sound holds no ceremony"
                     caption: "Good afternoon, Addi. Galaxy here - 31 notes indexed…"   ← and no more

prefers-reduced      {fired:1, reduced:true, said:true, jingle:{played:false}}
   -motion           jingle.why: "prefers-reduced-motion: the line, without the flourish"
                     caption: "…I am ready, Addi. Fully functional — every feature live."   ← up, legible

no gesture yet       {fired:1, said:true, spoke:false, jingle:{played:true, notes:9, ms:3100}}
                     why: "held for the first gesture, by the autoplay law"
```

A **muted** tab holds no ceremony at all and says so in words. Silence means silence, not "silence
except for the nice bits" — and the sentence is not given to the glass either, because a muted tab is a
harness's tab and nine of them would have booted into a page announcing something none of them asked
about. It still claims the flag, so unmuting mid-answer cannot set the ceremony off.

**Reduced motion** drops the flourish and keeps the sentence. The setting is a request about the
machine's manners, not a request to be told less, so the line goes through the funnel, raises the
caption and fades the quiet way. And the gesture that releases a held line checks the same setting
before it plays the music — one gate is not a law if the other door is open.

**And the common case is neither**: Chrome gives no sound before a gesture, so at boot the ceremony
fires, the jingle is armed, and the sentence is held by the autoplay law that already existed. The
first click releases both, so they arrive together instead of the music playing to an empty room and
the words turning up a minute later. `boot.why` keeps saying *"held for the first gesture"* afterwards
on purpose: it is the record of the ceremony's own moment, and the said-ledger is where you read that
the line was later heard.

### Once per session, and not once per poll

The rail polls `/health` every ten seconds for as long as the tab is open. So *"the first healthy one"*
has to still mean something after the two-hundredth, and the guard is a flag claimed **before** anything
is scheduled — not a timestamp, not a debounce, not a storage key:

```
ONCE PER SESSION, AND NOT ONCE PER POLL: 5 healthy /health readings have now landed, four of them
demanded just now, and the ceremony is still one firing at one timestamp with the same 9 notes
```

Demanded rather than waited for: four forced `__galaxy.brain.refresh()` round trips through the same
door the brain chip uses, because the rail's own poll returns early while a tab is hidden and a proof
that waited on it would be asserting the harness's patience. `voice_proof` asks the same question at
the *end* of an eleven-minute run, minutes and a great many polls later, and pins the timestamp and the
note count as well as the count of firings.

### The four frames

```
boot-01-held.png       the ceremony has fired; the browser will not make a sound yet; the sentence
                       is held and already on the glass
boot-02-sounding.png   600 ms after the first gesture: nine notes playing, the line being read over
                       them, and one text surface carrying it
boot-03-settled.png    the queue is dry and the caption's four seconds have run out: the card has
                       taken its paragraph back, the face is built, the seal reads READY
boot-04-reduced.png    the same moment as 02 on a machine that asked for less motion: the sentence
                       on the glass, nothing sounding
```

### What the plates caught, which no harness had

Frame 02, first cut: the greeting appeared **twice** — in the card and again inside the caption, forty
pixels apart. The one-surface rule compared the two character for character, and at boot the autoplay
law joins every held line into one breath, so the caption carried *salutation + readiness line* while
the card held the salutation alone. Not equal, therefore "different sentences", therefore both stood.
Exactly the duplication the rule exists to prevent, on the one screen every session starts with.

```js
const same = !!held && (spoken === held || spoken.indexOf(held) === 0) &&
             body.scrollHeight <= body.clientHeight + 1;
```

**Starts with** is the only clause added, and it is the safe direction: the voice is reading the whole
of the paragraph and then going on, so nothing is hidden that is not being said. The reverse — a caption
*shorter* than the card — still fails, which is what keeps the 260-character cap, a plan whose tail is
*"and two more steps on the card"* and an error softened for the ear readable while the voice is
pointing at them. A containment test anywhere in the middle was rejected: a three-word paragraph would
vanish behind any long sentence that happened to quote it. Preflight now fails on
`indexOf(held) > …` for that reason.

And the fix exposed the next thing, which is why plates are taken at all: with the paragraph hidden and
no question and no sources to show — the salutation is rendered with none — the card became an **empty
rounded box** hovering above the subtitle. The duplication cured and a piece of furniture left standing
in its place. So a yielded card with nothing left to show now stops drawing its frame:

```css
#answer.yield.bare{background:transparent;border-color:transparent}
#answer.yield.bare::before{opacity:0}
```

`bare` is measured off the card's own children — any visible sibling of the paragraph with text, an
image, a canvas or a button keeps the frame — rather than off the kind of answer, because the card
gains and loses a question, a source row, a thumbnail and a Yes/No pair at four different moments and a
rule that guessed from the route would be wrong at three of them. The element keeps its place in the
flow, so nothing below it moves when the paragraph comes back.

### Verdicts

```
boot_proof.mjs    VERIFY 21/21 PASS        new: three tabs - muted, reduced-motion, plain
voice_proof.mjs   VERIFY 169/169 PASS      the ceremony out loud, and once per session after 11 min
preflight.py      30 pass, 0 fail, 3 warn  (33 checks; warns are the routine 10, 11, 12)
```

Check 33 — *he reports for duty once, with music he makes, and is quiet three ways*:

```
the flag is claimed before the first sound (boot.fired at 254, the jingle at 507), and it guards the whole function - so the two-hundredth healthy poll is as quiet as the second
every note is an oscillator through the existing toneNote() - 9 scheduled frequencies, no fetch, no <audio>, no decode, nothing to ship
and it plays on the bus toneDuck() already lowers, which is the whole of "ducked beneath the voice" - no second gain to get wrong
a muted tab claims the ceremony, says why in words, and returns before the line and the music both
prefers-reduced-motion drops the flourish and keeps the sentence, and the gesture that releases a held line checks the same setting before it plays
and it fires on the first HEALTHY /health - the sentence is read off the probe rather than off DOMContentLoaded, which knows nothing
```

Ten doctored copies of `index.html` were run through it before it was trusted: the once-per-session
guard deleted; the jingle scheduled *before* the flag was claimed; `bootJingle`'s own second refusal
disabled; an asset fetched; a private gain node built; the muted branch stripped of its `return`; the
muted branch stripped of its reason; reduced motion made to drop the sentence with the flourish; the
first gesture made to play the flourish a quiet machine had declined; and the readiness claim made from
`true` instead of from the health poll's verdict. All ten fail, the untouched control passes, and no
doctored copy ever reached `viewer/` — the check was pointed at a temporary `ROOT` instead. The first
run of that negative test caught **two holes in the check itself**: the flag's position was being read
off the muted branch's copy of the same assignment, and one break had been written against an anchor
that appears in `tonesUp()` as well, so it had been mutating the wrong function all along.

### Left open

- **`SPEAKING` is on the glass twice** — `#status-text` above the input and `#seal-text` inside it,
  both fed by `setStatus()`, 46 px apart. Neither carries the *answer*, so it is not the one-surface
  law, and the seal is the state surface the transparency law is written on. It is a legibility
  judgement about two nodes nine harnesses read, so it is named here rather than cut quietly.
- **Stray untextured square sprites** appear in the corners of every headless plate, including the
  earlier `deck-*.png` set. They move between frames, which reads like point sprites drawn without a
  GPU rather than anything in the deck; unconfirmed on the employer's own browser.
