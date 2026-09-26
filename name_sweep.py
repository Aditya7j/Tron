"""NAME SWEEP - where a name actually lives in the Python, as against where it is discussed.

Written for persona_proof, which has to prove that a retired name survives only in the
places the machine LISTENS at, never in a place it SPEAKS from. A grep cannot make that
distinction and neither can a line-based filter, for two reasons this file exists to handle:

  - Most mentions of the old name in server.py are prose. They are comments and docstrings
    explaining the vocative peel, and they are the reason the peel is correct; a rename that
    deleted them would make the code harder to maintain in exchange for a cleaner grep.
  - The one mention that matters most is NOT distinguishable from a docstring by eye:
    FORCE_WEB_RE is a triple-quoted r-string. A line-based sweep either skips it with the
    docstrings, and misses the live one, or keeps every docstring and drowns.

So the instrument is Python's own parser. Every string constant in the module is collected,
then the ones that are prose by position - module, class and function docstrings, and bare
expression-strings used as commentary - are removed. What remains is the name as the program
uses it: list members, regex alternations, lines it would say.

Harness helper, not a hand: it has no registry entry, takes no parameters from the wire, and
reads only files named on its own command line.

    python name_sweep.py jarvis server.py focus.py hands.py
    -> {"jarvis": {"server.py": [{"line": 1029, "text": "jarvis"}, ...], ...}}
"""
import ast
import json
import sys


def prose_strings(tree):
    """The ids of every string node that sits where a comment would sit."""
    prose = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False) is not None and node.body:
                prose.add(id(node.body[0].value))
        body = getattr(node, 'body', None)
        for stmt in body if isinstance(body, list) else []:
            if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)):
                prose.add(id(stmt.value))
    return prose


def sweep(path, needle):
    """Live string constants in `path` that mention `needle`, lowest line first."""
    with open(path, encoding='utf-8') as fh:
        tree = ast.parse(fh.read(), filename=path)
    prose = prose_strings(tree)
    found = [
        {'line': node.lineno, 'text': node.value.strip()[:90]}
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and needle in node.value.lower() and id(node) not in prose
    ]
    return sorted(found, key=lambda row: row['line'])


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[-1].strip())
        return 2
    needle = argv[1].lower()
    out = {}
    for path in argv[2:]:
        try:
            out[path] = sweep(path, needle)
        except (OSError, SyntaxError) as exc:
            out[path] = {'error': '%s: %s' % (type(exc).__name__, exc)}
    print(json.dumps({needle: out}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
