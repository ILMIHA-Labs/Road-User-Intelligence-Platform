"""Remove obsolete motion-tag cleanup from renderNotes in rti_module.js."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "src" / "dashboard" / "app" / "rti_module.js"
lines = p.read_text(encoding="utf-8").splitlines()
out = []
i = 0
while i < len(lines):
    line = lines[i]
    if ".replace(/<\\/?motion[^>]*>/g" in line:
        out.append("      `;")
        i += 1
        while i < len(lines) and (
            "covEl.innerHTML = covEl.innerHTML" in lines[i]
            or lines[i].strip().startswith(".replace(")
        ):
            i += 1
        continue
    out.append(line)
    i += 1

text = "\n".join(out) + "\n"
if text != p.read_text(encoding="utf-8"):
    p.write_text(text, encoding="utf-8")
    print("Fixed", p)
else:
    print("No changes needed")
