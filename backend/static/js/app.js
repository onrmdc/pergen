    const API = window.location.origin;
    const $ = (id) => document.getElementById(id);
    var globalDeviceErrorsList = [];
    var globalDeviceEvents = [];
    var MAX_DEVICE_EVENTS = 300;
    var globalCommandLogs = [];
    var MAX_COMMAND_LOGS = 80;
    /** Device-level error only: top-level error, or all commands failed. Single-command failures are logged as warning and not returned here. */
    function getDeviceResultError(res) {
      if (!res) return null;
      if (res.error) return res.error;
      var cmds = res.commands || [];
      if (!cmds.length) return null;
      var failed = 0;
      var firstCmdError = null;
      for (var i = 0; i < cmds.length; i++) {
        if (cmds[i].error) { failed++; if (!firstCmdError) firstCmdError = cmds[i].error; }
      }
      if (failed === 0) return null;
      if (failed === cmds.length) return firstCmdError;
      return null;
    }
    /** Log per-command failures as warning events (e.g. BGP not available on this device). */
    function logDeviceCommandWarnings(res) {
      if (!res || !Array.isArray(res.commands)) return;
      var host = (res.hostname || res.ip || "?").trim();
      res.commands.forEach(function(c) {
        if (c.error && c.command_id) addDeviceEvent("warn", host, "Could not get response for " + (c.command_id || "command") + ": " + (c.error || "").trim());
      });
    }
    var headerProgressDetail = null;
    function closeHeaderProgressDetailPopup() {
      var pop = $("headerProgressDetailPopup");
      if (pop) {
        pop.classList.remove("open");
        pop.setAttribute("aria-hidden", "true");
      }
    }
    function renderHeaderProgressDetailBody() {
      var body = $("headerProgressDetailBody");
      var title = $("headerProgressDetailTitle");
      if (!body || !headerProgressDetail || !headerProgressDetail.devices) return;
      if (title) title.textContent = "Device progress (" + headerProgressDetail.devices.length + ")";
      var rows = headerProgressDetail.devices.map(function(d) {
        var phCls = d.phase === "queued" ? "ph-queued" : d.phase === "running" ? "ph-running" : d.phase === "done" ? "ph-done" : "ph-error";
        var phLabel = d.phase === "queued" ? "Queued" : d.phase === "running" ? "Running" : d.phase === "done" ? "Done" : "Error";
        return "<tr><td>" + escapeHtml(d.hostname) + "</td><td>" + escapeHtml(d.ip) + "</td><td class=\"" + phCls + "\">" + phLabel + "</td><td>" + escapeHtml(d.detail) + "</td></tr>";
      }).join("");
      body.innerHTML = "<table><thead><tr><th>Hostname</th><th>IP</th><th>Phase</th><th>Detail</th></tr></thead><tbody>" + rows + "</tbody></table>";
    }
    function openHeaderProgressDetailPopup() {
      if (!headerProgressDetail) return;
      renderHeaderProgressDetailBody();
      var pop = $("headerProgressDetailPopup");
      if (pop) {
        pop.classList.add("open");
        pop.setAttribute("aria-hidden", "false");
      }
    }
    function initHeaderProgressDetail(devList) {
      headerProgressDetail = {
        devices: devList.map(function(d) {
          var h = (d.hostname || "").trim();
          var ip = (d.ip || "").trim();
          var key = h || ip || "?";
          return { key: key, hostname: h || "—", ip: ip || "—", phase: "queued", detail: "" };
        })
      };
    }
    function updateHeaderProgressDetailPhase(key, phase, detail) {
      if (!headerProgressDetail || !headerProgressDetail.devices) return;
      for (var i = 0; i < headerProgressDetail.devices.length; i++) {
        if (headerProgressDetail.devices[i].key === key) {
          headerProgressDetail.devices[i].phase = phase;
          headerProgressDetail.devices[i].detail = detail || "";
          break;
        }
      }
      var pop = $("headerProgressDetailPopup");
      if (pop && pop.classList.contains("open")) renderHeaderProgressDetailBody();
    }
    function initHeaderProgressDetailUi() {
      var wrap = $("headerProgressWrap");
      var pop = $("headerProgressDetailPopup");
      var closeBtn = $("headerProgressDetailClose");
      if (wrap) {
        wrap.addEventListener("click", function(e) {
          e.stopPropagation();
          if (!headerProgressDetail) return;
          if (wrap.style.display === "none") return;
          openHeaderProgressDetailPopup();
        });
      }
      if (closeBtn) closeBtn.addEventListener("click", function(e) { e.stopPropagation(); closeHeaderProgressDetailPopup(); });
      document.addEventListener("click", function(e) {
        if (!pop || !pop.classList.contains("open")) return;
        if (pop.contains(e.target)) return;
        if (wrap && wrap.contains(e.target)) return;
        closeHeaderProgressDetailPopup();
      });
    }
    function showHeaderProgress(total) {
      var wrap = $("headerProgressWrap"); var text = $("headerProgressText"); var bar = $("headerProgressBar");
      if (wrap) {
        wrap.style.display = "flex";
        if (headerProgressDetail) {
          wrap.classList.add("header-progress-clickable");
          wrap.title = "Click for per-device status";
        } else {
          wrap.classList.remove("header-progress-clickable");
          wrap.title = "";
        }
      }
      if (text) text.textContent = "0/" + total + " devices";
      if (bar) bar.style.width = "0%";
    }
    function updateHeaderProgress(done, total) {
      var text = $("headerProgressText"); var bar = $("headerProgressBar");
      if (text) text.textContent = done + "/" + total + " devices";
      if (bar) bar.style.width = (total ? (done / total * 100) : 0) + "%";
    }
    function hideHeaderProgress() {
      var wrap = $("headerProgressWrap");
      if (wrap) {
        wrap.style.display = "none";
        wrap.classList.remove("header-progress-clickable");
        wrap.title = "";
      }
      headerProgressDetail = null;
      closeHeaderProgressDetailPopup();
    }
    function addDeviceEvent(type, hostname, message) {
      var now = new Date();
      var time = now.toLocaleString(undefined, { dateStyle: "short", timeStyle: "medium" });
      globalDeviceEvents.push({ type: type, hostname: hostname || "?", message: message || "", time: time, ts: now.getTime() });
      if (globalDeviceEvents.length > MAX_DEVICE_EVENTS) globalDeviceEvents = globalDeviceEvents.slice(-MAX_DEVICE_EVENTS);
      var successCount = globalDeviceEvents.filter(function(e) { return e.type === "success"; }).length;
      var warnCount = globalDeviceEvents.filter(function(e) { return e.type === "warn"; }).length;
      var failCount = globalDeviceEvents.filter(function(e) { return e.type === "fail"; }).length;
      var successEl = $("eventSuccessCount");
      var warnEl = $("eventWarnCount");
      var failEl = $("eventFailCount");
      var successBtn = $("eventSuccessBtn");
      var warnBtn = $("eventWarnBtn");
      var failBtn = $("eventFailBtn");
      if (successEl) successEl.textContent = successCount;
      if (successBtn) successBtn.style.display = successCount > 0 ? "inline-flex" : "none";
      if (warnEl) warnEl.textContent = warnCount;
      if (warnBtn) warnBtn.style.display = warnCount > 0 ? "inline-flex" : "none";
      if (failEl) failEl.textContent = failCount;
      if (failBtn) failBtn.style.display = failCount > 0 ? "inline-flex" : "none";
    }
    function setGlobalDeviceErrors(errors) {
      globalDeviceErrorsList = Array.isArray(errors) ? errors : [];
      var failEl = $("eventFailCount");
      var failBtn = $("eventFailBtn");
      if (!failBtn) return;
      var failCount = globalDeviceEvents.filter(function(e) { return e.type === "fail"; }).length;
      var totalFail = failCount || globalDeviceErrorsList.length;
      if (failEl) failEl.textContent = totalFail;
      failBtn.style.display = totalFail > 0 ? "inline-flex" : "none";
    }
    function renderEventPopupList(listEl, titleEl, events, titleLabel) {
      if (!listEl) return;
      var sorted = events.slice().sort(function(a, b) { return (b.ts || 0) - (a.ts || 0); });
      if (titleEl) titleEl.textContent = titleLabel + " (" + sorted.length + ")";
      listEl.innerHTML = sorted.map(function(e) {
        var cls = e.type === "success" ? "event-success" : e.type === "warn" ? "event-warn" : "event-fail";
        var timeStr = e.time ? "<span class=\"event-time\">" + escapeHtml(e.time) + "</span> " : "";
        return "<li class=\"" + cls + "\">" + timeStr + "<strong>" + escapeHtml(e.hostname || "?") + "</strong>: " + escapeHtml(e.message || e.error || "") + "</li>";
      }).join("");
    }
    function initErrorCountBtn() {
      var successBtn = $("eventSuccessBtn");
      var warnBtn = $("eventWarnBtn");
      var failBtn = $("eventFailBtn");
      var successPopup = $("eventSuccessPopup");
      var warnPopup = $("eventWarnPopup");
      var failPopup = $("eventFailPopup");
      var successList = $("eventSuccessPopupList");
      var warnList = $("eventWarnPopupList");
      var failList = $("eventFailPopupList");
      var successTitle = $("eventSuccessPopupTitle");
      var warnTitle = $("eventWarnPopupTitle");
      var failTitle = $("eventFailPopupTitle");
      var successClose = $("eventSuccessPopupClose");
      var warnClose = $("eventWarnPopupClose");
      var failClose = $("eventFailPopupClose");
      if (successBtn && successPopup) {
        successBtn.addEventListener("click", function() {
          var events = globalDeviceEvents.filter(function(e) { return e.type === "success"; });
          if (events.length === 0) return;
          renderEventPopupList(successList, successTitle, events, "Successful Operations");
          successPopup.classList.add("open");
          successPopup.setAttribute("aria-hidden", "false");
        });
        function closeSuccess() { successPopup.classList.remove("open"); successPopup.setAttribute("aria-hidden", "true"); }
        if (successClose) successClose.addEventListener("click", closeSuccess);
        document.addEventListener("click", function(e) {
          if (successPopup.classList.contains("open") && !successPopup.contains(e.target) && e.target !== successBtn) closeSuccess();
        });
      }
      if (warnBtn && warnPopup) {
        warnBtn.addEventListener("click", function() {
          var events = globalDeviceEvents.filter(function(e) { return e.type === "warn"; });
          if (events.length === 0) return;
          renderEventPopupList(warnList, warnTitle, events, "Warnings");
          warnPopup.classList.add("open");
          warnPopup.setAttribute("aria-hidden", "false");
        });
        function closeWarn() { warnPopup.classList.remove("open"); warnPopup.setAttribute("aria-hidden", "true"); }
        if (warnClose) warnClose.addEventListener("click", closeWarn);
        document.addEventListener("click", function(e) {
          if (warnPopup.classList.contains("open") && !warnPopup.contains(e.target) && e.target !== warnBtn) closeWarn();
        });
      }
      if (failBtn && failPopup) {
        failBtn.addEventListener("click", function() {
          var events = globalDeviceEvents.filter(function(e) { return e.type === "fail"; });
          var list = events.slice();
          if (list.length === 0 && globalDeviceErrorsList.length > 0) {
            list = globalDeviceErrorsList.map(function(e) { return { type: "fail", hostname: e.hostname || "?", message: e.error || "", time: "", ts: 0 }; });
          }
          if (list.length === 0) return;
          renderEventPopupList(failList, failTitle, list, "Errors");
          failPopup.classList.add("open");
          failPopup.setAttribute("aria-hidden", "false");
        });
        function closeFail() { failPopup.classList.remove("open"); failPopup.setAttribute("aria-hidden", "true"); }
        if (failClose) failClose.addEventListener("click", closeFail);
        document.addEventListener("click", function(e) {
          if (failPopup.classList.contains("open") && !failPopup.contains(e.target) && e.target !== failBtn) closeFail();
        });
      }
    }
    const fabricSel = $("fabric"), siteSel = $("site"), hallSel = $("hall"), roleSel = $("role");
    const deviceList = $("deviceList"), pingBtn = $("pingBtn"), pingStatus = $("pingStatus");
    let devicesCache = [];
    /** Ping results: index -> reachable (1:1 with device order) */
    let pingResultsByIndex = [];
    /** run_id from last Run PRE (for Run POST) */
    let lastRunId = null;
    /** Last run device_results for table */
    let lastDeviceResults = [];
    /** Run metadata: run_created_at (pre), post_created_at (post) */
    let lastRunMeta = {};
    /** PRE device_results (for show run diff after POST) */
    let lastPreDeviceResults = [];
    /** Device list for last run (fabric, site, role) — used for consistency check */
    let lastRunDevices = [];
    /** Comparison after POST: [ { hostname, ip, diff: { key: { pre, post } } }, ... ] */
    let lastComparison = [];
    /** Parsed columns to show (field names from parsers) */
    let selectedParsedColumns = [];
    /** Sort: { col: string, dir: 'asc'|'desc' } */
    let sortCol = null, sortDir = "asc";
    /** Filter per column: { colKey: { type: 'in'|'not-in', value: string } } */
    let columnFilters = {};
    /** Custom command results and table state */
    let lastCustomCommandResults = [];
    let customCommandSortCol = null;
    let customCommandSortDir = "asc";
    let customCommandColumnFilters = {};

    async function get(path) {
      const r = await fetch(API + path);
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    }

    async function loadFabrics() {
      const { fabrics } = await get("/api/fabrics");
      fabricSel.innerHTML = "<option value=\"\">—</option>" + fabrics.map(f => `<option value="${f}">${f}</option>`).join("");
    }

    async function loadSites() {
      const fabric = fabricSel.value;
      siteSel.innerHTML = "<option value=\"\">—</option>";
      hallSel.innerHTML = "<option value=\"\">—</option>";
      roleSel.innerHTML = "<option value=\"\">—</option>";
      deviceList.innerHTML = "";
      if (!fabric) return;
      const { sites } = await get("/api/sites?fabric=" + encodeURIComponent(fabric));
      siteSel.innerHTML = "<option value=\"\">— All —</option>" + (sites || []).map(s => `<option value="${s}">${s}</option>`).join("");
      siteSel.selectedIndex = 0;
      await loadHalls();
    }

    async function loadHalls() {
      const fabric = (fabricSel && fabricSel.value) ? fabricSel.value : "";
      const site = (siteSel && siteSel.value) != null ? siteSel.value : "";
      hallSel.innerHTML = "<option value=\"\">—</option>";
      roleSel.innerHTML = "<option value=\"\">—</option>";
      deviceList.innerHTML = "";
      if (!fabric) return;
      const { halls } = await get("/api/halls?fabric=" + encodeURIComponent(fabric) + "&site=" + encodeURIComponent(site || ""));
      hallSel.innerHTML = "<option value=\"\">— All —</option>" + (halls || []).map(h => `<option value="${h}">${h}</option>`).join("");
      await loadRoles();
    }

    async function loadRoles() {
      const fabric = (fabricSel && fabricSel.value) ? fabricSel.value : "";
      const site = (siteSel && siteSel.value) != null ? siteSel.value : "";
      const hall = (hallSel && hallSel.value) ? hallSel.value : "";
      roleSel.innerHTML = "<option value=\"\">—</option>";
      deviceList.innerHTML = "";
      if (!fabric) return;
      let path = "/api/roles?fabric=" + encodeURIComponent(fabric) + "&site=" + encodeURIComponent(site || "");
      if (hall) path += "&hall=" + encodeURIComponent(hall);
      const { roles } = await get(path);
      roleSel.innerHTML = "<option value=\"\">—</option>" + (roles || []).map(r => `<option value="${r}">${r}</option>`).join("");
    }

    async function loadDevices() {
      const fabric = fabricSel.value, site = siteSel.value, role = roleSel.value || "", hall = hallSel.value || "";
      deviceList.innerHTML = "";
      devicesCache = [];
      pingResultsByIndex = [];
      if (!fabric) return;
      let path = "/api/devices?fabric=" + encodeURIComponent(fabric) + "&site=" + encodeURIComponent(site);
      if (role) path += "&role=" + encodeURIComponent(role);
      if (hall) path += "&hall=" + encodeURIComponent(hall);
      const { devices } = await get(path);
      devicesCache = devices || [];
      renderDevices();
      if (devicesCache.length > 0) doPing();
    }

    function renderDevices() {
      deviceList.innerHTML = devicesCache.map((d, i) => {
        const reachable = pingResultsByIndex[i];
        const isReachable = reachable === true;
        const isUnreachable = reachable === false;
        const pending = reachable === undefined;
        const canSelect = isReachable;
        const iconClass = pending ? "pending" : (isReachable ? "reachable" : "unreachable");
        const key = d.ip || d.hostname || i;
        return `<div class="device-row ${isUnreachable ? "unreachable" : ""}" data-index="${i}" data-ip="${escapeHtml(key)}">
          <span class="icon ${iconClass}" title="${pending ? "No ping" : (isReachable ? "Reachable" : "Unreachable")}"></span>
          <input type="checkbox" ${canSelect ? "" : "disabled"} data-index="${i}" data-hostname="${escapeHtml(d.hostname || "")}" />
          <span class="hostname">${escapeHtml(d.hostname || "")}</span>
          <span class="ip">${escapeHtml(d.ip || "")}</span>
        </div>`;
      }).join("");
    }

    function escapeHtml(s) {
      const div = document.createElement("div");
      div.textContent = s;
      return div.innerHTML;
    }

    function formatRecoverApiOutput(data) {
      if (!data || typeof data !== "object") return "";
      var parts = [];
      if (data.interface_status_output != null && String(data.interface_status_output).trim() !== "") {
        parts.push(String(data.interface_status_output).trim());
      }
      if (data.interface_status_warning && String(data.interface_status_warning).trim() !== "") {
        parts.push("Note: " + String(data.interface_status_warning).trim());
      }
      if (parts.length) return parts.join("\n\n");
      if (data.output != null && String(data.output).trim() !== "") return String(data.output);
      if (Array.isArray(data.results)) {
        var cmds = Array.isArray(data.commands) ? data.commands : [];
        var results = data.results;
        function formatOneRecoverResult(r) {
          if (r == null) return "(null)";
          if (typeof r === "string") {
            var t = r.trim();
            return t || "(empty string)";
          }
          if (typeof r === "object") {
            try {
              var keys = Object.keys(r);
              if (keys.length === 0) {
                return "(ok — no output from eAPI; normal for Arista configure / interface commands)";
              }
              return JSON.stringify(r, null, 2);
            } catch (e0) {
              return String(r);
            }
          }
          return String(r);
        }
        try {
          if (cmds.length === results.length && cmds.length > 0) {
            return results.map(function(r, i) {
              return cmds[i] + "\n  → " + formatOneRecoverResult(r);
            }).join("\n\n");
          }
          return results.map(function(r, i) {
            return "[result " + i + "]\n" + formatOneRecoverResult(r);
          }).join("\n\n");
        } catch (e2) {
          return String(data.results);
        }
      }
      return "";
    }
    function addCommandLogEntry(hostname, title, commandsText, outputText, ok) {
      var now = new Date();
      var time = now.toLocaleString(undefined, { dateStyle: "short", timeStyle: "medium" });
      globalCommandLogs.push({
        hostname: hostname || "?",
        title: title || "Command",
        commands: commandsText || "",
        output: outputText || "",
        ok: ok !== false,
        time: time,
        ts: now.getTime()
      });
      if (globalCommandLogs.length > MAX_COMMAND_LOGS) globalCommandLogs = globalCommandLogs.slice(-MAX_COMMAND_LOGS);
      var cmdBtn = $("commandLogsBtn");
      var cmdCount = $("commandLogsCount");
      if (cmdCount) cmdCount.textContent = globalCommandLogs.length;
      if (cmdBtn) cmdBtn.style.display = globalCommandLogs.length > 0 ? "inline-flex" : "none";
    }
    function renderCommandLogsList() {
      var listEl = $("commandLogsList");
      var titleEl = $("commandLogsPopupTitle");
      if (!listEl) return;
      if (titleEl) titleEl.textContent = "Command logs (" + globalCommandLogs.length + ")";
      var sorted = globalCommandLogs.slice().sort(function(a, b) { return (b.ts || 0) - (a.ts || 0); });
      listEl.innerHTML = sorted.map(function(e) {
        var cls = e.ok ? "ok" : "fail";
        var cmdBlock = escapeHtml(e.commands || "(none)");
        var outBlock = escapeHtml(e.output || "");
        return "<div class=\"command-log-entry " + cls + "\"><h4>" + escapeHtml(e.title) + " — " + escapeHtml(e.hostname) + "</h4>" +
          "<div class=\"cmd-log-meta\"><span class=\"event-time\">" + escapeHtml(e.time) + "</span></div>" +
          "<div class=\"cmd-log-block-title\">Commands</div><pre>" + cmdBlock + "</pre>" +
          "<div class=\"cmd-log-block-title\">Output</div><pre>" + outBlock + "</pre></div>";
      }).join("");
    }
    function closeCommandLogsPopup() {
      var pop = $("commandLogsPopup");
      if (pop) {
        pop.classList.remove("open");
        pop.setAttribute("aria-hidden", "true");
      }
    }
    function openCommandLogsPopup() {
      renderCommandLogsList();
      var pop = $("commandLogsPopup");
      if (pop) {
        pop.classList.add("open");
        pop.setAttribute("aria-hidden", "false");
      }
    }
    function initCommandLogsUi() {
      var btn = $("commandLogsBtn");
      var pop = $("commandLogsPopup");
      var closeBtn = $("commandLogsPopupClose");
      var clearBtn = $("commandLogsClearBtn");
      if (btn && pop) {
        btn.addEventListener("click", function(e) {
          e.stopPropagation();
          if (globalCommandLogs.length === 0) return;
          openCommandLogsPopup();
        });
      }
      if (closeBtn) closeBtn.addEventListener("click", function(e) { e.stopPropagation(); closeCommandLogsPopup(); });
      if (clearBtn) clearBtn.addEventListener("click", function(e) {
        e.stopPropagation();
        globalCommandLogs = [];
        var cmdCount = $("commandLogsCount");
        if (cmdCount) cmdCount.textContent = "0";
        if (btn) btn.style.display = "none";
        renderCommandLogsList();
        closeCommandLogsPopup();
      });
      document.addEventListener("click", function(e) {
        if (!pop || !pop.classList.contains("open")) return;
        if (pop.contains(e.target)) return;
        if (btn && btn.contains(e.target)) return;
        closeCommandLogsPopup();
      });
    }

    async function doPing() {
      if (!devicesCache.length) { pingStatus.textContent = "Select Fabric, Site, and Role to load the device list."; return; }
      pingStatus.textContent = "Pinging…";
      pingBtn.disabled = true;
      try {
        const res = await fetch(API + "/api/ping", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ devices: devicesCache.map(d => ({ hostname: d.hostname, ip: d.ip })) }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || res.statusText);
        pingResultsByIndex = (data.results || []).map(r => r.reachable === true);
        (data.results || []).forEach(function(r) {
          if (!r.reachable) addDeviceEvent("fail", r.hostname || r.ip || "?", "Ping failed");
        });
        renderDevices();
        const ok = (data.results || []).filter(r => r.reachable).length;
        pingStatus.textContent = `${ok}/${(data.results || []).length} devices reachable.`;
      } catch (e) {
        pingStatus.textContent = "Error: " + e.message;
      }
      pingBtn.disabled = false;
    }

    function selectAll() {
      deviceList.querySelectorAll("input[type=checkbox]:not(:disabled)").forEach(cb => { cb.checked = true; });
    }
    function selectNone() {
      deviceList.querySelectorAll("input[type=checkbox]").forEach(cb => { cb.checked = false; });
    }

    function getSelectedDevices() {
      const indices = [];
      deviceList.querySelectorAll("input[type=checkbox]:checked:not(:disabled)").forEach(cb => {
        const i = parseInt(cb.getAttribute("data-index"), 10);
        if (!isNaN(i) && i >= 0 && i < devicesCache.length) indices.push(i);
      });
      return indices.map(i => devicesCache[i]);
    }

    var transceiverInited = false;
    var transceiverDevicesCache = [];
    var transceiverFabricSel, transceiverSiteSel, transceiverHallSel, transceiverRoleSel, transceiverDeviceListEl;
    var transceiverTableRows = [];
    var transceiverTableFilters = {};
    var transceiverTableSortCol = "hostname";
    var transceiverTableSortDir = "asc";
    var TRANSCEIVER_COLUMNS = ["hostname", "interface", "description", "mtu", "serial", "type", "manufacturer", "temp", "tx_power", "rx_power", "status", "last_flap", "flap_count", "errors"];
    var TRANSCEIVER_HEADERS = { hostname: "Hostname", interface: "Interface", description: "Description", mtu: "MTU", serial: "Serial", type: "Type", manufacturer: "Manufacturer", temp: "Temp", tx_power: "TX power", rx_power: "RX power", status: "Status", last_flap: "Last Flap", flap_count: "Flap", errors: "CRC/Input Err" };
    var transceiverTableVisibleCols = {};
    TRANSCEIVER_COLUMNS.forEach(function(c) { transceiverTableVisibleCols[c] = true; });
    var transceiverDeviceMap = {};
    var TRANSCEIVER_TX_RX_OK_LO = -8, TRANSCEIVER_TX_RX_OK_HI = 8, TRANSCEIVER_TX_RX_WARN_LO = -15, TRANSCEIVER_TX_RX_WARN_HI = 15;
    var TRANSCEIVER_ERR_OK = 0, TRANSCEIVER_ERR_WARN_MAX = 10;

    function transceiverStatusHasErr(status) {
      return status != null && String(status).toLowerCase().indexOf("err") !== -1;
    }
    function transceiverIsHostPortEthernet1to48(iface) {
      var s = String(iface || "").trim();
      var m = s.match(/^(?:Ethernet|Eth|Et)(\d+)\/(\d+)$/i);
      if (m) {
        var mod = parseInt(m[1], 10), port = parseInt(m[2], 10);
        return mod === 1 && port >= 1 && port <= 48;
      }
      m = s.match(/^(\d+)\/(\d+)$/);
      if (m) {
        var mod2 = parseInt(m[1], 10), port2 = parseInt(m[2], 10);
        return mod2 === 1 && port2 >= 1 && port2 <= 48;
      }
      return false;
    }
    function transceiverIsLeafHostRecoverablePort(r) {
      var role = String(r.device_role || "").trim().toLowerCase();
      if (!role) {
        var dev = null;
        var h = (r.hostname || "").trim();
        var ip = (r.ip || "").trim();
        if (h && transceiverDeviceMap[h]) dev = transceiverDeviceMap[h];
        else if (ip && transceiverDeviceMap["ip:" + ip]) dev = transceiverDeviceMap["ip:" + ip];
        role = dev ? String(dev.role || "").trim().toLowerCase() : "";
      }
      if (role !== "leaf") return false;
      return transceiverIsHostPortEthernet1to48(r.interface);
    }
    function transceiverFindDeviceFromTr(tr) {
      var h = (tr.getAttribute("data-hostname") || "").trim();
      var ip = (tr.getAttribute("data-ip") || "").trim();
      if (h && transceiverDeviceMap[h]) return transceiverDeviceMap[h];
      if (ip && transceiverDeviceMap["ip:" + ip]) return transceiverDeviceMap["ip:" + ip];
      return null;
    }
    function renderTransceiverErrTableBody(errRows) {
      var wrap = document.getElementById("transceiverErrWrap");
      var tbody = document.getElementById("transceiverErrTbody");
      var recoverAllBtn = document.getElementById("transceiverRecoverAllBtn");
      if (!wrap || !tbody) return;
      var hasRun = transceiverTableRows && transceiverTableRows.length > 0;
      if (!hasRun) {
        wrap.style.display = "none";
        tbody.innerHTML = "";
        if (recoverAllBtn) recoverAllBtn.disabled = true;
        return;
      }
      wrap.style.display = "block";
      if (!errRows || !errRows.length) {
        tbody.innerHTML = "<tr class=\"transceiver-err-empty\"><td colspan=\"9\" style=\"text-align:center; color:var(--muted); padding:0.75rem 0.5rem;\">No ports in an error-disabled or other <code>err</code> status (no matching interfaces in this result set).</td></tr>";
        if (recoverAllBtn) recoverAllBtn.disabled = true;
        return;
      }
      var recoverableErr = errRows.filter(function(r) { return transceiverIsLeafHostRecoverablePort(r); });
      if (recoverAllBtn) recoverAllBtn.disabled = recoverableErr.length === 0;
      tbody.innerHTML = errRows.map(function(r) {
        var canAct = transceiverIsLeafHostRecoverablePort(r);
        var actionCell = canAct
          ? "<button type=\"button\" class=\"btn-recover-one transceiver-icon-btn\" title=\"recover\" aria-label=\"recover\">" +
            "<img src=\"/static/assets/transceiver-recover.png\" alt=\"\" width=\"28\" height=\"28\" /></button>" +
            "<button type=\"button\" class=\"btn-clear-counters-one transceiver-icon-btn\" title=\"clear counters\" aria-label=\"clear counters\">" +
            "<img src=\"/static/assets/transceiver-clear-counters.png\" alt=\"\" width=\"28\" height=\"28\" /></button>"
          : "<span class=\"muted\" style=\"font-size:0.85em;\" title=\"Recovery only on Leaf, Ethernet1/1-1/48 host ports.\">&mdash;</span>";
        return "<tr data-hostname=\"" + escapeHtml(r.hostname || "") + "\" data-ip=\"" + escapeHtml(r.ip || "") + "\" data-interface=\"" + escapeHtml(r.interface || "") + "\">" +
          "<td>" + escapeHtml(r.hostname || "") + "</td><td>" + escapeHtml(r.interface || "") + "</td>" +
          "<td>" + escapeHtml(r.tx_power != null ? String(r.tx_power) : "") + "</td><td>" + escapeHtml(r.rx_power != null ? String(r.rx_power) : "") + "</td>" +
          "<td>" + escapeHtml(r.flap_count != null ? String(r.flap_count) : "") + "</td><td>" + escapeHtml(r.last_flap != null ? String(r.last_flap) : "") + "</td>" +
          "<td>" + escapeHtml(r.errors != null ? String(r.errors) : "") + "</td>" +
          "<td>" + escapeHtml(r.status || "") + "</td>" +
          "<td>" + actionCell + "</td></tr>";
      }).join("");
    }
    async function transceiverCallRecover(device, interfaces) {
      var host = (device.hostname || device.ip || "?").trim();
      var res;
      try {
        res = await fetch(API + "/api/transceiver/recover", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device: device, interfaces: interfaces }),
        });
      } catch (e) {
        addCommandLogEntry(host, "Interface recovery", "", "Request failed: " + (e.message || String(e)), false);
        throw e;
      }
      var data = await res.json().catch(function() { return {}; });
      var cmds = Array.isArray(data.commands) ? data.commands : [];
      var cmdText = cmds.join("\n");
      var outText = formatRecoverApiOutput(data);
      var ok = res.ok && data.ok !== false;
      if (!ok) {
        var errMsg = (data && data.error) ? data.error : (res.statusText || "Recovery failed");
        if (!outText) outText = errMsg;
        else if (errMsg) outText = outText + "\n\n---\nError: " + errMsg;
        addCommandLogEntry(host, "Interface recovery", cmdText, outText, false);
        throw new Error(errMsg);
      }
      if (!outText) outText = "(no output)";
      addCommandLogEntry(host, "Interface recovery", cmdText, outText, true);
      return data;
    }
    async function transceiverCallClearCounters(device, iface) {
      var host = (device.hostname || device.ip || "?").trim();
      var res;
      try {
        res = await fetch(API + "/api/transceiver/clear-counters", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device: device, interface: iface }),
        });
      } catch (e) {
        addCommandLogEntry(host, "Clear counters", "", "Request failed: " + (e.message || String(e)), false);
        throw e;
      }
      var data = await res.json().catch(function() { return {}; });
      var cmds = Array.isArray(data.commands) ? data.commands : [];
      var cmdText = cmds.join("\n");
      var outText = formatRecoverApiOutput(data);
      var ok = res.ok && data.ok !== false;
      if (!ok) {
        var errMsg = (data && data.error) ? data.error : (res.statusText || "Clear counters failed");
        if (!outText) outText = errMsg;
        else if (errMsg) outText = outText + "\n\n---\nError: " + errMsg;
        addCommandLogEntry(host, "Clear counters", cmdText, outText, false);
        throw new Error(errMsg);
      }
      if (!outText) outText = "(no output)";
      addCommandLogEntry(host, "Clear counters", cmdText, outText, true);
      return data;
    }

    function transceiverRowThresholdClass(r) {
      var bad = false, warn = false;
      var tx = parseFloat(String(r.tx_power || "").replace(/[^\d.-]/g, ""));
      var rx = parseFloat(String(r.rx_power || "").replace(/[^\d.-]/g, ""));
      if (!isNaN(tx) && (tx < TRANSCEIVER_TX_RX_WARN_LO || tx > TRANSCEIVER_TX_RX_WARN_HI)) bad = true;
      else if (!isNaN(tx) && (tx < TRANSCEIVER_TX_RX_OK_LO || tx > TRANSCEIVER_TX_RX_OK_HI)) warn = true;
      if (!isNaN(rx) && (rx < TRANSCEIVER_TX_RX_WARN_LO || rx > TRANSCEIVER_TX_RX_WARN_HI)) bad = true;
      else if (!isNaN(rx) && (rx < TRANSCEIVER_TX_RX_OK_LO || rx > TRANSCEIVER_TX_RX_OK_HI)) warn = true;
      var crcN = parseInt(String(r.crc_count || "0").replace(/\D/g, ""), 10);
      var inN = parseInt(String(r.in_errors || "0").replace(/\D/g, ""), 10);
      var errSum = (isNaN(crcN) ? 0 : crcN) + (isNaN(inN) ? 0 : inN);
      if (errSum > TRANSCEIVER_ERR_WARN_MAX) bad = true;
      else if (errSum > TRANSCEIVER_ERR_OK) warn = true;
      if (bad) return "row-threshold-bad";
      if (warn) return "row-threshold-warn";
      return "row-threshold-ok";
    }

    function renderTransceiverTable() {
      var thead = document.getElementById("transceiverThead");
      var tbody = document.getElementById("transceiverTbody");
      if (!thead || !tbody) return;
      var visibleCols = TRANSCEIVER_COLUMNS.filter(function(col) { return transceiverTableVisibleCols[col] !== false; });
      var rows = transceiverTableRows.slice();
      TRANSCEIVER_COLUMNS.forEach(function(col) {
        var f = transceiverTableFilters[col];
        if (f && f.value) {
          var v = (f.value || "").toLowerCase();
          var notIn = (f.type || "in") === "not-in";
          rows = rows.filter(function(r) {
            var cell = (r[col] != null && r[col] !== undefined) ? String(r[col]).toLowerCase() : "";
            var match = cell.indexOf(v) !== -1;
            return notIn ? !match : match;
          });
        }
      });
      rows.sort(function(a, b) {
        var va = a[transceiverTableSortCol];
        var vb = b[transceiverTableSortCol];
        var c = (va || "").localeCompare(vb || "", undefined, { numeric: true });
        return transceiverTableSortDir === "asc" ? c : -c;
      });
      var tableEl = document.getElementById("transceiverTable");
      var wrap = tableEl ? tableEl.parentElement : null;
      if (wrap && tableEl) {
        var chipsBar = wrap.querySelector(".filter-chips-bar");
        if (!chipsBar) { chipsBar = document.createElement("div"); chipsBar.className = "filter-chips-bar"; wrap.insertBefore(chipsBar, tableEl); }
        chipsBar.innerHTML = "";
        visibleCols.forEach(function(col) {
          var f = transceiverTableFilters[col];
          if (!f || !(f.value || "").trim()) return;
          var chip = document.createElement("span");
          chip.className = "filter-chip";
          var typ = (f.type || "in") === "not-in" ? "not-in" : "in";
          chip.textContent = (TRANSCEIVER_HEADERS[col] || col) + " " + typ + " \"" + (f.value || "").trim() + "\" ";
          var xBtn = document.createElement("button");
          xBtn.type = "button";
          xBtn.className = "filter-chip-remove";
          xBtn.textContent = "\u00d7";
          xBtn.setAttribute("aria-label", "Remove filter");
          (function(c) { xBtn.addEventListener("click", function() { transceiverTableFilters[c] = transceiverTableFilters[c] || {}; transceiverTableFilters[c].value = ""; renderTransceiverTable(); }); })(col);
          chip.appendChild(xBtn);
          chipsBar.appendChild(chip);
        });
      }
      var tr1 = document.createElement("tr");
      var tr2 = document.createElement("tr");
      tr2.className = "filter-row";
      visibleCols.forEach(function(col) {
        var th = document.createElement("th");
        th.className = "sortable";
        th.textContent = TRANSCEIVER_HEADERS[col] || col;
        th.dataset.col = col;
        var span = document.createElement("span");
        span.className = "sort-icon";
        span.textContent = transceiverTableSortCol === col ? (transceiverTableSortDir === "asc" ? " \u25b2" : " \u25bc") : "";
        th.appendChild(span);
        th.addEventListener("click", function() {
          if (transceiverTableSortCol === col) transceiverTableSortDir = transceiverTableSortDir === "asc" ? "desc" : "asc";
          else { transceiverTableSortCol = col; transceiverTableSortDir = "asc"; }
          renderTransceiverTable();
        });
        tr1.appendChild(th);
        var fth = document.createElement("th");
        var sel = document.createElement("select");
        sel.dataset.col = col;
        sel.innerHTML = "<option value=\"in\">in</option><option value=\"not-in\">not-in</option>";
        var f = transceiverTableFilters[col];
        if (f) sel.value = f.type || "in";
        sel.addEventListener("change", function() {
          transceiverTableFilters[col] = transceiverTableFilters[col] || {}; transceiverTableFilters[col].type = sel.value; renderTransceiverTable();
        });
        var inp = document.createElement("input");
        inp.type = "text";
        inp.placeholder = "Filter\u2026 Enter to apply";
        inp.dataset.col = col;
        if (f && f.value) inp.value = f.value;
        inp.addEventListener("keydown", function(e) {
          if (e.key === "Enter") {
            transceiverTableFilters[col] = transceiverTableFilters[col] || {}; transceiverTableFilters[col].type = sel.value; transceiverTableFilters[col].value = inp.value.trim(); renderTransceiverTable();
          }
        });
        fth.appendChild(sel);
        fth.appendChild(inp);
        tr2.appendChild(fth);
      });
      thead.innerHTML = "";
      thead.appendChild(tr1);
      thead.appendChild(tr2);
      var errRows = rows.filter(function(r) { return transceiverStatusHasErr(r.status); });
      var mainRows = rows.filter(function(r) { return !transceiverStatusHasErr(r.status); });
      renderTransceiverErrTableBody(errRows);
      tbody.innerHTML = mainRows.map(function(r) {
        var trClass = transceiverRowThresholdClass(r);
        return "<tr class=\"" + trClass + "\">" + visibleCols.map(function(col) {
          var val = (r[col] != null && r[col] !== "") ? String(r[col]) : "";
          return "<td>" + escapeHtml(val) + "</td>";
        }).join("") + "</tr>";
      }).join("");
    }
    async function loadTransceiverFabrics() {
      var sel = document.getElementById("transceiverFabric");
      if (!sel) return;
      var list = await get("/api/fabrics").then(function(d) { return d.fabrics || []; }).catch(function() { return []; });
      sel.innerHTML = "<option value=\"\">—</option>" + list.map(function(f) { return "<option value=\"" + escapeHtml(f) + "\">" + escapeHtml(f) + "</option>"; }).join("");
    }
    async function loadTransceiverSites() {
      var fabric = transceiverFabricSel ? transceiverFabricSel.value : "";
      if (!transceiverSiteSel) return;
      transceiverSiteSel.innerHTML = "<option value=\"\">—</option>";
      transceiverHallSel && (transceiverHallSel.innerHTML = "<option value=\"\">—</option>");
      transceiverRoleSel && (transceiverRoleSel.innerHTML = "<option value=\"\">—</option>");
      transceiverDeviceListEl && (transceiverDeviceListEl.innerHTML = "");
      transceiverDevicesCache = [];
      if (!fabric) return;
      var sites = await get("/api/sites?fabric=" + encodeURIComponent(fabric)).then(function(d) { return d.sites || []; }).catch(function() { return []; });
      transceiverSiteSel.innerHTML = "<option value=\"\">— All —</option>" + sites.map(function(s) { return "<option value=\"" + escapeHtml(s) + "\">" + escapeHtml(s) + "</option>"; }).join("");
    }
    async function loadTransceiverHalls() {
      var fabric = transceiverFabricSel ? transceiverFabricSel.value : "";
      var site = transceiverSiteSel ? transceiverSiteSel.value : "";
      if (!transceiverHallSel) return;
      transceiverHallSel.innerHTML = "<option value=\"\">—</option>";
      transceiverRoleSel && (transceiverRoleSel.innerHTML = "<option value=\"\">—</option>");
      transceiverDeviceListEl && (transceiverDeviceListEl.innerHTML = "");
      transceiverDevicesCache = [];
      if (!fabric) return;
      var halls = await get("/api/halls?fabric=" + encodeURIComponent(fabric) + "&site=" + encodeURIComponent(site || "")).then(function(d) { return d.halls || []; }).catch(function() { return []; });
      transceiverHallSel.innerHTML = "<option value=\"\">— All —</option>" + halls.map(function(h) { return "<option value=\"" + escapeHtml(h) + "\">" + escapeHtml(h) + "</option>"; }).join("");
    }
    async function loadTransceiverRoles() {
      var fabric = transceiverFabricSel ? transceiverFabricSel.value : "";
      var site = transceiverSiteSel ? transceiverSiteSel.value : "";
      var hall = transceiverHallSel ? transceiverHallSel.value : "";
      if (!transceiverRoleSel) return;
      transceiverRoleSel.innerHTML = "<option value=\"\">—</option>";
      transceiverDeviceListEl && (transceiverDeviceListEl.innerHTML = "");
      transceiverDevicesCache = [];
      if (!fabric) return;
      var path = "/api/roles?fabric=" + encodeURIComponent(fabric) + "&site=" + encodeURIComponent(site || "");
      if (hall) path += "&hall=" + encodeURIComponent(hall);
      var roles = await get(path).then(function(d) { return d.roles || []; }).catch(function() { return []; });
      transceiverRoleSel.innerHTML = "<option value=\"\">—</option>" + roles.map(function(r) { return "<option value=\"" + escapeHtml(r) + "\">" + escapeHtml(r) + "</option>"; }).join("");
    }
    async function loadTransceiverDevices() {
      var fabric = transceiverFabricSel ? transceiverFabricSel.value : "";
      var site = transceiverSiteSel ? transceiverSiteSel.value : "";
      var role = transceiverRoleSel ? transceiverRoleSel.value : "";
      var hall = transceiverHallSel ? transceiverHallSel.value : "";
      if (!transceiverDeviceListEl || !fabric) return;
      transceiverDeviceListEl.innerHTML = "";
      transceiverDevicesCache = [];
      var path = "/api/devices?fabric=" + encodeURIComponent(fabric) + "&site=" + encodeURIComponent(site);
      if (role) path += "&role=" + encodeURIComponent(role);
      if (hall) path += "&hall=" + encodeURIComponent(hall);
      var devices = await get(path).then(function(d) { return d.devices || []; }).catch(function() { return []; });
      transceiverDevicesCache = devices;
      transceiverDeviceListEl.innerHTML = devices.map(function(d, i) {
        return "<div class=\"device-row\" data-index=\"" + i + "\"><input type=\"checkbox\" data-index=\"" + i + "\" /><span class=\"hostname\">" + escapeHtml(d.hostname || "") + "</span><span class=\"ip\">" + escapeHtml(d.ip || "") + "</span></div>";
      }).join("");
    }
    function getSelectedTransceiverDevices() {
      if (!transceiverDeviceListEl) return [];
      var indices = [];
      transceiverDeviceListEl.querySelectorAll("input[type=checkbox]:checked").forEach(function(cb) {
        var i = parseInt(cb.getAttribute("data-index"), 10);
        if (!isNaN(i) && i >= 0 && i < transceiverDevicesCache.length) indices.push(i);
      });
      return indices.map(function(i) { return transceiverDevicesCache[i]; });
    }
    function initTransceiverPage() {
      if (transceiverInited) return;
      transceiverInited = true;
      transceiverFabricSel = document.getElementById("transceiverFabric");
      transceiverSiteSel = document.getElementById("transceiverSite");
      transceiverHallSel = document.getElementById("transceiverHall");
      transceiverRoleSel = document.getElementById("transceiverRole");
      transceiverDeviceListEl = document.getElementById("transceiverDeviceList");
      if (!transceiverFabricSel) return;
      loadTransceiverFabrics();
      transceiverFabricSel.addEventListener("change", loadTransceiverSites);
      transceiverSiteSel && transceiverSiteSel.addEventListener("change", loadTransceiverHalls);
      transceiverHallSel && transceiverHallSel.addEventListener("change", loadTransceiverRoles);
      transceiverRoleSel && transceiverRoleSel.addEventListener("change", loadTransceiverDevices);
      document.getElementById("transceiverSelectAll") && document.getElementById("transceiverSelectAll").addEventListener("click", function() {
        transceiverDeviceListEl && transceiverDeviceListEl.querySelectorAll("input[type=checkbox]").forEach(function(cb) { cb.checked = true; });
      });
      document.getElementById("transceiverSelectNone") && document.getElementById("transceiverSelectNone").addEventListener("click", function() {
        transceiverDeviceListEl && transceiverDeviceListEl.querySelectorAll("input[type=checkbox]").forEach(function(cb) { cb.checked = false; });
      });
      var colToggleBtn = document.getElementById("transceiverColumnToggleBtn");
      var colToggleDrop = document.getElementById("transceiverColumnToggleDropdown");
      if (colToggleBtn && colToggleDrop) {
        colToggleBtn.addEventListener("click", function(e) {
          e.stopPropagation();
          colToggleDrop.classList.toggle("open");
          if (colToggleDrop.classList.contains("open")) {
            TRANSCEIVER_COLUMNS.forEach(function(col) {
              var cb = colToggleDrop.querySelector("input[data-col=\"" + col + "\"]");
              if (cb) cb.checked = transceiverTableVisibleCols[col] !== false;
            });
          }
        });
        colToggleDrop.querySelectorAll("input[data-col]").forEach(function(cb) {
          cb.addEventListener("change", function() {
            var col = cb.getAttribute("data-col");
            transceiverTableVisibleCols[col] = cb.checked;
            renderTransceiverTable();
          });
        });
        document.addEventListener("click", function() { colToggleDrop.classList.remove("open"); });
        colToggleDrop.addEventListener("click", function(e) { e.stopPropagation(); });
      }
      var runBtn = document.getElementById("transceiverRunBtn");
      var progressWrap = document.getElementById("transceiverProgressWrap");
      var progressText = document.getElementById("transceiverProgressText");
      var progressBar = document.getElementById("transceiverProgressBar");
      var statusEl = document.getElementById("transceiverStatus");
      var tableWrap = document.getElementById("transceiverTableWrap");
      var tbody = document.getElementById("transceiverTbody");
      var recoverStatusEl = document.getElementById("transceiverRecoverStatus");
      var errTbody = document.getElementById("transceiverErrTbody");
      if (errTbody) {
        errTbody.addEventListener("click", async function(e) {
          var recoverBtn = e.target && e.target.closest && e.target.closest(".btn-recover-one");
          var clearBtn = e.target && e.target.closest && e.target.closest(".btn-clear-counters-one");
          if (!recoverBtn && !clearBtn) return;
          var tr = (recoverBtn || clearBtn).closest("tr");
          if (!tr) return;
          var dev = transceiverFindDeviceFromTr(tr);
          var iface = (tr.getAttribute("data-interface") || "").trim();
          if (!dev) { if (recoverStatusEl) recoverStatusEl.textContent = "Device not in map; run transceiver check again."; return; }
          if (!iface) return;
          var btn = recoverBtn || clearBtn;
          btn.disabled = true;
          if (recoverBtn) {
            if (recoverStatusEl) recoverStatusEl.textContent = "Recovering " + iface + "\u2026";
            try {
              await transceiverCallRecover(dev, [iface]);
              if (recoverStatusEl) recoverStatusEl.textContent = "OK: " + iface;
            } catch (err) {
              if (recoverStatusEl) recoverStatusEl.textContent = "Error: " + (err.message || String(err));
            }
          } else {
            if (recoverStatusEl) recoverStatusEl.textContent = "Clear counters " + iface + "\u2026";
            try {
              await transceiverCallClearCounters(dev, iface);
              if (recoverStatusEl) recoverStatusEl.textContent = "OK: clear counters " + iface;
            } catch (err) {
              if (recoverStatusEl) recoverStatusEl.textContent = "Error: " + (err.message || String(err));
            }
          }
          btn.disabled = false;
        });
      }
      var recoverAllBtn = document.getElementById("transceiverRecoverAllBtn");
      if (recoverAllBtn) recoverAllBtn.addEventListener("click", async function() {
        var errRows = transceiverTableRows.filter(function(r) { return transceiverStatusHasErr(r.status); });
        var recoverableRows = errRows.filter(function(r) { return transceiverIsLeafHostRecoverablePort(r); });
        if (!recoverableRows.length) {
          if (recoverStatusEl) recoverStatusEl.textContent = errRows.length ? "No Leaf host ports (Ethernet1/1-1/48) in error state to recover." : "No error interfaces.";
          return;
        }
        var groups = {};
        recoverableRows.forEach(function(r) {
          var dev = null;
          var h = (r.hostname || "").trim();
          var ip = (r.ip || "").trim();
          if (h && transceiverDeviceMap[h]) dev = transceiverDeviceMap[h];
          else if (ip && transceiverDeviceMap["ip:" + ip]) dev = transceiverDeviceMap["ip:" + ip];
          if (!dev) return;
          var k = (dev.hostname || dev.ip || "").trim();
          if (!groups[k]) groups[k] = { device: dev, interfaces: [] };
          var ifn = (r.interface || "").trim();
          if (ifn && groups[k].interfaces.indexOf(ifn) === -1) groups[k].interfaces.push(ifn);
        });
        var keys = Object.keys(groups);
        if (!keys.length) { if (recoverStatusEl) recoverStatusEl.textContent = "No devices mapped; run transceiver check again."; return; }
        recoverAllBtn.disabled = true;
        if (recoverStatusEl) recoverStatusEl.textContent = "Running recovery\u2026";
        try {
          for (var i = 0; i < keys.length; i++) {
            var g = groups[keys[i]];
            await transceiverCallRecover(g.device, g.interfaces);
          }
          if (recoverStatusEl) recoverStatusEl.textContent = "Recovery all completed.";
        } catch (err) {
          if (recoverStatusEl) recoverStatusEl.textContent = "Error: " + (err.message || String(err));
        }
        recoverAllBtn.disabled = false;
      });
      if (runBtn && tbody) runBtn.addEventListener("click", async function() {
        var devices = getSelectedTransceiverDevices();
        if (!devices.length) { statusEl.textContent = "Select one or more devices."; return; }
        statusEl.textContent = "";
        transceiverDeviceMap = {};
        devices.forEach(function(d) {
          var h = (d.hostname || "").trim();
          var ip = (d.ip || "").trim();
          if (h) transceiverDeviceMap[h] = d;
          if (ip) transceiverDeviceMap["ip:" + ip] = d;
        });
        var TRANSCEIVER_PARALLEL = 20;
        function transceiverDeviceKey(d) {
          return ((d.hostname || "").trim() || (d.ip || "").trim() || "?");
        }
        function errMatchesDevice(err, device, key) {
          var eh = (err && err.hostname ? String(err.hostname) : "").trim();
          if (!eh) return false;
          var h = (device.hostname || "").trim();
          var ip = (device.ip || "").trim();
          return eh === h || eh === ip || eh === key;
        }
        initHeaderProgressDetail(devices);
        showHeaderProgress(devices.length);
        runBtn.disabled = true;
        var allRows = [];
        var allErrs = [];
        var allInterfaceStatusTraces = [];
        var doneCount = 0;
        try {
          for (var bi = 0; bi < devices.length; bi += TRANSCEIVER_PARALLEL) {
            var batch = devices.slice(bi, bi + TRANSCEIVER_PARALLEL);
            await Promise.all(batch.map(function(device) {
              return (async function() {
                var key = transceiverDeviceKey(device);
                updateHeaderProgressDetailPhase(key, "running", "Transceiver API…");
                try {
                  var res = await fetch(API + "/api/transceiver", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ devices: [device] }) });
                  var data;
                  try {
                    data = await res.json();
                  } catch (parseErr) {
                    throw new Error("Invalid JSON response");
                  }
                  if (!res.ok) {
                    var msg = (data && data.error) ? data.error : (res.statusText || "HTTP " + res.status);
                    allErrs.push({ hostname: key, error: msg });
                    updateHeaderProgressDetailPhase(key, "error", msg);
                  } else {
                    var rows = data.rows || [];
                    var errs = data.errors || [];
                    allRows = allRows.concat(rows);
                    allErrs = allErrs.concat(errs);
                    if (data.interface_status_trace && data.interface_status_trace.length) {
                      allInterfaceStatusTraces = allInterfaceStatusTraces.concat(data.interface_status_trace);
                    }
                    var hostErr = null;
                    for (var ei = 0; ei < errs.length; ei++) {
                      if (errMatchesDevice(errs[ei], device, key)) { hostErr = errs[ei]; break; }
                    }
                    if (hostErr) {
                      updateHeaderProgressDetailPhase(key, "error", (hostErr.error || "Error").trim());
                    } else if (rows.length) {
                      updateHeaderProgressDetailPhase(key, "done", "OK (" + rows.length + " row" + (rows.length === 1 ? "" : "s") + ")");
                    } else {
                      updateHeaderProgressDetailPhase(key, "done", "No transceiver rows");
                    }
                  }
                } catch (e) {
                  allErrs.push({ hostname: key, error: e.message || String(e) });
                  updateHeaderProgressDetailPhase(key, "error", e.message || "Request failed");
                }
                doneCount++;
                updateHeaderProgress(doneCount, devices.length);
              })();
            }));
          }
          if (allErrs.length) statusEl.textContent = allErrs.length + " device(s) had errors.";
          transceiverTableRows = allRows;
          renderTransceiverTable();
          tableWrap.style.display = allRows.length ? "block" : "none";
          if (!allRows.length && !allErrs.length) statusEl.textContent = "No transceiver data returned.";
          var traceDet = document.getElementById("transceiverInterfaceStatusTrace");
          var tracePre = document.getElementById("transceiverInterfaceStatusTracePre");
          if (traceDet && tracePre) {
            if (allInterfaceStatusTraces.length) {
              tracePre.textContent = JSON.stringify(allInterfaceStatusTraces, null, 2);
              traceDet.style.display = "block";
            } else {
              traceDet.style.display = "none";
              tracePre.textContent = "";
            }
          }
        } catch (e) {
          statusEl.textContent = "Error: " + (e.message || "Request failed");
        }
        runBtn.disabled = false;
        hideHeaderProgress();
      });
    }

    async function runPhase() {
      const phase = ($("phase").value || "PRE").toUpperCase();
      const customCmd = ($("customCommandInput") && $("customCommandInput").value || "").trim();
      if (phase === "CUSTOM") {
        if (!customCmd) {
          $("runStatus").textContent = "Enter a command (show or dir only).";
          return;
        }
        const c = customCmd.toLowerCase();
        if (!c.startsWith("show") && !c.startsWith("dir")) {
          $("runStatus").textContent = "Only commands starting with 'show' or 'dir' are allowed.";
          return;
        }
        var readOnlyBlocklist = ["conf t", "configure terminal", "config t", "config terminal", "| write", "write mem", "write memory", "copy run start", "| append", "| tee", "terminal no monitor", "logging buffered"];
        for (var i = 0; i < readOnlyBlocklist.length; i++) {
          if (c.indexOf(readOnlyBlocklist[i]) !== -1) {
            $("runStatus").textContent = "Command rejected: read-only intent required (no config/write).";
            return;
          }
        }
        const devices = getSelectedDevices();
        if (!devices.length) {
          $("runStatus").textContent = "Select one or more devices first.";
          return;
        }
        $("runStatus").textContent = "";
        $("runBtn").disabled = true;
        $("customCommandOutputWrap").style.display = "block";
        const total = devices.length;
        showHeaderProgress(total);
        const PARALLEL = 20;
        const allCustomResults = [];
        for (let i = 0; i < devices.length; i += PARALLEL) {
          const batch = devices.slice(i, i + PARALLEL);
          const batchResults = await Promise.all(batch.map(async function(device) {
            try {
              const r = await fetch(API + "/api/custom-command", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ device: device, command: customCmd }),
              });
              const d = await r.json();
              var out = { device: device, output: d.output, error: d.error };
              addDeviceEvent(out.error ? "fail" : "success", device.hostname || device.ip || "?", out.error || "Command OK");
              return out;
            } catch (e) {
              addDeviceEvent("fail", device.hostname || device.ip || "?", e.message);
              return { device: device, output: null, error: e.message };
            }
          }));
          allCustomResults.push(...batchResults);
          updateHeaderProgress(allCustomResults.length, total);
        }
        hideHeaderProgress();
        lastCustomCommandResults = allCustomResults.map(function(r) {
          return {
            hostname: (r.device.hostname || r.device.ip || "").trim(),
            ip: (r.device.ip || "").trim(),
            output: r.error || r.output || "(no output)",
          };
        });
        renderCustomCommandTable();
        $("runStatus").textContent = "Done.";
        $("runBtn").disabled = false;
        return;
      }

      if ($("customCommandOutputWrap")) $("customCommandOutputWrap").style.display = "none";
      if (phase === "POST") {
        if (!lastRunId) {
          $("runStatus").textContent = "Run PRE first (select Phase PRE and run), then switch to POST and run.";
          $("runResult").textContent = "";
          return;
        }
        $("runStatus").textContent = "";
        $("runResult").textContent = "";
        $("runBtn").disabled = true;
        let runDevices = [];
        try {
          const runRes = await fetch(API + "/api/run/result/" + encodeURIComponent(lastRunId));
          if (!runRes.ok) throw new Error("Run not found");
          const runData = await runRes.json();
          runDevices = runData.devices || [];
        } catch (e) {
          $("runBtn").disabled = false;
          $("runStatus").textContent = "Error: " + e.message;
          return;
        }
        if (!runDevices.length) {
          $("runBtn").disabled = false;
          $("runStatus").textContent = "No devices in run.";
          return;
        }
        const PARALLEL_POST = 20;
        const total = runDevices.length;
        showHeaderProgress(total);
        const deviceResults = [];
        for (let i = 0; i < runDevices.length; i += PARALLEL_POST) {
          const batch = runDevices.slice(i, i + PARALLEL_POST);
          const batchResults = await Promise.all(batch.map(async function(device) {
            try {
              const r = await fetch(API + "/api/run/device", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ device: device }),
              });
              const d = await r.json();
              var res = d.device_result || { hostname: device.hostname, ip: device.ip, error: d.error || "No result" };
              var err = getDeviceResultError(res) || res.error || null;
              addDeviceEvent(err ? "fail" : "success", res.hostname || res.ip || "?", err || "Login/run OK");
              logDeviceCommandWarnings(res);
              return res;
            } catch (e) {
              addDeviceEvent("fail", device.hostname || device.ip || "?", e.message);
              return { hostname: device.hostname, ip: device.ip, error: e.message };
            }
          }));
          deviceResults.push(...batchResults);
          updateHeaderProgress(deviceResults.length, total);
        }
        let d = {};
        try {
          const cr = await fetch(API + "/api/run/post/complete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ run_id: lastRunId, device_results: deviceResults }),
          });
          d = await cr.json();
          if (!cr.ok) throw new Error(d.error || "Request failed");
        } catch (e) {
          hideHeaderProgress();
          $("runBtn").disabled = false;
          $("runStatus").textContent = "Error: " + e.message;
          return;
        }
        hideHeaderProgress();
        $("runStatus").textContent = "POST done. Comparison below.";
        $("runResult").textContent = JSON.stringify({ comparison: d.comparison, device_results: d.device_results }, null, 2);
        lastDeviceResults = d.device_results || [];
        lastPreDeviceResults = d.pre_device_results || [];
        lastComparison = d.comparison || [];
        lastRunMeta = { run_created_at: d.run_created_at, post_created_at: d.post_created_at };
        updateSavedReportPost(lastRunId, d.post_created_at, d.device_results, d.comparison);
        refreshSavedReportsList();
        renderResultsTable();
        renderShortfall(lastPreDeviceResults);
        renderConsistency(lastRunDevices, lastPreDeviceResults);
        renderFlappedPorts24h(lastDeviceResults);
        fillShowRunDiffDropdown();
        $("runBtn").disabled = false;
        var rpb = document.getElementById("runPostBtn");
        if (rpb) rpb.style.display = "none";
        return;
      }
      const devices = getSelectedDevices();
      if (!devices.length) {
        $("runStatus").textContent = "Select one or more devices first.";
        $("runResult").textContent = "";
        return;
      }
      const MAX_DEVICES = 20;
      const PARALLEL = 20;
      const list = devices.slice(0, MAX_DEVICES);
      const total = list.length;
      $("runStatus").textContent = "";
      $("runResult").textContent = "";
      showHeaderProgress(total);
      $("runBtn").disabled = true;
      const deviceResults = [];
      for (let i = 0; i < list.length; i += PARALLEL) {
        const batch = list.slice(i, i + PARALLEL);
        const batchResults = await Promise.all(batch.map(async function(device) {
          try {
            const r = await fetch(API + "/api/run/device", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ device: device }),
            });
            const d = await r.json();
              var res = d.device_result || { hostname: device.hostname, ip: device.ip, error: d.error || "No result" };
              var err = getDeviceResultError(res) || res.error || null;
              addDeviceEvent(err ? "fail" : "success", res.hostname || res.ip || "?", err || "Login/run OK");
              logDeviceCommandWarnings(res);
              return res;
            } catch (e) {
              addDeviceEvent("fail", device.hostname || device.ip || "?", e.message);
              return { hostname: device.hostname, ip: device.ip, error: e.message };
            }
          }));
          deviceResults.push(...batchResults);
          updateHeaderProgress(deviceResults.length, total);
        }
      const successCount = deviceResults.filter(function(r) { return !getDeviceResultError(r); }).length;
      let runId = null;
      let runCreatedAt = null;
      const fabricName = (fabricSel && fabricSel.value) ? fabricSel.value.trim() : "";
      const roleName = (roleSel && roleSel.value) ? roleSel.value.trim() : "";
      const preName = preReportName(fabricName, roleName, list.length);
      if (successCount > 0) {
        try {
          const cr = await fetch(API + "/api/run/pre/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ devices: list, device_results: deviceResults, name: preName }),
          });
          const cj = await cr.json();
          if (!cr.ok) throw new Error(cj.error || "Run creation failed");
          runId = cj.run_id;
          runCreatedAt = cj.run_created_at || null;
        } catch (e) {
          hideHeaderProgress();
          $("runStatus").textContent = "Error: " + e.message;
          $("runBtn").disabled = false;
          return;
        }
        try {
          localStorage.setItem("pergen_last_pre", JSON.stringify({ name: preName, run_id: runId, devices: list, device_results: deviceResults, created_at: runCreatedAt }));
          addSavedReport({ run_id: runId, name: preName, created_at: runCreatedAt, devices: list, device_results: deviceResults });
          await refreshSavedReportsList();
        } catch (e) {}
      }
      hideHeaderProgress();
      if (runId) lastRunId = runId;
      if (runCreatedAt) lastRunMeta = { run_created_at: runCreatedAt };
      lastDeviceResults = deviceResults;
      lastPreDeviceResults = [];
      lastRunDevices = list;
      lastComparison = [];
      const errCount = deviceResults.filter(function(r) { return getDeviceResultError(r); }).length;
      if (successCount === 0) {
        $("runStatus").textContent = "PRE completed but all " + total + " devices failed. Not saved. Fix errors and run again.";
      } else {
        $("runStatus").textContent = "PRE completed. " + total + " devices, " + errCount + " errors. Saved: " + preReportName((fabricSel && fabricSel.value) ? fabricSel.value.trim() : "", (roleSel && roleSel.value) ? roleSel.value.trim() : "", list.length) + ". Run POST for these devices when ready.";
      }
      $("runResult").textContent = JSON.stringify(deviceResults, null, 2);
      showResultsTable(true);
      renderResultsTable();
      renderShortfall(deviceResults);
      renderConsistency(lastRunDevices, deviceResults);
      renderFlappedPorts24h(deviceResults);
      var mainReportNameInp = document.getElementById("mainReportNameInput");
      if (mainReportNameInp) mainReportNameInp.value = successCount > 0 ? preReportName((fabricSel && fabricSel.value) ? fabricSel.value.trim() : "", (roleSel && roleSel.value) ? roleSel.value.trim() : "", list.length) : "";
      $("runBtn").disabled = false;
      var runPostBtn = document.getElementById("runPostBtn");
      if (runPostBtn) runPostBtn.style.display = "";
    }

    function updateRunPostButtonVisibility() {
      var runPostBtn = document.getElementById("runPostBtn");
      if (!runPostBtn) return;
      var phase = ($("phase").value || "PRE").toUpperCase();
      runPostBtn.style.display = (lastRunId && phase === "PRE") ? "" : "none";
    }

    $("runBtn").addEventListener("click", runPhase);
    var runPostBtnEl = document.getElementById("runPostBtn");
    if (runPostBtnEl) runPostBtnEl.addEventListener("click", function() {
      $("phase").value = "POST";
      updateRunPostButtonVisibility();
      runPhase();
    });
    $("showRunDiffSelect").addEventListener("change", onShowRunDiffSelect);

    /** Format ISO date string to DD-MM-YYYY HH:MM using browser local time */
    function formatLocalDateTime(isoStr) {
      if (!isoStr) return "";
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return isoStr;
      const day = String(d.getDate()).padStart(2, "0");
      const month = String(d.getMonth() + 1).padStart(2, "0");
      const year = d.getFullYear();
      const hour = String(d.getHours()).padStart(2, "0");
      const min = String(d.getMinutes()).padStart(2, "0");
      return day + "-" + month + "-" + year + " " + hour + ":" + min;
    }
    function getShowRunRaw(deviceResult) {
      if (!deviceResult || !Array.isArray(deviceResult.commands)) return "";
      const entry = deviceResult.commands.find(function(c) { return (c.command_id || "").indexOf("show_run") !== -1; });
      if (!entry || entry.raw == null) return "";
      if (typeof entry.raw === "string") return entry.raw;
      if (typeof entry.raw === "object") return JSON.stringify(entry.raw);
      return String(entry.raw);
    }
    function fillShowRunDiffDropdown() {
      const wrap = $("showRunDiffWrap");
      const sel = $("showRunDiffSelect");
      if (!lastPreDeviceResults.length || !lastDeviceResults.length) {
        wrap.style.display = "none";
        return;
      }
      wrap.style.display = "block";
      sel.innerHTML = lastDeviceResults.map(function(r, i) { return "<option value=\"" + i + "\">" + escapeHtml(r.hostname || r.ip || "Device " + (i+1)) + "</option>"; }).join("");
      if (sel.options.length) sel.dispatchEvent(new Event("change"));
    }
    async function onShowRunDiffSelect() {
      const idx = parseInt($("showRunDiffSelect").value, 10);
      if (isNaN(idx) || idx < 0 || idx >= lastPreDeviceResults.length || idx >= lastDeviceResults.length) {
        $("showRunDiffOut").textContent = "";
        return;
      }
      const preRaw = getShowRunRaw(lastPreDeviceResults[idx]);
      const postRaw = getShowRunRaw(lastDeviceResults[idx]);
      try {
        const r = await fetch(API + "/api/diff", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pre: preRaw, post: postRaw }),
        });
        const d = await r.json();
        $("showRunDiffOut").textContent = (d.diff || "") || "(no diff)";
      } catch (e) {
        $("showRunDiffOut").textContent = "Error: " + e.message;
      }
    }
    function showResultsTable(show) {
      $("resultsToolbar").style.display = show ? "flex" : "none";
      var exportWrap = document.getElementById("resultsExportWrap");
      if (exportWrap) exportWrap.style.display = show ? "flex" : "none";
      var detailsEl = document.getElementById("resultsTableDetails");
      if (detailsEl) detailsEl.style.display = show ? "block" : "none";
      $("resultsTableWrap").style.display = show ? "block" : "none";
    }
    /** Parse ISIS string: "up/ready" (e.g. 174/176) -> { up, ready }; single number -> { up, ready: null }. */
    function parseIsisUpReady(isisStr) {
      if (isisStr == null || isisStr === "") return { up: NaN, ready: null };
      var s = String(isisStr).trim();
      var slash = s.indexOf("/");
      if (slash !== -1) {
        var up = parseInt(s.substring(0, slash).trim(), 10);
        var ready = parseInt(s.substring(slash + 1).trim(), 10);
        return { up: isNaN(up) ? NaN : up, ready: isNaN(ready) ? null : ready };
      }
      var n = parseInt(s, 10);
      return { up: isNaN(n) ? NaN : n, ready: null };
    }
    function isInterfaceDown(state) {
      if (state == null || state === "") return true;
      var u = String(state).trim().toLowerCase();
      return u !== "connected" && u !== "up";
    }
    /** Extract plain description string; value may be string or { description: "..." }. */
    function getDescriptionValue(val) {
      if (val == null) return "";
      if (typeof val === "string") return val.trim();
      if (typeof val === "object" && val && val.description != null) return String(val.description).trim();
      return "";
    }
    /** Return Set of interface names that have IS-IS or BGP config (from parsed rows + running-config). */
    function getProtocolInterfaces(deviceResult) {
      var set = new Set();
      var flat = (deviceResult && deviceResult.parsed_flat) || {};
      var isisRows = flat.isis_interface_rows || flat.isis_adjacency_rows || [];
      if (Array.isArray(isisRows)) isisRows.forEach(function(row) { if (row && row.interface) set.add(String(row.interface).trim()); });
      var runText = getShowRunRaw(deviceResult);
      if (!runText || typeof runText !== "string") return set;
      var lines = runText.split(/\r?\n/);
      var neighborIps = [];
      var inBgp = false;
      for (var i = 0; i < lines.length; i++) {
        var trimmed = lines[i].trim();
        if (/^router\s+bgp\s+/i.test(trimmed)) inBgp = true;
        else if (inBgp && /^\s*neighbor\s+\S+/.test(trimmed)) {
          var ipMatch = trimmed.match(/neighbor\s+([\d.]+)/i);
          if (ipMatch) neighborIps.push(ipMatch[1]);
        } else if (inBgp && trimmed && !/^\s*(neighbor|remote-as|description|update-source|ebgp-multihop|password|address-family|\d)/i.test(trimmed)) inBgp = false;
      }
      var inInterface = false;
      var currentIface = "";
      var blockLines = [];
      for (var j = 0; j < lines.length; j++) {
        var line = lines[j];
        var t = line.trim();
        var ifaceMatch = t.match(/^interface\s+(\S+)/i);
        if (ifaceMatch) {
          if (inInterface && currentIface) {
            var block = blockLines.join(" ").toLowerCase();
            if (/ip\s+router\s+isis|isis\s+enable|isis\s+circuit-type|router\s+isis/.test(block)) set.add(currentIface);
            else for (var n = 0; n < neighborIps.length; n++) { if (block.indexOf("ip address " + neighborIps[n]) !== -1 || block.indexOf("ip address " + neighborIps[n] + "/") !== -1) { set.add(currentIface); break; } }
          }
          inInterface = true;
          currentIface = ifaceMatch[1];
          blockLines = [t];
        } else if (inInterface && (t === "!" || t.match(/^interface\s+/))) {
          var block = blockLines.join(" ").toLowerCase();
          if (/ip\s+router\s+isis|isis\s+enable|isis\s+circuit-type|router\s+isis/.test(block)) set.add(currentIface);
          else for (var n = 0; n < neighborIps.length; n++) { if (block.indexOf("ip address " + neighborIps[n]) !== -1 || block.indexOf("ip address " + neighborIps[n] + "/") !== -1) { set.add(currentIface); break; } }
          if (t.match(/^interface\s+/)) { var m = t.match(/interface\s+(\S+)/i); if (m) { currentIface = m[1]; blockLines = [t]; } } else inInterface = false;
        } else if (inInterface) blockLines.push(t);
      }
      if (inInterface && currentIface) {
        var block = blockLines.join(" ").toLowerCase();
        if (/ip\s+router\s+isis|isis\s+enable|isis\s+circuit-type|router\s+isis/.test(block)) set.add(currentIface);
        else for (var n = 0; n < neighborIps.length; n++) { if (block.indexOf("ip address " + neighborIps[n]) !== -1 || block.indexOf("ip address " + neighborIps[n] + "/") !== -1) { set.add(currentIface); break; } }
      }
      return set;
    }
    /** Parse run config for BGP: interface -> { peer_group, route_map_in, route_map_out } from neighbor update-source. */
    function getBgpInterfaceInfo(runText) {
      var out = {};
      if (!runText || typeof runText !== "string") return out;
      var lines = runText.split(/\r?\n/);
      var inBgp = false;
      var curNeighbor = null;
      var curPeerGroup = "";
      var curRouteMapIn = "";
      var curRouteMapOut = "";
      var curUpdateSource = "";
      for (var i = 0; i < lines.length; i++) {
        var t = lines[i].trim();
        if (/^router\s+bgp\s+/i.test(t)) { inBgp = true; curNeighbor = null; continue; }
        if (!inBgp) continue;
        if (t.match(/^!\s*$/) || (t && !t.startsWith(" ") && !t.startsWith("\t") && !/^\d/.test(t) && !/^(neighbor|address-family|exit|router\s)/i.test(t))) { inBgp = false; continue; }
        var neighborMatch = t.match(/^\s*neighbor\s+(\S+)\s+(\S+)/i);
        if (neighborMatch) {
          if (curNeighbor && curUpdateSource) { if (!out[curUpdateSource]) out[curUpdateSource] = { peer_group: curPeerGroup || "", route_map_in: curRouteMapIn || "", route_map_out: curRouteMapOut || "" }; }
          curNeighbor = neighborMatch[1];
          curPeerGroup = ""; curRouteMapIn = ""; curRouteMapOut = ""; curUpdateSource = "";
          var k2 = (neighborMatch[2] || "").toLowerCase();
          if (k2 === "peer-group") { var pm = t.match(/peer-group\s+(\S+)/i); if (pm) curPeerGroup = pm[1]; }
        }
        if (/update-source\s+/i.test(t)) { var m = t.match(/update-source\s+(\S+)/i); if (m) curUpdateSource = m[1]; }
        if (/route-map\s+\S+\s+in\s*$/i.test(t)) { var m = t.match(/route-map\s+(\S+)\s+in/i); if (m) curRouteMapIn = m[1]; }
        if (/route-map\s+\S+\s+out\s*$/i.test(t)) { var m = t.match(/route-map\s+(\S+)\s+out/i); if (m) curRouteMapOut = m[1]; }
        if (/peer-group\s+/i.test(t) && !curPeerGroup) { var m = t.match(/peer-group\s+(\S+)/i); if (m) curPeerGroup = m[1]; }
      }
      if (curNeighbor && curUpdateSource && !out[curUpdateSource]) out[curUpdateSource] = { peer_group: curPeerGroup || "", route_map_in: curRouteMapIn || "", route_map_out: curRouteMapOut || "" };
      return out;
    }
    /** Roles included in interface consistency check (same fabric+site). */
    var CONSISTENCY_ROLES = ["dci", "border-leaf", "border-gateway", "wan-edge", "wan-router", "wan edge", "wan router", "spine"];
    function roleMatchesConsistency(role) {
      if (!role) return false;
      var r = String(role).trim().toLowerCase().replace(/\s+/g, "-");
      return CONSISTENCY_ROLES.indexOf(r) !== -1 || CONSISTENCY_ROLES.indexOf(String(role).trim().toLowerCase()) !== -1;
    }
    function normalizeState(s) {
      if (s == null || s === "") return "down";
      var u = String(s).trim().toLowerCase();
      return (u === "connected" || u === "up") ? "up" : "down";
    }
    /** Compute interface consistency: group by fabric+site, find up-count or per-interface state diffs. Exclude IP and description. */
    function computeInterfaceConsistency(devices, deviceResults) {
      var groups = {};
      for (var i = 0; i < (devices || []).length; i++) {
        var d = devices[i];
        if (!d || !roleMatchesConsistency(d.role)) continue;
        var fabric = (d.fabric || "").trim() || "_";
        var site = (d.site || "").trim() || "_";
        var key = fabric + "\0" + site;
        if (!groups[key]) groups[key] = { fabric: fabric, site: site, indices: [] };
        groups[key].indices.push(i);
      }
      var report = [];
      for (var gk in groups) {
        var g = groups[gk];
        if (g.indices.length < 2) continue;
        var upCounts = [];
        var statusByIface = {};
        for (var si = 0; si < g.indices.length; si++) {
          var idx = g.indices[si];
          var res = deviceResults[idx];
          var flat = (res && res.parsed_flat) || {};
          var rows = flat.interface_status_rows || [];
          var up = 0;
          for (var ri = 0; ri < rows.length; ri++) {
            var r = rows[ri];
            var iface = (r && r.interface) ? String(r.interface).trim() : "";
            if (!iface) continue;
            var st = normalizeState(r.state);
            if (st === "up") up++;
            if (!statusByIface[iface]) statusByIface[iface] = {};
            statusByIface[iface][idx] = st;
          }
          upCounts.push({ idx: idx, up: up });
        }
        var upDiffer = upCounts.some(function(u) { return u.up !== upCounts[0].up; });
        var diffRows = [];
        for (var iface in statusByIface) {
          var states = statusByIface[iface];
          var vals = Object.keys(states).map(function(k) { return states[k]; });
          var allSame = vals.every(function(v) { return v === vals[0]; });
          if (allSame) continue;
          var bgpInfos = [];
          for (var di = 0; di < g.indices.length; di++) {
            var idx = g.indices[di];
            var runRaw = getShowRunRaw(deviceResults[idx]);
            bgpInfos.push(getBgpInterfaceInfo(runRaw)[iface] || { peer_group: "", route_map_in: "", route_map_out: "" });
          }
          var descMap = [];
          for (var di = 0; di < g.indices.length; di++) {
            var idx = g.indices[di];
            var flat = (deviceResults[idx] && deviceResults[idx].parsed_flat) || {};
            var descs = flat.interface_descriptions;
            var raw = typeof descs === "object" && descs && descs[iface] != null ? descs[iface] : null;
            descMap.push(getDescriptionValue(raw) || "—");
          }
          for (var di = 0; di < g.indices.length; di++) {
            diffRows.push({
              interface: iface,
              deviceIdx: g.indices[di],
              status: statusByIface[iface][g.indices[di]],
              description: descMap[di],
              peer_group: bgpInfos[di].peer_group,
              route_map_in: bgpInfos[di].route_map_in,
              route_map_out: bgpInfos[di].route_map_out
            });
          }
        }
        if (upDiffer || diffRows.length) report.push({ fabric: g.fabric, site: g.site, deviceIndices: g.indices, upCounts: upCounts, diffRows: diffRows });
      }
      return report;
    }
    function renderShortfall(deviceResults) {
      var wrap = $("shortfallWrap");
      var content = $("shortfallContent");
      if (!wrap || !content) return;
      var expectedBgp = parseInt(($("expectedBgp") && $("expectedBgp").value) || "", 10);
      var expectedIsisInput = parseInt(($("expectedIsis") && $("expectedIsis").value) || "", 10);
      var blocks = [];
      deviceResults.forEach(function(r) {
        var flat = r.parsed_flat || {};
        var hostname = r.hostname || r.ip || "?";
        var actualBgp = flat.established_count;
        if (typeof actualBgp !== "number") actualBgp = parseInt(flat.established_count, 10);
        if (isNaN(actualBgp)) actualBgp = null;
        var isisParsed = parseIsisUpReady(flat.ISIS);
        var actualIsis = isisParsed.up;
        var expectedIsis = (!isNaN(expectedIsisInput) && expectedIsisInput > 0) ? expectedIsisInput : (isisParsed.ready != null ? isisParsed.ready : null);
        var shortfallBgp = (expectedBgp && !isNaN(expectedBgp) && actualBgp != null && actualBgp < expectedBgp) ? (expectedBgp - actualBgp) : 0;
        var shortfallIsis = (expectedIsis != null && !isNaN(expectedIsis) && actualIsis != null && !isNaN(actualIsis) && actualIsis < expectedIsis) ? (expectedIsis - actualIsis) : 0;
        if (shortfallBgp === 0 && shortfallIsis === 0) return;
        var protocolIfaces = getProtocolInterfaces(r);
        var statusRows = flat.interface_status_rows || [];
        var descMap = flat.interface_descriptions || {};
        if (typeof descMap !== "object") descMap = {};
        var downIfaces = statusRows.filter(function(row) {
          if (!isInterfaceDown(row && row.state)) return false;
          var iface = (row && row.interface) ? String(row.interface).trim() : "";
          return iface && protocolIfaces.has(iface);
        }).map(function(row) {
          var iface = (row && row.interface) ? String(row.interface).trim() : "";
          var st = (row && row.state) ? String(row.state).trim() : "";
          var statusDisplay = isInterfaceDown(st) ? "Down" : "Up";
          return { interface: iface, status: statusDisplay, description: getDescriptionValue(descMap[iface]) };
        });
        var lines = [];
        if (shortfallBgp > 0) lines.push("BGP: expected " + expectedBgp + ", actual " + actualBgp + ", shortfall " + shortfallBgp);
        if (shortfallIsis > 0) lines.push("IS-IS: expected " + expectedIsis + " (ready), actual " + (actualIsis != null && !isNaN(actualIsis) ? actualIsis : "?") + " (up), shortfall " + shortfallIsis);
        var tableRows = downIfaces.length ? downIfaces.map(function(d) {
          return "<tr><td>" + escapeHtml(d.interface) + "</td><td><span style=\"color:var(--danger);\">" + escapeHtml(d.status) + "</span></td><td>" + escapeHtml(d.description) + "</td></tr>";
        }).join("") : "<tr><td colspan=\"3\" class=\"muted\">No DOWN interfaces with IS-IS/BGP config (or run config / interface status not available).</td></tr>";
        blocks.push("<div class=\"shortfall-device-block\"><p class=\"shortfall-device-title\"><span class=\"shortfall-device-icon\" aria-hidden=\"true\">🔴</span> " + escapeHtml(hostname) + "</p><p class=\"shortfall-lines\">" + escapeHtml(lines.join("; ")) + "</p><table class=\"results-table\"><thead><tr><th>Interface</th><th>Status</th><th>Description</th></tr></thead><tbody>" + tableRows + "</tbody></table></div>");
      });
      if (blocks.length === 0) {
        wrap.style.display = "none";
        return;
      }
      content.innerHTML = blocks.join("");
      wrap.style.display = "block";
    }
    function renderConsistency(devices, deviceResults) {
      var wrap = $("consistencyWrap");
      var content = $("consistencyContent");
      if (!wrap || !content) return;
      if (!(devices && devices.length) || !(deviceResults && deviceResults.length)) { wrap.style.display = "none"; return; }
      var report = computeInterfaceConsistency(devices, deviceResults);
      if (!report.length) { wrap.style.display = "none"; return; }
      var blocks = [];
      for (var gi = 0; gi < report.length; gi++) {
        var g = report[gi];
        var upLine = "Up counts: " + g.upCounts.map(function(u) {
          var dev = devices[u.idx];
          var name = (dev && dev.hostname) || (deviceResults[u.idx] && (deviceResults[u.idx].hostname || deviceResults[u.idx].ip)) || "?";
          return name + "=" + u.up;
        }).join(", ");
        var rows = [];
        for (var ri = 0; ri < g.diffRows.length; ri++) {
          var row = g.diffRows[ri];
          var dev = devices[row.deviceIdx];
          var res = deviceResults[row.deviceIdx];
          var name = (dev && dev.hostname) || (res && (res.hostname || res.ip)) || "?";
          rows.push({
            device: name,
            interface: row.interface,
            status: row.status,
            description: row.description != null ? row.description : "—",
            peer_group: row.peer_group || "—",
            route_map_in: row.route_map_in || "—",
            route_map_out: row.route_map_out || "—"
          });
        }
        var deviceNames = g.deviceIndices.map(function(idx) {
          var dev = devices[idx];
          var res = deviceResults[idx];
          return (dev && dev.hostname) || (res && (res.hostname || res.ip)) || "?";
        });
        var byIface = {};
        rows.forEach(function(r) {
          if (!byIface[r.interface]) byIface[r.interface] = {};
          byIface[r.interface][r.device] = { status: r.status, description: r.description, peer_group: r.peer_group, route_map_in: r.route_map_in, route_map_out: r.route_map_out };
        });
        var ifaces = Object.keys(byIface).sort();
        var headerCells = "<th>Interface</th>" + deviceNames.map(function(n) { return "<th>" + escapeHtml(n) + "</th>"; }).join("");
        var bodyRows;
        if (ifaces.length) {
          bodyRows = ifaces.map(function(iface) {
            var cells = deviceNames.map(function(devName) {
              var cell = byIface[iface][devName];
              if (!cell) return "<td class=\"muted\">—</td>";
              var status = cell.status || "—";
              var isDown = status === "down";
              var title = [cell.description, "peer_group: " + cell.peer_group, "route_map_in: " + cell.route_map_in, "route_map_out: " + cell.route_map_out].filter(Boolean).join(" | ");
              return "<td class=\"" + (isDown ? "consistency-cell-down" : "") + "\" title=\"" + escapeHtml(title) + "\">" + escapeHtml(status) + "</td>";
            }).join("");
            return "<tr><td>" + escapeHtml(iface) + "</td>" + cells + "</tr>";
          }).join("");
        } else {
          bodyRows = "<tr><td colspan=\"" + (deviceNames.length + 1) + "\" class=\"muted\">No per-interface state diff (only up-count diff).</td></tr>";
        }
        blocks.push("<div class=\"consistency-group-block\"><p class=\"consistency-group-title\">Fabric: " + escapeHtml(g.fabric) + " — Site: " + escapeHtml(g.site) + "</p><p class=\"shortfall-lines\">" + escapeHtml(upLine) + "</p><table class=\"results-table consistency-table\"><thead><tr>" + headerCells + "</tr></thead><tbody>" + bodyRows + "</tbody></table></div>");
      }
      content.innerHTML = blocks.join("");
      wrap.style.display = "block";
    }
    var FLAPPED_24H_SEC = 24 * 3600;
    function renderFlappedPorts24h(deviceResults) {
      var nowEpoch = Date.now() / 1000;
      var rows = [];
      (deviceResults || []).forEach(function(r) {
        var hostname = (r.hostname != null && r.hostname !== "") ? String(r.hostname) : (r.ip || "?");
        var flat = r.parsed_flat || {};
        var statusRows = flat.interface_flapped_rows && flat.interface_flapped_rows.length ? flat.interface_flapped_rows : (flat.interface_status_rows || []);
        statusRows.forEach(function(row) {
          if (!row || typeof row !== "object") return;
          var epoch = row.last_status_change_epoch;
          if (epoch == null || typeof epoch !== "number") return;
          if ((nowEpoch - epoch) > FLAPPED_24H_SEC) return;
          rows.push({
            hostname: hostname,
            interface: (row.interface != null ? String(row.interface) : "").trim(),
            description: (row.description != null ? String(row.description) : "").trim() || "-",
            state: (row.state != null ? String(row.state) : "").trim() || "-",
            last_link_flapped: (row.last_link_flapped != null ? String(row.last_link_flapped) : "").trim() || "-",
            flap_counter: (row.flap_counter != null ? String(row.flap_counter) : row.flap_count != null ? String(row.flap_count) : "").trim() || "-"
          });
        });
      });
      var headerHtml = "<th>Hostname</th><th>Interface</th><th>Description</th><th>Last flap time</th><th>Flap counter</th>";
      var bodyHtml;
      if (rows.length === 0) {
        bodyHtml = "<tr><td colspan=\"5\" class=\"muted\">Son 24 saat i&ccedil;inde flapped interface yok.</td></tr>";
      } else {
        bodyHtml = rows.map(function(row) {
          return "<tr><td>" + escapeHtml(row.hostname) + "</td><td>" + escapeHtml(row.interface) + "</td><td>" + escapeHtml(row.description) + "</td><td>" + escapeHtml(row.last_link_flapped) + "</td><td>" + escapeHtml(row.flap_counter) + "</td></tr>";
        }).join("");
      }
      var wrap = document.getElementById("flappedPortsWrap");
      var thead = document.getElementById("flappedPortsThead");
      var tbody = document.getElementById("flappedPortsTbody");
      if (wrap && thead && tbody) {
        thead.innerHTML = headerHtml;
        tbody.innerHTML = bodyHtml;
        wrap.style.display = "block";
      }
      var wrapRes = document.getElementById("flappedPortsWrapResults");
      var theadRes = document.getElementById("flappedPortsTheadResults");
      var tbodyRes = document.getElementById("flappedPortsTbodyResults");
      if (wrapRes && theadRes && tbodyRes) {
        theadRes.innerHTML = headerHtml;
        tbodyRes.innerHTML = bodyHtml;
        wrapRes.style.display = "block";
      }
    }
    function isScalarForTable(v) {
      if (v === null || v === undefined) return true;
      if (Array.isArray(v)) return false;
      return typeof v !== "object";
    }
    function renderResultsTable() {
      const data = lastDeviceResults;
      if (!data.length) {
        showResultsTable(false);
        return;
      }
      showResultsTable(true);
      const fixedCols = ["hostname", "ip", "vendor", "model", "error"];
      const hasPost = lastComparison && lastComparison.length > 0;
      const allParsedKeys = [];
      data.forEach(r => {
        const flat = r.parsed_flat || {};
        Object.keys(flat).forEach(k => { if (isScalarForTable(flat[k]) && !allParsedKeys.includes(k)) allParsedKeys.push(k); });
      });
      if (selectedParsedColumns.length === 0 && allParsedKeys.length) selectedParsedColumns = allParsedKeys.slice();
      const columns = fixedCols.concat(selectedParsedColumns.filter(k => allParsedKeys.includes(k) || data.some(r => isScalarForTable((r.parsed_flat || {})[k]))));
      let rows = data.map((r, idx) => {
        const err = getDeviceResultError(r);
        if (err) {
          return {
            hostname: (r.hostname != null && r.hostname !== "") ? String(r.hostname) : (r.ip || "?"),
            ip: (r.ip != null && r.ip !== "") ? String(r.ip) : "",
            vendor: (r.vendor != null && r.vendor !== "") ? String(r.vendor) : "",
            model: (r.model != null && r.model !== "") ? String(r.model) : "",
            error: err,
            _index: idx,
            _isError: true
          };
        }
        const row = { _index: idx, error: "" };
        if (r.hostname != null && r.hostname !== "") row.hostname = r.hostname;
        if (r.ip != null && r.ip !== "") row.ip = r.ip;
        if (r.vendor != null && r.vendor !== "") row.vendor = r.vendor;
        if (r.model != null && r.model !== "") row.model = r.model;
        const flat = r.parsed_flat || {};
        Object.keys(flat).forEach(k => { if (isScalarForTable(flat[k]) && flat[k] != null && flat[k] !== "") row[k] = flat[k]; });
        return row;
      });
      columnFilters = columnFilters || {};
      columns.forEach(col => {
        const f = columnFilters[col];
        if (f && (f.value || "").trim()) {
          const v = (f.value || "").trim().toLowerCase();
          const typ = (f.type || "in").toLowerCase();
          rows = rows.filter(row => {
            const cell = String(row[col] ?? "").toLowerCase();
            const has = cell.indexOf(v) >= 0;
            return typ === "not-in" ? !has : has;
          });
        }
      });
      if (sortCol && columns.includes(sortCol)) {
        rows.sort((a, b) => {
          const va = a[sortCol]; const vb = b[sortCol];
          const sa = va == null ? "" : String(va);
          const sb = vb == null ? "" : String(vb);
          const c = sa.localeCompare(sb, undefined, { numeric: true });
          return sortDir === "asc" ? c : -c;
        });
      }
      var resultsTableEl = document.getElementById("resultsTable");
      var resultsWrap = resultsTableEl ? resultsTableEl.parentElement : null;
      if (resultsWrap && resultsTableEl) {
        var chipsBar = resultsWrap.querySelector(".filter-chips-bar");
        if (!chipsBar) { chipsBar = document.createElement("div"); chipsBar.className = "filter-chips-bar"; resultsWrap.insertBefore(chipsBar, resultsTableEl); }
        chipsBar.innerHTML = "";
        columns.forEach(col => {
          const f = columnFilters[col];
          if (!f || !(f.value || "").trim()) return;
          const chip = document.createElement("span");
          chip.className = "filter-chip";
          const typ = (f.type || "in") === "not-in" ? "not-in" : "in";
          chip.textContent = col + " " + typ + " \"" + (f.value || "").trim() + "\" ";
          const xBtn = document.createElement("button");
          xBtn.type = "button";
          xBtn.className = "filter-chip-remove";
          xBtn.textContent = "\u00d7";
          xBtn.setAttribute("aria-label", "Remove filter");
          xBtn.addEventListener("click", () => { columnFilters[col] = columnFilters[col] || {}; columnFilters[col].value = ""; renderResultsTable(); });
          chip.appendChild(xBtn);
          chipsBar.appendChild(chip);
        });
      }
      const thead = $("resultsThead");
      const theadTr = document.createElement("tr");
      const filterTr = document.createElement("tr");
      filterTr.className = "filter-row";
      columns.forEach(col => {
        const th = document.createElement("th");
        th.className = "sortable";
        th.textContent = col;
        th.dataset.col = col;
        const sortSpan = document.createElement("span");
        sortSpan.className = "sort-icon";
        sortSpan.textContent = sortCol === col ? (sortDir === "asc" ? " \u25b2" : " \u25bc") : "";
        th.appendChild(sortSpan);
        th.addEventListener("click", () => {
          if (sortCol === col) sortDir = sortDir === "asc" ? "desc" : "asc";
          else { sortCol = col; sortDir = "asc"; }
          renderResultsTable();
        });
        theadTr.appendChild(th);
        const fth = document.createElement("th");
        const sel = document.createElement("select");
        sel.dataset.col = col;
        sel.innerHTML = "<option value=\"in\">in</option><option value=\"not-in\">not-in</option>";
        const f = columnFilters[col];
        if (f) { sel.value = f.type || "in"; }
        sel.addEventListener("change", () => {
          columnFilters[col] = columnFilters[col] || {}; columnFilters[col].type = sel.value; renderResultsTable();
        });
        const inp = document.createElement("input");
        inp.type = "text";
        inp.placeholder = "Filter\u2026 Enter to apply";
        inp.dataset.col = col;
        if (f && f.value) inp.value = f.value;
        inp.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            columnFilters[col] = columnFilters[col] || {}; columnFilters[col].type = sel.value; columnFilters[col].value = inp.value.trim(); renderResultsTable();
          }
        });
        fth.appendChild(sel);
        fth.appendChild(inp);
        filterTr.appendChild(fth);
      });
      thead.innerHTML = "";
      thead.appendChild(theadTr);
      thead.appendChild(filterTr);
      const tbody = $("resultsTbody");
      tbody.innerHTML = rows.map(row => {
        const idx = row._index;
        const comp = (hasPost && lastComparison[idx]) ? lastComparison[idx].diff : null;
        const trClass = row._isError ? " class=\"row-error\"" : "";
        return "<tr" + trClass + ">" + columns.map(col => {
          const val = row[col] != null && row[col] !== "" ? String(row[col]) : "";
          if (col === "hostname" && row._isError) {
            return "<td class=\"device-error-cell\"><span class=\"device-error-icon\" title=\"" + escapeHtml(row.error || "") + "\">\u2715</span> " + escapeHtml(val) + "</td>";
          }
          if (col === "error") {
            return "<td class=\"cell-error\" title=\"" + escapeHtml(val) + "\">" + escapeHtml(val) + "</td>";
          }
          if (fixedCols.indexOf(col) >= 0) {
            return "<td>" + escapeHtml(val) + "</td>";
          }
          if (hasPost && comp && (comp[col] || lastPreDeviceResults[idx])) {
            const preFlat = (lastPreDeviceResults[idx] || {}).parsed_flat || {};
            const postFlat = (lastDeviceResults[idx] || {}).parsed_flat || {};
            const preVal = comp[col] ? comp[col].pre : preFlat[col];
            const postVal = comp[col] ? comp[col].post : postFlat[col];
            const changed = comp[col] != null;
            const cls = changed ? "diff-cell-changed" : "diff-cell-same";
            const preStr = preVal != null && preVal !== "" ? String(preVal) : "(empty)";
            const postStr = postVal != null && postVal !== "" ? String(postVal) : "(empty)";
            const preSafe = escapeHtml(preStr).replace(/"/g, "&quot;");
            const postSafe = escapeHtml(postStr).replace(/"/g, "&quot;");
            const colSafe = escapeHtml(col).replace(/"/g, "&quot;");
            return "<td class=\"" + cls + "\" data-diff-pre=\"" + preSafe + "\" data-diff-post=\"" + postSafe + "\" data-diff-col=\"" + colSafe + "\" role=\"button\" tabindex=\"0\">" + escapeHtml(val) + "</td>";
          }
          return "<td>" + escapeHtml(val) + "</td>";
        }).join("") + "</tr>";
      }).join("");
      var wrap = document.getElementById("resultsTableWrap");
      if (wrap && !wrap._diffPopupBound) {
        wrap._diffPopupBound = true;
        wrap.addEventListener("click", function(e) {
          var td = e.target && e.target.closest ? e.target.closest("td[data-diff-pre]") : null;
          if (!td) return;
          e.preventDefault();
          var pre = td.getAttribute("data-diff-pre");
          var post = td.getAttribute("data-diff-post");
          var col = td.getAttribute("data-diff-col");
          var pop = document.getElementById("diffPopup");
          var titleEl = document.getElementById("diffPopupTitle");
          var preEl = document.getElementById("diffPopupPre");
          var postEl = document.getElementById("diffPopupPost");
          if (pop && preEl && postEl) {
            if (titleEl) titleEl.textContent = (col || "Value") + " — PRE vs POST";
            preEl.textContent = (pre !== undefined && pre !== null) ? pre : "(empty)";
            postEl.textContent = (post !== undefined && post !== null) ? post : "(empty)";
            pop.classList.add("open");
            pop.setAttribute("aria-hidden", "false");
          }
        });
      }
    }
    (function initDiffPopupClose() {
      var pop = document.getElementById("diffPopup");
      var closeBtn = document.getElementById("diffPopupClose");
      function closeDiffPopup() {
        if (pop) { pop.classList.remove("open"); pop.setAttribute("aria-hidden", "true"); }
      }
      if (closeBtn) closeBtn.addEventListener("click", closeDiffPopup);
      document.addEventListener("click", function(e) {
        if (pop && pop.classList.contains("open") && e.target && !pop.contains(e.target) && !(e.target.closest && e.target.closest("td[data-diff-pre]"))) closeDiffPopup();
      });
    })();

    const CUSTOM_CMD_COLS = ["hostname", "output"];
    function renderCustomCommandTable() {
      const thead = $("customCommandThead");
      const tbody = $("customCommandTbody");
      if (!thead || !tbody) return;
      let rows = lastCustomCommandResults.slice();
      CUSTOM_CMD_COLS.forEach(function(col) {
        const f = customCommandColumnFilters[col];
        if (!f || !(f.value || "").trim()) return;
        const val = (f.value || "").trim().toLowerCase();
        const typ = f.type || "in";
        rows = rows.filter(function(r) {
          const cell = (r[col] != null ? String(r[col]) : "").toLowerCase();
          const has = cell.indexOf(val) !== -1;
          return typ === "in" ? has : !has;
        });
      });
      if (customCommandSortCol && CUSTOM_CMD_COLS.includes(customCommandSortCol)) {
        rows.sort(function(a, b) {
          const va = a[customCommandSortCol]; const vb = b[customCommandSortCol];
          const sa = (va == null ? "" : String(va));
          const sb = (vb == null ? "" : String(vb));
          const c = sa.localeCompare(sb, undefined, { numeric: true });
          return customCommandSortDir === "asc" ? c : -c;
        });
      }
      const labels = { hostname: "Device", output: "Output" };
      var customWrap = document.getElementById("customCommandOutputWrap");
      var customTableEl = customWrap ? customWrap.querySelector("#customCommandTable") : null;
      if (customWrap && customTableEl) {
        var wrapDiv = customTableEl.parentElement;
        var chipsBar = wrapDiv ? wrapDiv.querySelector(".filter-chips-bar") : null;
        if (wrapDiv && !chipsBar) { chipsBar = document.createElement("div"); chipsBar.className = "filter-chips-bar"; wrapDiv.insertBefore(chipsBar, customTableEl); }
        if (chipsBar) {
          chipsBar.innerHTML = "";
          CUSTOM_CMD_COLS.forEach(function(col) {
            var f = customCommandColumnFilters[col];
            if (!f || !(f.value || "").trim()) return;
            var chip = document.createElement("span");
            chip.className = "filter-chip";
            var typ = (f.type || "in") === "not-in" ? "not-in" : "in";
            chip.textContent = (labels[col] || col) + " " + typ + " \"" + (f.value || "").trim() + "\" ";
            var xBtn = document.createElement("button");
            xBtn.type = "button";
            xBtn.className = "filter-chip-remove";
            xBtn.textContent = "\u00d7";
            xBtn.setAttribute("aria-label", "Remove filter");
            (function(c) { xBtn.addEventListener("click", function() { customCommandColumnFilters[c] = customCommandColumnFilters[c] || {}; customCommandColumnFilters[c].value = ""; renderCustomCommandTable(); }); })(col);
            chip.appendChild(xBtn);
            chipsBar.appendChild(chip);
          });
        }
      }
      const theadTr = document.createElement("tr");
      CUSTOM_CMD_COLS.forEach(function(col) {
        const th = document.createElement("th");
        th.className = "sortable";
        th.textContent = labels[col] || col;
        const span = document.createElement("span");
        span.className = "sort-icon";
        span.textContent = customCommandSortCol === col ? (customCommandSortDir === "asc" ? " \u25b2" : " \u25bc") : "";
        th.appendChild(span);
        th.dataset.col = col;
        th.addEventListener("click", function() {
          if (customCommandSortCol === col) customCommandSortDir = customCommandSortDir === "asc" ? "desc" : "asc";
          else { customCommandSortCol = col; customCommandSortDir = "asc"; }
          renderCustomCommandTable();
        });
        theadTr.appendChild(th);
      });
      const filterTr = document.createElement("tr");
      filterTr.className = "filter-row";
      CUSTOM_CMD_COLS.forEach(function(col) {
        const fth = document.createElement("th");
        const sel = document.createElement("select");
        sel.dataset.col = col;
        sel.innerHTML = "<option value=\"in\">in</option><option value=\"not-in\">not-in</option>";
        const f = customCommandColumnFilters[col];
        if (f) sel.value = f.type || "in";
        sel.addEventListener("change", function() {
          customCommandColumnFilters[col] = customCommandColumnFilters[col] || {};
          customCommandColumnFilters[col].type = sel.value;
          renderCustomCommandTable();
        });
        const inp = document.createElement("input");
        inp.type = "text";
        inp.placeholder = "Filter\u2026 Enter to apply";
        inp.dataset.col = col;
        if (f && f.value) inp.value = f.value;
        inp.addEventListener("keydown", function(e) {
          if (e.key === "Enter") {
            customCommandColumnFilters[col] = customCommandColumnFilters[col] || {};
            customCommandColumnFilters[col].type = sel.value;
            customCommandColumnFilters[col].value = inp.value.trim();
            renderCustomCommandTable();
          }
        });
        fth.appendChild(sel);
        fth.appendChild(inp);
        filterTr.appendChild(fth);
      });
      thead.innerHTML = "";
      thead.appendChild(theadTr);
      thead.appendChild(filterTr);
      tbody.innerHTML = rows.map(function(row) {
        const deviceCell = escapeHtml(row.hostname || "") + (row.ip ? " (" + escapeHtml(row.ip) + ")" : "");
        const outputCell = "<pre style=\"margin:0; padding:0.25rem 0; font-size:0.85em; white-space:pre-wrap; word-break:break-all; max-height:240px; overflow:auto;\">" + escapeHtml(row.output || "") + "</pre>";
        return "<tr><td>" + deviceCell + "</td><td>" + outputCell + "</td></tr>";
      }).join("");
    }

    function openGearPopup() {
      const pop = $("gearPopup");
      const list = $("gearFieldList");
      get("/api/parsers/fields").then(({ fields }) => {
        const all = fields || [];
        list.innerHTML = all.map(f => "<label><input type=\"checkbox\" data-field=\"" + escapeHtml(f) + "\"" + (selectedParsedColumns.includes(f) ? " checked" : "") + " /> " + escapeHtml(f) + "</label>").join("");
        list.querySelectorAll("input[type=checkbox]").forEach(cb => {
          cb.addEventListener("change", () => {
            const field = cb.getAttribute("data-field");
            if (cb.checked) selectedParsedColumns.push(field);
            else selectedParsedColumns = selectedParsedColumns.filter(x => x !== field);
            renderResultsTable();
          });
        });
        pop.classList.toggle("show");
      }).catch(() => { list.innerHTML = "Could not load fields."; pop.classList.toggle("show"); });
    }
    $("gearBtn").addEventListener("click", function(e) {
      e.stopPropagation();
      openGearPopup();
    });
    document.addEventListener("click", function() {
      $("gearPopup").classList.remove("show");
    });
    $("gearPopup").addEventListener("click", function(e) { e.stopPropagation(); });

    fabricSel.addEventListener("change", loadSites);
    siteSel.addEventListener("change", loadHalls);
    hallSel.addEventListener("change", loadRoles);
    roleSel.addEventListener("change", loadDevices);
    function updateCustomCommandVisibility() {
      const phase = ($("phase").value || "").toUpperCase();
      const wrap = $("customCommandWrap");
      if (wrap) wrap.style.display = phase === "CUSTOM" ? "block" : "none";
      const expWrap = $("expectedCountsWrap");
      if (expWrap) expWrap.style.display = phase === "PRE" ? "inline" : "none";
      updateRunPostButtonVisibility();
    }
    $("phase").addEventListener("change", updateCustomCommandVisibility);
    updateCustomCommandVisibility();
    pingBtn.addEventListener("click", doPing);
    $("selectAll").addEventListener("click", selectAll);
    $("selectNone").addEventListener("click", selectNone);

    var PAGE_TITLES = { home: "Home", prepost: "Pre/Post Check", "prepost-results": "Pre Check — Results", nat: "NAT Lookup", findleaf: "Find Leaf", bgp: "BGP / Looking Glass", custom: "Send Custom Command", transceiver: "Transceiver Check", credential: "Credential", routemap: "DCI / WAN Routers", inventory: "Inventory", notepad: "Live Notepad", diff: "Diff Checker", subnet: "Subnet Divide Calculator", restapi: "REST API" };
    function setHeaderPageTitle(pageName) {
      var el = document.getElementById("headerPageTitle");
      if (el) el.textContent = PAGE_TITLES[pageName] || pageName || "Home";
    }
    function showPage(name) {
      const page = (name || "home").toLowerCase();
      document.querySelectorAll(".page").forEach(el => el.classList.remove("active"));
      const el = document.getElementById("page-" + page);
      if (el) el.classList.add("active");
      setHeaderPageTitle(page);
      if (page === "credential") loadCredentials();
      if (page === "inventory") loadInventoryPage();
    }
    function closeMenu() {
      var ov = document.getElementById("menuOverlay");
      var sb = document.querySelector(".menu-sidebar");
      if (ov) ov.classList.remove("open");
      if (sb) sb.classList.remove("open");
      document.body.classList.remove("menu-open");
    }
    function openMenu() {
      var ov = document.getElementById("menuOverlay");
      var sb = document.querySelector(".menu-sidebar");
      if (ov) ov.classList.add("open");
      if (sb) sb.classList.add("open");
      document.body.classList.add("menu-open");
    }
    function refreshAllPages() {
      Promise.all([
        typeof loadFabrics === "function" ? loadFabrics() : Promise.resolve(),
        typeof loadTransceiverFabrics === "function" ? loadTransceiverFabrics() : Promise.resolve()
      ]).then(function() {
        var f = document.getElementById("fabric"); if (f) f.value = "";
        if (typeof loadSites === "function") loadSites();
        var tf = document.getElementById("transceiverFabric"); if (tf) tf.value = "";
        if (typeof loadTransceiverSites === "function") loadTransceiverSites();
      });
      if (typeof loadCredentials === "function") loadCredentials();
      if (typeof loadInventoryPage === "function") loadInventoryPage();
    }
    function onHashChange() {
      closeMenu();
      const hash = (location.hash || "#home").slice(1) || "home";
      if (hash !== "notepad" && notepadPollTimer) { clearInterval(notepadPollTimer); notepadPollTimer = null; }
      showPage(hash);
      if (hash === "home") refreshAllPages();
      if (hash === "prepost") {
        renderSavedReportsList();
        if (!savedReportsOpenBound) {
          bindSavedReportsOpen();
          savedReportsOpenBound = true;
        }
      }
      if (hash === "prepost-results") initResultsPage();
      if (hash === "notepad") initNotepadPage();
      if (hash === "diff") initDiffPage();
      if (hash === "subnet") initSubnetPage();
      if (hash === "routemap") initRouterPage();
      if (hash === "transceiver") initTransceiverPage();
      if (hash === "restapi") initRestApiPage();
      if (hash === "bgp") {
        initBgpPage();
        try {
          var prefill = sessionStorage.getItem("bgpPrefillPrefix");
          if (prefill) {
            sessionStorage.removeItem("bgpPrefillPrefix");
            var inp = document.getElementById("bgpResourceInput");
            if (inp && typeof bgpLookup === "function") { inp.value = prefill; bgpLookup(); }
          }
        } catch (err) {}
      }
    }
    window.addEventListener("hashchange", onHashChange);
    window.addEventListener("load", function() { initErrorCountBtn(); initHeaderProgressDetailUi(); initCommandLogsUi(); onHashChange(); });
    const hamburgerBtn = document.getElementById("hamburgerBtn");
    const menuOverlay = document.getElementById("menuOverlay");
    const menuSidebar = document.querySelector(".menu-sidebar");
    var headerHomeBtn = document.getElementById("headerHomeBtn");
    var headerBackBtn = document.getElementById("headerBackBtn");
    if (headerHomeBtn) headerHomeBtn.addEventListener("click", function() { closeMenu(); location.hash = "home"; });
    if (headerBackBtn) headerBackBtn.addEventListener("click", function() { closeMenu(); if (window.history && window.history.length > 1) window.history.back(); else location.hash = "home"; });
    if (hamburgerBtn && menuOverlay) {
      hamburgerBtn.addEventListener("click", function(e) {
        e.preventDefault();
        e.stopPropagation();
        if (menuOverlay.classList.contains("open")) closeMenu(); else openMenu();
      });
      menuOverlay.addEventListener("click", function(e) {
        if (e.target === menuOverlay) closeMenu();
      });
      if (menuSidebar) {
        menuSidebar.querySelectorAll("nav a").forEach(function(a) {
          a.addEventListener("click", function() { closeMenu(); });
        });
      }
    }
    const findLeafBtnEl = document.getElementById("findLeafBtn");
    if (findLeafBtnEl) findLeafBtnEl.addEventListener("click", findLeafSearch);
    const natLookupBtnEl = document.getElementById("natLookupBtn");
    if (natLookupBtnEl) natLookupBtnEl.addEventListener("click", natLookupSearch);

    var bgpPageInit = false;
    var lastBgpResult = null;
    var lastBgpQuery = null;
    var lastBgplayWindow = null;
    function initBgpPage() {
      if (bgpPageInit) return;
      bgpPageInit = true;
      var lookupBtn = document.getElementById("bgpLookupBtn");
      var exportBtn = document.getElementById("bgpExportJsonBtn");
      var bgplayPrevBtn = document.getElementById("bgpBgplayPrevBtn");
      var bgplayNextBtn = document.getElementById("bgpBgplayNextBtn");
      if (lookupBtn) lookupBtn.addEventListener("click", bgpLookup);
      if (exportBtn) exportBtn.addEventListener("click", function() {
        if (!lastBgpResult) return;
        var blob = new Blob([JSON.stringify(lastBgpResult, null, 2)], { type: "application/json" });
        var a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "bgp-lookup-" + (lastBgpResult.resource || "result") + ".json";
        a.click();
        URL.revokeObjectURL(a.href);
      });
      if (bgplayPrevBtn) bgplayPrevBtn.addEventListener("click", function() { bgpFetchBgplay("prev"); });
      if (bgplayNextBtn) bgplayNextBtn.addEventListener("click", function() { bgpFetchBgplay("next"); });
      var addFavBtn = document.getElementById("bgpAddFavBtn");
      var removeFavBtn = document.getElementById("bgpRemoveFavBtn");
      if (addFavBtn) addFavBtn.addEventListener("click", function() { bgpAddCurrentToFavourites(); });
      if (removeFavBtn) removeFavBtn.addEventListener("click", function() { bgpRemoveCurrentFromFavourites(); });
      bgpRenderFavourites();
    }
    var BGP_FAV_KEY = "bgp_favourites";
    function bgpFavValue(item) { return item && (typeof item === "object" ? item.value : item); }
    function bgpFavCompany(item) { return (item && typeof item === "object" && item.company) ? item.company : "Unknown"; }
    function bgpGetFavourites() {
      try {
        var s = localStorage.getItem(BGP_FAV_KEY);
        if (!s) return [];
        var a = JSON.parse(s);
        if (!Array.isArray(a)) return [];
        return a.map(function(el) {
          if (typeof el === "object" && el && el.value != null) return { value: String(el.value), company: String(el.company || "Unknown") };
          return { value: String(el), company: "Unknown" };
        });
      } catch (e) { return []; }
    }
    function bgpSetFavourites(arr) {
      try {
        var list = Array.isArray(arr) ? arr.map(function(el) {
          var v = el && (typeof el === "object" ? el.value : el);
          var c = el && typeof el === "object" ? (el.company || "Unknown") : "Unknown";
          return { value: String(v), company: String(c) };
        }) : [];
        localStorage.setItem(BGP_FAV_KEY, JSON.stringify(list));
      } catch (e) {}
    }
    function bgpAddCurrentToFavourites() {
      var input = document.getElementById("bgpResourceInput");
      var v = (input && input.value || "").trim();
      if (!v) return;
      var fav = bgpGetFavourites();
      if (fav.some(function(x) { return bgpFavValue(x) === v; })) return;
      var statusEl = document.getElementById("bgpLookupStatus");
      var addBtn = document.getElementById("bgpAddFavBtn");
      function doAdd(company) {
        fav = bgpGetFavourites();
        if (fav.some(function(x) { return bgpFavValue(x) === v; })) return;
        fav.push({ value: v, company: company || "Unknown" });
        bgpSetFavourites(fav);
        bgpUpdateFavButtons(v);
        bgpRenderFavourites();
        if (statusEl) statusEl.textContent = "";
        if (addBtn) addBtn.disabled = false;
      }
      var companyFromResult = (lastBgpResult && lastBgpResult.status && lastBgpResult.status.as_name) ? String(lastBgpResult.status.as_name).trim() : "";
      if (companyFromResult) {
        doAdd(companyFromResult);
        return;
      }
      var asnToFetch = null;
      if (/^AS?\s*\d+$/i.test(v.replace(/\s/g, ""))) {
        asnToFetch = v.replace(/^AS\s*/i, "").trim();
      } else if (lastBgpResult && lastBgpResult.status && lastBgpResult.status.origin_as) {
        asnToFetch = String(lastBgpResult.status.origin_as).replace(/^AS/i, "").trim();
      }
      if (asnToFetch) {
        if (statusEl) statusEl.textContent = "Adding…";
        if (addBtn) addBtn.disabled = true;
        fetch(API + "/api/bgp/as-info?asn=" + encodeURIComponent(asnToFetch)).then(function(r) { return r.json(); }).then(function(d) {
          doAdd(d.name ? String(d.name).trim() : null);
        }).catch(function() {
          doAdd("Unknown");
        });
      } else {
        doAdd("Unknown");
      }
    }
    function bgpRemoveCurrentFromFavourites() {
      var input = document.getElementById("bgpResourceInput");
      var v = (input && input.value || "").trim();
      if (!v) return;
      var fav = bgpGetFavourites().filter(function(x) { return bgpFavValue(x) !== v; });
      bgpSetFavourites(fav);
      bgpUpdateFavButtons(v);
      bgpRenderFavourites();
    }
    function bgpUpdateFavButtons(currentValue) {
      var addBtn = document.getElementById("bgpAddFavBtn");
      var removeBtn = document.getElementById("bgpRemoveFavBtn");
      var fav = bgpGetFavourites();
      var isFav = currentValue && fav.some(function(x) { return bgpFavValue(x) === currentValue; });
      if (addBtn) addBtn.style.display = currentValue && !isFav ? "inline-block" : "none";
      if (removeBtn) removeBtn.style.display = currentValue && isFav ? "inline-block" : "none";
    }
    function bgpRenderFavourites() {
      var listEl = document.getElementById("bgpFavouritesList");
      if (!listEl) return;
      var fav = bgpGetFavourites();
      var byCompany = {};
      fav.forEach(function(item) {
        var c = bgpFavCompany(item);
        if (!byCompany[c]) byCompany[c] = [];
        byCompany[c].push(bgpFavValue(item));
      });
      var html = "";
      Object.keys(byCompany).sort().forEach(function(company) {
        var values = byCompany[company];
        var nameShort = company.length > 25 ? company.slice(0, 25) + "…" : company;
        html += "<details class=\"bgp-fav-group\" style=\"display:block; margin:0 0 0.5rem 0;\"><summary style=\"cursor:pointer; padding:0.25rem 0.5rem; background:var(--card); border:1px solid var(--border); border-radius:6px; font-size:0.85em; list-style:none;\">" + String(nameShort).replace(/</g, "&lt;") + " (" + values.length + ")</summary>";
        html += "<div class=\"bgp-fav-group-chips\" style=\"margin-top:0.25rem; margin-left:0.5rem;\">";
        values.forEach(function(val) {
          var valEsc = String(val).replace(/"/g, "&quot;");
          var valSafe = String(val).replace(/</g, "&lt;");
          var isAsn = /^AS?\s*\d+$/i.test(String(val).replace(/\s/g, ""));
          var asnParam = isAsn ? String(val).replace(/^AS\s*/i, "").trim() : "";
          if (isAsn && asnParam) {
            html += "<div class=\"bgp-fav-as-row\" style=\"margin-bottom:0.35rem;\">";
            html += "<span class=\"bgp-fav-chip\" data-value=\"" + valEsc + "\" style=\"display:inline-flex; align-items:center; margin:0 0.25rem 0.25rem 0; padding:0.2rem 0.4rem; background:var(--card); border:1px solid var(--border); border-radius:6px; font-size:0.85em; cursor:pointer;\"><span class=\"bgp-fav-label\">" + valSafe + "</span><span class=\"bgp-fav-remove\" style=\"margin-left:0.35rem; color:var(--muted);\" title=\"Remove\">×</span></span>";
            html += "<button type=\"button\" class=\"bgp-fav-as-toggle\" data-asn=\"" + asnParam.replace(/"/g, "&quot;") + "\" style=\"padding:0.15rem 0.4rem; font-size:0.8em; background:var(--card); border:1px solid var(--border); border-radius:4px; cursor:pointer; color:var(--text);\" title=\"Show announced prefixes\">▼ Prefixes</button>";
            html += "<div class=\"bgp-fav-prefix-list\" data-asn=\"" + asnParam.replace(/"/g, "&quot;") + "\" style=\"display:none; margin-top:0.25rem; margin-left:0.5rem;\"></div>";
            html += "</div>";
          } else {
            html += "<span class=\"bgp-fav-chip\" data-value=\"" + valEsc + "\" style=\"display:inline-flex; align-items:center; margin:0 0.25rem 0.25rem 0; padding:0.2rem 0.4rem; background:var(--card); border:1px solid var(--border); border-radius:6px; font-size:0.85em; cursor:pointer;\"><span class=\"bgp-fav-label\">" + valSafe + "</span><span class=\"bgp-fav-remove\" style=\"margin-left:0.35rem; color:var(--muted);\" title=\"Remove\">×</span></span>";
          }
        });
        html += "</div></details>";
      });
      listEl.innerHTML = html || "<span class=\"muted\" style=\"font-size:0.9em;\">None. Add after a lookup.</span>";
      listEl.querySelectorAll(".bgp-fav-chip").forEach(function(chip) {
        var val = chip.getAttribute("data-value");
        if (!val) return;
        var label = chip.querySelector(".bgp-fav-label");
        if (label) label.addEventListener("click", function(e) { e.stopPropagation(); var inp = document.getElementById("bgpResourceInput"); if (inp) { inp.value = val; bgpLookup(); } });
        var rm = chip.querySelector(".bgp-fav-remove");
        if (rm) rm.addEventListener("click", function(e) { e.stopPropagation(); var f = bgpGetFavourites().filter(function(x) { return bgpFavValue(x) !== val; }); bgpSetFavourites(f); bgpRenderFavourites(); bgpUpdateFavButtons(document.getElementById("bgpResourceInput") && document.getElementById("bgpResourceInput").value.trim()); });
      });
      listEl.querySelectorAll(".bgp-fav-as-toggle").forEach(function(btn) {
        var asn = btn.getAttribute("data-asn");
        if (!asn) return;
        var row = btn.closest(".bgp-fav-as-row");
        var listDiv = row ? row.querySelector(".bgp-fav-prefix-list[data-asn=\"" + asn.replace(/"/g, "&quot;") + "\"]") : null;
        btn.addEventListener("click", function() {
          if (!listDiv) return;
          var isShown = listDiv.style.display !== "none";
          listDiv.style.display = isShown ? "none" : "block";
          if (!isShown && listDiv.getAttribute("data-loaded") !== "1") {
            listDiv.setAttribute("data-loaded", "1");
            listDiv.textContent = "Loading…";
            fetch(API + "/api/bgp/announced-prefixes?asn=" + encodeURIComponent(asn)).then(function(r) { return r.json(); }).then(function(d) {
              var prefixes = (d.prefixes || []).slice(0, 100);
              if (d.error) listDiv.innerHTML = "<span class=\"muted\" style=\"font-size:0.85em;\">" + escapeHtml(d.error || "Error") + "</span>";
              else if (prefixes.length === 0) listDiv.innerHTML = "<span class=\"muted\" style=\"font-size:0.85em;\">No prefixes</span>";
              else {
                listDiv.innerHTML = prefixes.map(function(p) {
                  var pEsc = String(p).replace(/"/g, "&quot;").replace(/</g, "&lt;");
                  return "<span class=\"bgp-fav-chip bgp-fav-prefix-chip\" data-value=\"" + pEsc + "\" style=\"display:inline-flex; align-items:center; margin:0 0.2rem 0.2rem 0; padding:0.15rem 0.35rem; background:var(--bg); border:1px solid var(--border); border-radius:4px; font-size:0.8em; cursor:pointer;\">" + pEsc + "</span>";
                }).join("");
                listDiv.querySelectorAll(".bgp-fav-prefix-chip").forEach(function(c) {
                  var pVal = c.getAttribute("data-value");
                  c.addEventListener("click", function() { var inp = document.getElementById("bgpResourceInput"); if (inp) { inp.value = pVal; bgpLookup(); } });
                });
              }
            }).catch(function() { listDiv.innerHTML = "<span class=\"muted\" style=\"font-size:0.85em;\">Failed to load</span>"; });
          }
        });
      });
    }
    function bgpGetAsPathFromResult(result) {
      if (!result) return null;
      var lg = result.looking_glass;
      if (lg && !lg.error && lg.peers && lg.peers.length) {
        var p = lg.peers[0];
        var path = p.as_path;
        if (typeof path === "string") path = path.split(/\s+/).filter(Boolean).map(function(x) { return String(x).trim(); });
        if (Array.isArray(path) && path.length) return path.map(function(x) { return String(x); });
      }
      var bp = result.bgplay;
      if (bp && !bp.error && bp.path_changes && bp.path_changes.length) {
        var c = bp.path_changes[bp.path_changes.length - 1];
        var path = c.new_path || c.previous_path;
        if (Array.isArray(path) && path.length) return path.map(function(x) { return String(x); });
      }
      return null;
    }
    /** From looking-glass peers: one RRC, per prefix up to 2 best paths (shortest first). defaultPrefix used when peer.prefix is empty (e.g. RIPEStat omits it). */
    function bgpPerPrefixBestTwoPathsFromOneRouter(lg, defaultPrefix) {
      if (!lg || lg.error || !lg.peers || !lg.peers.length) return null;
      var peers = lg.peers;
      var rrcCount = {};
      peers.forEach(function(p) {
        var r = (p.rrc != null ? String(p.rrc) : "") || "?";
        rrcCount[r] = (rrcCount[r] || 0) + 1;
      });
      var chosenRrc = "";
      var maxCount = 0;
      Object.keys(rrcCount).forEach(function(r) {
        if (rrcCount[r] > maxCount) { maxCount = rrcCount[r]; chosenRrc = r; }
      });
      if (!chosenRrc) chosenRrc = (peers[0] && peers[0].rrc != null) ? String(peers[0].rrc) : "?";
      var byPrefix = {};
      var fallbackPrefix = (defaultPrefix && String(defaultPrefix).trim()) || "(query)";
      peers.forEach(function(p) {
        if ((p.rrc != null ? String(p.rrc) : "") !== chosenRrc) return;
        var prefix = (p.prefix && String(p.prefix).trim()) || fallbackPrefix;
        var path = p.as_path;
        if (typeof path === "string") path = path.split(/\s+/).filter(Boolean).map(function(x) { return String(x).trim(); });
        if (!Array.isArray(path) || path.length === 0) return;
        var pathStr = path.map(function(x) { return String(x); }).join(",");
        if (!byPrefix[prefix]) byPrefix[prefix] = { paths: {}, order: [] };
        if (!byPrefix[prefix].paths[pathStr]) {
          byPrefix[prefix].paths[pathStr] = path.map(function(x) { return String(x); });
          byPrefix[prefix].order.push(pathStr);
        }
      });
      var location = "";
      for (var i = 0; i < peers.length; i++) {
        if (String(peers[i].rrc) === chosenRrc && peers[i].location) { location = String(peers[i].location); break; }
      }
      var perPrefix = [];
      Object.keys(byPrefix).sort().forEach(function(prefix) {
        var rec = byPrefix[prefix];
        var pathList = rec.order.map(function(k) { return rec.paths[k]; });
        pathList.sort(function(a, b) { return a.length - b.length; });
        perPrefix.push({ prefix: prefix, paths: pathList.slice(0, 2) });
      });
      if (perPrefix.length === 0) return null;
      return { rrc: chosenRrc, location: location, perPrefix: perPrefix };
    }
    var bgpAsNameCache = {};
    function bgpShowAsTooltip(asn, ev) {
      var tip = document.getElementById("bgpAsTooltip");
      if (!tip) return;
      var key = String(asn).replace(/^AS/i, "");
      var show = function(name) {
        var text = "AS" + key + (name ? " " + name : " (no holder data)");
        tip.textContent = text;
        tip.style.display = "block";
        var x = (ev && ev.clientX != null) ? ev.clientX : 0;
        var y = (ev && ev.clientY != null) ? ev.clientY : 0;
        tip.style.left = (x + 12) + "px";
        tip.style.top = (y + 8) + "px";
      };
      if (bgpAsNameCache[key] !== undefined) {
        show(bgpAsNameCache[key]);
        return;
      }
      fetch(API + "/api/bgp/as-info?asn=" + encodeURIComponent(key)).then(function(r) { return r.json(); }).then(function(d) {
        var name = d.name || null;
        bgpAsNameCache[key] = name;
        show(name);
      }).catch(function() {
        show(null);
      });
    }
    function bgpHideAsTooltip() {
      var tip = document.getElementById("bgpAsTooltip");
      if (tip) tip.style.display = "none";
    }
    var bgpRouterIconSvg = "<svg class=\"bgp-router-icon\" viewBox=\"0 0 24 24\" xmlns=\"http://www.w3.org/2000/svg\"><ellipse cx=\"12\" cy=\"7.5\" rx=\"9\" ry=\"3.5\" fill=\"var(--accent)\" stroke=\"var(--border)\" stroke-width=\"0.6\"/><path d=\"M3 7.5 L3 20 L21 20 L21 7.5 Z\" fill=\"var(--accent)\" stroke=\"var(--border)\" stroke-width=\"0.6\"/><path d=\"M12 7.5 L6 3\" stroke=\"var(--text)\" stroke-width=\"1.3\" stroke-linecap=\"round\"/><polygon points=\"6,3 7.5,4.5 5,4.5\" fill=\"var(--text)\"/><path d=\"M12 7.5 L18 3\" stroke=\"var(--text)\" stroke-width=\"1.3\" stroke-linecap=\"round\"/><polygon points=\"18,3 16.5,4.5 19,4.5\" fill=\"var(--text)\"/><path d=\"M12 7.5 L6 12\" stroke=\"var(--text)\" stroke-width=\"1.3\" stroke-linecap=\"round\"/><polygon points=\"6,12 7.5,10.5 5,10.5\" fill=\"var(--text)\"/><path d=\"M12 7.5 L18 12\" stroke=\"var(--text)\" stroke-width=\"1.3\" stroke-linecap=\"round\"/><polygon points=\"18,12 16.5,10.5 19,10.5\" fill=\"var(--text)\"/></svg>";
    function bgpPathToVizHtml(path) {
      if (!path || path.length === 0) return "";
      var groups = [];
      for (var i = 0; i < path.length; i++) {
        var as = String(path[i]);
        if (groups.length && groups[groups.length - 1].as === as) groups[groups.length - 1].count++;
        else groups.push({ as: as, count: 1 });
      }
      var parts = [];
      groups.forEach(function(g, i) {
        var asEsc = escapeHtml(g.as).replace(/"/g, "&quot;");
        var label = g.count > 1 ? g.count + " × " + g.as : g.as;
        var labelShort = label.length > 10 ? label.slice(0, 9) + "…" : label;
        var title = g.count > 1 ? g.count + " × AS " + g.as : "AS " + g.as;
        parts.push("<div class=\"bgp-aspath-node\" data-as=\"" + asEsc + "\" title=\"" + escapeHtml(title) + "\">" + bgpRouterIconSvg + "<span class=\"bgp-aspath-as\">" + escapeHtml(labelShort) + "</span></div>");
        if (i < groups.length - 1) parts.push("<span class=\"bgp-aspath-arrow\" aria-hidden=\"true\">→</span>");
      });
      return parts.join("");
    }
    function bgpBindAsPathNodeListeners(container) {
      if (!container) return;
      container.querySelectorAll(".bgp-aspath-node").forEach(function(node) {
        var asn = node.getAttribute("data-as");
        if (!asn) return;
        node.addEventListener("mouseenter", function(e) { bgpShowAsTooltip(asn, e); });
        node.addEventListener("mouseleave", function() { bgpHideAsTooltip(); });
        node.addEventListener("click", function(e) { e.preventDefault(); bgpShowAsTooltip(asn, e); });
      });
    }
    function bgpRenderAsPath(result) {
      var wrap = document.getElementById("bgpAsPathWrap");
      var routerLabel = document.getElementById("bgpAsPathRouterLabel");
      var perPrefixEl = document.getElementById("bgpAsPathPerPrefix");
      if (!wrap || !perPrefixEl) return;
      var resource = (result && result.resource) ? String(result.resource).trim() : "";
      var lg = result && result.looking_glass;
      var data = bgpPerPrefixBestTwoPathsFromOneRouter(lg, resource);
      if (!data || !data.perPrefix || data.perPrefix.length === 0) {
        var fallbackPath = bgpGetAsPathFromResult(result);
        if (fallbackPath && fallbackPath.length > 0) {
          wrap.style.display = "block";
          if (routerLabel) routerLabel.textContent = "Single path (from first available source)";
          var pEsc = escapeHtml(resource || "—").replace(/"/g, "&quot;");
          var html = "<div class=\"bgp-prefix-row\"><span class=\"bgp-prefix-label\">" + pEsc + "</span>";
          html += "<div class=\"bgp-path-cell\"><span class=\"bgp-path-cell-label\">Path 1</span><div class=\"bgp-aspath-viz\">" + bgpPathToVizHtml(fallbackPath) + "</div></div>";
          html += "<div class=\"bgp-path-cell\"><span class=\"bgp-path-cell-label\">Path 2</span><div class=\"bgp-aspath-viz\"><span class=\"muted\" style=\"font-size:0.85em;\">—</span></div></div></div>";
          perPrefixEl.innerHTML = html;
          perPrefixEl.querySelectorAll(".bgp-aspath-viz").forEach(bgpBindAsPathNodeListeners);
        } else {
          wrap.style.display = "none";
        }
        return;
      }
      wrap.style.display = "block";
      var rrcText = "RRC " + data.rrc + (data.location ? " — " + data.location : "");
      if (routerLabel) routerLabel.textContent = rrcText;
      var html = "";
      data.perPrefix.forEach(function(item) {
        var pEsc = escapeHtml(item.prefix).replace(/"/g, "&quot;");
        html += "<div class=\"bgp-prefix-row\"><span class=\"bgp-prefix-label\">" + pEsc + "</span>";
        var path1 = (item.paths && item.paths[0]) || [];
        var path2 = (item.paths && item.paths[1]) || [];
        html += "<div class=\"bgp-path-cell\"><span class=\"bgp-path-cell-label\">Path 1</span><div class=\"bgp-aspath-viz\">" + bgpPathToVizHtml(path1) + "</div></div>";
        html += "<div class=\"bgp-path-cell\"><span class=\"bgp-path-cell-label\">Path 2</span><div class=\"bgp-aspath-viz\">" + (path2.length ? bgpPathToVizHtml(path2) : "<span class=\"muted\" style=\"font-size:0.85em;\">—</span>") + "</div></div>";
        html += "</div>";
      });
      perPrefixEl.innerHTML = html;
      perPrefixEl.querySelectorAll(".bgp-aspath-viz").forEach(bgpBindAsPathNodeListeners);
    }
    function bgpBuildQuery() {
      var input = document.getElementById("bgpResourceInput");
      var raw = (input && input.value || "").trim();
      if (!raw) return null;
      var isAsn = /^AS?\d+$/i.test(raw.replace(/\s/g, ""));
      var param = isAsn ? "asn" : "prefix";
      var value = isAsn ? raw.replace(/^AS\s*/i, "").trim() : raw;
      return param + "=" + encodeURIComponent(value);
    }
    function bgpRenderLookingGlass(lg) {
      var wrap = document.getElementById("bgpLookingGlassWrap");
      var statusEl = document.getElementById("bgpLookingGlassStatus");
      var body = document.getElementById("bgpLookingGlassBody");
      if (!wrap || !body) return;
      if (lg.error) {
        wrap.style.display = "block";
        if (statusEl) statusEl.textContent = lg.error;
        body.innerHTML = "";
        return;
      }
      var peers = lg.peers || [];
      if (statusEl) statusEl.textContent = peers.length ? peers.length + " peer(s)." : "No peers.";
      body.innerHTML = peers.slice(0, 500).map(function(p) {
        var asPath = Array.isArray(p.as_path) ? p.as_path.join(" ") : (p.as_path || "");
        return "<tr><td>" + escapeHtml(p.rrc || "—") + "</td><td>" + escapeHtml(p.location || "—") + "</td><td>" + escapeHtml(p.ip || "—") + "</td><td>" + escapeHtml(p.as_number || "—") + "</td><td>" + escapeHtml(p.prefix || "—") + "</td></tr>";
      }).join("");
      wrap.style.display = "block";
    }
    function bgpRenderBgplay(bp) {
      var wrap = document.getElementById("bgpBgplayWrap");
      var timeEl = document.getElementById("bgpBgplayTimeRange");
      var body = document.getElementById("bgpBgplayBody");
      if (!wrap || !body) return;
      if (bp.error) {
        wrap.style.display = "block";
        if (timeEl) timeEl.textContent = bp.error;
        body.innerHTML = "";
        return;
      }
      var start = bp.query_starttime || "";
      var end = bp.query_endtime || "";
      if (timeEl) timeEl.textContent = (start && end) ? start + " — " + end : (start || end || "—");
      var changes = bp.path_changes || [];
      body.innerHTML = changes.slice(0, 200).map(function(c) {
        var prevPath = Array.isArray(c.previous_path) ? c.previous_path.join(" ") : (c.previous_path || "");
        var newPath = Array.isArray(c.new_path) ? c.new_path.join(" ") : (c.new_path || "");
        var src = [c.source_as, c.source_owner, c.source_ip].filter(Boolean).join(" / ") || "—";
        return "<tr><td>" + escapeHtml(c.timestamp || "—") + "</td><td>" + escapeHtml(c.target_prefix || "—") + "</td><td class=\"bgp-path-prev\" style=\"word-break:break-all;\">" + escapeHtml(prevPath) + "</td><td class=\"bgp-path-new\" style=\"word-break:break-all;\">" + escapeHtml(newPath) + "</td><td>" + escapeHtml(src) + "</td></tr>";
      }).join("");
      wrap.style.display = "block";
    }
    function bgpFetchBgplay(direction) {
      if (!lastBgpQuery || !lastBgplayWindow) return;
      var statusEl = document.getElementById("bgpBgplayStatus");
      if (statusEl) statusEl.textContent = "Loading...";
      var startTs = lastBgplayWindow.start_ts;
      var endTs = lastBgplayWindow.end_ts;
      var interval = 86400;
      var newStart, newEnd;
      if (direction === "prev") {
        newEnd = startTs;
        newStart = startTs - interval;
      } else {
        newStart = endTs;
        newEnd = Math.min(endTs + interval, Math.floor(Date.now() / 1000));
        if (newEnd <= newStart) { if (statusEl) statusEl.textContent = "No later data."; return; }
      }
      fetch(API + "/api/bgp/bgplay?" + lastBgpQuery + "&starttime=" + newStart + "&endtime=" + newEnd).then(function(r) { return r.json(); }).then(function(bp) {
        if (statusEl) statusEl.textContent = "";
        lastBgplayWindow = { start_ts: newStart, end_ts: newEnd };
        if (lastBgpResult && lastBgpResult.bgplay) lastBgpResult.bgplay = bp;
        bgpRenderBgplay(bp);
      }).catch(function(e) {
        if (statusEl) statusEl.textContent = "Error: " + e.message;
      });
    }
    function bgpLookup() {
      var input = document.getElementById("bgpResourceInput");
      var statusEl = document.getElementById("bgpLookupStatus");
      var cardsEl = document.getElementById("bgpStatusCards");
      var visWrap = document.getElementById("bgpVisibilityWrap");
      var diffWrap = document.getElementById("bgpHistoryDiffWrap");
      var diffOut = document.getElementById("bgpHistoryDiffOut");
      var hijackEl = document.getElementById("bgpHijackAlert");
      var exportBtn = document.getElementById("bgpExportJsonBtn");
      var lgWrap = document.getElementById("bgpLookingGlassWrap");
      var bgplayWrap = document.getElementById("bgpBgplayWrap");
      var asPathWrap = document.getElementById("bgpAsPathWrap");
      var raw = (input && input.value || "").trim();
      if (!raw) {
        if (statusEl) statusEl.textContent = "Enter a prefix or AS.";
        return;
      }
      var now = Date.now();
      if (window.lastBgpLookupTime && (now - window.lastBgpLookupTime) < 2000) {
        if (statusEl) statusEl.textContent = "Slow down — please wait a few seconds.";
        return;
      }
      window.lastBgpLookupTime = now;
      var q = bgpBuildQuery();
      if (!q) return;
      lastBgpQuery = q;
      if (statusEl) statusEl.textContent = "Loading...";
      cardsEl.style.display = "none";
      visWrap.style.display = "none";
      diffWrap.style.display = "none";
      hijackEl.style.display = "none";
      exportBtn.style.display = "none";
      if (lgWrap) lgWrap.style.display = "none";
      if (bgplayWrap) bgplayWrap.style.display = "none";
      if (asPathWrap) asPathWrap.style.display = "none";
      var wanRtrWrap = document.getElementById("bgpWanRtrWrap");
      if (wanRtrWrap) wanRtrWrap.style.display = "none";
      Promise.all([
        fetch(API + "/api/bgp/status?" + q).then(function(r) { return r.json(); }),
        fetch(API + "/api/bgp/history?" + q).then(function(r) { return r.json(); }),
        fetch(API + "/api/bgp/visibility?" + q).then(function(r) { return r.json(); }),
        fetch(API + "/api/bgp/looking-glass?" + q).then(function(r) { return r.json(); }),
        fetch(API + "/api/bgp/bgplay?" + q).then(function(r) { return r.json(); })
      ]).then(function(results) {
        var status = results[0];
        var history = results[1];
        var visibility = results[2];
        var lookingGlass = results[3];
        var bgplay = results[4];
        lastBgpResult = { resource: raw, status: status, history: history, visibility: visibility, looking_glass: lookingGlass, bgplay: bgplay };
        if (statusEl) statusEl.textContent = "";
        if (status.error) {
          if (statusEl) statusEl.textContent = status.error;
          if (typeof addDeviceEvent === "function") addDeviceEvent("warn", "BGP", status.error);
          return;
        }
        cardsEl.style.display = "grid";
        var html = "";
        html += "<div class=\"card\" style=\"padding:0.75rem;\"><strong>Announced</strong><br><span style=\"color:var(--success);\">" + (status.announced ? "Yes" : "No") + "</span></div>";
        html += "<div class=\"card\" style=\"padding:0.75rem;\"><strong>Withdrawn</strong><br><span>" + (status.withdrawn ? "Yes" : "No") + "</span></div>";
        html += "<div class=\"card\" style=\"padding:0.75rem;\"><strong>Origin AS</strong><br>" + escapeHtml(status.origin_as || "—") + (status.as_name ? " <span class=\"muted\">(" + escapeHtml(status.as_name) + ")</span>" : "") + "</div>";
        html += "<div class=\"card\" style=\"padding:0.75rem;\"><strong>RPKI</strong><br>" + escapeHtml(status.rpki_status || "Unknown") + "</div>";
        cardsEl.innerHTML = html;
        var pct = (visibility && visibility.percentage != null) ? visibility.percentage : null;
        var seeing = (visibility && visibility.probes_seeing != null) ? visibility.probes_seeing : (status.visibility_summary && status.visibility_summary.peers_seeing);
        var total = (visibility && visibility.total_probes != null) ? visibility.total_probes : (status.visibility_summary && status.visibility_summary.total_peers);
        if (pct == null && seeing != null && total && total > 0) pct = Math.round(100 * seeing / total);
        if ((seeing != null || total != null || (pct != null && pct >= 0)) && !status.error) {
          visWrap.style.display = "block";
          var visText = document.getElementById("bgpVisibilityText");
          var visFill = document.getElementById("bgpVisFill");
          if (visText) visText.textContent = (seeing != null ? seeing + " of " + (total || "?") + " RIS probes" : "") + (pct != null ? " (" + pct + "%)" : "");
          if (visFill) visFill.style.width = (pct != null && pct >= 0 ? Math.min(100, pct) : 0) + "%";
        }
        if (history.current || history.previous) {
          diffWrap.style.display = "block";
          if (history.current && history.previous) {
            fetch(API + "/api/diff", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pre: history.previous, post: history.current }) })
              .then(function(r) { return r.json(); })
              .then(function(d) { if (diffOut) diffOut.textContent = d.diff || "(no diff)"; })
              .catch(function(e) { if (diffOut) diffOut.textContent = "Current:\n" + history.current + "\n\nPrevious:\n" + history.previous; });
          } else {
            diffOut.textContent = history.current || history.previous || "(no data)";
          }
        }
        var expected = (document.getElementById("bgpExpectedOrigin") && document.getElementById("bgpExpectedOrigin").value || "").trim().replace(/^AS/i, "");
        var actual = (status.origin_as || "").replace(/^AS/i, "").trim();
        if (expected && actual && expected !== actual) {
          hijackEl.style.display = "block";
          // Safe construction: use textContent for untrusted values (form input + RIPEStat).
          hijackEl.textContent = "";
          var hjStrong = document.createElement("strong");
          hjStrong.textContent = "HIJACK DETECTED";
          hijackEl.appendChild(hjStrong);
          hijackEl.appendChild(document.createTextNode(" — Expected Origin AS " + expected + ", got " + actual + "."));
        }
        bgpRenderLookingGlass(lookingGlass);
        bgpRenderBgplay(bgplay);
        bgpRenderAsPath(lastBgpResult);
        var asnMatch = raw.match(/^(?:AS)?\s*(\d+)$/i);
        var asnNum = (asnMatch && asnMatch[1]) || (status.origin_as || "").replace(/^AS/i, "").trim();
        if (asnNum) {
          var wanRtrEl = document.getElementById("bgpWanRtrWrap");
          var wanRtrStatusEl = document.getElementById("bgpWanRtrStatus");
          var wanRtrBodyEl = document.getElementById("bgpWanRtrBody");
          if (wanRtrEl) wanRtrEl.style.display = "block";
          if (wanRtrStatusEl) wanRtrStatusEl.textContent = "Searching WAN RTR devices...";
          if (wanRtrBodyEl) wanRtrBodyEl.innerHTML = "";
          fetch(API + "/api/bgp/wan-rtr-match?asn=" + encodeURIComponent(asnNum)).then(function(r) { return r.json(); }).then(function(data) {
            var list = data.matches || [];
            if (wanRtrStatusEl) wanRtrStatusEl.textContent = list.length ? list.length + " device(s) with router bgp " + asnNum + "." : "No WAN RTR device has router bgp " + asnNum + ".";
            if (wanRtrBodyEl) wanRtrBodyEl.innerHTML = list.length ? list.map(function(m) { return "<tr><td>" + escapeHtml(m.hostname || "") + "</td><td>" + escapeHtml(m.fabric || "—") + "</td><td>" + escapeHtml(m.site || "—") + "</td></tr>"; }).join("") : "<tr><td colspan=\"3\" class=\"muted\">No match.</td></tr>";
          }).catch(function(e) {
            if (wanRtrStatusEl) wanRtrStatusEl.textContent = "Error: " + (e.message || "request failed");
            if (wanRtrBodyEl) wanRtrBodyEl.innerHTML = "";
          });
        }
        bgpUpdateFavButtons(raw);
        bgpRenderFavourites();
        if (bgplay && !bgplay.error && (bgplay.query_starttime != null || bgplay.query_endtime != null)) {
          var toSec = function(x) {
            if (x == null) return null;
            if (typeof x === "number") return x;
            var ms = Date.parse(x);
            return isNaN(ms) ? null : Math.floor(ms / 1000);
          };
          lastBgplayWindow = { start_ts: toSec(bgplay.query_starttime) || 0, end_ts: toSec(bgplay.query_endtime) || 0 };
        } else {
          lastBgplayWindow = null;
        }
        exportBtn.style.display = "block";
      }).catch(function(e) {
        if (statusEl) statusEl.textContent = "Error: " + e.message;
        if (typeof addDeviceEvent === "function") addDeviceEvent("fail", "BGP", e.message);
      });
    }

    var routerPageInit = false;
    var routerDevicesCache = [];
    var routerTableRows = [];
    var routerTableSortCol = null;
    var routerTableSortDir = "asc";
    var routerTableFilters = {};
    var routerTableVisibleCols = { peer_group: true, route_map_in: true, route_map_out: true, devices: true };
    var routerHighlightPrefix = "";
    function initRouterPage() {
      if (routerPageInit) return;
      routerPageInit = true;
      var scopeSel = document.getElementById("routerScope");
      var listEl = document.getElementById("routerDeviceList");
      var compareBtn = document.getElementById("routerCompareBtn");
      var statusEl = document.getElementById("routerStatus");
      var tableWrap = document.getElementById("routerTableWrap");
      var tableBody = document.getElementById("routerTableBody");
      var prefixInput = document.getElementById("routerPrefixInput");
      var prefixSearchBtn = document.getElementById("routerPrefixSearchBtn");
      var prefixStatusEl = document.getElementById("routerPrefixStatus");
      if (!scopeSel || !listEl) return;

      function loadRouterDevices() {
        var scope = (scopeSel && scopeSel.value) || "";
        if (!scope) { listEl.innerHTML = ""; routerDevicesCache = []; if (compareBtn) compareBtn.disabled = true; return; }
        fetch(API + "/api/router-devices?scope=" + encodeURIComponent(scope)).then(function(r) { return r.json(); }).then(function(data) {
          routerDevicesCache = data.devices || [];
          listEl.innerHTML = routerDevicesCache.map(function(d, i) {
            return "<div class=\"device-row\" data-index=\"" + i + "\"><input type=\"checkbox\" data-index=\"" + i + "\" /><span class=\"hostname\">" + escapeHtml(d.hostname || "") + "</span><span class=\"ip\">" + escapeHtml(d.ip || "") + "</span></div>";
          }).join("");
          if (compareBtn) compareBtn.disabled = routerDevicesCache.length === 0;
          if (statusEl) statusEl.textContent = routerDevicesCache.length + " device(s). Select and click Compare.";
        }).catch(function() {
          listEl.innerHTML = ""; routerDevicesCache = [];
          if (statusEl) statusEl.textContent = "Failed to load devices.";
        });
      }

      function getSelectedRouterDevices() {
        var out = [];
        if (!listEl) return out;
        listEl.querySelectorAll("input[type=checkbox]:checked").forEach(function(cb) {
          var i = parseInt(cb.getAttribute("data-index"), 10);
          if (!isNaN(i) && i >= 0 && i < routerDevicesCache.length) out.push(routerDevicesCache[i]);
        });
        return out;
      }

      function rowHasPrefix(row, prefix) {
        if (!prefix) return true;
        function hasInHierarchy(h) {
          for (var i = 0; i < (h || []).length; i++) {
            var pl = h[i];
            if ((pl.prefixes || []).indexOf(prefix) !== -1) return true;
          }
          return false;
        }
        return hasInHierarchy(row.hierarchy_in) || hasInHierarchy(row.hierarchy_out);
      }
      function renderRouterTable(rows) {
        routerTableRows = rows || [];
        if (!tableBody) return;
        var theadEl = document.getElementById("routerThead");
        var cols = ["peer_group", "route_map_in", "route_map_out", "devices"];
        var visibleCols = cols.filter(function(c) { return routerTableVisibleCols[c] !== false; });
        var labels = { peer_group: "Peer group", route_map_in: "Route-map IN", route_map_out: "Route-map OUT", devices: "Devices" };
        var highlightPrefix = (routerHighlightPrefix || "").trim() || null;

        var filtered = routerTableRows.filter(function(row) {
          if (highlightPrefix && !rowHasPrefix(row, highlightPrefix)) return false;
          for (var i = 0; i < cols.length; i++) {
            var col = cols[i];
            var f = routerTableFilters[col];
            if (!f || !(f.value || "").trim()) continue;
            var val = (f.value || "").trim().toLowerCase();
            var cell = col === "devices" ? (row.devices || []).join(" ") : (row[col] != null ? String(row[col]) : "");
            cell = cell.toLowerCase();
            var has = cell.indexOf(val) !== -1;
            if ((f.type || "in") === "not-in" ? has : !has) return false;
          }
          return true;
        });

        if (routerTableSortCol && cols.indexOf(routerTableSortCol) !== -1) {
          filtered = filtered.slice().sort(function(a, b) {
            var va = routerTableSortCol === "devices" ? (a.devices || []).join(",") : (a[routerTableSortCol] != null ? String(a[routerTableSortCol]) : "");
            var vb = routerTableSortCol === "devices" ? (b.devices || []).join(",") : (b[routerTableSortCol] != null ? String(b[routerTableSortCol]) : "");
            var c = (va || "").localeCompare(vb || "", undefined, { numeric: true });
            return routerTableSortDir === "asc" ? c : -c;
          });
        }

        if (theadEl) {
          var tr1 = document.createElement("tr");
          var tr2 = document.createElement("tr");
          tr2.className = "filter-row";
          var routerWrap = document.getElementById("routerTableWrap");
          var routerTableEl = document.getElementById("routerTable");
          var routerTableWrapDiv = routerTableEl ? routerTableEl.parentElement : null;
          if (routerTableWrapDiv && routerTableEl) {
            var chipsBar = routerTableWrapDiv.querySelector(".filter-chips-bar");
            if (!chipsBar) { chipsBar = document.createElement("div"); chipsBar.className = "filter-chips-bar"; routerTableWrapDiv.insertBefore(chipsBar, routerTableEl); }
            chipsBar.innerHTML = "";
            visibleCols.forEach(function(col) {
              var f = routerTableFilters[col];
              if (!f || !(f.value || "").trim()) return;
              var chip = document.createElement("span");
              chip.className = "filter-chip";
              var typ = (f.type || "in") === "not-in" ? "not-in" : "in";
              chip.textContent = (labels[col] || col) + " " + typ + " \"" + (f.value || "").trim() + "\" ";
              var xBtn = document.createElement("button");
              xBtn.type = "button";
              xBtn.className = "filter-chip-remove";
              xBtn.textContent = "\u00d7";
              xBtn.setAttribute("aria-label", "Remove filter");
              (function(c) { xBtn.addEventListener("click", function() { routerTableFilters[c] = routerTableFilters[c] || {}; routerTableFilters[c].value = ""; renderRouterTable(routerTableRows); }); })(col);
              chip.appendChild(xBtn);
              chipsBar.appendChild(chip);
            });
          }
          visibleCols.forEach(function(col) {
            var th = document.createElement("th");
            th.className = "sortable";
            th.textContent = labels[col] || col;
            th.dataset.col = col;
            var span = document.createElement("span");
            span.className = "sort-icon";
            span.textContent = routerTableSortCol === col ? (routerTableSortDir === "asc" ? " \u25b2" : " \u25bc") : "";
            th.appendChild(span);
            th.addEventListener("click", function() {
              if (routerTableSortCol === col) routerTableSortDir = routerTableSortDir === "asc" ? "desc" : "asc";
              else { routerTableSortCol = col; routerTableSortDir = "asc"; }
              renderRouterTable(routerTableRows);
            });
            tr1.appendChild(th);
            var fth = document.createElement("th");
            var sel = document.createElement("select");
            sel.dataset.col = col;
            sel.innerHTML = "<option value=\"in\">in</option><option value=\"not-in\">not-in</option>";
            var f = routerTableFilters[col];
            if (f) sel.value = f.type || "in";
            sel.addEventListener("change", function() {
              routerTableFilters[col] = routerTableFilters[col] || {}; routerTableFilters[col].type = sel.value; renderRouterTable(routerTableRows);
            });
            var inp = document.createElement("input");
            inp.type = "text";
            inp.placeholder = "Filter\u2026 Enter to apply";
            if (f && f.value) inp.value = f.value;
            inp.addEventListener("keydown", function(e) {
              if (e.key === "Enter") {
                routerTableFilters[col] = routerTableFilters[col] || {}; routerTableFilters[col].type = sel.value; routerTableFilters[col].value = inp.value.trim(); renderRouterTable(routerTableRows);
              }
            });
            fth.appendChild(sel);
            fth.appendChild(inp);
            tr2.appendChild(fth);
          });
          theadEl.innerHTML = "";
          theadEl.appendChild(tr1);
          theadEl.appendChild(tr2);
        }

        function cellHtml(hier, name) {
          if (!hier.length) return "<span>" + (name || "—") + "</span>";
          var openOuter = highlightPrefix && hier.some(function(pl) { return (pl.prefixes || []).indexOf(highlightPrefix) !== -1; });
          var parts = ["<span" + (openOuter ? " class=\"search-highlight\"" : "") + ">" + (name || "—") + "</span>", "<details" + (openOuter ? " open" : "") + " style=\"cursor:pointer; margin-top:0.25rem;\"><summary>Prefix-lists (" + hier.length + ")</summary><ul style=\"margin:0.25rem 0 0 0; padding-left:1rem; list-style:none;\">"];
          hier.forEach(function(pl) {
            var plOpen = highlightPrefix && (pl.prefixes || []).indexOf(highlightPrefix) !== -1;
            parts.push("<li><details" + (plOpen ? " open" : "") + " style=\"cursor:pointer;\"><summary" + (plOpen ? " class=\"search-highlight\"" : "") + ">" + (pl.prefix_list || "—") + "</summary><ul style=\"margin:0.15rem 0 0 1rem; padding:0; list-style:disc; font-size:0.8rem;\">");
            (pl.prefixes || []).forEach(function(p) {
              parts.push("<li" + (highlightPrefix && p === highlightPrefix ? " class=\"search-highlight\"" : "") + ">" + p + "</li>");
            });
            parts.push("</ul></details></li>");
          });
          parts.push("</ul></details>");
          return parts.join("");
        }
        tableBody.innerHTML = filtered.map(function(row) {
          var hi = row.hierarchy_in || [];
          var ho = row.hierarchy_out || [];
          var devStr = (row.devices || []).join(", ");
          var cells = [];
          if (visibleCols.indexOf("peer_group") !== -1) cells.push("<td>" + (row.peer_group || "—") + "</td>");
          if (visibleCols.indexOf("route_map_in") !== -1) cells.push("<td>" + cellHtml(hi, row.route_map_in) + "</td>");
          if (visibleCols.indexOf("route_map_out") !== -1) cells.push("<td>" + cellHtml(ho, row.route_map_out) + "</td>");
          if (visibleCols.indexOf("devices") !== -1) cells.push("<td>" + devStr + "</td>");
          return "<tr>" + cells.join("") + "</tr>";
        }).join("");
        if (tableWrap) tableWrap.style.display = "block";
      }

      scopeSel.addEventListener("change", loadRouterDevices);
      var selAll = document.getElementById("routerSelectAll");
      var selNone = document.getElementById("routerSelectNone");
      if (selAll) selAll.addEventListener("click", function() { if (listEl) listEl.querySelectorAll("input[type=checkbox]").forEach(function(cb) { cb.checked = true; }); });
      if (selNone) selNone.addEventListener("click", function() { if (listEl) listEl.querySelectorAll("input[type=checkbox]").forEach(function(cb) { cb.checked = false; }); });
      var routerColBtn = document.getElementById("routerColumnToggleBtn");
      var routerColDrop = document.getElementById("routerColumnToggleDropdown");
      if (routerColBtn && routerColDrop) {
        routerColBtn.addEventListener("click", function(e) { e.stopPropagation(); routerColDrop.classList.toggle("open"); if (routerColDrop.classList.contains("open")) { ["peer_group", "route_map_in", "route_map_out", "devices"].forEach(function(col) { var cb = routerColDrop.querySelector("input[data-col=\"" + col + "\"]"); if (cb) cb.checked = routerTableVisibleCols[col] !== false; }); } });
        routerColDrop.querySelectorAll("input[data-col]").forEach(function(cb) { cb.addEventListener("change", function() { var col = cb.getAttribute("data-col"); routerTableVisibleCols[col] = cb.checked; renderRouterTable(routerTableRows); }); });
        document.addEventListener("click", function() { routerColDrop.classList.remove("open"); });
        routerColDrop.addEventListener("click", function(e) { e.stopPropagation(); });
      }
      if (compareBtn) compareBtn.addEventListener("click", function() {
        var devices = getSelectedRouterDevices();
        if (!devices.length) { if (statusEl) statusEl.textContent = "Select at least one device."; return; }
        if (statusEl) statusEl.textContent = "Loading…";
        compareBtn.disabled = true;
        fetch(API + "/api/route-map/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ devices: devices }) })
          .then(function(r) { return r.json(); })
          .then(function(data) {
            compareBtn.disabled = false;
            var errList = data.errors || [];
            errList.forEach(function(e) { addDeviceEvent("fail", e.hostname, e.error); });
            var errHosts = {};
            errList.forEach(function(e) { errHosts[(e.hostname || "").trim()] = true; });
            devices.forEach(function(d) { if (!errHosts[(d.hostname || "").trim()]) addDeviceEvent("success", d.hostname || d.ip, "Route-map OK"); });
            setGlobalDeviceErrors(errList);
            if (data.errors && data.errors.length) {
              if (statusEl) statusEl.textContent = "Done with " + data.errors.length + " error(s).";
            } else {
              if (statusEl) statusEl.textContent = "Done.";
            }
            if (data.rows && data.rows.length) {
              routerHighlightPrefix = "";
              renderRouterTable(data.rows);
            } else if (tableWrap) tableWrap.style.display = "none";
          })
          .catch(function(e) {
            compareBtn.disabled = false;
            if (statusEl) statusEl.textContent = "Error: " + (e.message || "request failed");
          });
      });
      if (prefixSearchBtn && prefixInput) prefixSearchBtn.addEventListener("click", function() {
        var prefix = (prefixInput.value || "").trim();
        if (!prefix) { if (prefixStatusEl) prefixStatusEl.textContent = "Enter a prefix (e.g. 192.168.0.0/24)."; return; }
        if (!/^(\d{1,3}\.){3}\d{1,3}\/\d{1,2}$/.test(prefix)) { if (prefixStatusEl) prefixStatusEl.textContent = "Use IP/CIDR format (e.g. 192.168.0.0/24)."; return; }
        routerHighlightPrefix = prefix;
        function doSearch() {
          var matchCount = routerTableRows.filter(function(row) { return rowHasPrefix(row, prefix); }).length;
          if (prefixStatusEl) prefixStatusEl.textContent = matchCount ? "Found " + matchCount + " row(s)." : "No matching prefix.";
          renderRouterTable(routerTableRows);
        }
        if (routerTableRows.length > 0) {
          doSearch();
          return;
        }
        var scope = (scopeSel && scopeSel.value) || "all";
        function runCompareWithDevices(devices) {
          if (!devices.length) { if (prefixStatusEl) prefixStatusEl.textContent = "No routers in scope. Select scope first."; return; }
          if (prefixStatusEl) prefixStatusEl.textContent = "Loading " + devices.length + " router(s)…";
          if (prefixSearchBtn) prefixSearchBtn.disabled = true;
          fetch(API + "/api/route-map/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ devices: devices }) })
          .then(function(r) { return r.json(); })
          .then(function(data) {
            if (prefixSearchBtn) prefixSearchBtn.disabled = false;
            var errList = data.errors || [];
            errList.forEach(function(e) { addDeviceEvent("fail", e.hostname, e.error); });
            var errHosts = {};
            errList.forEach(function(e) { errHosts[(e.hostname || "").trim()] = true; });
            devices.forEach(function(d) { if (!errHosts[(d.hostname || "").trim()]) addDeviceEvent("success", d.hostname || d.ip, "Route-map OK"); });
            setGlobalDeviceErrors(errList);
            if (data.rows && data.rows.length) {
              routerTableRows = data.rows;
              if (tableWrap) tableWrap.style.display = "block";
              doSearch();
            } else {
              if (prefixStatusEl) prefixStatusEl.textContent = "No route-map data returned.";
            }
          })
          .catch(function(e) {
            if (prefixSearchBtn) prefixSearchBtn.disabled = false;
            if (prefixStatusEl) prefixStatusEl.textContent = "Error: " + (e.message || "request failed");
          });
        }
        if (routerDevicesCache.length > 0) {
          runCompareWithDevices(routerDevicesCache);
        } else {
          if (prefixStatusEl) prefixStatusEl.textContent = "Loading scope…";
          fetch(API + "/api/router-devices?scope=" + encodeURIComponent(scope)).then(function(r) { return r.json(); }).then(function(data) {
            routerDevicesCache = data.devices || [];
            runCompareWithDevices(routerDevicesCache);
          }).catch(function() {
            if (prefixStatusEl) prefixStatusEl.textContent = "Failed to load routers.";
          });
        }
      });
    }

    var notepadPollTimer = null;
    var notepadSaveTimer = null;
    var NOTEPAD_NAME_KEY = "pergen_notepad_name";
    function initNotepadPage() {
      var ta = document.getElementById("notepadText");
      var statusEl = document.getElementById("notepadStatus");
      var leftCol = document.getElementById("notepadLeftCol");
      var nameInput = document.getElementById("notepadUserName");
      if (!ta) return;
      try {
        var savedName = localStorage.getItem(NOTEPAD_NAME_KEY);
        if (nameInput && savedName) nameInput.value = savedName;
      } catch (e) {}
      if (nameInput) { nameInput.addEventListener("change", function() { try { localStorage.setItem(NOTEPAD_NAME_KEY, nameInput.value || ""); } catch (e) {} }); nameInput.addEventListener("input", function() { try { localStorage.setItem(NOTEPAD_NAME_KEY, nameInput.value || ""); } catch (e) {} }); }
      function setStatus(msg) { if (statusEl) statusEl.textContent = msg; }
      function renderLineEditors(lineEditors) {
        if (!leftCol || !Array.isArray(lineEditors)) return;
        var lines = lineEditors.length ? lineEditors : [""];
        var rowStyle = "height:1.5em; line-height:1.5em; box-sizing:border-box; border-bottom:1px solid rgba(128,128,128,0.12); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:1rem;";
        leftCol.innerHTML = lines.map(function(u, i) {
          var num = i + 1;
          var who = (u && u.trim()) ? u : "—";
          return "<div style=\"" + rowStyle + "\" title=\"" + escapeHtml(who) + "\"><span style=\"opacity:0.7;\">" + num + "</span> " + escapeHtml(who) + "</div>";
        }).join("");
      }
      function applyNotepadData(d) {
        var content = (d && d.content != null) ? String(d.content) : "";
        var editors = (d && d.line_editors) ? d.line_editors : [];
        if (document.activeElement !== ta && ta.value !== content) ta.value = content;
        var lines = content.split("\n");
        while (editors.length < lines.length) editors.push("");
        renderLineEditors(editors.slice(0, lines.length));
      }
      function loadNotepad() {
        fetch(API + "/api/notepad").then(function(r) { return r.json(); }).then(function(d) {
          applyNotepadData(d);
          setStatus("Synced. Changes sync live for everyone.");
        }).catch(function() { setStatus("Failed to load."); });
      }
      function saveNotepad() {
        var content = ta.value;
        var user = (nameInput && nameInput.value) ? nameInput.value.trim() : "";
        if (!user) { setStatus("Enter your name above, then edit."); return; }
        try { localStorage.setItem(NOTEPAD_NAME_KEY, user); } catch (e) {}
        fetch(API + "/api/notepad", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: content, user: user })
        }).then(function(r) { return r.json(); }).then(function(d) {
          if (d && d.content != null && ta.value === content) { ta.value = d.content; if (d.line_editors) renderLineEditors(d.line_editors); }
          setStatus("Saved. Synced for everyone.");
        }).catch(function() { setStatus("Save failed."); });
      }
      loadNotepad();
      if (notepadPollTimer) clearInterval(notepadPollTimer);
      notepadPollTimer = setInterval(function() {
        if (location.hash !== "#notepad") return;
        fetch(API + "/api/notepad").then(function(r) { return r.json(); }).then(function(d) {
          if (document.activeElement !== ta) applyNotepadData(d);
        }).catch(function() {});
      }, 2000);
      ta.addEventListener("input", function() {
        if (notepadSaveTimer) clearTimeout(notepadSaveTimer);
        notepadSaveTimer = setTimeout(saveNotepad, 800);
      });
      ta.addEventListener("blur", function() { saveNotepad(); });
      ta.addEventListener("scroll", function() { if (leftCol) leftCol.scrollTop = ta.scrollTop; });
    }

    function computeLcsPairs(leftArr, rightArr) {
      var n = leftArr.length;
      var m = rightArr.length;
      var dp = [];
      for (var i = 0; i <= n; i++) { dp[i] = []; dp[i][0] = 0; }
      for (var j = 1; j <= m; j++) dp[0][j] = 0;
      for (i = 1; i <= n; i++) {
        for (j = 1; j <= m; j++) {
          if (leftArr[i - 1] === rightArr[j - 1]) dp[i][j] = dp[i - 1][j - 1] + 1;
          else dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
        }
      }
      var pairs = [];
      i = n; j = m;
      while (i > 0 && j > 0) {
        if (leftArr[i - 1] === rightArr[j - 1]) { pairs.push([i - 1, j - 1]); i--; j--; }
        else if (dp[i - 1][j] >= dp[i][j - 1]) i--;
        else j--;
      }
      return pairs.reverse();
    }
    function computeDiffRows(leftLines, rightLines) {
      var lcsPairs = computeLcsPairs(leftLines, rightLines);
      var rows = [];
      var prevI = -1, prevJ = -1;
      for (var p = 0; p < lcsPairs.length; p++) {
        var ii = lcsPairs[p][0], jj = lcsPairs[p][1];
        for (var k = prevI + 1; k < ii; k++) rows.push({ kind: "rem", left: leftLines[k], right: null, leftNum: k + 1, rightNum: null });
        for (var k = prevJ + 1; k < jj; k++) rows.push({ kind: "add", left: null, right: rightLines[k], leftNum: null, rightNum: k + 1 });
        rows.push({ kind: "same", left: leftLines[ii], right: rightLines[jj], leftNum: ii + 1, rightNum: jj + 1 });
        prevI = ii; prevJ = jj;
      }
      for (var k = prevI + 1; k < leftLines.length; k++) rows.push({ kind: "rem", left: leftLines[k], right: null, leftNum: k + 1, rightNum: null });
      for (var k = prevJ + 1; k < rightLines.length; k++) rows.push({ kind: "add", left: null, right: rightLines[k], leftNum: null, rightNum: k + 1 });
      var merged = [];
      for (var idx = 0; idx < rows.length; idx++) {
        if (rows[idx].kind === "rem" && idx + 1 < rows.length && rows[idx + 1].kind === "add") {
          merged.push({ kind: "mod", left: rows[idx].left, right: rows[idx + 1].right, leftNum: rows[idx].leftNum, rightNum: rows[idx + 1].rightNum });
          idx++;
        } else merged.push(rows[idx]);
      }
      return merged;
    }
    var diffPageInited = false;
    var diffScrollToRow = function(rowIndex) {
      var el = document.getElementById("diff-row-" + rowIndex);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };
    function initDiffPage() {
      if (diffPageInited) return;
      diffPageInited = true;
      var btn = document.getElementById("diffCheckBtn");
      var leftTa = document.getElementById("diffLeft");
      var rightTa = document.getElementById("diffRight");
      var resultEl = document.getElementById("diffResult");
      var resultWrap = document.getElementById("diffResultWrap");
      var summaryBar = document.getElementById("diffSummaryBar");
      var guideEl = document.getElementById("diffGuide");
      if (!btn || !resultEl) return;
      btn.addEventListener("click", function() {
        var left = (leftTa && leftTa.value) ? leftTa.value : "";
        var right = (rightTa && rightTa.value) ? rightTa.value : "";
        var leftLines = left.split("\n");
        var rightLines = right.split("\n");
        var rows = computeDiffRows(leftLines, rightLines);
        if (rows.length === 0) rows = [{ kind: "same", left: "", right: "", leftNum: 1, rightNum: 1 }];
        var countAdd = 0, countRem = 0, countMod = 0;
        var addIndices = [], remIndices = [], modIndices = [];
        var changeRowIndices = [];
        for (var i = 0; i < rows.length; i++) {
          if (rows[i].kind === "add") { countAdd++; addIndices.push(i); changeRowIndices.push({ i: i, kind: "add" }); }
          else if (rows[i].kind === "rem") { countRem++; remIndices.push(i); changeRowIndices.push({ i: i, kind: "rem" }); }
          else if (rows[i].kind === "mod") { countMod++; modIndices.push(i); changeRowIndices.push({ i: i, kind: "mod" }); }
        }
        var addIdx = 0, remIdx = 0, modIdx = 0;
        var rowStyle = { add: "background:rgba(16,185,129,0.18); border-left:4px solid #10b981;", rem: "background:rgba(244,63,94,0.18); border-left:4px solid #f43f5e;", mod: "background:rgba(245,158,11,0.18); border-left:4px solid #f59e0b;", same: "" };
        var table = "<table style=\"width:100%; border-collapse:collapse;\"><thead><tr><th style=\"width:2.5rem; text-align:right; padding:0.35rem 0.5rem; border-bottom:1px solid var(--border); color:var(--muted);\">Left #</th><th style=\"width:2rem; text-align:center; padding:0.35rem; border-bottom:1px solid var(--border);\"></th><th style=\"text-align:left; padding:0.35rem 0.5rem; border-bottom:1px solid var(--border);\">Left (before)</th><th style=\"width:2.5rem; text-align:right; padding:0.35rem 0.5rem; border-bottom:1px solid var(--border); color:var(--muted);\">Right #</th><th style=\"text-align:left; padding:0.35rem 0.5rem; border-bottom:1px solid var(--border);\">Right (after)</th></tr></thead><tbody>";
        for (var i = 0; i < rows.length; i++) {
          var r = rows[i];
          var style = rowStyle[r.kind] ? " style=\"" + rowStyle[r.kind] + "\"" : "";
          var leftNum = r.leftNum != null ? r.leftNum : "";
          var rightNum = r.rightNum != null ? r.rightNum : "";
          var ind = r.kind === "add" ? "<span style=\"color:#10b981;\">+</span>" : r.kind === "rem" ? "<span style=\"color:#f43f5e;\">−</span>" : r.kind === "mod" ? "<span style=\"color:#f59e0b;\">≠</span>" : "";
          table += "<tr id=\"diff-row-" + i + "\"" + style + "><td style=\"text-align:right; padding:0.35rem 0.5rem; border-bottom:1px solid rgba(128,128,128,0.2); color:var(--muted);\">" + leftNum + "</td><td style=\"text-align:center; padding:0.35rem; border-bottom:1px solid rgba(128,128,128,0.2);\">" + ind + "</td><td style=\"padding:0.35rem 0.5rem; border-bottom:1px solid rgba(128,128,128,0.2); white-space:pre-wrap; word-break:break-all;\">" + escapeHtml(r.left != null ? r.left : "") + "</td><td style=\"text-align:right; padding:0.35rem 0.5rem; border-bottom:1px solid rgba(128,128,128,0.2); color:var(--muted);\">" + rightNum + "</td><td style=\"padding:0.35rem 0.5rem; border-bottom:1px solid rgba(128,128,128,0.2); white-space:pre-wrap; word-break:break-all;\">" + escapeHtml(r.right != null ? r.right : "") + "</td></tr>";
        }
        table += "</tbody></table>";
        resultEl.innerHTML = table;
        if (summaryBar) {
          summaryBar.innerHTML = "";
          var addBtn = document.createElement("button");
          addBtn.type = "button";
          addBtn.style.cssText = "padding:0.35rem 0.75rem; background:rgba(16,185,129,0.25); color:#10b981; border:1px solid #10b981; border-radius:6px; cursor:pointer; font-size:0.9rem;";
          addBtn.textContent = "Added " + countAdd;
          addBtn.addEventListener("click", function() { if (addIndices.length) { diffScrollToRow(addIndices[addIdx % addIndices.length]); addIdx++; } });
          summaryBar.appendChild(addBtn);
          var remBtn = document.createElement("button");
          remBtn.type = "button";
          remBtn.style.cssText = "padding:0.35rem 0.75rem; background:rgba(244,63,94,0.25); color:#f43f5e; border:1px solid #f43f5e; border-radius:6px; cursor:pointer; font-size:0.9rem;";
          remBtn.textContent = "Deleted " + countRem;
          remBtn.addEventListener("click", function() { if (remIndices.length) { diffScrollToRow(remIndices[remIdx % remIndices.length]); remIdx++; } });
          summaryBar.appendChild(remBtn);
          var modBtn = document.createElement("button");
          modBtn.type = "button";
          modBtn.style.cssText = "padding:0.35rem 0.75rem; background:rgba(245,158,11,0.25); color:#f59e0b; border:1px solid #f59e0b; border-radius:6px; cursor:pointer; font-size:0.9rem;";
          modBtn.textContent = "Changed " + countMod;
          modBtn.addEventListener("click", function() { if (modIndices.length) { diffScrollToRow(modIndices[modIdx % modIndices.length]); modIdx++; } });
          summaryBar.appendChild(modBtn);
        }
        if (guideEl && changeRowIndices.length > 0) {
          guideEl.innerHTML = "";
          guideEl.style.position = "relative";
          var total = rows.length;
          changeRowIndices.forEach(function(o) {
            var m = document.createElement("div");
            var pct = total > 0 ? (o.i / total * 100) : 0;
            m.style.cssText = "position:absolute; left:2px; width:10px; height:10px; top:" + pct + "%; margin-top:-5px; background:" + (o.kind === "add" ? "rgba(16,185,129,0.7)" : o.kind === "rem" ? "rgba(244,63,94,0.7)" : "rgba(245,158,11,0.7)") + "; cursor:pointer; border-radius:2px; transform:rotate(45deg);";
            m.title = (o.kind === "add" ? "Added" : o.kind === "rem" ? "Deleted" : "Changed") + " (row " + (o.i + 1) + ")";
            m.addEventListener("click", (function(idx) { return function() { diffScrollToRow(idx); }; })(o.i));
            guideEl.appendChild(m);
          });
        }
        if (resultWrap) resultWrap.style.display = "block";
      });
    }

    function ipToLong(ip) {
      var parts = (ip || "").trim().split(".");
      if (parts.length !== 4) return null;
      var n = 0;
      for (var i = 0; i < 4; i++) {
        var p = parseInt(parts[i], 10);
        if (isNaN(p) || p < 0 || p > 255) return null;
        n = (n << 8) | p;
      }
      return n >>> 0;
    }
    function longToIp(n) {
      n = n >>> 0;
      return ((n >>> 24) & 0xff) + "." + ((n >>> 16) & 0xff) + "." + ((n >>> 8) & 0xff) + "." + (n & 0xff);
    }
    function parseCidr(str) {
      str = (str || "").trim();
      var idx = str.indexOf("/");
      if (idx < 0) return null;
      var ip = str.slice(0, idx);
      var plen = parseInt(str.slice(idx + 1), 10);
      if (isNaN(plen) || plen < 0 || plen > 32) return null;
      var long = ipToLong(ip);
      if (long === null) return null;
      var mask = plen === 0 ? 0 : (0xffffffff << (32 - plen)) >>> 0;
      var base = (long & mask) >>> 0;
      return { base: base, prefixLen: plen };
    }
    function networkAddress(ipLong, mask) {
      var m = mask === 0 ? 0 : (0xffffffff << (32 - mask)) >>> 0;
      return (ipLong & m) >>> 0;
    }
    function subnetAddresses(mask) { return 1 << (32 - mask); }
    function subnetLastAddress(subnet, mask) { return (subnet + subnetAddresses(mask) - 1) >>> 0; }
    var subnetCurNetwork = 0;
    var subnetCurMask = 0;
    var subnetRoot = null;
    var subnetPageInited = false;
    function subnetUpdateNumChildren(node) {
      if (!node[2]) { node[1] = 1; node[0] = 1; return 1; }
      node[1] = subnetUpdateNumChildren(node[2][0]) + subnetUpdateNumChildren(node[2][1]);
      node[0] = node[1];
      return node[1];
    }
    function subnetDivide(node) { node[2] = [[0, 0, null], [0, 0, null]]; subnetRecreateTables(); }
    function subnetJoin(node) { node[2] = null; subnetRecreateTables(); }
    function newSubnetJoin(joinnode) { return function() { subnetJoin(joinnode); }; }
    function subnetCreateRow(calcbody, node, address, mask, labels, depth) {
      if (node[2]) {
        var newlabels = labels.slice();
        newlabels.push(mask + 1, node[2][0][1], node[2][0]);
        subnetCreateRow(calcbody, node[2][0], address, mask + 1, newlabels, depth);
        subnetCreateRow(calcbody, node[2][1], (address + subnetAddresses(mask + 1)) >>> 0, mask + 1, [mask + 1, node[2][1][1], node[2][1]], depth);
      } else {
        var tr = document.createElement("tr");
        var addrFirst = address;
        var addrLast = subnetLastAddress(address, mask);
        var useableFirst = mask <= 30 ? address + 1 : address;
        var useableLast = mask <= 30 ? addrLast - 1 : addrLast;
        var numHosts = mask >= 31 ? (mask === 32 ? 1 : 2) : (addrLast - addrFirst - 1);
        var rangeStr = mask === 32 ? longToIp(addrFirst) : longToIp(addrFirst) + " - " + longToIp(addrLast);
        var useableStr = mask >= 31 ? rangeStr : longToIp(useableFirst) + " - " + longToIp(useableLast);
        tr.appendChild(document.createElement("td")).appendChild(document.createTextNode(longToIp(address) + "/" + mask));
        tr.appendChild(document.createElement("td")).appendChild(document.createTextNode(rangeStr));
        tr.appendChild(document.createElement("td")).appendChild(document.createTextNode(useableStr));
        tr.appendChild(document.createElement("td")).appendChild(document.createTextNode(String(numHosts)));
        var divCell = tr.appendChild(document.createElement("td"));
        if (mask >= 32) {
          var span = document.createElement("span");
          span.style.color = "var(--muted)";
          span.textContent = "Divide";
          divCell.appendChild(span);
        } else {
          var a = document.createElement("a");
          a.href = "#";
          a.textContent = "Divide";
          a.style.color = "var(--accent)";
          a.addEventListener("click", function(e) { e.preventDefault(); subnetDivide(node); });
          divCell.appendChild(a);
        }
        var colspan = depth - node[0];
        if (colspan < 1) colspan = 1;
        var n = Math.floor(labels.length / 3);
        for (var i = n - 1; i >= 0; i--) {
          var maskVal = labels[i * 3];
          var rowspan = labels[i * 3 + 1];
          var joinnode = labels[i * 3 + 2];
          var td = document.createElement("td");
          td.rowSpan = rowspan > 1 ? rowspan : 1;
          td.colSpan = (i === n - 1) ? colspan : 1;
          td.style.background = "rgba(128,128,128,0.2)";
          td.style.textAlign = "right";
          td.style.padding = "0.35rem 0.5rem";
          td.style.borderBottom = "1px solid rgba(128,128,128,0.3)";
          td.style.verticalAlign = "middle";
          td.textContent = "/" + maskVal;
          if (i === n - 1) {
            td.style.color = "var(--muted)";
          } else {
            td.style.cursor = "pointer";
            td.title = "Join subnets back to /" + maskVal;
            td.addEventListener("click", newSubnetJoin(joinnode));
          }
          tr.appendChild(td);
        }
        calcbody.appendChild(tr);
      }
    }
    function subnetRecreateTables() {
      var calcbody = document.getElementById("subnetCalcBody");
      var joinHeader = document.getElementById("subnetJoinHeader");
      if (!calcbody) return;
      while (calcbody.firstChild) calcbody.removeChild(calcbody.firstChild);
      if (!subnetRoot) return;
      subnetUpdateNumChildren(subnetRoot);
      subnetCreateRow(calcbody, subnetRoot, subnetCurNetwork, subnetCurMask, [subnetCurMask, subnetRoot[1], subnetRoot], subnetRoot[0]);
      if (joinHeader) joinHeader.colSpan = subnetRoot[0] > 0 ? subnetRoot[0] : 1;
    }
    function subnetStartOver() {
      subnetRoot = [0, 0, null];
      subnetRecreateTables();
    }
    function subnetUpdateNetwork() {
      var netStr = (document.getElementById("subnetNetwork") && document.getElementById("subnetNetwork").value) ? document.getElementById("subnetNetwork").value.trim() : "";
      var maskVal = parseInt((document.getElementById("subnetMask") && document.getElementById("subnetMask").value) ? document.getElementById("subnetMask").value : "16", 10);
      var long = ipToLong(netStr);
      if (long === null) { if (document.getElementById("subnetStatus")) document.getElementById("subnetStatus").textContent = "Invalid network address."; return; }
      if (maskVal < 0 || maskVal > 32) { if (document.getElementById("subnetStatus")) document.getElementById("subnetStatus").textContent = "Mask must be 0–32."; return; }
      var netAddr = networkAddress(long, maskVal);
      if (netAddr !== long && document.getElementById("subnetNetwork")) {
        document.getElementById("subnetNetwork").value = longToIp(netAddr);
      }
      if (subnetCurMask === 0) {
        subnetCurMask = maskVal;
        subnetCurNetwork = netAddr;
        subnetRoot = [0, 0, null];
        subnetStartOver();
      } else if (subnetCurMask !== maskVal) {
        if (confirm("Changing the base network from /" + subnetCurMask + " to /" + maskVal + " will reset all divisions. Proceed?")) {
          subnetCurMask = maskVal;
          subnetCurNetwork = netAddr;
          subnetStartOver();
        } else {
          if (document.getElementById("subnetMask")) document.getElementById("subnetMask").value = subnetCurMask;
          return;
        }
      } else {
        subnetCurNetwork = netAddr;
        subnetRecreateTables();
      }
      var wrap = document.getElementById("subnetResultWrap");
      if (wrap) wrap.style.display = "block";
      if (document.getElementById("subnetStatus")) document.getElementById("subnetStatus").textContent = "Click Divide to split a subnet; click a Join cell to merge.";
    }
    function initSubnetPage() {
      if (subnetPageInited) return;
      subnetPageInited = true;
      var updateBtn = document.getElementById("subnetUpdateBtn");
      var resetBtn = document.getElementById("subnetResetBtn");
      if (updateBtn) updateBtn.addEventListener("click", subnetUpdateNetwork);
      if (resetBtn) resetBtn.addEventListener("click", function() { if (confirm("Reset all subnet divisions?")) { subnetStartOver(); } });
      subnetCurMask = 0;
      subnetCurNetwork = 0;
      subnetRoot = [0, 0, null];
      subnetUpdateNetwork();
    }

    var restApiInited = false;
    var restApiDevicesCache = [];
    var RESTAPI_DEFAULT_REQUEST = '{"cmd": "enable", "input": "my_enable_passw0rd"}\nconfigure\nmanagement ssh\nidle-timeout 15';
    var RESTAPI_EXAMPLES = {
      "version": '{"cmd": "enable", "input": "my_enable_passw0rd"}\nshow version',
      "idle-timeout": '{"cmd": "enable", "input": "my_enable_passw0rd"}\nconfigure\nmanagement ssh\nidle-timeout 15',
      "running-config": '{"cmd": "enable", "input": "my_enable_passw0rd"}\nshow running-config'
    };
    function initRestApiPage() {
      if (restApiInited) return;
      restApiInited = true;
      var fabricSel = document.getElementById("restapiFabric");
      var siteSel = document.getElementById("restapiSite");
      var hallSel = document.getElementById("restapiHall");
      var roleSel = document.getElementById("restapiRole");
      var listEl = document.getElementById("restapiDeviceList");
      var requestInput = document.getElementById("restapiRequestInput");
      var submitBtn = document.getElementById("restapiSubmitBtn");
      var statusEl = document.getElementById("restapiStatus");
      var resultWrap = document.getElementById("restapiResultWrap");
      var resultsTableEl = document.getElementById("restapiResultsTable");
      var resultsTbody = resultsTableEl ? resultsTableEl.querySelector("tbody") : null;
      if (!requestInput) return;
      document.querySelectorAll(".restapi-example-btn").forEach(function(btn) {
        var key = btn.getAttribute("data-example");
        if (key && RESTAPI_EXAMPLES[key]) {
          btn.addEventListener("click", function() { requestInput.value = RESTAPI_EXAMPLES[key]; });
        }
      });

      function loadRestApiFabrics() {
        get("/api/fabrics").then(function(d) {
          var list = d.fabrics || [];
          if (fabricSel) fabricSel.innerHTML = "<option value=\"\">—</option>" + list.map(function(f) { return "<option value=\"" + escapeHtml(f) + "\">" + escapeHtml(f) + "</option>"; }).join("");
        }).catch(function() { if (fabricSel) fabricSel.innerHTML = "<option value=\"\">—</option>"; });
      }
      function loadRestApiSites() {
        var fabric = (fabricSel && fabricSel.value) || "";
        if (!siteSel) return;
        siteSel.innerHTML = "<option value=\"\">—</option>";
        if (hallSel) hallSel.innerHTML = "<option value=\"\">—</option>";
        if (roleSel) roleSel.innerHTML = "<option value=\"\">—</option>";
        listEl.innerHTML = ""; restApiDevicesCache = [];
        if (!fabric) return;
        get("/api/sites?fabric=" + encodeURIComponent(fabric)).then(function(d) {
          var list = d.sites || [];
          siteSel.innerHTML = "<option value=\"\">—</option>" + list.map(function(s) { return "<option value=\"" + escapeHtml(s) + "\">" + escapeHtml(s) + "</option>"; }).join("");
        }).catch(function() {});
      }
      function loadRestApiHalls() {
        var fabric = (fabricSel && fabricSel.value) || "";
        var site = (siteSel && siteSel.value) || "";
        if (!hallSel) return;
        hallSel.innerHTML = "<option value=\"\">—</option>";
        if (roleSel) roleSel.innerHTML = "<option value=\"\">—</option>";
        listEl.innerHTML = ""; restApiDevicesCache = [];
        if (!fabric) return;
        get("/api/halls?fabric=" + encodeURIComponent(fabric) + "&site=" + encodeURIComponent(site || "")).then(function(d) {
          var list = d.halls || [];
          hallSel.innerHTML = "<option value=\"\">—</option>" + list.map(function(h) { return "<option value=\"" + escapeHtml(h) + "\">" + escapeHtml(h) + "</option>"; }).join("");
        }).catch(function() {});
      }
      function loadRestApiRoles() {
        var fabric = (fabricSel && fabricSel.value) || "";
        var site = (siteSel && siteSel.value) || "";
        var hall = (hallSel && hallSel.value) || "";
        if (!roleSel) return;
        roleSel.innerHTML = "<option value=\"\">—</option>";
        listEl.innerHTML = ""; restApiDevicesCache = [];
        if (!fabric) return;
        var path = "/api/roles?fabric=" + encodeURIComponent(fabric) + "&site=" + encodeURIComponent(site || "");
        if (hall) path += "&hall=" + encodeURIComponent(hall);
        get(path).then(function(d) {
          var list = d.roles || [];
          roleSel.innerHTML = "<option value=\"\">—</option>" + list.map(function(r) { return "<option value=\"" + escapeHtml(r) + "\">" + escapeHtml(r) + "</option>"; }).join("");
        }).catch(function() {});
      }
      function loadRestApiDevices() {
        var fabric = (fabricSel && fabricSel.value) || "";
        var site = (siteSel && siteSel.value) || "";
        var hall = (hallSel && hallSel.value) || "";
        var role = (roleSel && roleSel.value) || "";
        if (!fabric) { listEl.innerHTML = ""; restApiDevicesCache = []; if (statusEl) statusEl.textContent = "Select fabric first."; return; }
        var path = "/api/devices-arista?fabric=" + encodeURIComponent(fabric);
        if (site) path += "&site=" + encodeURIComponent(site);
        if (hall) path += "&hall=" + encodeURIComponent(hall);
        if (role) path += "&role=" + encodeURIComponent(role);
        if (statusEl) statusEl.textContent = "Loading…";
        get(path).then(function(d) {
          restApiDevicesCache = d.devices || [];
          listEl.innerHTML = restApiDevicesCache.map(function(dev, i) {
            return "<div class=\"device-row\" data-index=\"" + i + "\"><input type=\"checkbox\" data-index=\"" + i + "\" /><span class=\"hostname\">" + escapeHtml(dev.hostname || "") + "</span><span class=\"ip\">" + escapeHtml(dev.ip || "") + "</span></div>";
          }).join("");
          if (statusEl) statusEl.textContent = restApiDevicesCache.length + " device(s). Select device(s) and submit.";
        }).catch(function() {
          listEl.innerHTML = ""; restApiDevicesCache = [];
          if (statusEl) statusEl.textContent = "Failed to load devices.";
        });
      }
      loadRestApiFabrics();
      if (fabricSel) fabricSel.addEventListener("change", function() { loadRestApiSites(); });
      if (siteSel) siteSel.addEventListener("change", function() { loadRestApiHalls(); });
      if (hallSel) hallSel.addEventListener("change", function() { loadRestApiRoles(); });
      if (roleSel) roleSel.addEventListener("change", loadRestApiDevices);
      if (fabricSel) fabricSel.addEventListener("change", loadRestApiDevices);
      if (siteSel) siteSel.addEventListener("change", loadRestApiDevices);
      if (hallSel) hallSel.addEventListener("change", loadRestApiDevices);
      if (roleSel) roleSel.addEventListener("change", loadRestApiDevices);

      var selAll = document.getElementById("restapiSelectAll");
      var selNone = document.getElementById("restapiSelectNone");
      if (selAll) selAll.addEventListener("click", function() { if (listEl) listEl.querySelectorAll("input[type=checkbox]").forEach(function(cb) { cb.checked = true; }); });
      if (selNone) selNone.addEventListener("click", function() { if (listEl) listEl.querySelectorAll("input[type=checkbox]").forEach(function(cb) { cb.checked = false; }); });

      function parseRequestLines(text) {
        var lines = text.split(/\n/).map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
        var cmds = [];
        for (var i = 0; i < lines.length; i++) {
          var line = lines[i];
          if (line.charAt(0) === "{" && line.indexOf("cmd") >= 0) {
            try {
              var obj = JSON.parse(line);
              if (obj && typeof obj === "object") cmds.push(obj);
              else cmds.push(line);
            } catch (e) { cmds.push(line); }
          } else {
            cmds.push(line);
          }
        }
        return cmds;
      }
      if (submitBtn) submitBtn.addEventListener("click", function() {
        var selected = [];
        if (listEl) listEl.querySelectorAll("input[type=checkbox]:checked").forEach(function(cb) {
          var i = parseInt(cb.getAttribute("data-index"), 10);
          if (!isNaN(i) && i >= 0 && i < restApiDevicesCache.length) selected.push(restApiDevicesCache[i]);
        });
        if (!selected.length) { if (statusEl) statusEl.textContent = "Select at least one device."; return; }
        var raw = (requestInput && requestInput.value) || "";
        var cmds = parseRequestLines(raw);
        if (!cmds.length) { if (statusEl) statusEl.textContent = "Enter at least one command line."; return; }
        if (statusEl) statusEl.textContent = "Sending to " + selected.length + " device(s)…";
        submitBtn.disabled = true;
        var promises = selected.map(function(device) {
          return fetch(API + "/api/arista/run-cmds", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ device: device, cmds: cmds })
          }).then(function(r) { return r.json(); }).then(function(data) {
            if (data.error) addDeviceEvent("fail", device.hostname || device.ip, data.error);
            else addDeviceEvent("success", device.hostname || device.ip, "runCmds OK");
            return { device: device, error: data.error, result: data.result };
          }).catch(function(e) {
            addDeviceEvent("fail", device.hostname || device.ip, e.message || "Request failed");
            return { device: device, error: e.message || "Request failed", result: null };
          });
        });
        Promise.all(promises).then(function(results) {
          submitBtn.disabled = false;
          if (resultWrap) resultWrap.style.display = "block";
          if (resultsTbody) {
            resultsTbody.innerHTML = results.map(function(r) {
              var name = (r.device && (r.device.hostname || r.device.ip)) || "";
              var text = r.error ? ("Error: " + r.error) : (r.result != null ? JSON.stringify(r.result, null, 2) : "");
              return "<tr><td>" + escapeHtml(name) + "</td><td style=\"white-space:pre-wrap; word-break:break-all; max-width:480px; max-height:200px; overflow:auto; font-size:0.85em;\">" + escapeHtml(text) + "</td></tr>";
            }).join("");
          }
          var ok = results.filter(function(r) { return !r.error; }).length;
          if (statusEl) statusEl.textContent = "Done. " + ok + "/" + results.length + " succeeded.";
        });
      });
    }

    (function() {
      var themeKey = "pergen-theme";
      var themeToggle = document.getElementById("themeToggle");
      var themeLabel = document.getElementById("themeLabel");
      var themeIcon = document.getElementById("themeIcon");
      function getTheme() { return localStorage.getItem(themeKey) || "dark"; }
      function setTheme(theme) {
        localStorage.setItem(themeKey, theme);
        document.body.classList.toggle("theme-light", theme === "light");
        document.body.classList.toggle("theme-dark", theme === "dark");
        if (themeLabel) themeLabel.textContent = theme === "dark" ? "Dark" : "Light";
        if (themeIcon) themeIcon.textContent = theme === "dark" ? "🌙" : "☀️";
      }
      if (themeToggle) {
        setTheme(getTheme());
        themeToggle.addEventListener("click", function() { setTheme(getTheme() === "dark" ? "light" : "dark"); });
      }
    })();

    let inventoryCache = [];
    const INV_COLS = ["hostname", "ip", "fabric", "site", "hall", "vendor", "model", "role", "tag", "credential"];
    var invTableVisibleCols = {};
    INV_COLS.forEach(function(c) { invTableVisibleCols[c] = true; });
    const INV_LABELS = { hostname: "Hostname", ip: "IP", fabric: "Fabric", site: "Site", hall: "Hall", vendor: "Vendor", model: "Model", role: "Role", tag: "Tag", credential: "Credential" };
    let invSortCol = null;
    let invSortDir = "asc";
    let invColumnFilters = {};
    let invSelectedHostnames = new Set();
    let invEditCurrentHostname = null;

    function buildInvFilterOptions() {
      const invF = $("invFabric");
      const invS = $("invSite");
      const invH = $("invHall");
      const invR = $("invRole");
      const f = (invF && invF.value) || "";
      const s = (invS && invS.value) || "";
      const h = (invH && invH.value) || "";
      const fabrics = [...new Set(inventoryCache.map(d => d.fabric || "").filter(Boolean))].sort();
      const sites = f ? [...new Set(inventoryCache.filter(d => d.fabric === f).map(d => d.site || "").filter(Boolean))].sort() : [];
      const halls = (f && s) ? [...new Set(inventoryCache.filter(d => d.fabric === f && d.site === s).map(d => d.hall || "").filter(Boolean))].sort() : [];
      const roles = (f && s) ? [...new Set(inventoryCache.filter(d => d.fabric === f && d.site === s && (!h || d.hall === h)).map(d => d.role || "").filter(Boolean))].sort() : [];
      if (invF) {
        invF.innerHTML = "<option value=\"\">— All —</option>" + fabrics.map(x => "<option value=\"" + escapeHtml(x) + "\">" + escapeHtml(x) + "</option>").join("");
        invF.value = fabrics.includes(f) ? f : "";
      }
      if (invS) {
        invS.innerHTML = "<option value=\"\">— All —</option>" + sites.map(x => "<option value=\"" + escapeHtml(x) + "\">" + escapeHtml(x) + "</option>").join("");
        invS.value = sites.includes(s) ? s : "";
      }
      if (invH) {
        invH.innerHTML = "<option value=\"\">— All —</option>" + halls.map(x => "<option value=\"" + escapeHtml(x) + "\">" + escapeHtml(x) + "</option>").join("");
        invH.value = halls.includes(h) ? h : "";
      }
      if (invR) {
        invR.innerHTML = "<option value=\"\">— All —</option>" + roles.map(x => "<option value=\"" + escapeHtml(x) + "\">" + escapeHtml(x) + "</option>").join("");
        invR.value = roles.includes((invR.value || "")) ? invR.value : "";
      }
    }
    function getFilteredInventory() {
      const invF = $("invFabric");
      const invS = $("invSite");
      const invH = $("invHall");
      const invR = $("invRole");
      const f = (invF && invF.value) || "";
      const s = (invS && invS.value) || "";
      const h = (invH && invH.value) || "";
      const r = (invR && invR.value) || "";
      let list = inventoryCache.filter(d => {
        if (f && (d.fabric || "") !== f) return false;
        if (s && (d.site || "") !== s) return false;
        if (h && (d.hall || "") !== h) return false;
        if (r && (d.role || "") !== r) return false;
        return true;
      });
      INV_COLS.forEach(col => {
        const flt = invColumnFilters[col];
        if (!flt || !(flt.value || "").trim()) return;
        const val = (flt.value || "").trim().toLowerCase();
        const typ = flt.type || "in";
        list = list.filter(d => {
          const cell = (d[col] != null ? String(d[col]) : "").toLowerCase();
          const has = cell.indexOf(val) !== -1;
          return typ === "in" ? has : !has;
        });
      });
      return list;
    }
    function invApplySortAndRender(filtered) {
      if (invSortCol && INV_COLS.includes(invSortCol)) {
        filtered = filtered.slice().sort((a, b) => {
          const va = a[invSortCol]; const vb = b[invSortCol];
          const sa = va == null ? "" : String(va);
          const sb = vb == null ? "" : String(vb);
          const c = sa.localeCompare(sb, undefined, { numeric: true });
          return invSortDir === "asc" ? c : -c;
        });
      }
      return filtered;
    }
    function renderInvTable() {
      const theadWrap = $("invTheadWrap");
      const tbody = $("invTbody");
      const countEl = $("invCount");
      if (!theadWrap || !tbody) return;
      const visibleCols = INV_COLS.filter(c => invTableVisibleCols[c] !== false);
      let filtered = getFilteredInventory();
      filtered = invApplySortAndRender(filtered);

      const theadTr = document.createElement("tr");
      theadTr.appendChild(document.createElement("th"));
      visibleCols.forEach(c => {
        const th = document.createElement("th");
        th.className = "sortable";
        th.textContent = INV_LABELS[c] || c;
        const span = document.createElement("span");
        span.className = "sort-icon";
        span.textContent = invSortCol === c ? (invSortDir === "asc" ? " \u25b2" : " \u25bc") : "";
        th.appendChild(span);
        th.dataset.col = c;
        th.addEventListener("click", () => {
          if (invSortCol === c) invSortDir = invSortDir === "asc" ? "desc" : "asc";
          else { invSortCol = c; invSortDir = "asc"; }
          renderInvTable();
        });
        theadTr.appendChild(th);
      });
      var invTableEl = document.getElementById("invTable");
      var invWrap = invTableEl ? invTableEl.parentElement : null;
      if (invWrap && invTableEl) {
        var chipsBar = invWrap.querySelector(".filter-chips-bar");
        if (!chipsBar) { chipsBar = document.createElement("div"); chipsBar.className = "filter-chips-bar"; invWrap.insertBefore(chipsBar, invTableEl); }
        chipsBar.innerHTML = "";
        visibleCols.forEach(c => {
          const f = invColumnFilters[c];
          if (!f || !(f.value || "").trim()) return;
          const chip = document.createElement("span");
          chip.className = "filter-chip";
          const typ = (f.type || "in") === "not-in" ? "not-in" : "in";
          chip.textContent = (INV_LABELS[c] || c) + " " + typ + " \"" + (f.value || "").trim() + "\" ";
          const xBtn = document.createElement("button");
          xBtn.type = "button";
          xBtn.className = "filter-chip-remove";
          xBtn.textContent = "\u00d7";
          xBtn.setAttribute("aria-label", "Remove filter");
          xBtn.addEventListener("click", () => { invColumnFilters[c] = invColumnFilters[c] || {}; invColumnFilters[c].value = ""; renderInvTable(); });
          chip.appendChild(xBtn);
          chipsBar.appendChild(chip);
        });
      }
      const filterTr = document.createElement("tr");
      filterTr.className = "filter-row";
      filterTr.appendChild(document.createElement("th"));
      visibleCols.forEach(c => {
        const fth = document.createElement("th");
        const sel = document.createElement("select");
        sel.dataset.col = c;
        sel.innerHTML = "<option value=\"in\">in</option><option value=\"not-in\">not-in</option>";
        const f = invColumnFilters[c];
        if (f) sel.value = f.type || "in";
        sel.addEventListener("change", () => {
          invColumnFilters[c] = invColumnFilters[c] || {}; invColumnFilters[c].type = sel.value; renderInvTable();
        });
        const inp = document.createElement("input");
        inp.type = "text";
        inp.placeholder = "Filter\u2026 Enter to apply";
        inp.dataset.col = c;
        if (f && f.value) inp.value = f.value;
        inp.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            invColumnFilters[c] = invColumnFilters[c] || {}; invColumnFilters[c].type = sel.value; invColumnFilters[c].value = inp.value.trim(); renderInvTable();
          }
        });
        fth.appendChild(sel);
        fth.appendChild(inp);
        filterTr.appendChild(fth);
      });
      theadWrap.innerHTML = "";
      theadWrap.appendChild(theadTr);
      theadWrap.appendChild(filterTr);

      tbody.innerHTML = filtered.map(row => {
        const h = (row.hostname || "").trim();
        const checked = invSelectedHostnames.has(h) ? " checked" : "";
        return "<tr data-hostname=\"" + escapeHtml(h) + "\">" +
          "<td><input type=\"checkbox\" class=\"inv-row-cb\" data-hostname=\"" + escapeHtml(h) + "\"" + checked + " /></td>" +
          visibleCols.map(c => "<td>" + escapeHtml((row[c] != null ? row[c] : "")) + "</td>").join("") + "</tr>";
      }).join("");

      tbody.querySelectorAll(".inv-row-cb").forEach(cb => {
        cb.addEventListener("change", function() {
          const h = (this.dataset.hostname || "").trim();
          if (this.checked) invSelectedHostnames.add(h); else invSelectedHostnames.delete(h);
          invUpdateEditButton();
        });
      });

      const firstTh = theadTr.querySelector("th");
      if (firstTh) {
        const allCb = document.createElement("input");
        allCb.type = "checkbox";
        allCb.title = "Select all";
        allCb.checked = filtered.length > 0 && filtered.every(row => invSelectedHostnames.has((row.hostname || "").trim()));
        allCb.addEventListener("change", function() {
          filtered.forEach(row => {
            const h = (row.hostname || "").trim();
            if (this.checked) invSelectedHostnames.add(h); else invSelectedHostnames.delete(h);
          });
          renderInvTable();
          invUpdateEditButton();
        });
        firstTh.innerHTML = "";
        firstTh.appendChild(allCb);
      }

      if (countEl) countEl.textContent = filtered.length + " device(s)";
      invUpdateEditButton();
    }
    function invUpdateEditButton() {
      const btn = $("invEditBtn");
      if (btn) btn.disabled = invSelectedHostnames.size !== 1;
    }
    function invModalShow(isEdit, device) {
      invEditCurrentHostname = isEdit && device ? (device.hostname || "").trim() : null;
      $("invModalTitle").textContent = isEdit ? "Edit device" : "Add device";
      $("invModalDelete").style.display = isEdit ? "block" : "none";
      INV_COLS.forEach((c, i) => {
        const el = document.getElementById("invForm" + (c.charAt(0).toUpperCase() + c.slice(1)));
        if (el) el.value = device && device[c] != null ? device[c] : "";
      });
      $("invModal").style.display = "flex";
    }
    function invModalHide() {
      $("invModal").style.display = "none";
      invEditCurrentHostname = null;
    }
    function invFormData() {
      return {
        hostname: ($("invFormHostname") || {}).value.trim(),
        ip: ($("invFormIp") || {}).value.trim(),
        fabric: ($("invFormFabric") || {}).value.trim(),
        site: ($("invFormSite") || {}).value.trim(),
        hall: ($("invFormHall") || {}).value.trim(),
        vendor: ($("invFormVendor") || {}).value.trim(),
        model: ($("invFormModel") || {}).value.trim(),
        role: ($("invFormRole") || {}).value.trim(),
        tag: ($("invFormTag") || {}).value.trim(),
        credential: ($("invFormCredential") || {}).value.trim(),
      };
    }
    async function invSaveDevice() {
      const data = invFormData();
      if (!data.hostname) { alert("Hostname is required."); return; }
      const isEdit = !!invEditCurrentHostname;
      const url = API + "/api/inventory/device";
      const body = isEdit ? { ...data, current_hostname: invEditCurrentHostname } : data;
      try {
        const r = await fetch(url, {
          method: isEdit ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || "Request failed");
        invModalHide();
        await loadInventoryPage();
      } catch (e) {
        alert("Error: " + e.message);
      }
    }
    async function invDeleteDevice() {
      if (!invEditCurrentHostname) return;
      if (!confirm("Delete device " + invEditCurrentHostname + "?")) return;
      try {
        const r = await fetch(API + "/api/inventory/device?hostname=" + encodeURIComponent(invEditCurrentHostname), { method: "DELETE" });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || "Request failed");
        invModalHide();
        invSelectedHostnames.delete(invEditCurrentHostname);
        await loadInventoryPage();
      } catch (e) {
        alert("Error: " + e.message);
      }
    }
    function invExportCsv() {
      const filtered = getFilteredInventory();
      const header = INV_COLS.join(",");
      const rows = filtered.map(d => INV_COLS.map(c => {
        const v = (d[c] != null ? String(d[c]) : "");
        return v.indexOf(",") >= 0 || v.indexOf('"') >= 0 ? '"' + v.replace(/"/g, '""') + '"' : v;
      }).join(","));
      const csv = [header, ...rows].join("\r\n");
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "inventory_export.csv";
      a.click();
      URL.revokeObjectURL(a.href);
    }
    function invParseCsvLine(line) {
      const out = [];
      let i = 0;
      while (i < line.length) {
        if (line[i] === '"') {
          let s = "";
          i++;
          while (i < line.length) {
            if (line[i] === '"' && line[i + 1] === '"') { s += '"'; i += 2; continue; }
            if (line[i] === '"') { i++; break; }
            s += line[i++];
          }
          out.push(s.trim());
          if (line[i] === ",") i++;
        } else {
          let s = "";
          while (i < line.length && line[i] !== ",") s += line[i++];
          out.push(s.trim());
          if (line[i] === ",") i++;
        }
      }
      return out;
    }
    async function invImportCsv(file) {
      const text = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsText(file, "utf-8"); });
      const lines = text.split(/\r?\n/).filter(l => l.trim());
      if (!lines.length) { alert("File is empty."); return; }
      const header = invParseCsvLine(lines[0]).map(s => s.toLowerCase().trim());
      const rows = [];
      for (let i = 1; i < lines.length; i++) {
        const vals = invParseCsvLine(lines[i]);
        const row = {};
        header.forEach((h, j) => { row[h] = (vals[j] != null ? String(vals[j]).replace(/^"|"$/g, "") : "").trim(); });
        rows.push(row);
      }
      try {
        const r = await fetch(API + "/api/inventory/import", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rows }),
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || "Request failed");
        alert("Imported: " + (j.added || 0) + " added, " + (j.skipped || []).length + " skipped (duplicate or invalid).");
        await loadInventoryPage();
      } catch (e) {
        alert("Error: " + e.message);
      }
    }
    async function loadInventoryPage() {
      const invStatus = $("invStatus");
      if (invStatus) invStatus.textContent = "Loading…";
      try {
        const r = await fetch(API + "/api/inventory");
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || "Failed to load inventory");
        inventoryCache = data.inventory || [];
        buildInvFilterOptions();
        renderInvTable();
        if (invStatus) invStatus.textContent = "";
      } catch (e) {
        if (invStatus) invStatus.textContent = "Error: " + e.message;
        inventoryCache = [];
        renderInvTable();
      }
      if (!window._invListenersAttached) {
        window._invListenersAttached = true;
        const invF = $("invFabric");
        const invS = $("invSite");
        const invH = $("invHall");
        const invR = $("invRole");
        invF && invF.addEventListener("change", function() { buildInvFilterOptions(); renderInvTable(); });
        invS && invS.addEventListener("change", function() { buildInvFilterOptions(); renderInvTable(); });
        invH && invH.addEventListener("change", function() { buildInvFilterOptions(); renderInvTable(); });
        invR && invR.addEventListener("change", renderInvTable);

        $("invAddBtn") && $("invAddBtn").addEventListener("click", () => invModalShow(false));
        $("invEditBtn") && $("invEditBtn").addEventListener("click", () => {
          if (invSelectedHostnames.size !== 1) return;
          const h = [...invSelectedHostnames][0];
          const device = inventoryCache.find(d => (d.hostname || "").trim() === h);
          if (device) invModalShow(true, device);
        });
        $("invImportBtn") && $("invImportBtn").addEventListener("click", () => $("invFileInput") && $("invFileInput").click());
        $("invFileInput") && $("invFileInput").addEventListener("change", function() {
          const f = this.files && this.files[0];
          if (f) invImportCsv(f);
          this.value = "";
        });
        $("invExportBtn") && $("invExportBtn").addEventListener("click", invExportCsv);
        $("invModalSave") && $("invModalSave").addEventListener("click", invSaveDevice);
        $("invModalDelete") && $("invModalDelete").addEventListener("click", invDeleteDevice);
        $("invModalCancel") && $("invModalCancel").addEventListener("click", invModalHide);
        $("invModal") && $("invModal").addEventListener("click", function(e) { if (e.target === this) invModalHide(); });
        var invColBtn = document.getElementById("invColumnToggleBtn");
        var invColDrop = document.getElementById("invColumnToggleDropdown");
        if (invColBtn && invColDrop) {
          invColBtn.addEventListener("click", function(e) { e.stopPropagation(); invColDrop.classList.toggle("open"); if (invColDrop.classList.contains("open")) { INV_COLS.forEach(function(col) { var cb = invColDrop.querySelector("input[data-col=\"" + col + "\"]"); if (cb) cb.checked = invTableVisibleCols[col] !== false; }); } });
          invColDrop.querySelectorAll("input[data-col]").forEach(function(cb) { cb.addEventListener("change", function() { var col = cb.getAttribute("data-col"); invTableVisibleCols[col] = cb.checked; renderInvTable(); }); });
          document.addEventListener("click", function() { invColDrop.classList.remove("open"); });
          invColDrop.addEventListener("click", function(e) { e.stopPropagation(); });
        }
      }
    }

    function findLeafSearch() {
      const ipInput = $("findLeafIp");
      const statusEl = $("findLeafStatus");
      const listEl = $("findLeafDeviceList");
      const resultWrap = $("findLeafResult");
      const resultBody = $("findLeafResultBody");
      const ip = (ipInput && ipInput.value || "").trim();
      if (!ip) {
        if (statusEl) { statusEl.textContent = "Enter an IP address."; statusEl.className = "ping-status"; }
        if (listEl) listEl.style.display = "none";
        if (resultWrap) resultWrap.style.display = "none";
        return;
      }
      const ipv4Re = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])$/;
      if (!ipv4Re.test(ip)) {
        if (statusEl) { statusEl.textContent = "Only IP format is allowed (e.g. 10.1.2.3)."; statusEl.className = "ping-status"; }
        if (listEl) listEl.style.display = "none";
        if (resultWrap) resultWrap.style.display = "none";
        return;
      }
      if (resultWrap) resultWrap.style.display = "none";
      fetch(API + "/api/devices-by-tag?tag=leaf-search")
        .then(function(r) { return r.json(); })
        .then(function(tagRes) {
          const devs = tagRes.devices || [];
          if (!listEl || !devs.length) {
            if (statusEl) { statusEl.textContent = "No leaf-search devices."; statusEl.className = "ping-status"; }
            return;
          }
          listEl.innerHTML = devs.map(function(d) {
            var name = d.hostname || d.ip || "?";
            return "<li data-hostname=\"" + name.replace(/"/g, "&quot;") + "\"><span class=\"device-check-name\">" + name + "</span><span class=\"device-check-status\"><span class=\"device-check-loading\"></span></span></li>";
          }).join("");
          listEl.style.display = "block";
          if (statusEl) { statusEl.textContent = "Checking " + devs.length + " device(s)..."; statusEl.className = "ping-status"; }
          var firstFound = null;
          var abortController = new AbortController();
          function updateRow(hostname, found) {
            var li = listEl.querySelector("li[data-hostname=\"" + hostname.replace(/"/g, "&quot;") + "\"]");
            if (!li) return;
            var status = li.querySelector(".device-check-status");
            if (!status) return;
            status.innerHTML = found ? "<span class=\"device-check-ok\">✓</span>" : "<span class=\"device-check-fail\">✗</span>";
          }
          function showResult(d) {
            if (statusEl) { statusEl.textContent = "Found."; statusEl.className = "ping-status"; }
            if (!resultBody || !resultWrap) return;
            var rows = [
              ["Leaf hostname", d.leaf_hostname || ""],
              ["Leaf IP", d.leaf_ip || ""],
              ["Fabric", d.fabric || ""],
              ["Site", d.site || ""],
              ["Hall", d.hall || ""],
              ["Interface", d.interface || ""]
            ];
            resultBody.innerHTML = rows.map(function(r) { return "<tr><td>" + r[0] + "</td><td>" + (r[1] ? String(r[1]) : "") + "</td></tr>"; }).join("");
            resultWrap.style.display = "block";
          }
          devs.forEach(function(d) {
            var name = d.hostname || d.ip || "?";
            fetch(API + "/api/find-leaf-check-device", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ ip: ip, hostname: d.hostname || undefined, device_ip: d.ip || undefined }),
              signal: abortController.signal
            }).then(function(r) { return r.json(); }).then(function(data) {
              if (abortController.signal.aborted) return;
              var found = data && data.found;
              var ch = (data && data.checked_hostname) || name;
              addDeviceEvent(found ? "success" : "fail", ch, found ? "Find leaf OK" : (data && data.error) || "Not found");
              updateRow(ch, found);
              if (found && !firstFound) {
                firstFound = data;
                abortController.abort();
                var winningHostname = data.checked_hostname || name || "";
                listEl.querySelectorAll("li").forEach(function(li) {
                  var hn = li.getAttribute("data-hostname");
                  if (hn && hn !== winningHostname) {
                    var st = li.querySelector(".device-check-status");
                    if (st) st.innerHTML = "—";
                  }
                });
                showResult(data);
              }
            }).catch(function(err) {
              if (err && err.name === "AbortError") return;
              addDeviceEvent("fail", name, err && err.message || "Request failed");
              updateRow(name, false);
            });
          });
        })
        .catch(function(e) {
          if (statusEl) { statusEl.textContent = "Error: " + (e.message || "request failed"); statusEl.className = "ping-status"; }
          if (listEl) listEl.style.display = "none";
        });
    }

    function natLookupSearch() {
      const srcEl = $("natSrcIp");
      const destEl = $("natDestIp");
      const debugCb = $("natLookupDebug");
      const statusEl = $("natLookupStatus");
      const listEl = $("natLookupDeviceList");
      const resultWrap = $("natLookupResult");
      const resultBody = $("natLookupResultBody");
      const debugOut = $("natLookupDebugOut");
      const debugMatch = $("natLookupDebugMatch");
      const debugConfig = $("natLookupDebugConfig");
      const srcIp = (srcEl && srcEl.value || "").trim();
      const destIp = (destEl && destEl.value || "").trim() || "8.8.8.8";
      if (!srcIp) {
        if (statusEl) { statusEl.textContent = "Enter source IP."; statusEl.className = "ping-status"; }
        if (listEl) listEl.style.display = "none";
        if (resultWrap) resultWrap.style.display = "none";
        return;
      }
      const ipv4Re = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])$/;
      if (!ipv4Re.test(srcIp) || (destIp && !ipv4Re.test(destIp))) {
        if (statusEl) { statusEl.textContent = "Source and destination must be valid IPv4."; statusEl.className = "ping-status"; }
        if (listEl) listEl.style.display = "none";
        if (resultWrap) resultWrap.style.display = "none";
        return;
      }
      if (resultWrap) resultWrap.style.display = "none";
      if (debugOut) debugOut.style.display = "none";
      fetch(API + "/api/devices-by-tag?tag=leaf-search")
        .then(function(r) { return r.json(); })
        .then(function(tagRes) {
          const leafDevs = tagRes.devices || [];
          if (!listEl) return;
          function addListRows(devs, label) {
            devs.forEach(function(d) {
              var name = d.hostname || d.ip || "?";
              var li = document.createElement("li");
              li.setAttribute("data-hostname", name);
              li.innerHTML = "<span class=\"device-check-name\">" + (label ? label + " " : "") + name + "</span><span class=\"device-check-status\"><span class=\"device-check-loading\"></span></span>";
              listEl.appendChild(li);
            });
          }
          function updateRow(hostname, found) {
            var li = listEl.querySelector("li[data-hostname=\"" + hostname.replace(/"/g, "&quot;") + "\"]");
            if (!li) return;
            var status = li.querySelector(".device-check-status");
            if (status) status.innerHTML = found ? "<span class=\"device-check-ok\">✓</span>" : "<span class=\"device-check-fail\">✗</span>";
          }
          listEl.innerHTML = "";
          addListRows(leafDevs);
          listEl.style.display = "block";
          if (statusEl) { statusEl.textContent = "Checking leaves..."; statusEl.className = "ping-status"; }
          var fabric = "", site = "";
          var leafChecked = leafDevs.map(function(d) { return { hostname: (d.hostname || "").trim(), ip: (d.ip || "").trim() }; });
          var leafAbort = new AbortController();
          var leafFound = false;
          function onLeafDone(data, name) {
            if (leafAbort.signal.aborted) return;
            var found = !!(data && data.found);
            var ch = (data && data.checked_hostname) || name;
            addDeviceEvent(found ? "success" : "fail", ch, found ? "Find leaf OK" : (data && data.error) || "Not found");
            updateRow(ch, found);
            if (data && data.found && !leafFound) {
              leafFound = true;
              fabric = (data.fabric || "").trim();
              site = (data.site || "").trim();
              leafAbort.abort();
              var winningHostname = data.checked_hostname || name || "";
              listEl.querySelectorAll("li").forEach(function(li) {
                var hn = li.getAttribute("data-hostname");
                if (hn && hn !== winningHostname) {
                  var st = li.querySelector(".device-check-status");
                  if (st) st.innerHTML = "—";
                }
              });
              startFirewallStep();
              return;
            }
          }
          function onLeafAllDone() {
            if (leafFound) return;
            if (fabric && site) startFirewallStep();
            else if (statusEl) statusEl.textContent = "Source IP not found on any leaf.";
          }
          var leafDone = 0;
          leafDevs.forEach(function(d) {
            var name = d.hostname || d.ip || "?";
            fetch(API + "/api/find-leaf-check-device", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ ip: srcIp, hostname: d.hostname || undefined, device_ip: d.ip || undefined }),
              signal: leafAbort.signal
            }).then(function(r) { return r.json(); }).then(function(data) {
              if (leafAbort.signal.aborted) return;
              onLeafDone(data, name);
              leafDone++;
              if (leafDone >= leafDevs.length) onLeafAllDone();
            }).catch(function(err) {
              if (err && err.name === "AbortError") return;
              addDeviceEvent("fail", name, err && err.message || "Request failed");
              updateRow(name, false);
              leafDone++;
              if (leafDone >= leafDevs.length) onLeafAllDone();
            });
          });
          if (!leafDevs.length) {
            if (statusEl) statusEl.textContent = "No leaf-search devices.";
            return;
          }
          function startFirewallStep() {
            fetch(API + "/api/devices-by-tag?tag=natlookup&fabric=" + encodeURIComponent(fabric) + "&site=" + encodeURIComponent(site))
              .then(function(r) { return r.json(); })
              .then(function(fwRes) {
                var fwDevs = fwRes.devices || [];
                addListRows(fwDevs.map(function(d) { return { hostname: d.hostname || d.ip, ip: d.ip }; }), "FW:");
                if (statusEl) statusEl.textContent = "Querying firewall(s)..."; statusEl.className = "ping-status";
                return fetch(API + "/api/nat-lookup", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    src_ip: srcIp,
                    dest_ip: destIp || "8.8.8.8",
                    debug: !!(debugCb && debugCb.checked),
                    fabric: fabric,
                    site: site,
                    leaf_checked_devices: leafChecked
                  })
                }).then(function(r) { return r.json(); });
              })
              .then(function(data) {
                if (statusEl) statusEl.textContent = data.ok ? "Done." : (data.error || "Lookup failed."); statusEl.className = "ping-status";
                if (data.ok && data.firewall_hostname) updateRow(data.firewall_hostname, true);
                if (data.ok && data.firewall_ip) updateRow(data.firewall_ip, true);
                if (!resultBody || !resultWrap) return;
                if (!data.ok) {
                  resultBody.innerHTML = "<tr><td colspan=\"2\">" + (data.error || "") + "</td></tr>";
                  resultWrap.style.display = "block";
                  if (data.debug && debugOut && debugMatch && debugConfig) {
                    debugMatch.textContent = data.debug.nat_policy_match != null ? data.debug.nat_policy_match : (data.debug.nat_policy_match_error != null ? "Error: " + data.debug.nat_policy_match_error : "");
                    debugConfig.textContent = data.debug.nat_rule_config != null ? data.debug.nat_rule_config : (data.debug.nat_rule_config_error != null ? "Error: " + data.debug.nat_rule_config_error : "");
                    debugOut.style.display = "block";
                  }
                  return;
                }
                var rows = [
                  ["Fabric", data.fabric || ""],
                  ["Site", data.site || ""],
                  ["NAT rule", data.rule_name || ""],
                  ["Translated IP(s)", (data.translated_ips && data.translated_ips.length) ? data.translated_ips.join(", ") : ""],
                  ["Firewall", (data.firewall_hostname || data.firewall_ip || "").trim() || ""]
                ];
                resultBody.innerHTML = rows.map(function(r) { return "<tr><td>" + r[0] + "</td><td>" + (r[1] ? String(r[1]) : "") + "</td></tr>"; }).join("");
                var firstIp = data.translated_ips && data.translated_ips.length ? data.translated_ips[0].trim() : "";
                if (firstIp) {
                  var pathRow = "<tr><td>BGP path (Looking Glass)</td><td id=\"natBgpPathCell\" class=\"muted\" style=\"font-size:0.9em;\">Loading…</td></tr>";
                  resultBody.insertAdjacentHTML("beforeend", pathRow);
                  fetch(API + "/api/bgp/looking-glass?prefix=" + encodeURIComponent(firstIp + "/32")).then(function(res) { return res.json(); }).then(function(lg) {
                    var cell = document.getElementById("natBgpPathCell");
                    if (!cell) return;
                    if (lg.error) { cell.textContent = lg.error; return; }
                    var peers = lg.peers || [];
                    var path = peers.length && peers[0].as_path ? (Array.isArray(peers[0].as_path) ? peers[0].as_path.join(" ") : String(peers[0].as_path)) : "";
                    cell.textContent = "";
                    cell.appendChild(document.createTextNode(path || "—"));
                    var link = document.createElement("a");
                    link.href = "#bgp";
                    link.className = "nat-bgp-link";
                    link.style.marginLeft = "0.5rem";
                    link.textContent = "BGP sayfasında aç";
                    link.addEventListener("click", function(e) {
                      e.preventDefault();
                      try { sessionStorage.setItem("bgpPrefillPrefix", firstIp); } catch (err) {}
                      location.hash = "bgp";
                    });
                    cell.appendChild(link);
                    cell.classList.remove("muted");
                  }).catch(function() {
                    var cell = document.getElementById("natBgpPathCell");
                    if (cell) cell.textContent = "Failed to load path";
                  });
                }
                resultWrap.style.display = "block";
                if (data.debug && debugOut && debugMatch && debugConfig) {
                  debugMatch.textContent = data.debug.nat_policy_match != null ? data.debug.nat_policy_match : (data.debug.nat_policy_match_error != null ? "Error: " + data.debug.nat_policy_match_error : "");
                  debugConfig.textContent = data.debug.nat_rule_config != null ? data.debug.nat_rule_config : (data.debug.nat_rule_config_error != null ? "Error: " + data.debug.nat_rule_config_error : "");
                  debugOut.style.display = "block";
                }
              })
              .catch(function(e) {
                if (statusEl) statusEl.textContent = "Error: " + (e.message || "request failed"); statusEl.className = "ping-status";
              });
          }
        })
        .catch(function(e) {
          if (statusEl) { statusEl.textContent = "Error: " + (e.message || "request failed"); statusEl.className = "ping-status"; }
          if (listEl) listEl.style.display = "none";
        });
    }

    let resultsRunId = null;
    let resultsDeviceResults = [];
    let resultsTable2Columns = [];
    let resultsTable2Rows = [];
    let resultsTable2SortCol = null;
    let resultsTable2SortDir = "asc";
    let resultsTable2Filters = {};
    let resultsDevices = [];
    let resultsSavedName = null;
    let resultsLastRunMeta = {};

    var SAVED_REPORTS_KEY = "pergen_saved_reports";
    var SAVED_REPORTS_MAX = 50;
    var savedReportsOpenBound = false;
    var savedReportsListCache = [];
    function getSavedReports() {
      if (savedReportsListCache.length > 0) return savedReportsListCache;
      try {
        var raw = localStorage.getItem(SAVED_REPORTS_KEY);
        var list = [];
        if (raw) {
          try { list = JSON.parse(raw); } catch (e) {}
        }
        if (!Array.isArray(list)) list = [];
        if (list.length === 0) {
          var last = localStorage.getItem("pergen_last_pre");
          if (last) {
            try {
              var o = JSON.parse(last);
              list = [{
                run_id: o.run_id,
                name: o.name || "pre_report",
                created_at: o.created_at || null,
                devices: o.devices || [],
                device_results: o.device_results || [],
                post_created_at: null,
                post_device_results: null,
                comparison: null
              }];
              try { setSavedReports(list); } catch (e2) {}
            } catch (e) {}
          }
        }
        return list;
      } catch (e) { return []; }
    }
    async function refreshSavedReportsList() {
      try {
        var r = await fetch(API + "/api/reports");
        var data = await r.json();
        if (r.ok && Array.isArray(data.reports)) {
          savedReportsListCache = data.reports;
          renderSavedReportsList();
          return;
        }
      } catch (e) {}
      savedReportsListCache = [];
      renderSavedReportsList();
    }
    function setSavedReports(list) {
      try {
        localStorage.setItem(SAVED_REPORTS_KEY, JSON.stringify(list.slice(0, SAVED_REPORTS_MAX)));
      } catch (e) {}
    }
    function addSavedReport(report) {
      if (!report || !report.run_id) return;
      var list = getSavedReports();
      var runIdStr = String(report.run_id);
      var existing = list.findIndex(function(r) { return String(r.run_id || "") === runIdStr; });
      var entry = {
        run_id: report.run_id,
        name: report.name || "pre_report",
        created_at: report.created_at || null,
        devices: report.devices || [],
        device_results: report.device_results || [],
        post_created_at: (existing >= 0 ? list[existing].post_created_at : null) || null,
        post_device_results: (existing >= 0 ? list[existing].post_device_results : null) || null,
        comparison: (existing >= 0 ? list[existing].comparison : null) || null
      };
      if (existing >= 0) {
        list[existing] = entry;
      } else {
        list.unshift(entry);
      }
      setSavedReports(list);
    }
    function updateSavedReportPost(run_id, post_created_at, post_device_results, comparison) {
      var list = getSavedReports();
      var runIdStr = run_id ? String(run_id) : "";
      for (var i = 0; i < list.length; i++) {
        if (String(list[i].run_id || "") === runIdStr) {
          list[i].post_created_at = post_created_at;
          list[i].post_device_results = post_device_results;
          list[i].comparison = comparison;
          setSavedReports(list);
          return;
        }
      }
      var firstPre = list.find(function(r) { return !r.post_created_at; });
      if (firstPre && runIdStr) {
        firstPre.post_created_at = post_created_at;
        firstPre.post_device_results = post_device_results;
        firstPre.comparison = comparison;
        setSavedReports(list);
      }
    }
    async function deleteSavedReport(run_id) {
      if (!run_id) return;
      try {
        await fetch(API + "/api/reports/" + encodeURIComponent(run_id), { method: "DELETE" });
      } catch (e) {}
      await refreshSavedReportsList();
    }
    function renameSavedReport(run_id, newName) {
      if (!run_id || !(newName = (newName || "").trim())) return false;
      var list = getSavedReports();
      for (var i = 0; i < list.length; i++) {
        if (list[i].run_id === run_id) {
          list[i].name = newName;
          setSavedReports(list);
          return true;
        }
      }
      return false;
    }
    var REPORT_EXPORT_CSS = ":root{--bg:#0f172a;--card:#1e293b;--border:#334155;--text:#f1f5f9;--muted:#94a3b8;--accent:#58a6ff;--success:#10b981;--warn:#f59e0b;--danger:#f43f5e;--table-zebra-odd:#1e293b;--table-zebra-even:#0f172a;--table-header-bg:#1e293b}body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);padding:1rem;margin:0}.results-table{width:100%;border-collapse:collapse;font-size:0.9em}.results-table th,.results-table td{border:1px solid var(--border);padding:0.35rem 0.6rem;text-align:left}.results-table thead th{background:var(--table-header-bg);position:sticky;top:0}.results-table tbody tr:nth-child(odd){background:var(--table-zebra-odd)}.results-table tbody tr:nth-child(even){background:var(--table-zebra-even)}.results-table tbody tr:hover{background:rgba(88,166,255,0.15)}.cell-error,.device-error-cell{color:var(--danger)}.muted{color:var(--muted)}h1{font-size:1.1rem;margin-bottom:0.5rem}h2{font-size:1rem;margin:1.25rem 0 0.5rem 0}.export-section{margin-top:1.25rem}#shortfallWrap,#consistencyWrap{border-radius:10px;padding:1rem 1.25rem;margin-top:0.75rem;overflow-x:auto;max-width:100%}#shortfallWrap{border:1px solid var(--warn);border-left:4px solid var(--danger);background:rgba(245,158,11,0.08)}#shortfallWrap .shortfall-main-title{display:flex;align-items:center;gap:0.5rem;font-size:1.05rem;font-weight:700;color:var(--danger);margin:0 0 0.35rem 0}#shortfallWrap .shortfall-desc{font-size:0.9em;color:var(--muted);margin:0 0 0.75rem 0}.shortfall-device-block{border:1px solid rgba(244,63,94,0.4);border-left:4px solid var(--danger);background:rgba(244,63,94,0.06);border-radius:8px;padding:0.75rem 1rem;margin-bottom:1rem;overflow-x:auto;max-width:100%}.shortfall-device-block .shortfall-device-title{display:flex;align-items:center;gap:0.4rem;font-weight:700;color:var(--danger);font-size:0.95rem;margin-bottom:0.5rem}.shortfall-device-block .shortfall-lines{color:var(--warn);font-size:0.9em;margin-bottom:0.5rem}.shortfall-device-block .results-table{margin-top:0.5rem}#consistencyWrap{border:1px solid var(--warn);border-left:4px solid var(--warn);background:rgba(245,158,11,0.08)}#consistencyWrap .shortfall-main-title{color:var(--warn)}.consistency-group-block{border:1px solid rgba(245,158,11,0.5);border-left:4px solid var(--warn);background:rgba(245,158,11,0.06);border-radius:8px;padding:0.75rem 1rem;margin-bottom:1rem;overflow-x:auto;max-width:100%}.consistency-group-block .consistency-group-title{font-weight:700;color:var(--warn);font-size:0.95rem;margin-bottom:0.5rem}.consistency-cell-down{background:rgba(244,63,94,0.2);color:var(--danger);font-weight:600}.export-pre{max-height:300px;overflow:auto;font-size:0.8em;background:var(--card);padding:0.5rem;border-radius:4px;white-space:pre-wrap;word-break:break-all;border:1px solid var(--border)}.table-details{border:1px solid var(--border);border-radius:8px;padding:0.5rem 0.75rem;background:var(--card)}.table-details summary{list-style:none}.table-details summary::-webkit-details-marker{display:none}.table-details summary::before{content:\"\25b8\";display:inline-block;min-width:1.25em;font-size:1.1em;margin-right:0.5rem;transition:transform 0.15s;color:var(--muted);text-align:center}.table-details[open] summary::before{transform:rotate(90deg)}";
    function buildReportHtmlFromData(cols, rows, reportName, runCreatedAt) {
      var title = (reportName || "Report") + " — " + (runCreatedAt || "");
      var theadCells = cols.map(function(c) { return "<th>" + escapeHtml(c) + "</th>"; }).join("");
      var tbodyTrs = rows.map(function(row) {
        return "<tr>" + cols.map(function(col) {
          var val = row[col];
          var text = (val != null && val !== "") ? String(val) : "";
          return "<td>" + escapeHtml(text) + "</td>";
        }).join("") + "</tr>";
      }).join("");
      var tableHtml = "<table class=\"results-table\"><thead><tr>" + theadCells + "</tr></thead><tbody>" + tbodyTrs + "</tbody></table>";
      return "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>" + escapeHtml(title) + "</title><style>" + REPORT_EXPORT_CSS + "</style></head><body><h1>" + escapeHtml(title) + "</h1>" + tableHtml + "</body></html>";
    }
    /** Build full-page report HTML from main Pre/Post page: main table + shortfall + consistency + raw JSON + show run diff. */
    function buildFullPageReportHtml(reportName, runCreatedAt) {
      var title = (reportName || "Report") + " — " + (runCreatedAt || "");
      var exportData = getMainPageExportData();
      var mainTableHtml = "";
      if (exportData.rows.length) {
        var cols = exportData.columns;
        var rows = exportData.rows;
        var theadCells = cols.map(function(c) { return "<th>" + escapeHtml(c) + "</th>"; }).join("");
        var tbodyTrs = rows.map(function(row) {
          return "<tr>" + cols.map(function(col) {
            var val = row[col];
            var text = (val != null && val !== "") ? String(val) : "";
            return "<td>" + escapeHtml(text) + "</td>";
          }).join("") + "</tr>";
        }).join("");
        mainTableHtml = "<h2>Results</h2><div class=\"export-section\">" + "<table class=\"results-table\"><thead><tr>" + theadCells + "</tr></thead><tbody>" + tbodyTrs + "</tbody></table>" + "</div>";
      }
      var shortfallWrap = document.getElementById("shortfallWrap");
      var shortfallHtml = (shortfallWrap && shortfallWrap.style.display !== "none" && shortfallWrap.innerHTML) ? "<div class=\"export-section\" id=\"shortfallWrap\">" + shortfallWrap.innerHTML + "</div>" : "";
      var consistencyWrap = document.getElementById("consistencyWrap");
      var consistencyHtml = (consistencyWrap && consistencyWrap.style.display !== "none" && consistencyWrap.innerHTML) ? "<div class=\"export-section\" id=\"consistencyWrap\">" + consistencyWrap.innerHTML + "</div>" : "";
      var flappedPortsWrap = document.getElementById("flappedPortsWrap");
      var flappedPortsHtml = (flappedPortsWrap && flappedPortsWrap.style.display !== "none" && flappedPortsWrap.innerHTML) ? "<div class=\"export-section\" id=\"flappedPortsWrap\">" + flappedPortsWrap.innerHTML + "</div>" : "";
      var showRunDiffWrap = document.getElementById("showRunDiffWrap");
      var diffHtml = "";
      if (showRunDiffWrap && showRunDiffWrap.style.display !== "none") {
        var diffSummary = showRunDiffWrap.querySelector("summary");
        var diffInner = showRunDiffWrap.querySelector("div");
        var diffPre = showRunDiffWrap.querySelector("#showRunDiffOut");
        diffHtml = "<h2>Show run diff (PRE vs POST)</h2><div class=\"export-section\">";
        if (diffPre && diffPre.textContent) diffHtml += "<pre class=\"export-pre\">" + escapeHtml(diffPre.textContent) + "</pre>";
        diffHtml += "</div>";
      }
      var body = "<h1>" + escapeHtml(title) + "</h1>" + mainTableHtml + shortfallHtml + consistencyHtml + flappedPortsHtml + diffHtml;
      return "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>" + escapeHtml(title) + "</title><style>" + REPORT_EXPORT_CSS + "</style></head><body>" + body + "</body></html>";
    }
    function buildReportHtml() {
      return buildReportHtmlFromData(
        resultsTable2Columns || [],
        resultsTable2Rows || [],
        resultsSavedName || "Report",
        resultsLastRunMeta && resultsLastRunMeta.run_created_at ? resultsLastRunMeta.run_created_at : ""
      );
    }
    /** Build columns and rows from main page lastDeviceResults for export. */
    function getMainPageExportData() {
      var data = lastDeviceResults;
      if (!data || !data.length) return { columns: [], rows: [] };
      var fixedCols = ["hostname", "ip", "vendor", "model", "error"];
      var allParsedKeys = [];
      data.forEach(function(r) {
        var flat = r.parsed_flat || {};
        Object.keys(flat).forEach(function(k) { if (isScalarForTable(flat[k]) && allParsedKeys.indexOf(k) === -1) allParsedKeys.push(k); });
      });
      var parsedCols = (selectedParsedColumns.length ? selectedParsedColumns : allParsedKeys).filter(function(k) { return allParsedKeys.indexOf(k) !== -1 || data.some(function(r) { return isScalarForTable((r.parsed_flat || {})[k]); }); });
      var columns = fixedCols.concat(parsedCols);
      var rows = data.map(function(r) {
        var err = getDeviceResultError(r);
        if (err) {
          return { hostname: (r.hostname != null && r.hostname !== "") ? String(r.hostname) : (r.ip || "?"), ip: (r.ip != null && r.ip !== "") ? String(r.ip) : "", vendor: (r.vendor != null && r.vendor !== "") ? String(r.vendor) : "", model: (r.model != null && r.model !== "") ? String(r.model) : "", error: err };
        }
        var row = { error: "" };
        if (r.hostname != null && r.hostname !== "") row.hostname = r.hostname;
        if (r.ip != null && r.ip !== "") row.ip = r.ip;
        if (r.vendor != null && r.vendor !== "") row.vendor = r.vendor;
        if (r.model != null && r.model !== "") row.model = r.model;
        var flat = r.parsed_flat || {};
        Object.keys(flat).forEach(function(k) { if (isScalarForTable(flat[k]) && flat[k] != null && flat[k] !== "") row[k] = flat[k]; });
        return row;
      });
      return { columns: columns, rows: rows };
    }
    function renderSavedReportsList() {
      var preSel = document.getElementById("savedReportsPreSelect") || (typeof $ === "function" ? $("savedReportsPreSelect") : null);
      var postSel = document.getElementById("savedReportsPostSelect") || (typeof $ === "function" ? $("savedReportsPostSelect") : null);
      var emptyEl = document.getElementById("savedReportsEmpty") || (typeof $ === "function" ? $("savedReportsEmpty") : null);
      var detailsEl = document.getElementById("savedReportsDetails");
      var list = getSavedReports();
      if (list.length === 0 && typeof lastRunId !== "undefined" && lastRunId && typeof lastRunDevices !== "undefined" && lastRunDevices && lastRunDevices.length) {
        var curName = typeof lastRunMeta !== "undefined" && lastRunMeta && lastRunMeta.run_created_at ? ("pre_" + (lastRunMeta.run_created_at || "")) : "Current report";
        list = [{
          run_id: lastRunId,
          name: curName,
          created_at: (typeof lastRunMeta !== "undefined" && lastRunMeta) ? lastRunMeta.run_created_at : null,
          devices: lastRunDevices || [],
          device_results: (typeof lastDeviceResults !== "undefined" ? lastDeviceResults : null) || [],
          post_created_at: (typeof lastRunMeta !== "undefined" && lastRunMeta) ? lastRunMeta.post_created_at : null,
          post_device_results: null,
          comparison: (typeof lastComparison !== "undefined" ? lastComparison : null) || null
        }];
      }
      if (preSel) {
        preSel.innerHTML = "<option value=\"\">— Seçin —</option>" + list.map(function(r, idx) {
          var label = (r.name || "Rapor") + " — " + (r.created_at || "");
          return "<option value=\"" + idx + "\">" + escapeHtml(label) + "</option>";
        }).join("");
      }
      if (postSel) {
        postSel.innerHTML = "<option value=\"\">— Seçin —</option>" + list.map(function(r, idx) {
          if (!r.post_created_at) return "";
          var label = (r.name || "Rapor") + " — PRE: " + (r.created_at || "") + " / POST: " + (r.post_created_at || "");
          return "<option value=\"" + idx + "\">" + escapeHtml(label) + "</option>";
        }).filter(Boolean).join("");
      }
      if (emptyEl) emptyEl.style.display = list.length === 0 ? "block" : "none";
      if (detailsEl && list.length > 0) detailsEl.setAttribute("open", "");
    }
    function bindSavedReportsOpen() {
      var preOpen = $("savedReportsPreOpen");
      var postOpen = $("savedReportsPostOpen");
      var preSel = $("savedReportsPreSelect");
      var postSel = $("savedReportsPostSelect");
      var preDelete = document.getElementById("savedReportsPreDelete");
      var postDelete = document.getElementById("savedReportsPostDelete");
      if (preOpen && preSel) {
        preOpen.addEventListener("click", async function() {
          var idx = parseInt(preSel.value, 10);
          var list = getSavedReports();
          if (isNaN(idx) || idx < 0 || idx >= list.length) return;
          await openSavedReport(list[idx]);
        });
      }
      if (postOpen && postSel) {
        postOpen.addEventListener("click", async function() {
          var idx = parseInt(postSel.value, 10);
          var list = getSavedReports();
          if (isNaN(idx) || idx < 0 || idx >= list.length) return;
          await openSavedReport(list[idx]);
        });
      }
      if (preDelete && preSel) {
        preDelete.addEventListener("click", async function() {
          var idx = parseInt(preSel.value, 10);
          var list = getSavedReports();
          if (isNaN(idx) || idx < 0 || idx >= list.length) { alert("Select a report to delete."); return; }
          var r = list[idx];
          if (!confirm("Delete report \"" + (r.name || r.run_id) + "\"?")) return;
          await deleteSavedReport(r.run_id);
        });
      }
      if (postDelete && postSel) {
        postDelete.addEventListener("click", async function() {
          var idx = parseInt(postSel.value, 10);
          var list = getSavedReports();
          if (isNaN(idx) || idx < 0 || idx >= list.length) { alert("Select a report to delete."); return; }
          var r = list[idx];
          if (!confirm("Delete report \"" + (r.name || r.run_id) + "\"?")) return;
          await deleteSavedReport(r.run_id);
        });
      }
    }
    async function openSavedReport(report) {
      if (!report.run_id) {
        $("runStatus").textContent = "Report has no run_id.";
        return;
      }
      var devices = report.devices || [];
      var deviceResults = report.device_results || [];
      if (!devices.length || !deviceResults.length) {
        try {
          var getRes = await fetch(API + "/api/reports/" + encodeURIComponent(report.run_id) + "?restore=1");
          var fullReport = await getRes.json();
          if (!getRes.ok) {
            $("runStatus").textContent = "Could not load report: " + (fullReport.error || getRes.status);
            return;
          }
          report = fullReport;
          devices = report.devices || [];
          deviceResults = report.device_results || [];
        } catch (e) {
          $("runStatus").textContent = "Error loading report: " + e.message;
          return;
        }
      }
      if (!devices.length) {
        $("runStatus").textContent = "Report has no devices.";
        return;
      }
      try {
        var restoreRes = await fetch(API + "/api/run/pre/restore", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            run_id: report.run_id,
            devices: devices,
            device_results: deviceResults,
            created_at: report.created_at || null
          })
        });
        var restoreData = await restoreRes.json();
        if (!restoreRes.ok) {
          $("runStatus").textContent = "Could not restore run: " + (restoreData.error || restoreRes.status);
          return;
        }
      } catch (e) {
        $("runStatus").textContent = "Error restoring run: " + e.message;
        return;
      }
      resultsRunId = report.run_id;
      resultsSavedName = report.name;
      resultsDeviceResults = report.post_device_results || report.device_results || [];
      resultsDevices = report.devices || [];
      resultsLastRunMeta = {
        run_created_at: report.created_at || null,
        post_created_at: report.post_created_at || null
      };
      lastRunId = report.run_id;
      lastDeviceResults = report.post_device_results || report.device_results || [];
      lastPreDeviceResults = report.device_results || [];
      lastRunDevices = report.devices || [];
      lastComparison = report.comparison || [];
      lastRunMeta = { run_created_at: report.created_at || null, post_created_at: report.post_created_at || null };
      $("phase").value = "PRE";
      updateRunPostButtonVisibility();
      showResultsTable(true);
      renderResultsTable();
      renderShortfall(lastPreDeviceResults);
      renderConsistency(lastRunDevices, lastPreDeviceResults);
      renderFlappedPorts24h(lastDeviceResults);
      $("runStatus").textContent = "Opened: " + (report.name || "report") + (report.post_created_at ? " (PRE+POST). Run POST again for these devices if needed." : ". Run POST for these devices when ready.");
      if (location.hash !== "#prepost" && location.hash !== "#prepost-results") location.hash = "prepost";
      var mainReportNameInp = document.getElementById("mainReportNameInput");
      if (mainReportNameInp) mainReportNameInp.value = report.name || "";
      var resultsProgressWrap = $("resultsProgressWrap");
      var resultsDoneWrap = $("resultsDoneWrap");
      if (resultsProgressWrap) resultsProgressWrap.style.display = "none";
      if (resultsDoneWrap) resultsDoneWrap.style.display = "block";
      var resultsSavedNameEl = $("resultsSavedName");
      if (resultsSavedNameEl) resultsSavedNameEl.textContent = (report.post_created_at ? "Rapor (PRE+POST): " : "Rapor (PRE): ") + (report.name || "");
      var postCheckBtn = $("postCheckBtn");
      if (postCheckBtn) postCheckBtn.style.display = "block";
      var nameInp = document.getElementById("resultsReportNameInput");
      if (nameInp) nameInp.value = resultsSavedName || "";
      var postResultWrap = $("postResultWrap");
      if (postResultWrap) {
        if (report.comparison && report.comparison.length) {
          postResultWrap.style.display = "block";
          var postComparison = $("postComparison");
          if (postComparison) postComparison.textContent = JSON.stringify(report.comparison, null, 2);
        } else {
          postResultWrap.style.display = "none";
        }
      }
      renderResultsTable2(resultsDeviceResults);
    }

    function preReportName(fabric, role, deviceCount) {
      const now = new Date();
      const dd = String(now.getDate()).padStart(2, "0");
      const mm = String(now.getMonth() + 1).padStart(2, "0");
      const yyyy = now.getFullYear();
      const hh = String(now.getHours()).padStart(2, "0");
      const min = String(now.getMinutes()).padStart(2, "0");
      const fabricPart = (fabric || "unknown").toString().trim().toLowerCase().replace(/\s+/g, "_") || "unknown";
      const rolePart = (role || "all").toString().trim().toLowerCase().replace(/\s+/g, "_") || "all";
      const countPart = (deviceCount != null && !isNaN(deviceCount)) ? Number(deviceCount) : 0;
      return "pre_" + dd + mm + yyyy + "-" + hh + min + "_" + fabricPart + "_" + rolePart + "_" + countPart;
    }

    async function initResultsPage() {
      if (!savedReportsOpenBound) {
        bindSavedReportsOpen();
        savedReportsOpenBound = true;
      }
      await refreshSavedReportsList();
      const raw = localStorage.getItem("pergen_pre_devices");
      try {
        localStorage.removeItem("pergen_pre_devices");
      } catch (e) {}
      if (!raw) {
        $("resultsProgressWrap").style.display = "none";
        var doneWrap = $("resultsDoneWrap");
        if (doneWrap) doneWrap.style.display = "block";
        $("resultsSavedName").textContent = "Device list not found. Select devices on the main page and run PRE first.";
        try {
          const last = localStorage.getItem("pergen_last_pre");
          if (last) {
            const o = JSON.parse(last);
            resultsRunId = o.run_id;
            resultsSavedName = o.name;
            $("resultsDoneWrap").style.display = "block";
            $("resultsSavedName").textContent = "Last saved report: " + (o.name || "");
            $("postCheckBtn").style.display = "block";
            var nameInp = document.getElementById("resultsReportNameInput");
            if (nameInp) nameInp.value = resultsSavedName || "";
          } else {
            $("postCheckBtn").style.display = "none";
          }
        } catch (e) {
          $("postCheckBtn").style.display = "none";
        }
        return;
      }
      let devices;
      try {
        devices = JSON.parse(raw);
      } catch (e) {
        $("resultsProgressText").textContent = "Could not read device list.";
        return;
      }
      if (!devices.length) {
        $("resultsProgressText").textContent = "No devices.";
        return;
      }
      $("resultsProgressWrap").style.display = "block";
      $("resultsDoneWrap").style.display = "none";
      const total = devices.length;
      $("resultsProgressText").textContent = "0/" + total + " devices checked";
      $("resultsProgressBar").style.width = "0%";
      const deviceResults = [];
      for (let i = 0; i < devices.length; i++) {
        try {
          const r = await fetch(API + "/api/run/device", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ device: devices[i] }),
          });
          const d = await r.json();
          var res = d.device_result || { hostname: devices[i].hostname, ip: devices[i].ip, error: d.error || "No result" };
          var err = getDeviceResultError(res) || res.error || null;
          addDeviceEvent(err ? "fail" : "success", res.hostname || res.ip || "?", err || "Login/run OK");
          logDeviceCommandWarnings(res);
          deviceResults.push(res);
        } catch (e) {
          addDeviceEvent("fail", devices[i].hostname || devices[i].ip || "?", e.message);
          deviceResults.push({ hostname: devices[i].hostname, ip: devices[i].ip, error: e.message });
        }
        $("resultsProgressText").textContent = (i + 1) + "/" + total + " devices checked";
        $("resultsProgressBar").style.width = ((i + 1) / total * 100) + "%";
      }
      var reportFabric = (devices.length && devices[0].fabric) ? devices[0].fabric : "";
      var reportRole = (devices.length && devices[0].role) ? devices[0].role : "";
      resultsSavedName = preReportName(reportFabric, reportRole, devices.length);
      try {
        const cr = await fetch(API + "/api/run/pre/create", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ devices: devices, device_results: deviceResults, name: resultsSavedName }),
        });
        const cj = await cr.json();
        if (!cr.ok) throw new Error(cj.error || "Run creation failed");
        resultsRunId = cj.run_id;
        resultsDeviceResults = deviceResults;
        resultsDevices = devices;
        resultsLastRunMeta = { run_created_at: cj.run_created_at };
      } catch (e) {
        $("resultsProgressText").textContent = "Error: " + e.message;
        return;
      }
      try {
        localStorage.setItem("pergen_last_pre", JSON.stringify({
          name: resultsSavedName,
          run_id: resultsRunId,
          devices: devices,
          device_results: deviceResults,
          created_at: resultsLastRunMeta.run_created_at,
        }));
        addSavedReport({
          run_id: resultsRunId,
          name: resultsSavedName,
          created_at: resultsLastRunMeta.run_created_at,
          devices: devices,
          device_results: deviceResults
        });
      } catch (e) {}
      $("resultsProgressWrap").style.display = "none";
      $("resultsDoneWrap").style.display = "block";
      $("resultsSavedName").textContent = "Saved report: " + resultsSavedName;
      renderResultsTable2(deviceResults);
      renderFlappedPorts24h(deviceResults);
      $("postCheckBtn").style.display = "block";
      $("postResultWrap").style.display = "none";
      var nameInp = document.getElementById("resultsReportNameInput");
      if (nameInp) nameInp.value = resultsSavedName || "";
      await refreshSavedReportsList();
    }

    function renderResultsTable2(data) {
      if (!data.length) return;
      const fixedCols = ["hostname", "ip", "vendor", "model", "error"];
      const runCols = [];
      if (resultsLastRunMeta.run_created_at) runCols.push("Pre check");
      if (resultsLastRunMeta.post_created_at) runCols.push("Post check");
      const allParsedKeys = [];
      data.forEach(r => {
        const flat = r.parsed_flat || {};
        Object.keys(flat).forEach(k => { if (isScalarForTable(flat[k]) && !allParsedKeys.includes(k)) allParsedKeys.push(k); });
      });
      resultsTable2Columns = fixedCols.concat(runCols).concat(allParsedKeys);
      resultsTable2Rows = data.map(r => {
        const err = getDeviceResultError(r);
        if (err) {
          return {
            hostname: (r.hostname != null && r.hostname !== "") ? String(r.hostname) : (r.ip || "?"),
            ip: (r.ip != null && r.ip !== "") ? String(r.ip) : "",
            vendor: (r.vendor != null && r.vendor !== "") ? String(r.vendor) : "",
            model: (r.model != null && r.model !== "") ? String(r.model) : "",
            error: err,
            _isError: true
          };
        }
        const row = { error: "" };
        if (r.hostname != null && r.hostname !== "") row.hostname = r.hostname;
        if (r.ip != null && r.ip !== "") row.ip = r.ip;
        if (r.vendor != null && r.vendor !== "") row.vendor = r.vendor;
        if (r.model != null && r.model !== "") row.model = r.model;
        const flat = r.parsed_flat || {};
        Object.keys(flat).forEach(k => { if (isScalarForTable(flat[k]) && flat[k] != null && flat[k] !== "") row[k] = flat[k]; });
        if (resultsLastRunMeta.run_created_at) row["Pre check"] = formatLocalDateTime(resultsLastRunMeta.run_created_at);
        if (resultsLastRunMeta.post_created_at) row["Post check"] = formatLocalDateTime(resultsLastRunMeta.post_created_at);
        return row;
      });
      renderResultsTable2Content();
    }
    function renderResultsTable2Content() {
      const thead = $("resultsThead2");
      const tbody = $("resultsTbody2");
      if (!thead || !tbody || !resultsTable2Columns.length) return;
      let rows = resultsTable2Rows.slice();
      resultsTable2Columns.forEach(col => {
        const f = resultsTable2Filters[col];
        if (!f || !(f.value || "").trim()) return;
        const val = (f.value || "").trim().toLowerCase();
        const typ = f.type || "in";
        rows = rows.filter(r => {
          const cell = (r[col] != null ? String(r[col]) : "").toLowerCase();
          const has = cell.indexOf(val) !== -1;
          return typ === "in" ? has : !has;
        });
      });
      if (resultsTable2SortCol && resultsTable2Columns.includes(resultsTable2SortCol)) {
        rows.sort((a, b) => {
          const va = a[resultsTable2SortCol]; const vb = b[resultsTable2SortCol];
          const sa = (va == null ? "" : String(va));
          const sb = (vb == null ? "" : String(vb));
          const c = sa.localeCompare(sb, undefined, { numeric: true });
          return resultsTable2SortDir === "asc" ? c : -c;
        });
      }
      var results2Wrap = document.getElementById("resultsDoneWrap");
      var results2TableEl = $("resultsTable2");
      if (results2Wrap && results2TableEl) {
        var wrapDiv = results2TableEl.parentElement;
        var chipsBar = wrapDiv ? wrapDiv.querySelector(".filter-chips-bar") : null;
        if (wrapDiv && !chipsBar) { chipsBar = document.createElement("div"); chipsBar.className = "filter-chips-bar"; wrapDiv.insertBefore(chipsBar, results2TableEl); }
        if (chipsBar) {
          chipsBar.innerHTML = "";
          resultsTable2Columns.forEach(col => {
            const f = resultsTable2Filters[col];
            if (!f || !(f.value || "").trim()) return;
            const chip = document.createElement("span");
            chip.className = "filter-chip";
            const typ = (f.type || "in") === "not-in" ? "not-in" : "in";
            chip.textContent = col + " " + typ + " \"" + (f.value || "").trim() + "\" ";
            const xBtn = document.createElement("button");
            xBtn.type = "button";
            xBtn.className = "filter-chip-remove";
            xBtn.textContent = "\u00d7";
            xBtn.setAttribute("aria-label", "Remove filter");
            xBtn.addEventListener("click", () => { resultsTable2Filters[col] = resultsTable2Filters[col] || {}; resultsTable2Filters[col].value = ""; renderResultsTable2Content(); });
            chip.appendChild(xBtn);
            chipsBar.appendChild(chip);
          });
        }
      }
      const theadTr = document.createElement("tr");
      const filterTr = document.createElement("tr");
      filterTr.className = "filter-row";
      resultsTable2Columns.forEach(col => {
        const th = document.createElement("th");
        th.className = "sortable";
        th.textContent = col;
        th.dataset.col = col;
        const sortSpan = document.createElement("span");
        sortSpan.className = "sort-icon";
        sortSpan.textContent = resultsTable2SortCol === col ? (resultsTable2SortDir === "asc" ? " \u25b2" : " \u25bc") : "";
        th.appendChild(sortSpan);
        th.addEventListener("click", () => {
          if (resultsTable2SortCol === col) resultsTable2SortDir = resultsTable2SortDir === "asc" ? "desc" : "asc";
          else { resultsTable2SortCol = col; resultsTable2SortDir = "asc"; }
          renderResultsTable2Content();
        });
        theadTr.appendChild(th);
        const fth = document.createElement("th");
        const sel = document.createElement("select");
        sel.dataset.col = col;
        sel.innerHTML = "<option value=\"in\">in</option><option value=\"not-in\">not-in</option>";
        const f = resultsTable2Filters[col];
        if (f) sel.value = f.type || "in";
        sel.addEventListener("change", () => {
          resultsTable2Filters[col] = resultsTable2Filters[col] || {}; resultsTable2Filters[col].type = sel.value; renderResultsTable2Content();
        });
        const inp = document.createElement("input");
        inp.type = "text";
        inp.placeholder = "Filter\u2026 Enter to apply";
        if (f && f.value) inp.value = f.value;
        inp.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            resultsTable2Filters[col] = resultsTable2Filters[col] || {}; resultsTable2Filters[col].type = sel.value; resultsTable2Filters[col].value = inp.value.trim(); renderResultsTable2Content();
          }
        });
        fth.appendChild(sel);
        fth.appendChild(inp);
        filterTr.appendChild(fth);
      });
      thead.innerHTML = "";
      thead.appendChild(theadTr);
      thead.appendChild(filterTr);
      tbody.innerHTML = rows.map(row => {
        const trClass = row._isError ? " class=\"row-error\"" : "";
        return "<tr" + trClass + ">" + resultsTable2Columns.map(col => {
          const val = row[col] != null && row[col] !== "" ? String(row[col]) : "";
          if (col === "hostname" && row._isError) {
            return "<td class=\"device-error-cell\"><span class=\"device-error-icon\" title=\"" + escapeHtml(row.error || "") + "\">\u2715</span> " + escapeHtml(val) + "</td>";
          }
          if (col === "error") {
            return "<td class=\"cell-error\" title=\"" + escapeHtml(val) + "\">" + escapeHtml(val) + "</td>";
          }
          return "<td>" + escapeHtml(val) + "</td>";
        }).join("") + "</tr>";
      }).join("");
    }

    $("postCheckBtn").addEventListener("click", async function() {
      if (!resultsRunId) {
        const saved = localStorage.getItem("pergen_last_pre");
        if (saved) {
          try {
            const o = JSON.parse(saved);
            resultsRunId = o.run_id;
          } catch (e) {}
        }
      }
      if (!resultsRunId) {
        alert("Last saved PRE report not found.");
        return;
      }
      this.disabled = true;
      try {
        const r = await fetch(API + "/api/run/post", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ run_id: resultsRunId }),
        });
        const d = await r.json();
        if (!r.ok) {
          alert(d.error || "Post check başarısız");
          return;
        }
        var postRunId = d.run_id || resultsRunId;
        if (postRunId) resultsRunId = postRunId;
        resultsLastRunMeta = { run_created_at: d.run_created_at, post_created_at: d.post_created_at };
        resultsDeviceResults = d.device_results || [];
        updateSavedReportPost(postRunId, d.post_created_at, d.device_results, d.comparison);
        try {
          var lastPre = localStorage.getItem("pergen_last_pre");
          var lastObj = lastPre ? JSON.parse(lastPre) : null;
          if (lastObj && String(lastObj.run_id || "") === String(postRunId || "")) {
            lastObj.post_created_at = d.post_created_at;
            lastObj.device_results = d.device_results;
            lastObj.comparison = d.comparison;
            localStorage.setItem("pergen_last_pre", JSON.stringify(lastObj));
          }
        } catch (e) {}
        renderResultsTable2(resultsDeviceResults);
        renderFlappedPorts24h(resultsDeviceResults);
        $("postResultWrap").style.display = "block";
        $("postComparison").textContent = JSON.stringify(d.comparison || [], null, 2);
        refreshSavedReportsList();
      } catch (e) {
        alert("Error: " + e.message);
      }
      this.disabled = false;
    });

    var resultsSaveNameBtn = document.getElementById("resultsSaveNameBtn");
    if (resultsSaveNameBtn) resultsSaveNameBtn.addEventListener("click", function() {
      var nameInp = document.getElementById("resultsReportNameInput");
      var newName = nameInp && nameInp.value ? nameInp.value.trim() : "";
      if (!newName) { alert("Enter a report name."); return; }
      if (!resultsRunId) { alert("No report to rename."); return; }
      if (renameSavedReport(resultsRunId, newName)) {
        resultsSavedName = newName;
        $("resultsSavedName").textContent = (resultsLastRunMeta && resultsLastRunMeta.post_created_at ? "Rapor (PRE+POST): " : "Rapor (PRE): ") + resultsSavedName;
        renderSavedReportsList();
      }
    });
    var resultsExportZipBtn = document.getElementById("resultsExportZipBtn");
    if (resultsExportZipBtn) resultsExportZipBtn.addEventListener("click", function() {
      if (typeof JSZip === "undefined") { alert("JSZip not loaded."); return; }
      var name = (resultsSavedName || "report").replace(/[^\w\-_.]/g, "_");
      var reportHtml = buildReportHtml();
      var zip = new JSZip();
      zip.file("report.html", reportHtml);
      zip.generateAsync({ type: "blob" }).then(function(blob) {
        var a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "report_" + name + ".zip";
        a.click();
        URL.revokeObjectURL(a.href);
      }).catch(function(e) { alert("Export failed: " + (e && e.message)); });
    });
    var mainExportZipBtn = document.getElementById("mainExportZipBtn");
    if (mainExportZipBtn) mainExportZipBtn.addEventListener("click", function() {
      if (typeof JSZip === "undefined") { alert("JSZip not loaded."); return; }
      var nameInp = document.getElementById("mainReportNameInput");
      var reportName = (nameInp && nameInp.value && nameInp.value.trim()) ? nameInp.value.trim() : preReportName(($("fabric") && $("fabric").value) ? $("fabric").value.trim() : "", ($("role") && $("role").value) ? $("role").value.trim() : "", (lastRunDevices || []).length);
      var safeName = (reportName || "report").replace(/[^\w\-_.]/g, "_");
      var exportData = getMainPageExportData();
      if (!exportData.rows.length) { alert("No results to export. Run PRE first."); return; }
      var reportHtml = buildFullPageReportHtml(reportName, lastRunMeta && lastRunMeta.run_created_at ? lastRunMeta.run_created_at : "");
      var zip = new JSZip();
      zip.file("report.html", reportHtml);
      zip.generateAsync({ type: "blob" }).then(function(blob) {
        var a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "report_" + safeName + ".zip";
        a.click();
        URL.revokeObjectURL(a.href);
      }).catch(function(e) { alert("Export failed: " + (e && e.message)); });
    });

    document.querySelector("nav").addEventListener("click", function(e) {
      const a = e.target.closest("a[href^=\"#\"]");
      if (a) { location.hash = a.getAttribute("href"); }
    });

    var credListCache = [];
    var credSortCol = null;
    var credSortDir = "asc";
    var credFilters = {};
    function renderCredTable() {
      const thead = $("credThead");
      const tbody = $("credListBody");
      if (!tbody) return;
      let rows = credListCache.slice();
      ["name", "method"].forEach(function(col) {
        var f = credFilters[col];
        if (!f || !(f.value || "").trim()) return;
        var val = (f.value || "").trim().toLowerCase();
        var typ = f.type || "in";
        rows = rows.filter(function(c) {
          var cell = (c[col] != null ? String(c[col]) : "").toLowerCase();
          var has = cell.indexOf(val) !== -1;
          return typ === "in" ? has : !has;
        });
      });
      if (credSortCol && ["name", "method"].indexOf(credSortCol) !== -1) {
        rows.sort(function(a, b) {
          var sa = (a[credSortCol] != null ? String(a[credSortCol]) : "");
          var sb = (b[credSortCol] != null ? String(b[credSortCol]) : "");
          var c = sa.localeCompare(sb, undefined, { numeric: true });
          return credSortDir === "asc" ? c : -c;
        });
      }
      var credListEl = document.querySelector(".credential-list");
      var credTableEl = credListEl ? credListEl.querySelector("table") : null;
      if (credListEl && credTableEl) {
        var chipsBar = credListEl.querySelector(".filter-chips-bar");
        if (!chipsBar) { chipsBar = document.createElement("div"); chipsBar.className = "filter-chips-bar"; credListEl.insertBefore(chipsBar, credTableEl); }
        chipsBar.innerHTML = "";
        ["name", "method"].forEach(function(col) {
          var f = credFilters[col];
          if (!f || !(f.value || "").trim()) return;
          var chip = document.createElement("span");
          chip.className = "filter-chip";
          var typ = (f.type || "in") === "not-in" ? "not-in" : "in";
          var label = col === "name" ? "Name" : "Method";
          chip.textContent = label + " " + typ + " \"" + (f.value || "").trim() + "\" ";
          var xBtn = document.createElement("button");
          xBtn.type = "button";
          xBtn.className = "filter-chip-remove";
          xBtn.textContent = "\u00d7";
          xBtn.setAttribute("aria-label", "Remove filter");
          (function(c) { xBtn.addEventListener("click", function() { credFilters[c] = credFilters[c] || {}; credFilters[c].value = ""; renderCredTable(); }); })(col);
          chip.appendChild(xBtn);
          chipsBar.appendChild(chip);
        });
      }
      if (thead) {
        var tr1 = document.createElement("tr");
        ["name", "method"].forEach(function(col) {
          var th = document.createElement("th");
          th.className = "sortable";
          th.textContent = col === "name" ? "Name" : "Method";
          th.dataset.col = col;
          var span = document.createElement("span");
          span.className = "sort-icon";
          span.textContent = credSortCol === col ? (credSortDir === "asc" ? " \u25b2" : " \u25bc") : "";
          th.appendChild(span);
          th.addEventListener("click", function() {
            if (credSortCol === col) credSortDir = credSortDir === "asc" ? "desc" : "asc";
            else { credSortCol = col; credSortDir = "asc"; }
            renderCredTable();
          });
          tr1.appendChild(th);
        });
        tr1.appendChild(document.createElement("th"));
        var filterTr = document.createElement("tr");
        filterTr.className = "filter-row";
        ["name", "method"].forEach(function(col) {
          var fth = document.createElement("th");
          var sel = document.createElement("select");
          sel.innerHTML = "<option value=\"in\">in</option><option value=\"not-in\">not-in</option>";
          var f = credFilters[col];
          if (f) sel.value = f.type || "in";
          sel.addEventListener("change", function() {
            credFilters[col] = credFilters[col] || {}; credFilters[col].type = sel.value; renderCredTable();
          });
          var inp = document.createElement("input");
          inp.type = "text";
          inp.placeholder = "Filter\u2026 Enter to apply";
          if (f && f.value) inp.value = f.value;
          inp.addEventListener("keydown", function(e) {
            if (e.key === "Enter") {
              credFilters[col] = credFilters[col] || {}; credFilters[col].type = sel.value; credFilters[col].value = inp.value.trim(); renderCredTable();
            }
          });
          fth.appendChild(sel);
          fth.appendChild(inp);
          filterTr.appendChild(fth);
        });
        filterTr.appendChild(document.createElement("th"));
        thead.innerHTML = "";
        thead.appendChild(tr1);
        thead.appendChild(filterTr);
      }
      tbody.innerHTML = rows.map(function(c) {
        return "<tr><td>" + escapeHtml(c.name) + "</td><td>" + escapeHtml(c.method) + "</td><td><button type=\"button\" class=\"cred-update\" data-name=\"" + escapeHtml(c.name) + "\" data-method=\"" + escapeHtml(c.method) + "\">Update</button> <button type=\"button\" class=\"cred-validate\" data-name=\"" + escapeHtml(c.name) + "\">Validate</button> <button type=\"button\" class=\"cred-delete\" data-name=\"" + escapeHtml(c.name) + "\">Delete</button></td></tr>";
      }).join("");
      tbody.querySelectorAll(".cred-update").forEach(function(btn) {
        btn.addEventListener("click", function() {
          var name = btn.getAttribute("data-name");
          var method = (btn.getAttribute("data-method") || "basic").toLowerCase();
          $("credName").value = name;
          $("credMethod").value = method;
          $("credBasicFields").style.display = method === "basic" ? "block" : "none";
          $("credApiKeyFields").style.display = method === "api_key" ? "block" : "none";
          $("credPassword").value = "";
          $("credApiKey").value = "";
          $("credMsg").textContent = "Enter new password and click Add / Update credential.";
          $("credMsg").className = "credential-msg";
          (method === "basic" ? $("credPassword") : $("credApiKey")).focus();
        });
      });
      tbody.querySelectorAll(".cred-validate").forEach(function(btn) {
        btn.addEventListener("click", function() {
          var name = btn.getAttribute("data-name");
          $("credMsg").textContent = "Validating…";
          $("credMsg").className = "credential-msg";
          fetch(API + "/api/credentials/" + encodeURIComponent(name) + "/validate", { method: "POST" })
            .then(function(r) { return r.json(); })
            .then(function(d) {
              if (d.ok) {
                var msg = (d.device ? d.device + ": " : "") + (d.message || "Login success.");
                if (d.uptime) msg += " Uptime: " + d.uptime;
                $("credMsg").textContent = msg;
                $("credMsg").className = "credential-msg ok";
              } else {
                $("credMsg").textContent = (d.device ? d.device + ": " : "") + (d.error || "Validation failed.");
                $("credMsg").className = "credential-msg error";
              }
            })
            .catch(function(e) {
              $("credMsg").textContent = "Error: " + (e.message || "Request failed.");
              $("credMsg").className = "credential-msg error";
            });
        });
      });
      tbody.querySelectorAll(".cred-delete").forEach(function(btn) {
        btn.addEventListener("click", function() {
          var name = btn.getAttribute("data-name");
          fetch(API + "/api/credentials/" + encodeURIComponent(name), { method: "DELETE" })
            .then(function(r) { return r.json().then(function(d) { return { ok: r.ok, d: d }; }); })
            .then(function(o) {
              $("credMsg").textContent = o.ok ? "Deleted." : (o.d && o.d.error ? o.d.error : "Error");
              $("credMsg").className = "credential-msg " + (o.ok ? "ok" : "error");
              loadCredentials();
            });
        });
      });
    }
    function loadCredentials() {
      get("/api/credentials").then(function(data) {
        credListCache = data.credentials || [];
        renderCredTable();
      }).catch(function(e) {
        credListCache = [];
        $("credListBody").innerHTML = "<tr><td colspan=\"3\">Error loading credentials.</td></tr>";
      });
    }
    $("credMethod").addEventListener("change", function() {
      const isBasic = this.value === "basic";
      $("credBasicFields").style.display = isBasic ? "block" : "none";
      $("credApiKeyFields").style.display = isBasic ? "none" : "block";
    });
    $("credSubmit").addEventListener("click", function() {
      const name = ($("credName").value || "").trim();
      const method = ($("credMethod").value || "basic").toLowerCase();
      if (!name) { $("credMsg").textContent = "Name is required."; $("credMsg").className = "credential-msg error"; return; }
      const body = method === "api_key"
        ? { name: name, method: "api_key", api_key: ($("credApiKey").value || "").trim() }
        : { name: name, method: "basic", username: ($("credUsername").value || "").trim(), password: ($("credPassword").value || "").trim() };
      fetch(API + "/api/credentials", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then(function(r) { return r.json().then(function(d) { return { ok: r.ok, d }; }); }).then(function(o) {
        $("credMsg").textContent = o.ok ? "Saved." : (o.d.error || "Error");
        $("credMsg").className = "credential-msg " + (o.ok ? "ok" : "error");
        if (o.ok) { loadCredentials(); $("credPassword").value = ""; $("credApiKey").value = ""; }
      }).catch(function(e) {
        $("credMsg").textContent = "Error: " + e.message;
        $("credMsg").className = "credential-msg error";
      });
    });

    loadFabrics();
