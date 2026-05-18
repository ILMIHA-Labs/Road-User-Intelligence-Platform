/**
 * RTI / RTC surveillance visualizations (integrated main dashboard).
 */
(function (global) {
  const RTI_VIEW_IDS = new Set([
    "rti-overview",
    "rti-timing",
    "rti-location",
    "rti-road-user",
    "rti-crash",
    "rti-injury",
    "rti-notes",
  ]);

  const VIEW_TITLES = {
    "rti-overview": "Mobility Intelligence Overview",
    "rti-timing": "Event Timing",
    "rti-location": "Crash Location",
    "rti-road-user": "Road User Characteristics",
    "rti-crash": "Crash Characteristics",
    "rti-injury": "Injury & Clinical Outcome",
    "rti-notes": "Notes & Clinical Narrative",
  };

  let stateRef = null;

  function formatCompact(n) {
    if (n == null || Number.isNaN(n)) return "—";
    const abs = Math.abs(n);
    if (abs >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
    if (abs >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
    if (abs >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
    return Number(n).toLocaleString();
  }

  function pct(part, total) {
    return total > 0 ? Math.round((part / total) * 100) : 0;
  }

  function normalizePayload(raw) {
    if (!raw) return { traffic: {}, rtc: {}, form: { sections: [] } };
    return {
      traffic: raw.traffic || raw,
      rtc: raw.rtc_analytics || {},
      form: raw.rtc_form || { sections: [] },
      source: raw.source || "https://roaduserintelligence.com/rti",
    };
  }

  function renderBarList(container, items, labelKey, valueKey, opts = {}) {
    if (!container) return;
    container.innerHTML = "";
    if (!items?.length) {
      container.innerHTML = '<p class="text-sm text-on-surface-variant">No data available.</p>';
      return;
    }
    const max = opts.max ?? Math.max(...items.map((i) => i[valueKey]), 1);
    const dark = !!opts.dark;
    items.forEach((item) => {
      const val = item[valueKey];
      const width = (val / max) * 100;
      const label = item[labelKey];
      const sub = opts.subKey ? item[opts.subKey] : null;
      const row = document.createElement("div");
      row.className = dark ? "bg-white/5 p-3" : "bg-surface-container-low p-3";
      row.innerHTML = `
        <div class="mb-2 flex justify-between gap-2 text-[10px] uppercase tracking-[0.15em] ${dark ? "text-white" : ""}">
          <span class="min-w-0 truncate">${label}${sub ? ` <span class="opacity-50">· ${sub}</span>` : ""}</span>
          <span class="shrink-0 font-black tabular-nums">${opts.pct ? `${val}%` : formatCompact(val)}</span>
        </div>
        <div class="relative h-1.5 overflow-hidden ${dark ? "bg-white/10" : "bg-surface-container"}">
          <div class="bar-fill absolute left-0 top-0 h-full ${opts.barClass || (dark ? "bg-white" : "bg-black")}" style="width:${width}%"></div>
        </div>
      `;
      container.appendChild(row);
    });
  }

  function renderMetricRow(container, cards) {
    if (!container) return;
    container.innerHTML = cards
      .map(
        (c) => `
      <article class="metric-card flex flex-col justify-between bg-surface-container-lowest p-6">
        <p class="text-[10px] font-bold uppercase tracking-[0.2em] text-on-surface-variant">${c.label}</p>
        <div>
          <p class="text-4xl font-black tracking-tighter ${c.error ? "text-error" : ""}">${c.value}</p>
          <p class="mt-2 text-xs text-on-surface-variant">${c.hint || ""}</p>
        </div>
      </article>
    `,
      )
      .join("");
  }

  function renderFormFields(container, sectionId) {
    const data = stateRef?.rti;
    if (!container || !data) return;
    const sec = data.form.sections?.find((s) => s.id === sectionId);
    if (!sec) {
      container.innerHTML = "";
      return;
    }
    const title = (sec.title || "").replace(/&amp;/g, "&");
    const opts = Object.entries(sec.options || {})
      .map(([k, v]) => `<p class="mt-2"><span class="font-bold">${k}:</span> ${v.map((o) => o.label).join(" · ")}</p>`)
      .join("");
    container.innerHTML = `
      <p class="text-[10px] font-bold uppercase tracking-[0.2em] text-on-surface-variant">RTC form schema · ${title}</p>
      <p class="mt-2 text-sm text-on-surface-variant">${(sec.fields || []).join(" · ")}</p>
      ${opts ? `<div class="mt-3 text-xs text-on-surface-variant">${opts}</div>` : ""}
      <p class="mt-3 text-[10px] text-on-surface-variant">
        <a class="underline" href="${data.form.form_url || "https://roaduserintelligence.com/RTC_Surveillance_Form_v5.html"}" target="_blank" rel="noopener">RTC Surveillance Form</a>
        · <a class="underline" href="${data.source}" target="_blank" rel="noopener">roaduserintelligence.com/rti</a>
      </p>
    `;
  }

  function renderOverview() {
    const t = stateRef.rti.traffic;
    const hc = t.helmet_compliance || {};
    const mc = t.vehicle_mix?.find((v) => v.type === "motorcycle");
    renderMetricRow(document.getElementById("rti-overview-metrics"), [
      { label: "Helmet Compliance", value: `${hc.rate ?? "—"}%`, hint: "Tamale observation network" },
      { label: "Motorcycles", value: formatCompact(mc?.count), hint: "Detection volume" },
      { label: "With Helmet", value: formatCompact(hc.withHelmet), hint: "Observed riders" },
      { label: "Without Helmet", value: formatCompact(hc.withoutHelmet), hint: "Observed riders", error: true },
      { label: "Sites", value: String(t.sites_detail?.length || 10), hint: "Observation locations" },
    ]);
    renderBarList(
      document.getElementById("rti-composition-bars"),
      (t.road_user_composition || []).map((x) => ({ label: x.name, value: x.value })),
      "label",
      "value",
      { pct: true },
    );
    const total = (hc.withHelmet || 0) + (hc.withoutHelmet || 0);
    renderBarList(
      document.getElementById("rti-helmet-bars"),
      [
        { label: "With helmet", value: hc.withHelmet },
        { label: "Without helmet", value: hc.withoutHelmet },
      ],
      "label",
      "value",
      { dark: true, max: total },
    );
    const totalEl = document.getElementById("rti-helmet-total");
    if (totalEl) totalEl.textContent = `${formatCompact(total)} riders · ${hc.rate}% compliance`;

    const grid = document.getElementById("rti-sites-grid");
    if (grid) {
      grid.innerHTML = "";
      (t.sites_detail || []).forEach((site) => {
        const card = document.createElement("article");
        card.className = "bg-surface-container-lowest p-5";
        card.innerHTML = `
          <p class="text-[10px] font-bold uppercase tracking-[0.2em] text-on-surface-variant">${site.id}</p>
          <h4 class="mt-1 text-sm font-bold leading-snug">${site.location}</h4>
          <p class="mt-3 text-3xl font-black ${site.helmetRate < 10 ? "text-error" : ""}">${site.helmetRate}%</p>
          <p class="text-[10px] uppercase tracking-[0.2em] text-on-surface-variant">helmet · ${site.status}</p>
        `;
        grid.appendChild(card);
      });
    }

    renderBarList(
      document.getElementById("rti-hotspots-bars"),
      (t.hotspots || []).map((h) => ({ label: h.location, value: h.riskScore, sub: h.primaryIssue })),
      "label",
      "value",
      { barClass: "bg-error" },
    );
  }

  function renderTiming() {
    const rtc = stateRef.rti.rtc.event_timing || {};
    const t = stateRef.rti.traffic;
    renderMetricRow(document.getElementById("rti-timing-metrics"), [
      { label: "Median Onset", value: `${rtc.prehospital_delay_median_mins ?? "—"} min`, hint: "Crash to first contact" },
      { label: "Peak Crash Window", value: "16–19", hint: "Highest RTC volume" },
      {
        label: "Peak Traffic",
        value: t.hourly_activity?.length
          ? t.hourly_activity.reduce((a, b) => ((b.volume || 0) > (a?.volume || 0) ? b : a)).hour
          : "—",
        hint: "Live RTI window",
      },
    ]);
    renderBarList(
      document.getElementById("rti-crash-by-hour"),
      (rtc.crash_by_hour || []).map((x) => ({ label: x.hour, value: x.count })),
      "label",
      "value",
    );
    renderBarList(
      document.getElementById("rti-onset-care"),
      (rtc.onset_of_care || []).map((x) => ({ label: x.bucket, value: x.count })),
      "label",
      "value",
      { dark: true },
    );
    const chart = document.getElementById("rti-hourly-chart");
    const labels = document.getElementById("rti-hourly-labels");
    if (chart && labels) {
      chart.innerHTML = "";
      labels.innerHTML = "";
      const hours = t.hourly_activity || [];
      const maxV = Math.max(...hours.map((h) => h.volume || 0), 1);
      hours.forEach((h) => {
        const col = document.createElement("div");
        col.className = "flex shrink-0 flex-col items-center justify-end";
        col.style.width = "28px";
        col.style.height = "9rem";
        col.innerHTML = `<div class="speed-bar-fill w-4 bg-black" style="height:${((h.volume || 0) / maxV) * 100}%;min-height:2px"></div>`;
        chart.appendChild(col);
        const lbl = document.createElement("div");
        lbl.className = "shrink-0 text-center text-[8px] uppercase text-on-surface-variant";
        lbl.style.width = "28px";
        lbl.textContent = (h.hour || "").replace(":00", "");
        labels.appendChild(lbl);
      });
    }
    renderFormFields(document.getElementById("rti-form-timing"), "s1");
  }

  function renderLocation() {
    const loc = stateRef.rti.rtc.crash_location || {};
    renderBarList(
      document.getElementById("rti-road-type"),
      (loc.road_type || []).map((x) => ({ label: x.type, value: x.count })),
      "label",
      "value",
    );
    renderBarList(
      document.getElementById("rti-districts"),
      (loc.top_districts || []).map((x) => ({ label: x.location, value: x.count })),
      "label",
      "value",
    );
    renderBarList(
      document.getElementById("rti-lighting"),
      (loc.lighting || []).map((x) => ({ label: x.condition, value: x.count })),
      "label",
      "value",
      { dark: true },
    );
    renderBarList(
      document.getElementById("rti-weather"),
      (loc.weather || []).map((x) => ({ label: x.condition, value: x.count })),
      "label",
      "value",
    );
    renderFormFields(document.getElementById("rti-form-location"), "s2");
  }

  function renderRoadUser() {
    const ru = stateRef.rti.rtc.road_user_crash || {};
    renderBarList(
      document.getElementById("rti-user-type"),
      (ru.user_type || []).map((x) => ({ label: x.type, value: x.count, sub: x.icd })),
      "label",
      "value",
    );
    renderBarList(
      document.getElementById("rti-sex"),
      (ru.sex || []).map((x) => ({ label: x.sex, value: x.count })),
      "label",
      "value",
      { dark: true },
    );
    renderBarList(
      document.getElementById("rti-age"),
      (ru.age_group || []).map((x) => ({ label: x.group, value: x.count })),
      "label",
      "value",
    );
    renderBarList(
      document.getElementById("rti-counterpart"),
      (ru.counterpart_vehicle || []).map((x) => ({ label: x.vehicle, value: x.count })),
      "label",
      "value",
    );
    renderFormFields(document.getElementById("rti-form-road-user"), "s3");
  }

  function renderCrash() {
    const cc = stateRef.rti.rtc.crash_characteristics || {};
    renderBarList(
      document.getElementById("rti-vehicles"),
      (cc.vehicles_involved || []).map((x) => ({ label: x.count, value: x.cases })),
      "label",
      "value",
    );
    renderBarList(
      document.getElementById("rti-collision"),
      (cc.collision_type || []).map((x) => ({ label: x.type, value: x.count })),
      "label",
      "value",
      { dark: true },
    );
    renderBarList(
      document.getElementById("rti-alcohol"),
      (cc.alcohol_suspected || []).map((x) => ({ label: x.status, value: x.count })),
      "label",
      "value",
    );
    renderFormFields(document.getElementById("rti-form-crash"), "s4");
  }

  function renderInjury() {
    const inj = stateRef.rti.rtc.injury_outcome || {};
    renderBarList(
      document.getElementById("rti-gcs"),
      (inj.gcs_distribution || []).map((x) => ({ label: x.category, value: x.count })),
      "label",
      "value",
    );
    renderBarList(
      document.getElementById("rti-iss"),
      (inj.iss_distribution || []).map((x) => ({ label: x.band, value: x.count })),
      "label",
      "value",
    );
    renderBarList(
      document.getElementById("rti-anatomical"),
      (inj.anatomical_site || []).map((x) => ({ label: x.site, value: x.count })),
      "label",
      "value",
      { dark: true },
    );
    renderBarList(
      document.getElementById("rti-injury-type"),
      (inj.injury_type || []).map((x) => ({ label: x.type, value: x.count })),
      "label",
      "value",
    );
    renderBarList(
      document.getElementById("rti-interventions"),
      (inj.interventions || []).map((x) => ({ label: x.intervention, value: x.pct })),
      "label",
      "value",
      { pct: true },
    );
    renderBarList(
      document.getElementById("rti-discharge"),
      (inj.discharge_outcome || []).map((x) => ({ label: x.outcome, value: x.count })),
      "label",
      "value",
      { dark: true },
    );
    const flow = document.getElementById("rti-severity-flow");
    if (flow) {
      flow.innerHTML = "";
      (inj.severity_flow || []).forEach((f) => {
        const card = document.createElement("article");
        card.className = "bg-surface-container-low p-4";
        card.innerHTML = `<p class="text-[10px] uppercase tracking-[0.15em] text-on-surface-variant">${f.initial} → ${f.outcome}</p><p class="mt-2 text-2xl font-black">${f.count}</p>`;
        flow.appendChild(card);
      });
    }
    renderFormFields(document.getElementById("rti-form-injury"), "s5");
  }

  function renderNotes() {
    const n = stateRef.rti.rtc.notes || {};
    const cov = n.total_records ? pct(n.records_with_notes, n.total_records) : 0;
    renderMetricRow(document.getElementById("rti-notes-metrics"), [
      { label: "Total Records", value: String(n.total_records || "—"), hint: "RTC surveillance" },
      { label: "With Notes", value: String(n.records_with_notes || "—"), hint: "Clinical narrative" },
      { label: "Coverage", value: `${cov}%`, hint: "Documented cases" },
    ]);
    renderBarList(
      document.getElementById("rti-themes"),
      (n.common_themes || []).map((x) => ({ label: x.theme, value: x.mentions })),
      "label",
      "value",
    );
    const covEl = document.getElementById("rti-notes-coverage");
    if (covEl) {
      covEl.innerHTML = `
        <p class="text-5xl font-black">${cov}%</p>
        <p class="mt-2 text-sm text-white/60">${n.records_with_notes} of ${n.total_records} records include clinical notes.</p>
        <div class="mt-6 h-1.5 bg-white/10"><div class="bar-fill h-full bg-white" style="width:${cov}%"></div></div>
      `;
    }
    const tbody = document.getElementById("rti-notes-table");
    if (tbody) {
      tbody.innerHTML = "";
      (n.sample_notes || []).forEach((row, idx) => {
        const tr = document.createElement("tr");
        tr.className = idx % 2 ? "bg-surface-container-low/50" : "";
        tr.innerHTML = `
          <td class="py-4 pr-4 font-mono text-xs">${row.record_id}</td>
          <td class="py-4 pr-4 text-xs">${row.facility}</td>
          <td class="py-4 pr-4 text-sm leading-6">${row.excerpt}</td>
          <td class="py-4 text-xs text-on-surface-variant">${row.reviewed_by}<br>${row.review_date}</td>
        `;
        tbody.appendChild(tr);
      });
    }
    renderFormFields(document.getElementById("rti-form-notes"), "s6");
  }

  const RTI_EMPTY =
    '<p class="rounded-sm bg-surface-container-low p-4 text-sm text-on-surface-variant">RTI data is loading or unavailable. Click <strong>Refresh Data</strong> or open <a class="underline" href="/dashboard/">/dashboard/</a> from the API server.</p>';

  function showRtiEmptyState(view) {
    const root = document.querySelector(`[data-view="${view}"]`);
    if (!root) return;
    let slot = root.querySelector("[id$='-metrics']") || root.querySelector("article, .grid");
    if (!slot) slot = root;
    if (!slot.querySelector(".rti-empty-msg")) {
      const msg = document.createElement("div");
      msg.className = "rti-empty-msg mb-6";
      msg.innerHTML = RTI_EMPTY;
      root.insertBefore(msg, root.firstChild);
    }
  }

  function clearRtiEmptyState(view) {
    document.querySelector(`[data-view="${view}"]`)?.querySelector(".rti-empty-msg")?.remove();
  }

  function updateBanner() {
    const banner = document.getElementById("rti-data-banner");
    if (!banner || !stateRef?.rti) return;
    const note = stateRef.rti.rtc._analytics_note;
    if (note) {
      banner.textContent = note;
      banner.classList.remove("hidden");
    } else {
      banner.classList.add("hidden");
    }
  }

  const RENDERERS = {
    "rti-overview": renderOverview,
    "rti-timing": renderTiming,
    "rti-location": renderLocation,
    "rti-road-user": renderRoadUser,
    "rti-crash": renderCrash,
    "rti-injury": renderInjury,
    "rti-notes": renderNotes,
  };

  global.RtiDashboard = {
    VIEW_TITLES,
    RTI_VIEW_IDS,
    init(state) {
      stateRef = state;
      if (!stateRef.rti) stateRef.rti = null;
    },
    isRtiView(view) {
      return RTI_VIEW_IDS.has(view);
    },
    getTitle(view) {
      return VIEW_TITLES[view] || "Mobility Intelligence";
    },
    normalizePayload,
    async loadSnapshot() {
      try {
        const res = await fetch(`/rti/snapshot?t=${Date.now()}`);
        if (res.ok) return normalizePayload(await res.json());
      } catch (_) {
        /* fall through to static snapshot */
      }
      const fallback = await fetch(`rti_data.json?t=${Date.now()}`);
      if (!fallback.ok) throw new Error("RTI snapshot unavailable");
      return normalizePayload(await fallback.json());
    },
    render(view) {
      if (!stateRef?.rti) {
        showRtiEmptyState(view);
        return;
      }
      clearRtiEmptyState(view);
      const fn = RENDERERS[view];
      if (fn) fn();
      updateBanner();
    },
    renderAll() {
      if (!stateRef?.rti) return;
      Object.keys(RENDERERS).forEach((v) => RENDERERS[v]());
      updateBanner();
    },
  };
})(window);
