const { useEffect, useMemo, useRef, useState } = React;
const { createRoot } = ReactDOM;
const {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  CssBaseline,
  Divider,
  FormControlLabel,
  Grid,
  IconButton,
  Stack,
  Switch,
  TextField,
  Tooltip,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  createTheme,
  ThemeProvider,
  Icon,
} = MaterialUI;

const iconFactory = (name) => (props) => <Icon {...props}>{name}</Icon>;
const createIconSet = () => {
  const iconsSource =
    typeof window !== 'undefined' &&
    window.MaterialUI &&
    window.MaterialUI.Icons &&
    typeof window.MaterialUI.Icons === 'object'
      ? window.MaterialUI.Icons
      : {};
  return {
    Favorite: iconsSource.Favorite || iconFactory('favorite'),
    FavoriteBorder: iconsSource.FavoriteBorder || iconFactory('favorite_border'),
    NotificationsActive: iconsSource.NotificationsActive || iconFactory('notifications_active'),
    NotificationsOff: iconsSource.NotificationsOff || iconFactory('notifications_off'),
    Refresh: iconsSource.Refresh || iconFactory('refresh'),
    Save: iconsSource.Save || iconFactory('save'),
    AccessTime: iconsSource.AccessTime || iconFactory('schedule'),
    People: iconsSource.People || iconFactory('group'),
  };
};

const { Favorite, FavoriteBorder, NotificationsActive, NotificationsOff, Refresh, Save, AccessTime, People } = createIconSet();

const NOTIFY_STORAGE_KEY = 'gym-notify-enabled';
const NOTIFY_THRESHOLD = 4;
const NOTIFY_COOLDOWN = 5 * 60 * 1000;

async function fetchJSON(url, opts = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText || '请求失败');
  }
  return res.json();
}

function isOpenHour(ts, start, end) {
  if (!ts) return true;
  const hour = Number(ts.slice(11, 13));
  if (Number.isNaN(hour)) return true;
  if (start <= end) return hour >= start && hour < end;
  return hour >= start || hour < end;
}

function ChartCanvas({ type, labels, values, label }) {
  const canvasRef = useRef(null);
  useEffect(() => {
    if (!canvasRef.current) return undefined;
    const chart = new Chart(canvasRef.current, {
      type,
      data: {
        labels,
        datasets: [
          {
            label,
            data: values,
            borderColor: type === 'line' ? '#6e8bff' : '#66d483',
            backgroundColor: type === 'line' ? 'rgba(110,139,255,0.2)' : '#66d483',
            fill: type === 'line',
            tension: 0.35,
            borderRadius: 6,
          },
        ],
      },
      options: { responsive: true, plugins: { legend: { display: false } } },
    });
    return () => chart.destroy();
  }, [type, label, labels, values]);

  return <canvas ref={canvasRef} height={200} />;
}

function CurrentPeople({ people, favorites, onToggleFavorite, snapshotTime }) {
  if (!people?.length) {
    return (
      <Card variant="outlined" sx={{ background: 'rgba(255,255,255,0.04)', borderColor: 'rgba(255,255,255,0.12)' }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1}>
            <People fontSize="small" />
            <Typography variant="body2" color="text.secondary">
              当前无人健身
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    );
  }

  return (
    <Stack spacing={1.25}>
      {people.map((p) => {
        const pid = String(p.id ?? '');
        const favorited = favorites.has(pid);
        return (
          <Card
            key={pid || p.name}
            variant="outlined"
            sx={{ background: 'rgba(255,255,255,0.06)', borderColor: 'rgba(255,255,255,0.16)' }}
          >
            <CardContent>
              <Stack direction="row" spacing={2} alignItems="center">
                {p.avatar ? (
                  <Avatar src={p.avatar} alt={p.name} sx={{ width: 52, height: 52 }} />
                ) : (
                  <Avatar sx={{ width: 52, height: 52 }}>{p.name?.slice(0, 1) || '?'}</Avatar>
                )}
                <Box sx={{ flex: 1 }}>
                  <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                    {p.name || '匿名用户'}
                  </Typography>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <AccessTime fontSize="small" />
                    <Typography variant="body2" color="text.secondary">
                      停留 {p.minutes ?? 0} 分钟
                    </Typography>
                  </Stack>
                </Box>
                <Tooltip title={favorited ? '取消收藏' : '收藏成员'}>
                  <IconButton color={favorited ? 'warning' : 'default'} onClick={() => onToggleFavorite(pid, p.name, p.avatar)}>
                    {favorited ? <Favorite /> : <FavoriteBorder />}
                  </IconButton>
                </Tooltip>
              </Stack>
            </CardContent>
          </Card>
        );
      })}
      {snapshotTime ? (
        <Typography variant="caption" color="text.secondary" textAlign="right">
          最新数据：{snapshotTime}
        </Typography>
      ) : null}
    </Stack>
  );
}

