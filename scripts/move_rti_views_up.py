"""Move RTI view blocks directly under #view-anchor for visible layout."""
from pathlib import Path

index = Path(__file__).resolve().parents[1] / "src/dashboard/app/index.html"
html = index.read_text(encoding="utf-8")
start = html.index("      <!-- ═══ RTI / RTC SURVEILLANCE VIEWS ═══ -->")
end = html.index("      <!-- ═══ / RTI VIEWS ═══ -->") + len("      <!-- ═══ / RTI VIEWS ═══ -->\n")
block = html[start:end]
html = html[:start] + html[end:]
marker = '<div id="view-anchor"></motion>'
if marker not in html:
    marker = '<div id="view-anchor"></div>'
insert_at = html.index(marker) + len(marker) + 1
html = html[:insert_at] + block + html[insert_at:]
index.write_text(html, encoding="utf-8")
print("Moved RTI views after #view-anchor")
