(function () {
  const DEFAULT_ARRIVAL_MESSAGE_TEMPLATE = "{user_name}（ID: {user_id}）来健身房了，当前人数 {current_count}。时间：{timestamp}";
  const AUTO_REFRESH_INTERVAL_MS = 60000;
  const REQUEST_TIMEOUT_MS = 15000;
  const THEME_STORAGE_KEY = "checkmygym-theme";

  const state = {
    config: null,
    data: null,
    hourScope: "all",
    theme: "dark",
    formDirty: false,
    loadingDepth: 0,
    refreshTimer: null,
    refreshInFlight: null,
    refreshAbortController: null,
  };

  const weekdayLabels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
  const elements = {};

  document.addEventListener("DOMContentLoaded", () => {
    init().catch((error) => {
      console.error(error);
      setFeedback(getErrorMessage(error), true);
    });
  });

  async function init() {
    bindElements();
    initTheme();
    bindEvents();
    setAutoRefreshStatus();
    setFeedback("正在加载页面...");
    await bootstrap();
    startAutoRefresh();
    setFeedback("页面已就绪。");
  }

  function bindElements() {
    const ids = [
      "auto-refresh-status",
      "theme-toggle",
      "refresh-now",
      "poll-now",
      "save-config",
      "config-form",
      "hour-scope",
      "current-count",
      "current-treadmill-using",
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
      "qq_enabled",
      "qq_endpoint",
      "qq_access_token",
      "qq_target_type",
      "qq_target_id",
      "qq_timeout_seconds",
      "qq_cooldown_minutes",
      "low_traffic_enabled",
      "low_traffic_threshold",
      "low_traffic_start_time",
      "low_traffic_end_time",
      "low_traffic_message_template",
      "arrival-rules-list",
      "add-arrival-rule",
    ];

    ids.forEach((id) => {
      elements[id] = document.getElementById(id);
    });
  }

  function bindEvents() {
    elements["theme-toggle"].addEventListener("click", () => {
      toggleTheme();
    });

    elements["refresh-now"].addEventListener("click", async () => {
      await withButtonBusy(elements["refresh-now"], "刷新中...", "立即刷新", async () => {
        await refreshData({ showFeedback: true, preferLatest: true });
      });
    });

    elements["poll-now"].addEventListener("click", async () => {
      await withButtonBusy(elements["poll-now"], "轮询中...", "立即轮询", async () => {
        await fetchJson("/api/poll", { method: "POST" });
        await delay(600);
        await refreshData({ showFeedback: false, preferLatest: true });
        setFeedback("轮询完成并更新数据。", false);
      });
    });

    elements["config-form"].addEventListener("submit", async (event) => {
      event.preventDefault();
      await saveConfig();
    });

    elements["config-form"].addEventListener("input", () => {
      state.formDirty = true;
    });

    elements["config-form"].addEventListener("change", () => {
      state.formDirty = true;
    });

    elements["hour-scope"].addEventListener("change", (event) => {
      state.hourScope = String(event.target.value || "all");
      renderHourBars();
    });

    elements["add-arrival-rule"].addEventListener("click", () => {
      const row = createArrivalRuleRow();
      const list = elements["arrival-rules-list"];
      list.classList.remove("empty-state");
      if (list.dataset.empty === "1") {
        list.textContent = "";
        list.dataset.empty = "0";
      }
      list.appendChild(row);
      state.formDirty = true;
    });

    elements["current-people-list"].addEventListener("click", async (event) => {
      const button = event.target.closest("[data-favorite-toggle]");
      if (!button) {
        return;
      }
      await toggleFavorite(String(button.dataset.userId || ""), button.dataset.favoriteNext === "1");
    });

    elements["favorite-records-list"].addEventListener("click", async (event) => {
      const button = event.target.closest("[data-favorite-toggle]");
      if (!button) {
        return;
      }
      await toggleFavorite(String(button.dataset.userId || ""), false);
    });

    document.addEventListener("visibilitychange", () => {
      setAutoRefreshStatus();
    });

    window.addEventListener("beforeunload", () => {
      if (state.refreshTimer) {
        window.clearInterval(state.refreshTimer);
      }
      if (state.refreshAbortController) {
        state.refreshAbortController.abort();
      }
    });
  }

  async function bootstrap() {
    beginDashboardLoading();
    try {
      const payload = await fetchJson("/api/bootstrap");
      state.config = payload.config || {};
      state.data = payload.data || {};
      fillConfigForm();
      render();
    } finally {
      endDashboardLoading();
    }
  }

  function startAutoRefresh() {
    if (state.refreshTimer) {
      window.clearInterval(state.refreshTimer);
    }

    state.refreshTimer = window.setInterval(() => {
      if (document.hidden) {
        return;
      }
      refreshData({ showFeedback: false, preferLatest: false }).catch((error) => {
        if (isAbortError(error)) {
          return;
        }
        console.error(error);
      });
    }, AUTO_REFRESH_INTERVAL_MS);
  }

  function setAutoRefreshStatus() {
    const target = elements["auto-refresh-status"];
    if (!target) {
      return;
    }
    const paused = Boolean(document.hidden);
    target.textContent = paused ? "自动刷新：暂停（后台）" : "自动刷新：开启";
    target.classList.toggle("off", paused);
  }

  function initTheme() {
    const current = document.documentElement.dataset.theme;
    let theme = current === "light" ? "light" : "dark";
    try {
      const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
      if (stored === "light" || stored === "dark") {
        theme = stored;
      }
    } catch (error) {
      console.warn(error);
    }
    applyTheme(theme, false);
  }

  function toggleTheme() {
    applyTheme(state.theme === "dark" ? "light" : "dark", true);
  }

  function applyTheme(theme, persist) {
    const next = theme === "light" ? "light" : "dark";
    state.theme = next;
    document.documentElement.dataset.theme = next;
    updateThemeToggleButton(next);
    if (!persist) {
      return;
    }
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch (error) {
      console.warn(error);
    }
  }

  function updateThemeToggleButton(theme) {
    const button = elements["theme-toggle"];
    if (!button) {
      return;
    }
    const isLight = theme === "light";
    button.setAttribute("aria-checked", isLight ? "true" : "false");
    button.setAttribute("aria-label", isLight ? "切换深色模式" : "切换浅色模式");
    button.title = isLight ? "切换深色模式" : "切换浅色模式";
  }

  async function refreshData(options) {
    const opts = options || {};
    const preferLatest = opts.preferLatest !== false;
    const showFeedback = Boolean(opts.showFeedback);

    if (preferLatest && state.refreshAbortController) {
      state.refreshAbortController.abort();
    }

    if (state.refreshInFlight && !preferLatest) {
      await state.refreshInFlight;
      return;
    }

    const abortController = new AbortController();
    state.refreshAbortController = abortController;
    beginDashboardLoading();
    state.refreshInFlight = (async () => {
      const data = await fetchJson("/api/data", { signal: abortController.signal });
      if (abortController.signal.aborted) {
        return;
      }
      state.data = data || {};
      render();
      if (showFeedback) {
        setFeedback("数据已刷新。", false);
      }
    })();

    try {
      await state.refreshInFlight;
    } catch (error) {
      if (!isAbortError(error)) {
        throw error;
      }
    } finally {
      endDashboardLoading();
      if (state.refreshAbortController === abortController) {
        state.refreshAbortController = null;
      }
      state.refreshInFlight = null;
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
      qq_notification: {
        enabled: elements["qq_enabled"].checked,
        endpoint: elements["qq_endpoint"].value.trim(),
        access_token: elements["qq_access_token"].value.trim(),
        target_type: elements["qq_target_type"].value === "group" ? "group" : "private",
        target_id: elements["qq_target_id"].value.trim(),
        timeout_seconds: clamp(toNumber(elements["qq_timeout_seconds"].value, 10), 3, 60),
        cooldown_minutes: clamp(toNumber(elements["qq_cooldown_minutes"].value, 15), 0, 1440),
        low_traffic: {
          enabled: elements["low_traffic_enabled"].checked,
          threshold: Math.max(0, toNumber(elements["low_traffic_threshold"].value, 4)),
          start_time: normalizeTimeInput(elements["low_traffic_start_time"].value, "00:00"),
          end_time: normalizeTimeInput(elements["low_traffic_end_time"].value, "00:00"),
          message_template: elements["low_traffic_message_template"].value.trim(),
        },
        user_arrival_rules: collectArrivalRules(),
      },
    };

    await withButtonBusy(elements["save-config"], "保存中...", "保存配置", async () => {
      const response = await fetchJson("/api/config", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.config = response.config || payload;
      state.formDirty = false;
      fillConfigForm();
      await refreshData({ showFeedback: false, preferLatest: true });
      setFeedback("配置已保存。", false);
    });
  }

  function collectArrivalRules() {
    const rows = Array.from(elements["arrival-rules-list"].querySelectorAll("[data-arrival-rule]"));
    return rows
      .map((row) => ({
        user_id: row.querySelector("[data-field='user_id']").value.trim(),
        label: row.querySelector("[data-field='label']").value.trim(),
        enabled: row.querySelector("[data-field='enabled']").checked,
        require_low_traffic: row.querySelector("[data-field='require_low_traffic']").checked,
        message_template: row.querySelector("[data-field='message_template']").value.trim(),
      }))
      .filter((item) => item.user_id);
  }

  async function toggleFavorite(userId, favorite) {
    if (!userId) {
      return;
    }
    try {
      await fetchJson("/api/favorites", {
        method: "POST",
        body: JSON.stringify({ id: userId, favorite: favorite }),
      });
      await refreshData({ showFeedback: false, preferLatest: true });
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
  }

  function beginDashboardLoading() {
    state.loadingDepth += 1;
    if (state.loadingDepth > 1) {
      return;
    }
    renderDashboardSkeletons();
  }

  function endDashboardLoading() {
    if (state.loadingDepth > 0) {
      state.loadingDepth -= 1;
    }
    if (state.loadingDepth > 0) {
      return;
    }
    setListBusy(elements["current-people-list"], false);
    setListBusy(elements["favorite-records-list"], false);
    setListBusy(elements["weekday-bars"], false);
    setListBusy(elements["hour-bars"], false);
  }

  function renderDashboardSkeletons() {
    renderListSkeleton(elements["current-people-list"], 4);
    renderListSkeleton(elements["favorite-records-list"], 3);
    renderBarSkeleton(elements["weekday-bars"], 7);
    renderBarSkeleton(elements["hour-bars"], 8);
  }

  function renderListSkeleton(target, count) {
    if (!target) {
      return;
    }
    setListBusy(target, true);
    const fragment = document.createDocumentFragment();
    for (let i = 0; i < count; i += 1) {
      const card = document.createElement("div");
      card.className = "skeleton-card";

      const avatar = document.createElement("div");
      avatar.className = "skeleton-avatar";

      const content = document.createElement("div");
      content.className = "skeleton-content";

      const lineTop = document.createElement("div");
      lineTop.className = "skeleton-line w-80";

      const lineBottom = document.createElement("div");
      lineBottom.className = "skeleton-line w-60";

      const dot = document.createElement("div");
      dot.className = "skeleton-dot";

      content.appendChild(lineTop);
      content.appendChild(lineBottom);
      card.appendChild(avatar);
      card.appendChild(content);
      card.appendChild(dot);
      fragment.appendChild(card);
    }
    target.replaceChildren(fragment);
  }

  function renderBarSkeleton(target, count) {
    if (!target) {
      return;
    }
    setListBusy(target, true);
    const fragment = document.createDocumentFragment();
    for (let i = 0; i < count; i += 1) {
      const row = document.createElement("div");
      row.className = "skeleton-bar-row";

      const label = document.createElement("div");
      label.className = "skeleton-bar-label";

      const track = document.createElement("div");
      track.className = "skeleton-bar-track";

      const value = document.createElement("div");
      value.className = "skeleton-bar-value";

      row.appendChild(label);
      row.appendChild(track);
      row.appendChild(value);
      fragment.appendChild(row);
    }
    target.replaceChildren(fragment);
  }

  function setListBusy(target, busy) {
    if (!target) {
      return;
    }
    target.classList.toggle("is-loading", busy);
    if (busy) {
      target.classList.remove("empty-state");
    }
    target.setAttribute("aria-busy", busy ? "true" : "false");
  }

  function renderStats() {
    const data = state.data || {};
    const favorites = Array.isArray(data.favorites) ? data.favorites : [];
    const openHours = data.open_hours || {};

    elements["current-count"].textContent = String(toNumber(data.current_count, 0));
    elements["current-treadmill-using"].textContent = String(toNumber(data.current_treadmill_using, 0));
    elements["favorite-count"].textContent = String(favorites.length);
    elements["sample-count"].textContent = String(toNumber(data.sample_count, 0));
    elements["last-updated"].textContent = data.last_timestamp || "暂无采样";
    elements["open-hours-label"].textContent =
      "营业时间：" + padHour(openHours.start, 6) + ":00 - " + padHour(openHours.end, 23) + ":00";
  }

  function renderCurrentPeople() {
    const people = Array.isArray(state.data && state.data.current_people) ? state.data.current_people : [];
    const favorites = favoriteSet();
    const list = elements["current-people-list"];

    if (!people.length) {
      list.textContent = "当前健身房无人。";
      list.classList.add("empty-state");
      return;
    }

    list.classList.remove("empty-state");
    const fragment = document.createDocumentFragment();
    people.forEach((person) => {
      const card = document.createElement("article");
      card.className = "person-card";
      card.appendChild(createAvatar(person.avatar, person.name));

      const meta = document.createElement("div");
      meta.className = "person-meta";

      const name = document.createElement("div");
      name.className = "person-name";
      name.textContent = person.name || "未知用户";

      const detail = document.createElement("div");
      detail.className = "person-detail";
      detail.textContent = "已锻炼：" + String(toNumber(person.minutes, 0)) + " 分钟";

      meta.appendChild(name);
      meta.appendChild(detail);
      card.appendChild(meta);

      const isFavorite = favorites.has(String(person.id));
      card.appendChild(createStarButton(isFavorite, String(person.id), !isFavorite));
      fragment.appendChild(card);
    });

    list.replaceChildren(fragment);
  }

  function renderFavoriteRecords() {
    const records = Array.isArray(state.data && state.data.favorite_records) ? state.data.favorite_records : [];
    const list = elements["favorite-records-list"];

    if (!records.length) {
      list.textContent = "暂无收藏用户记录。";
      list.classList.add("empty-state");
      return;
    }

    list.classList.remove("empty-state");
    const fragment = document.createDocumentFragment();
    records.forEach((item) => {
      const card = document.createElement("article");
      card.className = "favorite-card";
      card.appendChild(createAvatar(item.avatar, item.name));

      const meta = document.createElement("div");
      meta.className = "favorite-meta";

      const name = document.createElement("div");
      name.className = "favorite-name";
      name.textContent = item.name || ("ID " + String(item.id || ""));

      const userId = document.createElement("div");
      userId.className = "favorite-detail";
      userId.textContent = "用户 ID：" + String(item.id || "--");

      const status = document.createElement("span");
      status.className = item.is_current ? "badge" : "badge dim";
      status.textContent = item.is_current ? "当前在馆" : "最近出现：" + (item.last_seen || "未知");

      const detail = document.createElement("div");
      detail.className = "favorite-detail";
      detail.textContent =
        "最近锻炼：" + String(toNumber(item.last_minutes, 0)) + " 分钟 | 记录次数：" + String(toNumber(item.record_count, 0));

      const sessions = document.createElement("div");
      sessions.className = "session-list";
      const recent = Array.isArray(item.recent_records) ? item.recent_records : [];
      if (!recent.length) {
        const line = document.createElement("span");
        line.textContent = "暂无历史时段记录。";
        sessions.appendChild(line);
      } else {
        recent.slice(0, 3).forEach((record) => {
          const line = document.createElement("span");
          line.textContent = formatSession(record);
          sessions.appendChild(line);
        });
      }

      meta.appendChild(name);
      meta.appendChild(userId);
      meta.appendChild(status);
      meta.appendChild(detail);
      meta.appendChild(sessions);
      card.appendChild(meta);
      card.appendChild(createStarButton(true, String(item.id || ""), false));
      fragment.appendChild(card);
    });

    list.replaceChildren(fragment);
  }

  function renderWeekdayBars() {
    const values = state.data && state.data.weekday_avg ? state.data.weekday_avg : {};
    const rows = weekdayLabels.map((label, index) => ({
      label: label,
      value: toNumber(values[String(index)], 0),
    }));
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
    if (!rows.length) {
      target.textContent = "暂无图表数据。";
      target.classList.add("empty-state");
      return;
    }

    target.classList.remove("empty-state");
    const maxValue = rows.reduce((max, row) => Math.max(max, row.value), 0) || 1;
    const fragment = document.createDocumentFragment();

    rows.forEach((row) => {
      const rowElement = document.createElement("div");
      rowElement.className = "bar-row";

      const label = document.createElement("span");
      label.className = "bar-label";
      label.textContent = row.label;

      const track = document.createElement("div");
      track.className = "bar-track";

      const fill = document.createElement("div");
      fill.className = "bar-fill";
      fill.style.setProperty("--bar-width", Math.max(4, Math.round((row.value / maxValue) * 100)) + "%");
      track.appendChild(fill);

      const value = document.createElement("span");
      value.className = "bar-value";
      value.textContent = row.value.toFixed(1);

      rowElement.appendChild(label);
      rowElement.appendChild(track);
      rowElement.appendChild(value);
      fragment.appendChild(rowElement);
    });

    target.replaceChildren(fragment);
  }

  function fillConfigForm() {
    if (!state.config || state.formDirty) {
      return;
    }

    const qq = state.config.qq_notification || {};
    const lowTraffic = qq.low_traffic || {};

    elements["storage_dir"].value = state.config.storage_dir || "";
    elements["poll_interval_minutes"].value = toNumber(state.config.poll_interval_minutes, 5);
    elements["shop_id"].value = toNumber(state.config.shop_id, 218);
    elements["api_base"].value = state.config.api_base || "";
    elements["open_hour_start"].value = toNumber(state.config.open_hour_start, 6);
    elements["open_hour_end"].value = toNumber(state.config.open_hour_end, 23);

    elements["qq_enabled"].checked = Boolean(qq.enabled);
    elements["qq_endpoint"].value = qq.endpoint || "";
    elements["qq_access_token"].value = qq.access_token || "";
    elements["qq_target_type"].value = qq.target_type === "group" ? "group" : "private";
    elements["qq_target_id"].value = qq.target_id || "";
    elements["qq_timeout_seconds"].value = toNumber(qq.timeout_seconds, 10);
    elements["qq_cooldown_minutes"].value = toNumber(qq.cooldown_minutes, 15);

    elements["low_traffic_enabled"].checked = Boolean(lowTraffic.enabled);
    elements["low_traffic_threshold"].value = toNumber(lowTraffic.threshold, 4);
    elements["low_traffic_start_time"].value = normalizeTimeInput(lowTraffic.start_time, "00:00");
    elements["low_traffic_end_time"].value = normalizeTimeInput(lowTraffic.end_time, "00:00");
    elements["low_traffic_message_template"].value = lowTraffic.message_template || "";

    renderArrivalRules(Array.isArray(qq.user_arrival_rules) ? qq.user_arrival_rules : []);
  }

  function renderArrivalRules(rules) {
    const list = elements["arrival-rules-list"];
    list.textContent = "";

    if (!rules.length) {
      list.textContent = "还没有到场规则。";
      list.classList.add("empty-state");
      list.dataset.empty = "1";
      return;
    }

    list.dataset.empty = "0";
    list.classList.remove("empty-state");
    const fragment = document.createDocumentFragment();
    rules.forEach((rule) => {
      fragment.appendChild(createArrivalRuleRow(rule));
    });
    list.replaceChildren(fragment);
  }

  function createArrivalRuleRow(rule) {
    const data = rule || {};
    const wrapper = document.createElement("article");
    wrapper.className = "arrival-rule-card";
    wrapper.dataset.arrivalRule = "1";

    const top = document.createElement("div");
    top.className = "arrival-rule-top";

    const enabled = document.createElement("label");
    enabled.className = "checkbox-row";
    const enabledInput = document.createElement("input");
    enabledInput.type = "checkbox";
    enabledInput.checked = data.enabled !== false;
    enabledInput.dataset.field = "enabled";
    enabled.appendChild(enabledInput);
    const enabledLabel = document.createElement("span");
    enabledLabel.textContent = "启用";
    enabled.appendChild(enabledLabel);
    top.appendChild(enabled);

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "button secondary small-button";
    removeButton.textContent = "删除";
    removeButton.addEventListener("click", () => {
      wrapper.remove();
      if (!elements["arrival-rules-list"].querySelector("[data-arrival-rule]")) {
        renderArrivalRules([]);
      }
      state.formDirty = true;
    });
    top.appendChild(removeButton);
    wrapper.appendChild(top);

    const grid = document.createElement("div");
    grid.className = "rule-grid";
    grid.appendChild(createRuleField("用户 ID（可用逗号分隔多个）", "user_id", data.user_id || "", false));
    grid.appendChild(createRuleField("备注标签（可选）", "label", data.label || "", false));
    grid.appendChild(
      createRuleCheckboxField(
        "要求同时满足低人数条件（且）",
        "require_low_traffic",
        Boolean(data.require_low_traffic)
      )
    );
    grid.appendChild(
      createRuleField(
        "消息模板",
        "message_template",
        data.message_template || DEFAULT_ARRIVAL_MESSAGE_TEMPLATE,
        true
      )
    );

    wrapper.appendChild(grid);
    return wrapper;
  }

  function createRuleField(labelText, fieldName, value, multiline) {
    const label = document.createElement("label");
    label.className = multiline ? "form-span-2" : "";

    const title = document.createElement("span");
    title.textContent = labelText;
    label.appendChild(title);

    const control = multiline ? document.createElement("textarea") : document.createElement("input");
    if (multiline) {
      control.rows = 3;
    } else {
      control.type = "text";
    }
    control.value = value || "";
    control.dataset.field = fieldName;
    label.appendChild(control);
    return label;
  }

  function createRuleCheckboxField(labelText, fieldName, checked) {
    const label = document.createElement("label");
    label.className = "checkbox-field";

    const title = document.createElement("span");
    title.textContent = labelText;
    label.appendChild(title);

    const control = document.createElement("input");
    control.type = "checkbox";
    control.checked = Boolean(checked);
    control.dataset.field = fieldName;
    label.appendChild(control);
    return label;
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
      image.alt = name || "用户头像";
      image.loading = "lazy";
      image.referrerPolicy = "no-referrer";
      image.addEventListener(
        "error",
        () => {
          image.replaceWith(createAvatar("", name));
        },
        { once: true }
      );
      return image;
    }

    const fallback = document.createElement("div");
    fallback.className = "avatar avatar-placeholder";
    fallback.textContent = getInitials(name);
    return fallback;
  }

  function createStarButton(active, userId, nextFavorite) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "star-button" + (active ? "" : " off");
    button.textContent = active ? "★" : "☆";
    button.setAttribute("aria-label", active ? "取消收藏" : "加入收藏");
    button.dataset.favoriteToggle = "1";
    button.dataset.userId = userId;
    button.dataset.favoriteNext = nextFavorite ? "1" : "0";
    return button;
  }

  async function withButtonBusy(button, busyLabel, idleLabel, task) {
    setButtonBusy(button, true, busyLabel);
    try {
      await task();
    } catch (error) {
      console.error(error);
      setFeedback(getErrorMessage(error), true);
    } finally {
      setButtonBusy(button, false, idleLabel);
    }
  }

  function getInitials(name) {
    const value = String(name || "?").trim();
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
    return (isCurrent ? "当前时段" : "历史时段") + "：" + start + " -> " + end + " | 峰值 " + String(maxMinutes) + " 分钟";
  }

  function setButtonBusy(button, busy, label) {
    button.disabled = busy;
    button.textContent = label;
  }

  function setFeedback(message, isError) {
    if (!elements.feedback) {
      return;
    }
    elements.feedback.textContent = message || "";
    elements.feedback.classList.toggle("error", Boolean(isError));
  }

  function getErrorMessage(error) {
    if (error && error.message) {
      return error.message;
    }
    return "请求失败，请稍后重试。";
  }

  function isAbortError(error) {
    return error && (error.name === "AbortError" || /aborted/i.test(String(error.message || "")));
  }

  async function fetchJson(url, options) {
    const opts = options || {};
    const controller = new AbortController();
    let timedOut = false;

    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, REQUEST_TIMEOUT_MS);

    const outerSignal = opts.signal;
    const onOuterAbort = () => {
      controller.abort();
    };

    if (outerSignal) {
      if (outerSignal.aborted) {
        controller.abort();
      } else {
        outerSignal.addEventListener("abort", onOuterAbort, { once: true });
      }
    }

    try {
      const response = await fetch(url, {
        method: opts.method || "GET",
        headers: {
          "Content-Type": "application/json",
          ...(opts.headers || {}),
        },
        body: opts.body,
        cache: "no-store",
        signal: controller.signal,
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
    } catch (error) {
      if (timedOut) {
        throw new Error("请求超时，请稍后重试。");
      }
      throw error;
    } finally {
      window.clearTimeout(timeoutId);
      if (outerSignal) {
        outerSignal.removeEventListener("abort", onOuterAbort);
      }
    }
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

  function normalizeTimeInput(value, fallback) {
    const text = String(value || "").trim();
    if (/^\d{2}:\d{2}$/.test(text)) {
      return text;
    }
    if (/^\d{1,2}:\d{1,2}$/.test(text)) {
      const parts = text.split(":");
      const hour = clamp(toNumber(parts[0], 0), 0, 23);
      const minute = clamp(toNumber(parts[1], 0), 0, 59);
      return String(hour).padStart(2, "0") + ":" + String(minute).padStart(2, "0");
    }
    if (/^\d{1,2}$/.test(text)) {
      return String(clamp(toNumber(text, 0), 0, 23)).padStart(2, "0") + ":00";
    }
    return fallback;
  }

  function delay(ms) {
    return new Promise((resolve) => {
      window.setTimeout(resolve, ms);
    });
  }
})();
