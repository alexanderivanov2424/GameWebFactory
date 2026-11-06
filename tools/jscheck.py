"""Rough syntax check for browser JS, since Node isn't allowed: matches brackets, strings,
template literals (with nested ${...}) and comments, and reports the first mismatch by line.
It doesn't understand regex literals or catch undefined names; it catches the typical
broken-edit mistakes (a lost brace, an unterminated string or template).

    python3 -I tools/jscheck.py path/to/file.js [more.js ...]

tools/run_tests.py runs it on every .js file in the app.
"""
import sys


def check(path):
    s = open(path).read()
    i, n = 0, len(s)
    stack = []  # brackets; '`' marks template; '${' marks template expression
    def line(i): return s.count("\n", 0, i) + 1
    while i < n:
        ch = s[i]
        top = stack[-1][0] if stack else None
        if top == '`':
            if ch == '\\': i += 2; continue
            if ch == '`': stack.pop(); i += 1; continue
            if s.startswith('${', i): stack.append(('${', i)); i += 2; continue
            i += 1; continue
        if s.startswith('//', i): i = s.index('\n', i); continue
        if s.startswith('/*', i): i = s.index('*/', i) + 2; continue
        if ch in '"\'':
            j = i + 1
            while s[j] != ch:
                if s[j] == '\\': j += 1
                if s[j] == '\n': return (f"unterminated string line {line(i)}")
                j += 1
            i = j + 1; continue
        if ch == '`': stack.append(('`', i)); i += 1; continue
        if ch in '([{': stack.append((ch, i))
        elif ch in ')]}':
            if not stack: return (f"extra {ch} at line {line(i)}")
            o, j = stack.pop()
            want = {'(': ')', '[': ']', '{': '}', '${': '}'}[o]
            if want != ch: return (f"mismatch: {o} at line {line(j)} closed by {ch} at line {line(i)}")
        i += 1
    return ("ok" if not stack else f"unclosed {stack[-3:]} lines {[line(j) for _, j in stack[-3:]]}")


if __name__ == "__main__":
    failed = False
    for path in sys.argv[1:]:
        result = check(path)
        print(f"{path}: {result}")
        failed |= result != "ok"
    sys.exit(1 if failed else 0)
