// 人格后台页 —— 对应 ui/dashboard/persona_mind_page.py。
// 顶部是实时状态快照，下面 6+ 个只读标签页展示人格数据库里的轨迹。

import { h, fill, card, empty, statCard, formatTime, modal, field } from '../dom.js';
import { endpoints } from '../api.js';

// 标签名必须与后端/提示词用词一致：effects=短期影响、cues=线索、todos=待办。
// 之前 effects 叫「动向」、cues 叫「短期影响」，与 prompt 里的叫法正好错位，
// 排查缓存问题时极易看错对象。
const TABS = [
  ['effects', '短期影响'],
  ['cues', '线索'],
  ['todos', '待办'],
  ['profiles', '用户画像'],
  ['monologues', '内心独白'],
  ['trajectories', '整理轨迹'],
  ['state_logs', '状态日志'],
  ['sleep', '睡眠记录'],
  ['eat', '进食记录'],
  ['arc', '人格弧光'],
];

const REFRESH_MS = 3000;

export async function render(container, ctx) {
  let activeTab = 'effects';
  let timer = null;
  let disposed = false;

  const stateCards = h('div', { class: 'grid grid-4' });
  const wakeResultHost = h('div', {});
  const tabBody = h('div', {});
  const tabBar = h('div', { class: 'tabs' });
  let wakeBtn = null;
  let wakeBusy = false;

  function renderState(data) {
    if (!data.available) {
      if (wakeBtn) {
        wakeBtn.disabled = true;
        wakeBtn.title = data.reason || '人格后台不可用';
      }
      fill(stateCards, card('人格后台未启用', '', h('div', { class: 'field-help' }, data.reason || '')));
      return;
    }
    const s = data.state || {};
    if (wakeBtn) {
      const sleeping = s.current_action === 'sleeping' || s.current_action === 'collapsing';
      wakeBtn.disabled = wakeBusy || !sleeping;
      wakeBtn.title = sleeping ? '像被人叫醒一样唤醒人格' : '只有睡眠/昏睡中的人格才能被唤醒';
    }
    const phys = data.physiology || {};
    const actionLabels = {
      awake: '清醒',
      sleeping: '睡眠中',
      eating: '进食中',
      collapsing: '体力崩溃',
      working: '专注工作中',
    };
    const cards = [
      statCard('当前心情', s.mood != null ? Number(s.mood).toFixed(2) : '—'),
      statCard('社交需求', s.social_need != null ? Number(s.social_need).toFixed(2) : '—'),
      statCard('当前动作', actionLabels[s.current_action] || s.current_action || '空闲'),
      statCard('年龄', data.age && data.age.effective != null ? String(data.age.effective) : '—'),
    ];
    if (phys.energy_mode && phys.energy_mode !== 'off') {
      cards.push(statCard('能量', s.energy != null ? Number(s.energy).toFixed(1) : '—'));
    }
    if (phys.satiety_mode && phys.satiety_mode !== 'off') {
      cards.push(statCard('饱食度', s.satiety != null ? Number(s.satiety).toFixed(1) : '—'));
    }
    cards.push(statCard('上次心跳',
      s.last_tick_at ? formatTime(s.last_tick_at) : '—'));

    // 独白卡每次都重建，避免轮询时不断往后追加。
    fill(stateCards, ...cards,
      s.latest_monologue
        ? card('最近一次内心独白', '', h('div', {}, s.latest_monologue))
        : null,
    );
  }

  function renderRows(items) {
    if (!items.length) return empty('暂无记录');
    const columns = [...new Set(items.flatMap((row) => Object.keys(row)))].slice(0, 6);
    return h('table', { class: 'table' },
      h('thead', {}, h('tr', {}, ...columns.map((c) => h('th', {}, c)))),
      h('tbody', {}, ...items.map((row) =>
        h('tr', {}, ...columns.map((c) => {
          let value = row[c];
          if (value === null || value === undefined) value = '—';
          else if (typeof value === 'object') value = JSON.stringify(value);
          else if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
            value = formatTime(value);
          }
          return h('td', {}, String(value));
        })))),
    );
  }

  function showWakeResult(data) {
    if (data.reply_error) {
      fill(wakeResultHost, card('唤醒对话', '',
        empty(`人格已经醒了，但生成对白失败（${data.reply_error}）。`)));
      return;
    }
    const reply = String(data.reply || '').trim();
    fill(wakeResultHost, card('唤醒对话',
      '只显示在人格后台，不会自动发送到 QQ。',
      h('div', { class: 'wake-reply' }, reply || '（没有生成对白）'),
    ));
  }

  function openWakeModal() {
    if (wakeBusy) return;
    const message = h('textarea', {
      rows: 3,
      maxlength: 2000,
      placeholder: '例如：醒醒，群里有人找你 / 起来看看这个消息',
    });
    const submit = h('button', { class: 'btn btn-primary' }, '叫醒');
    const dialog = modal({
      title: '唤醒人格',
      subtitle: '像被人叫醒一样，人格会回一句自然的话。',
      body: h('div', {},
        field('叫醒留言（可选）', message,
          '会作为“叫醒你的人说的话”交给模型；留空时只表示把人格叫醒。'),
        h('p', { class: 'field-help' },
          '唤醒后需要一次模型调用；回复只显示在这里，不会自动发到 QQ。'),
      ),
      footer: h('div', { class: 'row' },
        h('button', { class: 'btn', onclick: () => dialog.close() }, '取消'),
        submit,
      ),
    });
    submit.onclick = async () => {
      if (wakeBusy) return;
      wakeBusy = true;
      submit.disabled = true;
      submit.textContent = '正在叫醒…';
      try {
        const data = await endpoints.wakePersona({
          message: message.value.trim(),
          reason: 'admin_webui',
        });
        dialog.close();
        showWakeResult(data || {});
        ctx.toast('已唤醒人格', 'ok');
        await refresh();
      } catch (e) {
        ctx.toast(e.message, 'error');
      } finally {
        wakeBusy = false;
        submit.disabled = false;
        submit.textContent = '叫醒';
      }
    };
    document.body.append(dialog.el);
    message.focus();
  }

  async function loadTab(key) {
    activeTab = key;
    for (const btn of tabBar.querySelectorAll('.tab')) {
      btn.classList.toggle('active', btn.dataset.tab === key);
    }
    fill(tabBody, empty('读取中…'));
    try {
      const data = await endpoints.mindTab(key, 60);
      if (disposed || activeTab !== key) return;
      if (!data.available) return fill(tabBody, empty(data.reason || '不可用'));
      fill(tabBody, card(data.title || key, `${(data.items || []).length} 条`, renderRows(data.items || [])));
    } catch (e) {
      if (!disposed) fill(tabBody, empty(`读取失败：${e.message}`));
    }
  }

  fill(tabBar, ...TABS.map(([key, title]) =>
    h('button', { class: 'tab', dataset: { tab: key }, onclick: () => loadTab(key) }, title)));

  wakeBtn = h('button', {
    class: 'btn btn-primary',
    disabled: true,
    onclick: openWakeModal,
  }, '唤醒');

  fill(container,
    h('div', { class: 'page-head' },
      h('div', {},
        h('h1', { class: 'page-title' }, '人格后台'),
        h('p', { class: 'page-desc' },
          '人格的内心状态与决策轨迹。需要「设置 → 人格与生理 → 启用人格后台」才会产生数据。'),
      ),
      h('div', { class: 'row' },
        wakeBtn,
        h('button', { class: 'btn', onclick: () => refresh() }, '刷新'),
      ),
    ),
    stateCards,
    wakeResultHost,
    tabBar,
    tabBody,
  );

  async function refresh() {
    if (disposed) return;
    try {
      renderState(await endpoints.mindState());
    } catch (e) {
      fill(stateCards, card('人格后台', '', empty(e.message)));
    }
  }

  await refresh();
  await loadTab(activeTab);
  timer = setInterval(refresh, REFRESH_MS);

  return {
    destroy() {
      disposed = true;
      clearInterval(timer);
    },
  };
}
