"""Build standalone rti.html and remove RTI integration from index.html."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/dashboard/app"
INDEX = APP / "index.html"
RTI = APP / "rti.html"
INC = APP / "rti_views.inc.html"

HEAD = """<!DOCTYPE html>
<html class="light" lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <base href="/dashboard/" />
  <title>Mobility Intelligence | RTI Surveillance</title>
  <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@100;200;300;400;500;600;700;800;900&display=swap" rel="stylesheet" />
  <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet" />
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            primary: "#000000", secondary: "#5f5e5e", surface: "#f9f9f9",
            "surface-container": "#eeeeee", "surface-container-low": "#f3f3f4",
            "surface-container-high": "#e8e8e8", "surface-container-lowest": "#ffffff",
            "on-surface": "#1a1c1c", "on-surface-variant": "#474747",
            outline: "#777777", "outline-variant": "#c6c6c6",
            error: "#ba1a1a", "error-container": "#ffdad6", "on-primary": "#e2e2e2"
          },
          fontFamily: { sans: ["Inter", "sans-serif"] },
          borderRadius: { DEFAULT: "0.125rem", lg: "0.25rem", xl: "0.5rem" }
        }
      }
    };
  </script>
  <style>
    body { font-family: "Inter", sans-serif; }
    .material-symbols-outlined { font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24; }
    .metric-card { min-height: 10rem; }
    .bar-fill { transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1); }
    .speed-bar-fill { transition: height 0.6s cubic-bezier(0.4, 0, 0.2, 1); }
  </style>
</head>
<body class="bg-surface text-on-surface">
  <aside id="sidebar" class="fixed left-0 top-0 z-40 flex h-screen w-64 -translate-x-full flex-col border-r border-black/5 bg-gray-50 p-6 transition-transform md:translate-x-0">
    <div class="mb-10 pt-8">
      <h2 class="text-xs font-bold uppercase tracking-[0.25em] text-black">Mobility Intelligence</h2>
      <p class="mt-2 text-[10px] uppercase tracking-[0.2em] text-on-surface-variant">RTI · RTC Surveillance</p>
    </div>
    <nav class="flex-1 space-y-2">
      <button data-view-button="rti-overview" class="nav-btn flex w-full items-center gap-3 rounded-sm bg-white px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.2em] text-black shadow-sm">
        <span class="material-symbols-outlined text-lg">public</span> Overview
      </button>
      <button data-view-button="rti-timing" class="nav-btn flex w-full items-center gap-3 px-4 py-3 text-left text-[11px] uppercase tracking-[0.2em] text-on-surface-variant">
        <span class="material-symbols-outlined text-lg">schedule</span> Event Timing
      </button>
      <button data-view-button="rti-location" class="nav-btn flex w-full items-center gap-3 px-4 py-3 text-left text-[11px] uppercase tracking-[0.2em] text-on-surface-variant">
        <span class="material-symbols-outlined text-lg">map</span> Crash Location
      </button>
      <button data-view-button="rti-road-user" class="nav-btn flex w-full items-center gap-3 px-4 py-3 text-left text-[11px] uppercase tracking-[0.2em] text-on-surface-variant">
        <span class="material-symbols-outlined text-lg">groups</span> Road User
      </button>
      <button data-view-button="rti-crash" class="nav-btn flex w-full items-center gap-3 px-4 py-3 text-left text-[11px] uppercase tracking-[0.2em] text-on-surface-variant">
        <span class="material-symbols-outlined text-lg">car_crash</span> Crash Details
      </button>
      <button data-view-button="rti-injury" class="nav-btn flex w-full items-center gap-3 px-4 py-3 text-left text-[11px] uppercase tracking-[0.2em] text-on-surface-variant">
        <span class="material-symbols-outlined text-lg">medical_services</span> Injury &amp; Outcome
      </button>
      <button data-view-button="rti-notes" class="nav-btn flex w-full items-center gap-3 px-4 py-3 text-left text-[11px] uppercase tracking-[0.2em] text-on-surface-variant">
        <span class="material-symbols-outlined text-lg">description</span> Notes
      </button>
    </nav>
    <a href="index.html" class="mt-6 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-on-surface-variant underline">
      <span class="material-symbols-outlined text-base">arrow_back</span> Traffic Console
    </a>
  </aside>
  <div id="sidebar-backdrop" class="fixed inset-0 z-30 hidden bg-black/40 md:hidden"></div>
  <main class="min-h-screen md:ml-64">
    <header class="sticky top-0 z-30 flex items-center justify-between border-b border-black/5 bg-white/85 px-6 py-4 backdrop-blur-xl md:px-8">
      <div class="flex min-w-0 items-center gap-3">
        <button id="sidebar-toggle" type="button" class="shrink-0 rounded-sm border border-black/10 p-2 md:hidden" aria-label="Menu">
          <span class="material-symbols-outlined text-xl">menu</span>
        </button>
        <div class="min-w-0">
          <p class="text-[10px] uppercase tracking-[0.3em] text-on-surface-variant">roaduserintelligence.com/rti</p>
          <h1 id="page-heading" class="text-2xl font-black tracking-tighter md:text-3xl">Mobility Intelligence Overview</h1>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <p id="last-updated" class="hidden text-[10px] uppercase tracking-[0.2em] text-on-surface-variant md:block">Syncing…</p>
        <button id="refresh-button" class="rounded-sm bg-primary px-4 py-2 text-[10px] font-bold uppercase tracking-[0.2em] text-on-primary">Refresh</button>
      </div>
    </header>
    <section class="mx-auto max-w-[1440px] p-6 md:p-8">
