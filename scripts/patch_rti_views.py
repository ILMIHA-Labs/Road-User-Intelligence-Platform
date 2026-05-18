from pathlib import Path

p = Path("src/dashboard/app/rti.html")
text = p.read_text(encoding="utf-8")

old = (
    '        <p class="text-[10px] font-bold uppercase tracking-[0.2em] text-on-surface-variant">'
    "Crash characteristics · RTC Form §04</p>\n"
    '        <motion class="grid grid-cols-1 gap-8 xl:grid-cols-12">'
).replace("motion", "div")

new = (
    "      </div>\n\n"
    '      <div id="view-crash-details" class="view-panel space-y-8">\n'
    '        <p class="text-sm text-on-surface-variant">'
    "Vehicles involved, collision type, and substance involvement (RTC Form §04).</p>\n"
    '        <div class="grid grid-cols-1 gap-8 xl:grid-cols-12">'
)

if old not in text:
    raise SystemExit("pattern not found")

text = text.replace(old, new, 1)
text = text.replace(
    '<article class="bg-surface-container-low p-6" id="form-fields-road-user"></article>\n'
    '        <article class="bg-surface-container-low p-6" id="form-fields-crash"></article>',
    '<article class="bg-surface-container-low p-6" id="form-fields-road-user"></article>',
    1,
)

# JS updates
text = text.replace(
    '      sites: "Observation Sites"\n    };',
    '      sites: "Observation Sites",\n'
    '      "crash-details": "Crash Characteristics"\n    };',
)
text = text.replace(
    "      renderRoadUser();\n      renderInjuryOutcome();",
    "      renderRoadUser();\n      renderCrashDetails();\n      renderInjuryOutcome();",
)
if "function renderCrashDetails" not in text:
    text = text.replace(
        "    function renderInjuryOutcome() {",
        """    function renderCrashDetails() {
      const cc = state.data.rtc.crash_characteristics || {};
      renderBarList(document.getElementById("cc-vehicles"),
        (cc.vehicles_involved || []).map((x) => ({ label: x.count, value: x.cases })), "label", "value");
      renderBarList(document.getElementById("cc-collision"),
        (cc.collision_type || []).map((x) => ({ label: x.type, value: x.count })), "label", "value", { dark: true });
      renderBarList(document.getElementById("cc-alcohol"),
        (cc.alcohol_suspected || []).map((x) => ({ label: x.status, value: x.count })), "label", "value");
      renderFormFields(document.getElementById("form-fields-crash"), "s4");
    }

    function renderInjuryOutcome() {""",
    )

# Remove cc rendering from road user (duplicate ids would break - keep in crash-details only)
text = text.replace(
    """      renderBarList(document.getElementById("cc-vehicles"),
        (cc.vehicles_involved || []).map((x) => ({ label: x.count, value: x.cases })), "label", "value");
      renderBarList(document.getElementById("cc-collision"),
        (cc.collision_type || []).map((x) => ({ label: x.type, value: x.count })), "label", "value", { dark: true });
      renderBarList(document.getElementById("cc-alcohol"),
        (cc.alcohol_suspected || []).map((x) => ({ label: x.status, value: x.count })), "label", "value");
      renderFormFields(document.getElementById("form-fields-road-user"), "s3");
      renderFormFields(document.getElementById("form-fields-crash"), "s4");""",
    '      renderFormFields(document.getElementById("form-fields-road-user"), "s3");',
)

text = text.replace(
    "      const cc = state.data.rtc.crash_characteristics || {};\n      ",
    "",
)

# Banner in renderAll
if "data-banner" in text and "getElementById(\"data-banner\")" not in text:
    text = text.replace(
        "      document.getElementById(\"meta-scope\").textContent =",
        """      const banner = document.getElementById("data-banner");
      const note = state.data.rtc._analytics_note;
      if (note) {
        banner.textContent = note;
        banner.classList.remove("hidden");
      }
      document.getElementById("meta-scope").textContent =""",
    )
    text = text.replace(
        "      const note = state.data.rtc._analytics_note;\n      if (note) {\n"
        '        document.getElementById("data-note").textContent = "RTC aggregates illustrative";\n'
        '        document.getElementById("data-note").classList.remove("hidden");\n'
        "      }\n",
        '      document.getElementById("data-note").textContent = "RTC + traffic snapshot";\n'
        '      document.getElementById("data-note").classList.remove("hidden");\n',
    )

p.write_text(text, encoding="utf-8")
print("patched")
