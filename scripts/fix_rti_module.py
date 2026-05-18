from pathlib import Path

p = Path("src/dashboard/app/rti_module.js")
lines = p.read_text(encoding="utf-8").splitlines()
out = []
skip_until_close = False
for i, line in enumerate(lines):
    if "`.replace(/<motion " in line or "`.replace(/</motion>" in line:
        continue
    if "`.replace(/</?motion" in line:
        out.append("      `;")
        skip_until_close = True
        continue
    if skip_until_close:
        if line.strip() == "}" and "covEl" not in lines[i - 1] if i else True:
            skip_until_close = False
        if ".replace(" in line or "covEl.innerHTML = covEl" in line:
            continue
        if skip_until_close and line.strip() == "}":
            skip_until_close = False
            out.append(line)
        continue
    if skip_until_close and "const tbody" in line:
        skip_until_close = False
        out.append(line)
        continue
    if not skip_until_close:
        out.append(line)

p.write_text("\n".join(out) + "\n", encoding="utf-8")
text = p.read_text(encoding="utf-8")
print("ok, lines", len(text.splitlines()))
