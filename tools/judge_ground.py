"""THE GROUNDING JUDGE. Reads turns on stdin as JSON, writes verdicts on stdout as JSON.

    python tools/judge_ground.py < turns.json

WHY THIS EXISTS AT ALL. server.grounding_class() decides an answer's grounding class from the
instruments: a card on the table, a protected route, fetched sources, a passage that opened over
threshold. Where the class turns on what the SENTENCE CLAIMS it returns "" and says nothing,
deliberately, because a regex over English prose deciding whether a sentence was a refusal is a
classifier that guesses - and a classifier that guesses would launder exactly the hallucinations
the audit exists to catch. Those turns need a reader. This is the reader.

WHY IT DOES NOT GO THROUGH call_model(). Two reasons, and both are disqualifying:

  THE COSTUME. call_model() runs wear_persona() on every message list it is handed - one place,
  every call, by design - so a judge routed through it is given the butler's name, his abilities
  and his manners, and is then asked to rule on whether the butler overstepped them. It would
  answer in character, address the reader as sir, and decline to find fault with itself.

  THE METER. call_model() completes the open turn's budget plan and files a model call against
  it. A judge running inside the session it is auditing would show up in that session's own
  numbers as an extra prompt nobody assembled.

So this file takes the same three-way provider dispatch call_model() takes, and nothing else.

WHY IT IS NOT GIVEN A FREE HAND. The prompt carries the mechanical facts for the turn - what was
cited, what was fetched, whether a retrieval door opened, whether the conversation summary was in
the prompt - and says the judge may not contradict them. The judge's job is to read one English
sentence and say what it stands on. It is not asked to re-run the retrieval in its head, and a
verdict is only accepted by the caller when it names one of the six declared classes.

NO CREDENTIAL CAN REACH THE OUTPUT. It loads config.json for the provider dispatch, the same as
every other caller, and writes back nothing but a class, a verdict word and a sentence of reason.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402  - after the path insert, on purpose

CLASSES = ("notes", "web", "persona", "state", "refusal", "chain")

RUBRIC = """You are auditing one turn of a butler assistant's conversation with its employer.
Name what the assistant's answer STANDS ON. Choose exactly one:

  notes    - it reports what the employer's own documents say.
  web      - it reports what a fetched web page says.
  persona  - it speaks about itself, its abilities or its manners, OR it is the assistant's
             own composition: a greeting, a translation, a summary in its own words, a
             pleasantry. Nothing is being reported from anywhere; the assistant wrote it.
  state    - it reports this machine's own live condition, INCLUDING what was said earlier
             in this same conversation.
  refusal  - it declines, and claims nothing while declining.
  chain    - it proposes one or more actions for approval.

THE MECHANICAL FACTS about this turn, measured by the server. You may not contradict them:
%s

THE EMPLOYER ASKED: %s

THE ASSISTANT ANSWERED: %s

Reply with ONE line and nothing else, in this exact shape:

  CLASS|grounded|one short clause of reason

Use "ungrounded" in place of "grounded" ONLY if the answer asserts a specific fact that none
of the mechanical facts above could have supplied - an invented passage, an invented source, an
invented account, an invented earlier turn. An answer that is the assistant's own words, or that
honestly says it does not hold something, is grounded."""


def provider_call(cfg, prompt):
    """The prompt to whichever brain config.json names. No persona, no budget, no turn."""
    which = server.provider_of(cfg)
    messages = [{"role": "user", "content": prompt}]
    if which == "openrouter":
        return server.call_openrouter(cfg, messages, None)
    if which == "openai":
        return server.call_openai(cfg, messages, None)
    return server.call_bedrock(cfg, messages, None)


def main():
    turns = json.loads(sys.stdin.read() or "[]")
    cfg = server.load_config()[0]
    out = []
    for turn in turns:
        prompt = RUBRIC % (json.dumps(turn.get("facts") or {}, indent=2),
                           turn.get("asked") or "", turn.get("answer") or "")
        said, error = provider_call(cfg, prompt)
        # FIRST NON-EMPTY LINE. The rubric asks for one line; a model that adds a preamble
        # gets read for the line that matches the shape rather than refused, because the
        # caller is asserting on the CLASS and a chatty judge is not a failed audit.
        pick = ""
        for line in str(said or "").splitlines():
            line = line.strip().lstrip("-* ").strip()
            if "|" in line and line.split("|")[0].strip().strip("`").lower() in CLASSES:
                pick = line
                break
        out.append({"n": turn.get("n"), "verdict": (pick or str(said or "").strip())[:300],
                    "error": str(error or "")[:200]})
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    main()
