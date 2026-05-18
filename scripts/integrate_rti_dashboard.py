"""Integrate RTI views into main dashboard index.html."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "src/dashboard/app/index.html"
INC = ROOT / "src/dashboard/app/rti_views.inc.html"

NAV_OLD = """      <a href="/dashboard/rti.html" class="nav-btn flex w-full items-center gap-3 px-4 py-3 text-left text-[11px] uppercase tracking-[0.2em] text-on-surface-variant hover:bg-white/60">
        <span class="material-symbols-outlined text-lg">public</span> RTI Surveillance
      </a>
    </nav>"""

NAV_NEW = """      <p class="pt-4 text-[9px] font-bold uppercase tracking-[0.25em] text-on-surface-variant">Mobility Intel · RTI</p>
      <button data-view-button="rti-overview" class="nav-btn flex w-full items-center gap-3 px-4 py-3 text-left text-[11px] uppercase tracking-[0.2em] text-on-surface-variant">
        <span class="material-symbols-outlined text-lg">public</span> RTI Overview
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
    </nav>"""

def main():
    html = INDEX.read_text(encoding="utf-8")
    if NAV_OLD not in html:
        if "data-view-button=\"rti-overview\"" in html:
            print("Nav already integrated")
        else:
            raise SystemExit("Nav anchor not found")
    else:
        html = html.replace(NAV_OLD, NAV_NEW)

    html = html.replace(
        '<h1 class="text-2xl font-black tracking-tighter md:text-3xl">Traffic Operations Dashboard</h1>',
        '<h1 id="page-heading" class="text-2xl font-black tracking-tighter md:text-3xl">Traffic Operations Dashboard</h1>',
    )

    if "rti-overview-view" not in html:
        inc = INC.read_text(encoding="utf-8")
        marker = "      <!-- ═══ / VIOLATIONS PAGE ═══ -->\n    </section>\n  </main>"
        if marker not in html:
            marker = "    </section>\n  </main>"
        html = html.replace(marker, inc + "\n" + marker, 1)

    if "rti_module.js" not in html:
        html = html.replace(
            "  <script>\n    const VIOLATION_META",
            '  <script src="rti_module.js"></script>\n  <script>\n    const VIOLATION_META',
        )

    if "rti: null" not in html:
        html = html.replace(
            "      isRefreshing: false,\n    };",
            "      isRefreshing: false,\n      rti: null,\n    };",
        )

    if "RtiDashboard.init" not in html:
        html = html.replace(
            "    const LIVE_REFRESH_INTERVAL_MS = 5000;",
            "    const LIVE_REFRESH_INTERVAL_MS = 5000;\n    RtiDashboard.init(state);",
        )

    # setActiveView - update page heading and filter visibility
    if "updatePageChrome" not in html:
        old_set = """    function setActiveView(viewName) {
      state.activeView = viewName;
      document.querySelectorAll("[data-view]").forEach((section) => {
        section.classList.toggle("hidden", section.dataset.view !== viewName);
      });

      // camera-detail is a sub-view of cameras — highlight the Cameras nav button
      const navHighlight = viewName === "camera-detail" ? "cameras" : viewName;
      document.querySelectorAll("[data-view-button]").forEach((button) => {
        const isActive = button.dataset.viewButton === navHighlight;
        button.classList.toggle("bg-white", isActive);
        button.classList.toggle("shadow-sm", isActive);
        button.classList.toggle("font-bold", isActive);
        button.classList.toggle("text-black", isActive);
        button.classList.toggle("text-on-surface-variant", !isActive);
      });
    }"""
        new_set = """    function updatePageChrome(viewName) {
      const isRti = typeof RtiDashboard !== "undefined" && RtiDashboard.isRtiView(viewName);
      const heading = document.getElementById("page-heading");
      if (heading) {
        heading.textContent = isRti
          ? RtiDashboard.getTitle(viewName)
          : "Traffic Operations Dashboard";
      }
      const filters = document.getElementById("platform-filters");
      const narrative = document.getElementById("platform-narrative");
      const scope = document.getElementById("active-scope");
      if (filters) filters.classList.toggle("hidden", isRti);
      if (narrative) narrative.classList.toggle("hidden", isRti);
      if (scope) scope.classList.toggle("hidden", isRti);
    }

    function setActiveView(viewName) {
      state.activeView = viewName;
      document.querySelectorAll("[data-view]").forEach((section) => {
        section.classList.toggle("hidden", section.dataset.view !== viewName);
      });

      const navHighlight = viewName === "camera-detail" ? "cameras" : viewName;
      document.querySelectorAll("[data-view-button]").forEach((button) => {
        const isActive = button.dataset.viewButton === navHighlight;
        button.classList.toggle("bg-white", isActive);
        button.classList.toggle("shadow-sm", isActive);
        button.classList.toggle("font-bold", isActive);
        button.classList.toggle("text-black", isActive);
        button.classList.toggle("text-on-surface-variant", !isActive);
      });
      updatePageChrome(viewName);
    }"""
        if old_set in html:
            html = html.replace(old_set, new_set)

    # renderActiveView - add RTI branches
    if 'state.activeView === "rti-overview"' not in html:
        html = html.replace(
            "      } else if (state.activeView === \"camera-detail\" && state.currentCameraDetailId) {",
            """      } else if (typeof RtiDashboard !== "undefined" && RtiDashboard.isRtiView(state.activeView)) {
        RtiDashboard.render(state.activeView);
      } else if (state.activeView === "camera-detail" && state.currentCameraDetailId) {""",
        )

    # refreshDashboard - load RTI
    if "RtiDashboard.loadSnapshot" not in html:
        html = html.replace(
            """        const [summary, byCamera, violations, crossings, recent, speedDist, cameraConfigs, liveFeeds] = await Promise.all([
          loadJson(`/analytics/summary${buildQuery(filterParams)}`),
          loadJson(`/analytics/by-camera${buildQuery({ start: filterParams.start, end: filterParams.end })}`),
          loadJson(`/analytics/violations${buildQuery(filterParams)}`),
          loadJson(`/analytics/crossings${buildQuery(filterParams)}`),
          loadJson(`/events/recent${buildQuery({ ...filterParams, limit: 20 })}`),
          loadJson(`/analytics/speed-distribution${buildQuery(filterParams)}`),
          loadJson(`/cameras/config`),
          loadJson(`/live/cameras`)
        ]);""",
            """        const [summary, byCamera, violations, crossings, recent, speedDist, cameraConfigs, liveFeeds, rtiSnapshot] = await Promise.all([
          loadJson(`/analytics/summary${buildQuery(filterParams)}`),
          loadJson(`/analytics/by-camera${buildQuery({ start: filterParams.start, end: filterParams.end })}`),
          loadJson(`/analytics/violations${buildQuery(filterParams)}`),
          loadJson(`/analytics/crossings${buildQuery(filterParams)}`),
          loadJson(`/events/recent${buildQuery({ ...filterParams, limit: 20 })}`),
          loadJson(`/analytics/speed-distribution${buildQuery(filterParams)}`),
          loadJson(`/cameras/config`),
          loadJson(`/live/cameras`),
          typeof RtiDashboard !== "undefined" ? RtiDashboard.loadSnapshot().catch(() => null) : Promise.resolve(null)
        ]);""",
        )
        html = html.replace(
            "        state.liveFeeds = Object.fromEntries((liveFeeds.cameras || []).map((camera) => [camera.camera_id, camera]));",
            """        state.liveFeeds = Object.fromEntries((liveFeeds.cameras || []).map((camera) => [camera.camera_id, camera]));
        state.rti = rtiSnapshot;""",
        )

    # Add ids to filter section and narrative
    if 'id="platform-filters"' not in html:
        html = html.replace(
            '<section class="mb-8 grid grid-cols-1 gap-4 bg-surface-container-low p-4',
            '<section id="platform-filters" class="mb-8 grid grid-cols-1 gap-4 bg-surface-container-low p-4',
        )
    if 'id="platform-narrative"' not in html:
        html = html.replace(
            '<motion class="mb-10 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">',
            '<div id="platform-narrative" class="mb-10 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">',
        ).replace(
            "Operational Narrative</h2>",
            "Operational Narrative</h2>",
        )
    # fix narrative div if motion was introduced - read and fix
    html = html.replace("<motion id=\"platform-narrative\"", '<div id="platform-narrative"')
    html = html.replace('id="platform-narrative" class="mb-10', 'id="platform-narrative" class="mb-10')
    # close narrative - find duplicate
    html = html.replace(
        '<motion class="mb-10 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">',
        '<div id="platform-narrative" class="mb-10 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">',
    )

    INDEX.write_text(html, encoding="utf-8")
    print("Integrated into", INDEX)

if __name__ == "__main__":
    main()
