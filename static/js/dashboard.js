(function () {
  const state = {
    config: null,
    data: null,
    hourScope: "all",
    notifyEnabled: false,
    formDirty: false,
    refreshTimer: null,
    lastNotifyAt: 0,
  };

  const labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const notifyStorageKey = "checkmygym-notify-enabled";
  const notifyThreshold = 4;
  const notifyCooldownMs = 5 * 60 * 1000;

  const elements = {};

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    bindElements();
    bindEvents();
    loadNotifyPreference();
    setFeedback("Loading dashboard...");

    try {
      await bootstrap();
      state.refreshTimer = window.setInterval(() => {
        refreshData(false).catch((error) => {
          console.error(error);
        });
      }, 60000);
    } catch (error) {
      console.error(error);
      setFeedback(getErrorMessage(error), true);
    }
  }

  function bindElements() {
    const ids = [
      "notify-toggle",
      "refresh-now",
      "poll-now",
      "save-config",
      "config-form",
      "hour-scope",
      "current-count",
      "favorite-count",
      "sample-count",
      "last-updated",
      "open-hours-label",
      "current-people-list",
      "favorite-records-list",
      "weekday-bars",
      "hour-bars",
      "feedback",
      "storage_dir",
      "poll_interval_minutes",
      "shop_id",
      "api_base",
      "open_hour_start",
      "open_hour_end",
    ];

    ids.forEach((id) => {
      elements[id] = document.getElementById(id);
    });
  }

  function bindEvents() {
    elements["refresh-now"].addEventListener("click", () => {
      refreshData(true).catch((error) => {
        console.error(error);
        setFeedback(getErrorMessage(error), true);
      });
    });

    elements["poll-now"].addEventListener("click", async () => {
      try {
        setButtonBusy(elements["poll-now"], true, "Polling...");
        await fetchJson("/api/poll", { method: "POST" });
        await delay(900);
        await refreshData(false);
        setFeedback("Polling completed.");
      } catch (error) {
        console.error(error);
        setFeedback(getErrorMessage(error), true);
      } finally {
        setButtonBusy(elements["poll-now"], false, "Poll Now");
      }
    });

    elements["config-form"].addEventListener("submit", async (event) => {
      event.preventDefault();
      await saveConfig();
    });

    elements["hour-scope"].addEventListener("change", (event) => {
      state.hourScope = event.target.value;
      renderHourBars();
    });

    [
      "storage_dir",
      "poll_interval_minutes",
      "shop_id",
      "api_base",
      "open_hour_start",
      "open_hour_end",
    ].forEach((id) => {
      elements[id].addEventListener("input", () => {
        state.formDirty = true;
      });
    });

    elements["notify-toggle"].addEventListener("click", async () => {
      await toggleNotifications();
    });
  }

  async function bootstrap() {
    const payload = await fetchJson("/api/bootstrap");
    state.config = payload.config || {};
    state.data = payload.data || {};
    fillConfigForm();
    render();
    setFeedback("Dashboard ready.");
  }

  async function refreshData(showFeedback) {
    const data = await fetchJson("/api/data");
    state.data = data || {};
    render();
    if (showFeedback) {
      setFeedback("Dashboard refreshed.");
    }
  }

  async function saveConfig() {
    const payload = {
      storage_dir: elements["storage_dir"].value.trim(),
      poll_interval_minutes: toNumber(elements["poll_interval_minutes"].value, 5),
      shop_id: toNumber(elements["shop_id"].value, 218),
      api_base: elements["api_base"].value.trim(),
      open_hour_start: clamp(toNumber(elements["open_hour_start"].value, 6), 0, 23),
      open_hour_end: clamp(toNumber(elements["open_hour_end"].value, 23), 0, 23),
    };

    try {
      setButtonBusy(elements["save-config"], true, "Saving...");
      const response = await fetchJson("/api/config", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.config = response.config || payload;
      state.formDirty = false;
      fillConfigForm();
      await refreshData(false);
      setFeedback("Configuration saved.");
    } catch (error) {
      console.error(error);
      setFeedback(getErrorMessage(error), true);
    } finally {
      setButtonBusy(elements["save-config"], false, "Save Config");
    }
  }

  async function toggleFavorite(userId, favorite) {
    try {
      await fetchJson("/api/favorites", {
        method: "POST",
        body: JSON.stringify({ id: userId, favorite: favorite }),
      });
      await refreshData(false);
    } catch (error) {
      console.error(error);
      setFeedback(getErrorMessage(error), true);
    }
  }

  function render() {
    renderStats();
    renderCurrentPeople();
    renderFavoriteRecords();
    renderWeekdayBars();
    renderHourBars();
    updateNotifyButton();
    maybeNotifyLowTraffic();
  }

  function renderStats() {
    const data = state.data || {};
    const favorites = Array.isArray(data.favorites) ? data.favorites : [];
    const lastTimestamp = data.last_timestamp || "No samples yet";

    elements["current-count"].textContent = String(toNumber(data.current_count, 0));
    elements["favorite-count"].textContent = String(favorites.length);
    elements["sample-count"].textContent = String(toNumber(data.sample_count, 0));
    elements["last-updated"].textContent = lastTimestamp;

    const openHours = data.open_hours || {};
    elements["open-hours-label"].textContent =
      "Open hours: " + padHour(openHours.start, 6) + ":00 - " + padHour(openHours.end, 23) + ":00";
  }

  function renderCurrentPeople() {
    const people = Array.isArray(state.data && state.data.current_people) ? state.data.current_people : [];
    const favorites = favoriteSet();
    const list = elements["current-people-list"];
    list.innerHTML = "";

    if (!people.length) {
      list.textContent = "No one is currently in the gym.";
      list.classList.add("empty-state");
      return;
    }

    list.classList.remove("empty-state");
    people.forEach((person) => {
      const card = document.createElement("article");
      card.className = "person-card";

      card.appendChild(createAvatar(person.avatar, person.name));

      const meta = document.createElement("div");
      meta.className = "person-meta";

      const name = document.createElement("div");
      name.className = "person-name";
      name.textContent = person.name || "Unknown";
      meta.appendChild(name);

      const detail = document.createElement("div");
      detail.className = "person-detail";
      detail.textContent = "Stay: " + String(toNumber(person.minutes, 0)) + " min";
      meta.appendChild(detail);

      card.appendChild(meta);

      const button = createStarButton(favorites.has(String(person.id)), () => {
        toggleFavorite(String(person.id), !favorites.has(String(person.id)));
      });
      card.appendChild(button);
      list.appendChild(card);
    });
  }

  function renderFavoriteRecords() {
    const records = Array.isArray(state.data && state.data.favorite_records) ? state.data.favorite_records : [];
    const list = elements["favorite-records-list"];
    list.innerHTML = "";

    if (!records.length) {
      list.textContent = "No favorite history yet.";
      list.classList.add("empty-state");
      return;
    }

    list.classList.remove("empty-state");
    records.forEach((item) => {
      const card = document.createElement("article");
      card.className = "favorite-card";

      card.appendChild(createAvatar(item.avatar, item.name));

      const meta = document.createElement("div");
      meta.className = "favorite-meta";

      const name = document.createElement("div");
      name.className = "favorite-name";
      name.textContent = item.name || ("ID " + String(item.id || ""));
      meta.appendChild(name);

      const status = document.createElement("span");
      status.className = item.is_current ? "badge" : "badge dim";
      status.textContent = item.is_current ? "In gym now" : "Last seen: " + (item.last_seen || "unknown");
      meta.appendChild(status);

      const detail = document.createElement("div");
      detail.className = "favorite-detail";
      detail.textContent =
        "Last stay: " + String(toNumber(item.last_minutes, 0)) + " min | Sessions: " + String(toNumber(item.record_count, 0));
      meta.appendChild(detail);

      const sessions = document.createElement("div");
      sessions.className = "session-list";
      const recent = Array.isArray(item.recent_records) ? item.recent_records : [];
      if (!recent.length) {
        const line = document.createElement("span");
        line.textContent = "No stored sessions yet.";
        sessions.appendChild(line);
      } else {
        recent.slice(0, 3).forEach((record) => {
          const line = document.createElement("span");
          line.textContent = formatSession(record);
          sessions.appendChild(line);
        });
      }
      meta.appendChild(sessions);

      card.appendChild(meta);

      const button = createStarButton(true, () => {
        toggleFavorite(String(item.id), false);
      });
      card.appendChild(button);
      list.appendChild(card);
    });
  }

  function renderWeekdayBars() {
    const values = state.data && state.data.weekday_avg ? state.data.weekday_avg : {};
    const rows = labels.map((label, index) => ({ label: label, value: toNumber(values[String(index)], 0) }));
    renderBarList(elements["weekday-bars"], rows);
  }

  function renderHourBars() {
    const data = state.data || {};
    const hours = state.hourScope === "all" ? data.hour_avg : (data.weekday_hour_avg || {})[state.hourScope];
    const openHours = data.open_hours || {};
    const start = toNumber(openHours.start, 6);
    const end = toNumber(openHours.end, 23);
    const rows = [];

    const span = start === end ? 24 : ((end - start + 24) % 24 || 24);
    for (let offset = 0; offset < span; offset += 1) {
      const hour = (start + offset) % 24;
      rows.push({
        label: padHour(hour, 0) + ":00",
        value: toNumber(hours && hours[String(hour)], 0),
      });
    }

    renderBarList(elements["hour-bars"], rows);
  }

  function renderBarList(target, rows) {
    target.innerHTML = "";
    if (!rows.length) {
      target.textContent = "No chart data available yet.";
      target.classList.add("empty-state");
      return;
    }

    target.classList.remove("empty-state");
    const maxValue = rows.reduce((max, row) => Math.max(max, row.value), 0) || 1;

    rows.forEach((row) => {
      const rowElement = document.createElement("div");
      rowElement.className = "bar-row";

      const label = document.createElement("span");
      label.className = "bar-label";
      label.textContent = row.label;
      rowElement.appendChild(label);

      const track = document.createElement("div");
      track.className = "bar-track";
      const fill = document.createElement("div");
      fill.className = "bar-fill";
      fill.style.width = Math.max(4, Math.round((row.value / maxValue) * 100)) + "%";
      track.appendChild(fill);
      rowElement.appendChild(track);

      const value = document.createElement("span");
      value.className = "bar-value";
      value.textContent = row.value.toFixed(1);
      rowElement.appendChild(value);

      target.appendChild(rowElement);
    });
  }

  function fillConfigForm() {
    if (!state.config || state.formDirty) {
      return;
    }

    elements["storage_dir"].value = state.config.storage_dir || "";
    elements["poll_interval_minutes"].value = toNumber(state.config.poll_interval_minutes, 5);
    elements["shop_id"].value = toNumber(state.config.shop_id, 218);
    elements["api_base"].value = state.config.api_base || "";
    elements["open_hour_start"].value = toNumber(state.config.open_hour_start, 6);
    elements["open_hour_end"].value = toNumber(state.config.open_hour_end, 23);
  }

  function favoriteSet() {
    const values = Array.isArray(state.data && state.data.favorites) ? state.data.favorites : [];
    return new Set(values.map((value) => String(value)));
  }

  function createAvatar(url, name) {
    if (url) {
      const image = document.createElement("img");
      image.className = "avatar";
      image.src = url;
      image.alt = name || "Member avatar";
      image.loading = "lazy";
      image.referrerPolicy = "no-referrer";
      image.addEventListener("error", () => {
        image.replaceWith(createAvatar("", name));
      }, { once: true });
      return image;
    }

    const fallback = document.createElement("div");
    fallback.className = "avatar avatar-placeholder";
    fallback.textContent = getInitials(name);
    return fallback;
  }

  function createStarButton(active, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "star-button" + (active ? "" : " off");
    button.textContent = active ? "★" : "☆";
    button.setAttribute("aria-label", active ? "Remove favorite" : "Add favorite");
    button.addEventListener("click", onClick);
    return button;
  }

  function getInitials(name) {
    const value = (name || "?").trim();
    if (!value) {
      return "?";
    }
    return value.slice(0, 2).toUpperCase();
  }

  function formatSession(record) {
    const start = record && record.start ? record.start : "--";
    const end = record && record.end ? record.end : "--";
    const maxMinutes = toNumber(record && record.max_minutes, 0);
    const isCurrent = Boolean(record && record.current);
    return (isCurrent ? "Live" : "Session") + ": " + start + " -> " + end + " | peak " + String(maxMinutes) + " min";
  }

  function loadNotifyPreference() {
    if (!("Notification" in window)) {
      updateNotifyButton();
      return;
    }

    try {
      const saved = window.localStorage.getItem(notifyStorageKey);
      if (saved === "1" && Notification.permission === "granted") {
        state.notifyEnabled = true;
      }
    } catch (error) {
      console.warn(error);
    }
    updateNotifyButton();
  }

  async function toggleNotifications() {
    if (!("Notification" in window)) {
      setFeedback("This browser does not support notifications.", true);
      return;
    }

    if (state.notifyEnabled) {
      state.notifyEnabled = false;
      try {
        window.localStorage.removeItem(notifyStorageKey);
      } catch (error) {
        console.warn(error);
      }
      updateNotifyButton();
      setFeedback("Low-traffic alerts disabled.");
      return;
    }

    let permission = Notification.permission;
    if (permission === "default") {
      permission = await Notification.requestPermission();
    }

    if (permission !== "granted") {
      setFeedback("Notification permission was not granted.", true);
      return;
    }

    state.notifyEnabled = true;
    state.lastNotifyAt = 0;
    try {
      window.localStorage.setItem(notifyStorageKey, "1");
    } catch (error) {
      console.warn(error);
    }
    updateNotifyButton();
    setFeedback("Low-traffic alerts enabled.");
  }

  function updateNotifyButton() {
    if (!("Notification" in window)) {
      elements["notify-toggle"].textContent = "Browser Alerts Unsupported";
      elements["notify-toggle"].disabled = true;
      return;
    }

    elements["notify-toggle"].disabled = false;
    elements["notify-toggle"].textContent = state.notifyEnabled
      ? "Disable Low-Traffic Alerts"
      : "Enable Low-Traffic Alerts";
  }

  function maybeNotifyLowTraffic() {
    if (!state.notifyEnabled || !("Notification" in window) || Notification.permission !== "granted") {
      return;
    }

    const currentCount = toNumber(state.data && state.data.current_count, -1);
    if (currentCount < 0 || currentCount > notifyThreshold) {
      return;
    }

    const now = Date.now();
    if (now - state.lastNotifyAt < notifyCooldownMs) {
      return;
    }

    state.lastNotifyAt = now;
    try {
      new Notification("CheckMyGym", {
        body: "Low traffic detected: " + String(currentCount) + " people currently in the gym.",
        tag: "checkmygym-low-traffic",
      });
    } catch (error) {
      console.error(error);
    }
  }

  function setButtonBusy(button, busy, label) {
    button.disabled = busy;
    button.textContent = label;
  }

  function setFeedback(message, isError) {
    elements.feedback.textContent = message || "";
    elements.feedback.classList.toggle("error", Boolean(isError));
  }

  function getErrorMessage(error) {
    if (error && error.message) {
      return error.message;
    }
    return "Request failed.";
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      ...options,
    });

    if (!response.ok) {
      let text = "";
      try {
        text = await response.text();
      } catch (error) {
        console.warn(error);
      }
      throw new Error(text || ("HTTP " + response.status));
    }

    return response.json();
  }

  function toNumber(value, fallback) {
    const result = Number(value);
    return Number.isFinite(result) ? result : fallback;
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function padHour(value, fallback) {
    return String(toNumber(value, fallback)).padStart(2, "0");
  }

  function delay(ms) {
    return new Promise((resolve) => {
      window.setTimeout(resolve, ms);
    });
  }
})();