function HeroSection({ notifyEnabled, onToggleNotify, onRefresh }) {
  return (
    <Box textAlign="center">
      <Chip label="实时监控 · React + Material UI" color="primary" variant="outlined" sx={{ mb: 2 }} />
      <Typography variant="h4" fontWeight={700} gutterBottom>
        健身房人数监控
      </Typography>
      <Typography variant="body1" color="text.secondary">
        以 React 组件重构的液态玻璃风格仪表盘，展示实时人数、趋势与在馆成员。
      </Typography>
      <Stack direction="row" spacing={2} justifyContent="center" sx={{ mt: 2 }}>
        <Button
          variant="contained"
          color={notifyEnabled ? 'secondary' : 'primary'}
          startIcon={notifyEnabled ? <NotificationsActive /> : <NotificationsOff />}
          onClick={onToggleNotify}
        >
          {notifyEnabled ? '关闭低人流提醒' : '启用低人流提醒'}
        </Button>
        <Button variant="outlined" startIcon={<Refresh />} onClick={onRefresh}>
          刷新数据
        </Button>
      </Stack>
    </Box>
  );
}

function ChartsSection({ lineLabels, lineValues, weekdayEntries, hourDataset, hourScope, onHourScopeChange }) {
  return (
    <Grid container spacing={2.5}>
      <Grid item xs={12} md={6}>
        <Card elevation={6} sx={{ backdropFilter: 'blur(12px)' }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              实时曲线（最近一段时间）
            </Typography>
            <ChartCanvas type="line" labels={lineLabels} values={lineValues} label="人数" />
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={6}>
        <Card elevation={6} sx={{ backdropFilter: 'blur(12px)' }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              按星期平均人数
            </Typography>
            <ChartCanvas
              type="bar"
              labels={weekdayEntries.map(([k]) => `周${'一二三四五六日'[k]}`)}
              values={weekdayEntries.map(([, v]) => v)}
              label="平均人数"
            />
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12}>
        <Card elevation={6} sx={{ backdropFilter: 'blur(12px)' }}>
          <CardContent>
            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems="center" spacing={2}>
              <Typography variant="h6">按小时平均人数</Typography>
              <ToggleButtonGroup exclusive size="small" value={hourScope} onChange={(e, val) => val && onHourScopeChange(val)}>
                <ToggleButton value="all">全部</ToggleButton>
                <ToggleButton value="0">周一</ToggleButton>
                <ToggleButton value="1">周二</ToggleButton>
                <ToggleButton value="2">周三</ToggleButton>
                <ToggleButton value="3">周四</ToggleButton>
                <ToggleButton value="4">周五</ToggleButton>
                <ToggleButton value="5">周六</ToggleButton>
                <ToggleButton value="6">周日</ToggleButton>
              </ToggleButtonGroup>
            </Stack>
            <Box mt={2}>
              <ChartCanvas type="bar" labels={hourDataset.labels} values={hourDataset.values} label="平均人数" />
            </Box>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
}

function ConfigSection({ config, setConfig, openStart, openEnd, onSaveConfig, onPollNow, saving }) {
  return (
    <Card elevation={6} sx={{ backdropFilter: 'blur(12px)' }}>
      <CardContent>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ xs: 'stretch', sm: 'center' }}>
          <Typography variant="h6" sx={{ flex: 1 }}>
            配置
          </Typography>
          <Stack direction="row" spacing={1}>
            <Button variant="contained" startIcon={<Save />} onClick={onSaveConfig} disabled={!config || saving}>
              保存配置
            </Button>
            <Button variant="outlined" startIcon={<Refresh />} onClick={onPollNow}>
              立即抓取一次
            </Button>
          </Stack>
        </Stack>
        <Divider sx={{ my: 2 }} />
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              label="数据存储目录"
              value={config?.storage_dir || ''}
              onChange={(e) => setConfig((prev) => ({ ...(prev || {}), storage_dir: e.target.value }))}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              type="number"
              label="轮询间隔（分钟）"
              value={config?.poll_interval_minutes ?? ''}
              onChange={(e) => setConfig((prev) => ({ ...(prev || {}), poll_interval_minutes: Number(e.target.value) }))}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              type="number"
              label="门店 ID（shop_id）"
              value={config?.shop_id ?? ''}
              onChange={(e) => setConfig((prev) => ({ ...(prev || {}), shop_id: Number(e.target.value) }))}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              label="接口基础地址"
              value={config?.api_base || ''}
              onChange={(e) => setConfig((prev) => ({ ...(prev || {}), api_base: e.target.value }))}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              type="number"
              label="统计开始小时（0-23）"
              value={config?.open_hour_start ?? ''}
              onChange={(e) => setConfig((prev) => ({ ...(prev || {}), open_hour_start: Number(e.target.value) }))}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              type="number"
              label="统计结束小时（0-23）"
              value={config?.open_hour_end ?? ''}
              onChange={(e) => setConfig((prev) => ({ ...(prev || {}), open_hour_end: Number(e.target.value) }))}
            />
          </Grid>
        </Grid>
        <Alert severity="info" sx={{ mt: 2 }}>
          开放时间：{String(openStart).padStart(2, '0')}:00 - {String(openEnd).padStart(2, '0')}:00（过滤统计与通知阈值）
        </Alert>
      </CardContent>
    </Card>
  );
}

