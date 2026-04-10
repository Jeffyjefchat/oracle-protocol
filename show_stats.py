"""Quick stats for Oracle Protocol."""
import os, re

src_dir = os.path.join(os.path.dirname(__file__), "oracle_memory")
test_dir = os.path.join(os.path.dirname(__file__), "tests")

src_files = [f for f in os.listdir(src_dir) if f.endswith(".py")]
modules = []
total_src_lines = 0
total_classes = 0
total_functions = 0

for f in sorted(src_files):
    path = os.path.join(src_dir, f)
    with open(path, encoding="utf-8") as fh:
        content = fh.read()
        lines = content.count("\n") + 1
        cls = len(re.findall(r"^class ", content, re.MULTILINE))
        fns = len(re.findall(r"^\s*def ", content, re.MULTILINE))
        modules.append((f, lines, cls, fns))
        total_src_lines += lines
        total_classes += cls
        total_functions += fns

test_files = [f for f in os.listdir(test_dir) if f.endswith(".py")]
total_test_lines = 0
total_tests = 0
for f in test_files:
    path = os.path.join(test_dir, f)
    with open(path, encoding="utf-8") as fh:
        content = fh.read()
        total_test_lines += content.count("\n") + 1
        total_tests += len(re.findall(r"^def test_", content, re.MULTILINE))

print("=" * 60)
print("  ORACLE PROTOCOL v2.0.0 — STATISTICS")
print("=" * 60)
print()
print("SOURCE CODE")
print("  Modules:             %d" % len(src_files))
print("  Lines of code:       %s" % f"{total_src_lines:,}")
print("  Classes:             %d" % total_classes)
print("  Functions/methods:   %d" % total_functions)
print()
print("TESTS")
print("  Test files:          %d" % len(test_files))
print("  Test functions:      %d" % total_tests)
print("  Test lines:          %s" % f"{total_test_lines:,}")
print()
print("MODULE BREAKDOWN")
header = "  %-30s %6s %8s %10s" % ("Module", "Lines", "Classes", "Functions")
print(header)
print("  " + "-" * 56)
for name, lines, cls, fns in modules:
    print("  %-30s %6d %8d %10d" % (name, lines, cls, fns))
print("  " + "-" * 56)
print("  %-30s %6d %8d %10d" % ("TOTAL", total_src_lines, total_classes, total_functions))
print()
print("DEPENDENCIES:  0 required (stdlib only)")
print("PYTHON:        3.9+")
print("LICENSE:       MIT")
