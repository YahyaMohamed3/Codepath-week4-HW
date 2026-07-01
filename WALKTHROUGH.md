# Provenance Guard — Walkthrough Script (2–3 minutes)

*A conversational script for a screen recording. Adjust wording as you go.*

---

**[0:00 — Purpose]**

"Hi — this is Provenance Guard. It's a tool for a creative-writing platform that
helps figure out whether a piece of writing was likely written by a person or
generated with AI. The important thing up front: it does **not** claim to prove
anything. AI detection is genuinely uncertain, and falsely accusing a human
writer is a real harm — so this system is built to be conservative, to show its
uncertainty, and to let creators push back."

**[0:20 — Text submission + three signals]**

"Let me paste a passage in and hit Analyze. Notice the result card breaks the
score down into three independent signals: a Groq language-model semantic
signal, a stylometric signal that looks at sentence-length variation and
vocabulary, and a phrase-pattern signal that flags formulaic phrasing like
'it is important to note' or 'delve into'. You can see each score individually —
nothing is hidden behind a single number."

**[0:45 — Ensemble + uncertainty]**

"Those three combine with fixed weights — fifty, thirty, twenty. But look at
this 'signal disagreement' line. When the signals disagree, the system lowers
its own confidence, and it shows you that instead of hiding it. In this
formulaic example the phrase signal says 'very AI' but the stylometric signal
disagrees, so the disagreement is high and the verdict is honestly 'uncertain'
rather than a confident accusation."

**[1:10 — Label variants]**

"Every result comes with a plain-language label. There are three variants —
likely AI, likely human, and uncertain — plus a special note when the sample is
too short to judge. This human-style passage comes back 'likely human' with high
confidence and the label says clearly it's an estimate, not a guarantee."

**[1:30 — Appeal → under_review]**

"If a creator disagrees, they can appeal using the content ID. I'll add my
reasoning and submit. The status flips to 'under_review' — and critically, the
original classification is never overwritten. The appeal is recorded alongside
it."

**[1:45 — Audit log]**

"Everything lands in a structured audit log. Each entry has the attribution, the
confidence, and a timestamp. Notice we never store the full private text — just a
hash and a short preview. And here's the appeal event sitting right next to the
original classification it's contesting."

**[2:00 — Rate limiting]**

"Over in the terminal, here's the rate-limit demo. Ten submissions per minute
are accepted, and the eleventh gets a clean JSON 429. This runs with a mocked
detector so it doesn't burn API credits, but the limiter config is identical to
the real endpoint."

**[2:15 — Image metadata]**

"The system is also multimodal — but for images it analyzes the *metadata*, not
the pixels. I'll submit metadata that names 'Midjourney'. The generation-tool
signal spikes, but watch — because the other signals don't corroborate strongly,
the conservative gate still keeps it at 'uncertain'. That's the design working."

**[2:30 — Provenance certificate]**

"Finally, creators can earn a provenance certificate. They request a challenge,
get a short phrase, and write a fifty-word process note that includes it plus
draft evidence. On success they get a 'Verified Human Process' badge — shown
*next to* the automated label, never replacing it. And it doesn't erase an
active appeal."

**[2:45 — Dashboard + one decision + one limitation]**

"The dashboard summarizes attribution distribution, appeal rate, and average
confidence. One engineering decision I'll call out: I moved persistence to
SQLite because appeals, analytics, and certificates all need relational state.
And one limitation to be honest about: heavily edited AI text can look human to
these signals — no detector catches that reliably, which is exactly why we lead
with uncertainty and appeals. Thanks for watching."

---

## Recording checklist

**Browser tabs to open first:**
1. `http://127.0.0.1:5000/` — the demo home (text, appeal, image, certificate).
2. `http://127.0.0.1:5000/dashboard` — analytics dashboard.
3. `http://127.0.0.1:5000/log` — audit log JSON (optional, for the log beat).

**Terminal windows to prepare:**
1. One running the app: `python app.py`.
2. One ready to run: `python scripts/rate_limit_demo.py`.
3. (Optional) One ready to run: `python scripts/run_demo.py --reset`.

**Before recording:**
- Add `GROQ_API_KEY` to `.env` if you want the live semantic signal on screen.
- Run `python scripts/reset_demo_db.py` for a clean dashboard, or
  `python scripts/run_demo.py --reset` to pre-populate realistic data.
- Have a clearly AI-like passage and a clearly human passage on your clipboard.
- Confirm `pytest -q` is green so you can show passing tests if asked.
