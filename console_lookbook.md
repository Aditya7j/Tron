# The Console — Lookbook

What the Console Constitution asked for, what the deck actually does, and the measurement
behind each claim. Every number here was read off this machine on 25 September 2026; none of
it is typed from the specification. Where a claim is a *measurement* the harness and line are
named, so anything in this document can be re-run rather than believed.

Machine: Windows 11, Chrome on the real GPU, `python server.py` on 127.0.0.1:4700 serving
only `viewer/`. Run logs for this date, in the project root: `_pre.out` (preflight),
`_conv.out`, `_deck.out`, `_voice.out`, `_layout.out`, `_desk.out`, `_tools.out`,
`_focus.out`. Each is the stdout of the harness of the same name, and every harness can be
re-run by name.

Sections 1–9 were written first; **sections 10–16 were added the same day**, after the worlds,
the Mind, the deep field, the spoken dial and the Open Ear landed. Where those parts falsified
a sentence in 1–9 the sentence was **rewritten from a new measurement** rather than left
standing, and the rewrite says what it replaced.

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

Every harness in the matrix, run **solo on a quiet machine**, on 25 September 2026:

```
preflight.py            14 pass, 0 fail, 3 warn
conversation_proof.mjs  VERIFY 67/67 PASS
deck_proof.mjs          VERIFY 173/173 PASS      (idle 59.2 fps with textures, nebula, ear open)
voice_proof.mjs         VERIFY 123/123 PASS
layout_proof.mjs        VERIFY 43/43 PASS
desk_proof.mjs          37 checks, 0 failed
tools_live.mjs          VERIFY 50/50 PASS
focus_probe.mjs         63 checks, 0 failed  ·  PROBE 25/25 PASS
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

**What §§10–16 do not claim.** The plates were captured headless on this GPU, so they are what
the renderer draws and not what a projector would. No claim is made here about how the voices
*sound* — only that the recast landed, was announced in the voice it named, and was put back.
The Open Ear's recognition is Chrome's, which is why the seal says `browser`: nothing in §14
claims local recognition, and the page cannot say the word. One explicit click per session
remains the privacy contract, by design.