function SidebarSection({ openStart, openEnd, data, favoritesSet, onToggleFavorite, notifyEnabled, onToggleNotify, loading }) {
  return (
    <Stack spacing={2.5}>
      <Card elevation={6} sx={{ backdropFilter: 'blur(12px)' }}>
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2}>
            <Typography variant="h6">当前在馆成员</Typography>
            <Chip label={`开馆 ${openStart}:00 - ${openEnd}:00`} variant="outlined" color="secondary" size="small" />
          </Stack>
          <Box mt={2}>
            <CurrentPeople
              people={data?.current_people || []}
              favorites={favoritesSet}
              onToggleFavorite={onToggleFavorite}
              snapshotTime={data?.last_timestamp}
            />
          </Box>
        </CardContent>
      </Card>
      <Card elevation={6} sx={{ backdropFilter: 'blur(12px)' }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            状态
          </Typography>
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Chip size="small" color="success" label={loading ? '加载中' : '运行中'} />
              <Typography variant="body2" color="text.secondary">
                配置与调度在后台运行
              </Typography>
            </Stack>
            <FormControlLabel control={<Switch checked={notifyEnabled} onChange={onToggleNotify} />} label="低人流浏览器通知" />
            <Typography variant="body2" color="text.secondary">
              收藏列表：{data?.favorites?.length || 0} 个 · 当前数据点：{data?.series?.length || 0}
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}

function App() {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [data, setData] = useState(null);
  const [hourScope, setHourScope] = useState('all');
  const [notifyEnabled, setNotifyEnabled] = useState(false);
  const favoritesSet = useMemo(() => new Set((data?.favorites || []).map((x) => String(x))), [data]);
  const lastNotifyRef = useRef(0);

  const openStart = Number(data?.open_hours?.start ?? config?.open_hour_start ?? 6);
  const openEnd = Number(data?.open_hours?.end ?? config?.open_hour_end ?? 23);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const cfg = await fetchJSON('/api/config');
        setConfig(cfg);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || !('Notification' in window)) return;
    try {
      const saved = localStorage.getItem(NOTIFY_STORAGE_KEY);
      if (saved === '1' && Notification.permission === 'granted') {
        setNotifyEnabled(true);
      }
    } catch (err) {
      console.warn('读取通知偏好失败', err);
    }
  }, []);

  const refreshData = async () => {
    try {
      const res = await fetchJSON('/api/data');
      setData(res);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    refreshData();
    const timer = setInterval(refreshData, 60_000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!notifyEnabled || !data || !('Notification' in window) || Notification.permission !== 'granted') return;
    const series = (data.series || []).filter((item) => isOpenHour(item.t, openStart, openEnd));
    const latest = series[series.length - 1] || (data.series || []).slice(-1)[0];
    if (!latest) return;
    const people = Number(latest.people_num ?? latest.people ?? 0);
    if (Number.isNaN(people) || people > NOTIFY_THRESHOLD) return;
    const now = Date.now();
    if (now - lastNotifyRef.current < NOTIFY_COOLDOWN) return;
    lastNotifyRef.current = now;
    try {
      new Notification('健身房人数提醒', { body: `当前人数 ${people} 人，适合前往健身房。`, tag: 'gym-low-occupancy' });
    } catch (err) {
      console.error('发送通知失败', err);
    }
  }, [data, notifyEnabled, openStart, openEnd]);

  const handleSaveConfig = async () => {
    if (!config) return;
    setSaving(true);
    try {
      const payload = {
        storage_dir: config.storage_dir,
        poll_interval_minutes: Number(config.poll_interval_minutes || 5),
        shop_id: Number(config.shop_id || 218),
        api_base: config.api_base,
        open_hour_start: Number(config.open_hour_start || openStart),
        open_hour_end: Number(config.open_hour_end || openEnd),
      };
      await fetchJSON('/api/config', { method: 'POST', body: JSON.stringify(payload) });
      setConfig((prev) => ({ ...prev, ...payload }));
    } catch (err) {
      console.error(err);
      alert('保存配置失败，请检查输入');
    } finally {
      setSaving(false);
    }
  };

  const handlePollNow = async () => {
    try {
      await fetchJSON('/api/poll', { method: 'POST' });
      await refreshData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleToggleFavorite = async (pid) => {
    const current = new Set(favoritesSet);
    const favorite = !current.has(pid);
    if (favorite) current.add(pid);
    else current.delete(pid);
    setData((prev) => ({ ...(prev || {}), favorites: Array.from(current) }));
    try {
      await fetchJSON('/api/favorites', {
        method: 'POST',
        body: JSON.stringify({ id: pid, favorite }),
      });
    } catch (err) {
      console.error(err);
    }
  };

  const handleToggleNotify = async () => {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      alert('当前浏览器不支持通知');
      return;
    }
    if (notifyEnabled) {
      setNotifyEnabled(false);
      localStorage.removeItem(NOTIFY_STORAGE_KEY);
      return;
    }
    let permission = Notification.permission;
    if (permission === 'default') {
      try {
        permission = await Notification.requestPermission();
      } catch (err) {
        alert('通知授权失败');
        return;
      }
    }
    if (permission !== 'granted') {
      alert('浏览器未授予通知权限');
      return;
    }
    setNotifyEnabled(true);
    localStorage.setItem(NOTIFY_STORAGE_KEY, '1');
    lastNotifyRef.current = 0;
  };

  const filteredSeries = useMemo(() => {
    return (data?.series || []).filter((item) => isOpenHour(item.t, openStart, openEnd));
  }, [data, openStart, openEnd]);

  const lineLabels = filteredSeries.map((x) => x.t.slice(5, 16));
  const lineValues = filteredSeries.map((x) => x.people_num);

  const weekdayEntries = useMemo(() => {
    const wk = data?.weekday_avg || {};
    return Object.entries(wk)
      .map(([k, v]) => [Number(k), v])
      .sort((a, b) => a[0] - b[0]);
  }, [data]);

  const hourDataset = useMemo(() => {
    const base = hourScope === 'all' ? data?.hour_avg : data?.weekday_hour_avg?.[hourScope];
    const values = [];
    const labels = [];
    for (let h = openStart; h < openEnd; h += 1) {
      labels.push(`${String(h).padStart(2, '0')}:00`);
      values.push(Number(base?.[String(h)] ?? 0));
    }
    return { labels, values };
  }, [data, hourScope, openStart, openEnd]);

  const theme = useMemo(
    () =>
      createTheme({
        palette: {
          mode: 'dark',
          background: { default: 'transparent', paper: 'rgba(255,255,255,0.06)' },
          primary: { main: '#6e8bff' },
          secondary: { main: '#66d483' },
        },
        shape: { borderRadius: 16 },
      }),
    [],
  );

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Stack spacing={3}>
          <HeroSection notifyEnabled={notifyEnabled} onToggleNotify={handleToggleNotify} onRefresh={refreshData} />
          <Grid container spacing={2.5}>
            <Grid item xs={12} md={8}>
              <Stack spacing={2.5}>
                <ChartsSection
                  lineLabels={lineLabels}
                  lineValues={lineValues}
                  weekdayEntries={weekdayEntries}
                  hourDataset={hourDataset}
                  hourScope={hourScope}
                  onHourScopeChange={setHourScope}
                />
                <ConfigSection
                  config={config}
                  setConfig={setConfig}
                  openStart={openStart}
                  openEnd={openEnd}
                  onSaveConfig={handleSaveConfig}
                  onPollNow={handlePollNow}
                  saving={saving}
                />
              </Stack>
            </Grid>
            <Grid item xs={12} md={4}>
              <SidebarSection
                openStart={openStart}
                openEnd={openEnd}
                data={data}
                favoritesSet={favoritesSet}
                onToggleFavorite={handleToggleFavorite}
                notifyEnabled={notifyEnabled}
                onToggleNotify={handleToggleNotify}
                loading={loading}
              />
            </Grid>
          </Grid>

          <Box textAlign="center" py={2}>
            <Divider sx={{ mb: 2 }} />
            <Typography variant="body2" color="text.secondary">
              React + Material UI 前端 · 后端 Flask + APScheduler · 数据 JSONL
            </Typography>
          </Box>
        </Stack>
      </Container>
    </ThemeProvider>
  );
}

const root = createRoot(document.getElementById('root'));
root.render(<App />);