"""

FOOT = """
    </section>
  </main>
  <script src="rti_module.js"></script>
  <script>
    const state = { activeView: "rti-overview", rti: null, isRefreshing: false };
    RtiDashboard.init(state);

    function setSidebarOpen(open) {
      document.getElementById("sidebar")?.classList.toggle("-translate-x-full", !open);
      document.getElementById("sidebar")?.classList.toggle("translate-x-0", open);
      document.getElementById("sidebar-backdrop")?.classList.toggle("hidden", !open);
    }

    function setActiveView(viewName) {
      state.activeView = viewName;
      document.querySelectorAll("[data-view]").forEach((el) => {
        el.classList.toggle("hidden", el.dataset.view !== viewName);
      });
      document.querySelectorAll("[data-view-button]").forEach((btn) => {
        const on = btn.dataset.viewButton === viewName;
        btn.classList.toggle("bg-white", on);
        btn.classList.toggle("shadow-sm", on);
        btn.classList.toggle("font-bold", on);
        btn.classList.toggle("text-black", on);
        btn.classList.toggle("text-on-surface-variant", !on);
      });
      const heading = document.getElementById("page-heading");
      if (heading) heading.textContent = RtiDashboard.getTitle(viewName);
    }

    async function switchView(viewName) {
      setActiveView(viewName);
      setSidebarOpen(false);
      if (!state.rti) await loadData();
      RtiDashboard.render(viewName);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    async function loadData() {
      if (state.isRefreshing) return;
      state.isRefreshing = true;
      const btn = document.getElementById("refresh-button");
      const stamp = document.getElementById("last-updated");
      btn.disabled = true;
      btn.textContent = "Syncing";
      try {
        state.rti = await RtiDashboard.loadSnapshot();
        RtiDashboard.render(state.activeView);
        if (stamp) {
          stamp.classList.remove("hidden");
          stamp.textContent = "Updated " + new Date().toLocaleString();
        }
      } catch (e) {
        console.error(e);
        if (stamp) stamp.textContent = "Sync failed";
        RtiDashboard.render(state.activeView);
      } finally {
        state.isRefreshing = false;
        btn.disabled = false;
        btn.textContent = "Refresh";
      }
    }

    document.querySelectorAll("[data-view-button]").forEach((b) => {
      b.addEventListener("click", () => void switchView(b.dataset.viewButton));
    });
    document.getElementById("refresh-button").addEventListener("click", () => loadData());
    document.getElementById("sidebar-toggle")?.addEventListener("click", () => {
      const sb = document.getElementById("sidebar");
      setSidebarOpen(sb?.classList.contains("-translate-x-full"));
    });
    document.getElementById("sidebar-backdrop")?.addEventListener("click", () => setSidebarOpen(false));

    setActiveView("rti-overview");
    loadData();
  </script>
</body>
</html>
"""

def build_rti_html():
    views = INC.read_text(encoding="utf-8")
    views = views.replace(
        'data-view="rti-overview" class="hidden space-y-8"',
        'data-view="rti-overview" class="space-y-8"',
    )
    html = HEAD.replace("<motion.div", "<motion.div").replace("</motion>", "</div>")
    # fix accidental motion tags in HEAD template
    html = HEAD.replace("    <motion.div class=\"mb-10 pt-8\">", "    <div class=\"mb-10 pt-8\">")
    html = html.replace("    </div>\n    <nav", "    </div>\n    <nav", 1)  # noop if already div
    if "<motion" in html:
        html = html.replace("<motion.div", "<div").replace("</motion>", "</div>")
    RTI.write_text(html + views + FOOT, encoding="utf-8")
    print("Wrote", RTI)


def deintegrate_index():
    html = INDEX.read_text(encoding="utf-8")
    start = html.find("      <!-- ═══ RTI / RTC SURVEILLANCE VIEWS ═══ -->")
    end = html.find("      <!-- ═══ / RTI VIEWS ═══ -->")
    if start != -1 and end != -1:
        end = html.find("\n", end) + 1
        html = html[:start] + html[end:]

    nav_start = html.find('      <p class="pt-4 text-[9px] font-bold uppercase tracking-[0.25em] text-on-surface-variant">Mobility Intel · RTI</p>')
    if nav_start != -1:
        nav_end = html.find("    </nav>", nav_start)
        html = html[:nav_start] + html[nav_end:]

    html = html.replace('  <base href="/dashboard/" />\n', "")
    html = html.replace('  <script src="rti_module.js"></script>\n', "")
    html = html.replace("      rti: null,\n", "")
    html = html.replace(
        "    if (typeof RtiDashboard !== \"undefined\") {\n      RtiDashboard.init(state);\n    }\n\n",
        "",
    )
    html = html.replace(
        "          typeof RtiDashboard !== \"undefined\" ? RtiDashboard.loadSnapshot().catch(() => null) : Promise.resolve(null)\n",
        "          Promise.resolve(null)\n",
    )
    html = html.replace("        state.rti = rtiSnapshot;\n", "")

    # Remove RTI from destructuring - change to 8 items
    html = html.replace(
        "const [summary, byCamera, violations, crossings, recent, speedDist, cameraConfigs, liveFeeds, rtiSnapshot] = await Promise.all([",
        "const [summary, byCamera, violations, crossings, recent, speedDist, cameraConfigs, liveFeeds] = await Promise.all([",
    )

    # Remove catch block RTI reload
    import re
    html = re.sub(
        r"\n        if \(typeof RtiDashboard !== \"undefined\" && !state\.rti\) \{[^}]+\}[^}]+\}[^}]+\}\n",
        "\n",
        html,
        count=1,
    )

    # Simplify updatePageChrome - remove RTI bits
    old_chrome = """    function updatePageChrome(viewName) {
      const isRti = typeof RtiDashboard !== \"undefined\" && RtiDashboard.isRtiView(viewName);
      const heading = document.getElementById(\"page-heading\");
      if (heading) {
        heading.textContent = isRti
          ? RtiDashboard.getTitle(viewName)
          : \"Traffic Operations Dashboard\";
      }
      const filters = document.getElementById(\"platform-filters\");
      const narrative = document.getElementById(\"platform-narrative\");
      const scope = document.getElementById(\"active-scope\");
      const rtiBanner = document.getElementById(\"rti-data-banner\");
      if (filters) filters.classList.toggle(\"hidden\", isRti);
      if (narrative) narrative.classList.toggle(\"hidden\", isRti);
      if (scope) scope.classList.toggle(\"hidden\", isRti);
      if (rtiBanner && !isRti) rtiBanner.classList.add(\"hidden\");
    }

    function setSidebarOpen(open) {
      const sidebar = document.getElementById(\"sidebar\");
      const backdrop = document.getElementById(\"sidebar-backdrop\");
      if (!sidebar || !backdrop) return;
      sidebar.classList.toggle(\"-translate-x-full\", !open);
      sidebar.classList.toggle(\"translate-x-0\", open);
      backdrop.classList.toggle(\"hidden\", !open);
    }

    async function ensureRtiData() {
      if (state.rti || typeof RtiDashboard === \"undefined\") return state.rti;
      try {
        state.rti = await RtiDashboard.loadSnapshot();
      } catch (error) {
        console.error(\"RTI snapshot load failed\", error);
      }
      return state.rti;
    }
"""
    new_chrome = """    function setSidebarOpen(open) {
      const sidebar = document.getElementById(\"sidebar\");
      const backdrop = document.getElementById(\"sidebar-backdrop\");
      if (!sidebar || !backdrop) return;
      sidebar.classList.toggle(\"-translate-x-full\", !open);
      sidebar.classList.toggle(\"translate-x-0\", open);
      backdrop.classList.toggle(\"hidden\", !open);
    }
"""
    if old_chrome in html:
        html = html.replace(old_chrome, new_chrome)
        html = html.replace("      updatePageChrome(viewName);\n", "")

    html = html.replace(
        """      } else if (typeof RtiDashboard !== \"undefined\" && RtiDashboard.isRtiView(state.activeView)) {
        RtiDashboard.render(state.activeView);
      } else if""",
        "      } else if",
    )

    html = html.replace(
        """    async function switchView(viewName) {
      setActiveView(viewName);
      setSidebarOpen(false);
      if (typeof RtiDashboard !== \"undefined\" && RtiDashboard.isRtiView(viewName)) {
        await ensureRtiData();
      }
      renderActiveView();
      document.getElementById(\"view-anchor\")?.scrollIntoView({ behavior: \"smooth\", block: \"start\" });
      if (viewName === \"violations\" && !state.isRefreshing) {
        loadViolationLog();
      }
    }""",
        """    function switchView(viewName) {
      setActiveView(viewName);
      setSidebarOpen(false);
      renderActiveView();
      if (viewName === \"violations\" && !state.isRefreshing) {
        loadViolationLog();
      }
    }""",
    )

    html = html.replace('<motion.div id="page-heading"', '<h1 id="page-heading"').replace(
        'id="page-heading" class="text-2xl', 'id="page-heading" class="text-2xl'
    )
    # remove view-anchor if present
    html = html.replace('      <div id="view-anchor"></motion>\n', "")
    html = html.replace('      <div id="view-anchor"></div>\n', "")

    INDEX.write_text(html, encoding="utf-8")
    print("De-integrated", INDEX)


if __name__ == "__main__":
    build_rti_html()
    deintegrate_index()
