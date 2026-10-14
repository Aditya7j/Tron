"""Operator 1.3: the parts of the generic door that are pure - no browser, no server.

What a sentence becomes (operator_act.parse_request), what a description becomes
(operator_core.parse_target), what the card says (operator_act.describe), and what the
browser hand will do with a site (operator_browser.resolve). Everything that touches a
page was measured live instead - see the phase report - because a fake DOM can be made to
say anything about a real one.

The cases that matter most are the ones that must NOT become an action: a question, a web
search, "press release", the code editor's own sentences. A door that opens on those is a
door that clicks things nobody asked for.

Run it:  python test_operator_parse.py
Exit status is the number of failures.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))
import operator_act      # noqa: E402
import operator_browser  # noqa: E402
import operator_core     # noqa: E402

FAILURES = []


def check(label, got, want):
    ok = got == want
    print("  %s %s" % ("ok  " if ok else "FAIL", label))
    if not ok:
        print("       got  %r\n       want %r" % (got, want))
        FAILURES.append(label)


def act(sentence):
    p = operator_act.parse_request(sentence)
    return None if p is None else (p["action"], p["target"], p["text"], p["submit"])


print("THE SENTENCE - what becomes an action, and what must not")
check("click", act("click the subscribe button"), ("click", "the subscribe button", "", False))
check("polite click", act("can you click the run button"), ("click", "the run button", "", False))
check("press a control", act("press the play button"), ("click", "the play button", "", False))
check("Hinglish click", act("subscribe button pe click karo"), ("click", "subscribe button", "", False))
check("type, keeping case and punctuation", act("enter asha@example.com in the email box"),
      ("type", "the email box", "asha@example.com", False))
check("type and press enter", act("type kesariya into the search box and press enter"),
      ("type", "the search box", "kesariya", True))
check("type then search", act("type kesariya in the search bar, then search"),
      ("type", "the search bar", "kesariya", True))
check("fill ... with ... and submit", act("fill the customer name field with Asha Verma and submit"),
      ("type", "the customer name field", "Asha Verma", True))
check("search ON THIS PAGE", act("search for lofi beats on this page"),
      ("type", "the search box", "lofi beats", True))
check("select from a dropdown", act("select Banana from the favorite fruit dropdown"),
      ("select", "the favorite fruit dropdown", "Banana", False))
check("scroll to", act("scroll to the history section"), ("scroll", "the history section", "", False))
check("hover over", act("hover over the guido van rossum link"),
      ("hover", "the guido van rossum link", "", False))
check("a promo CODE box is a field, not the editor", act("type 1234 into the promo code box"),
      ("type", "the promo code box", "1234", False))
for sentence in ("what does the subscribe button do", "how do I click the run button",
                 "search for lofi beats", "press release for the new phone", "hit songs of 2024",
                 "type it in", "type the solution into the editor", "put my code in the editor",
                 "play kesariya on youtube", "open youtube", ""):
    check("NOT an action: %r" % sentence, act(sentence), None)

print("THE DESCRIPTION - what the finder looks for")


def target(d):
    t = operator_core.parse_target(d)
    return (t["words"], t["exact"], t["role"], t["ordinal"])


check("kind word comes out of the words", target("the subscribe button"), (["subscribe"], "", "button", 0))
check("prepositions inside a name stay (measured: 'sign in')", target("the sign in button"),
      (["sign", "in"], "", "button", 0))
check("a location phrase is cut whole", target("the sign in button at the top of the page"),
      (["sign", "in"], "", "button", 0))
check("search bar is a field", target("the search bar"), (["search"], "", "field", 0))
check("quoted text is matched exactly", target('the "Sign in" link'), ([], "sign in", "link", 0))
check("curly quotes too", target("the \u201cSign in\u201d link"), ([], "sign in", "link", 0))
check("an ordinal with no kind is a result", target("the first result"), ([], "", "result", 1))
check("the second video", target("the second video"), ([], "", "result", 2))
check("the last one", target("the last link"), ([], "", "link", -1))
check("a section is somewhere to scroll", target("the history section"), (["history"], "", "heading", 0))
check("the kind word that comes last wins", target("the search box button"), (["search"], "", "button", 0))

print("THE CARD - what is said before Yes")
check("click names what the look found",
      operator_act.describe({"action": "click", "target": "the subscribe button", "expect": "Subscribe"}),
      "click 'Subscribe'")
check("type speaks a short text and the Enter",
      operator_act.describe({"action": "type", "target": "the search box", "text": "kesariya",
                             "submit": True, "expect": "search"}),
      "type 'kesariya' into 'search' and press Enter")
check("a long text is 'the text on the card', never read aloud",
      operator_act.describe({"action": "type", "target": "the notes box", "text": "x" * 41}),
      "type the text on the card into the notes box")
check("no expect falls back to the description",
      operator_act.describe({"action": "scroll", "target": "history section"}),
      "scroll to the history section")
check("C++ is a name, not punctuation (measured: it was spoken as 'a button')",
      operator_core.ascii_words("c++"), "c++")

print("THE BROWSER HAND - what a site and a query become")


def resolved(site, query=""):
    kind, url, plan, _layer = operator_browser.resolve(site, query)
    return kind, url


check("youtube with a query", resolved("youtube", "kesariya"), ("youtube", "https://www.youtube.com/"))
check("jiohotstar is hotstar", resolved("jiohotstar.com", "bigg boss"), ("hotstar", "https://www.hotstar.com/in"))
check("any other site WITH a query is searched", resolved("vimeo.com", "lofi"), ("search", "https://vimeo.com"))
check("any site WITHOUT a query is only opened", resolved("example.com"), ("open", "https://example.com"))
check("a bare word gets .com", resolved("wikipedia"), ("open", "https://wikipedia.com"))
check("localhost stays http", resolved("localhost:8080"), ("open", "http://localhost:8080"))
check("javascript: is never opened", resolved("javascript:alert(1)")[0], "")
check("describe() still gives hands.py its two blanks",
      operator_browser.describe("vimeo.com", "lofi"),
      ("vimeo.com", "search it for 'lofi', open the first match, and start it if it is a video"))

print("%d failure(s)" % len(FAILURES))
sys.exit(len(FAILURES))
