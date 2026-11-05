// 群聊 @ 触发规则。
//
// 只有名单里的群受限制：普通消息先丢弃，被 @ 后才按条数/时长开启接收窗口。
// 规则保存后热更新；窗口本身是 Runtime 内存状态，重启后清空。

import { h, fill, card, empty, field, table, formatNumber } from '../dom.js';
import { endpoints } from '../api.js';

function asInt(value, fallback = 0) {
  const num = Number.parseInt(String(value ?? '').trim(), 10);
  return Number.isFinite(num) ? num : fallback;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export async function render(container, ctx) {
  let data = null;
  let dirty = false;
  let busy = false;

  const enabledInput = h('input', { type: 'checkbox' });
  const groupInput = h('input', {
    placeholder: '输入群号',
    inputmode: 'numeric',
    autocomplete: 'off',
  });
  const maxInput = h('input', {
    type: 'number',
    min: 0,
    max: 1000,
    value: 0,
    style: { width: '110px' },
  });
  const minutesInput = h('input', {
    type: 'number',
    min: 0,
    max: 1440,
    value: 0,
    style: { width: '130px' },
  });
  const cacheInput = h('input', {
    type: 'number',
    min: 0,
    max: 500,
    value: 50,
    style: { width: '110px' },
  });
  const addBtn = h('button', { class: 'btn' }, '添加群');
  const saveBtn = h('button', { class: 'btn btn-primary', onclick: save }, '保存并立即生效');
  const statusLine = h('p', { class: 'field-help' });
  const rulesHost = h('div', {});
  const windowsHost = h('div', {});

  function renderStatus() {
    if (!data) return;
    const count = data.groups?.length || 0;
    const windows = data.active_windows?.length || 0;
    const llm = data.active_llm_groups?.length || 0;
    statusLine.textContent = enabledInput.checked
      ? `@ 触发已启用：${formatNumber(count)} 个群受限制，当前 ${formatNumber(windows)} 个活动窗口，`
        + `LLM 临时放行 ${formatNumber(llm)}/${formatNumber(data.max_llm_groups || 2)} 个群。`
      : `@ 触发已关闭：${formatNumber(count)} 条规则会保存，但不会过滤消息。`;
  }

  function renderRules() {
    if (!data) return;
    if (!data.groups?.length) {
      fill(rulesHost, empty('还没有配置 @ 触发群', {
        subtitle: '添加群号后，这些群只在被 @ 后开启接收窗口。',
        iconName: 'chats',
      }));
      return;
    }
    fill(rulesHost, table(
      ['群号', '最多连续消息数', '时间窗口（分钟）', '过滤缓存条数', '操作'],
      data.groups.map((rule, index) => {
        const max = h('input', {
          type: 'number',
          min: 0,
          max: 1000,
          value: rule.max_messages,
          style: { width: '110px' },
        });
        const minutes = h('input', {
          type: 'number',
          min: 0,
          max: 1440,
          value: rule.window_minutes,
          style: { width: '130px' },
        });
        const cache = h('input', {
          type: 'number',
          min: 0,
          max: 500,
          value: rule.cache_messages,
          style: { width: '110px' },
        });
        max.oninput = () => {
          rule.max_messages = clamp(asInt(max.value, 0), 0, 1000);
          dirty = true;
        };
        minutes.oninput = () => {
          rule.window_minutes = clamp(asInt(minutes.value, 0), 0, 1440);
          dirty = true;
        };
        cache.oninput = () => {
          rule.cache_messages = clamp(asInt(cache.value, 50), 0, 500);
          dirty = true;
        };
        return h('tr', {},
          h('td', { class: 'mono' }, String(rule.group_id)),
          h('td', {}, max, h('span', { class: 'field-help' }, ' 0 = 不限')),
          h('td', {}, minutes, h('span', { class: 'field-help' }, ' 0 = 不限')),
          h('td', {}, cache, h('span', { class: 'field-help' }, ' 0 = 不缓存')),
          h('td', {}, h('button', {
            class: 'btn btn-sm btn-danger',
            onclick: () => {
              data.groups.splice(index, 1);
              dirty = true;
              renderRules();
              renderStatus();
            },
          }, '移除')),
        );
      }),
    ));
  }

  function renderWindows() {
    if (!data) return;
    const windows = data.active_windows || [];
    if (!windows.length) {
      fill(windowsHost, empty('当前没有活动接收窗口', {
        subtitle: '@ 机器人或由 LLM 调用 group_trigger_window open 后，这里会显示剩余条数/时间。',
        iconName: 'chats',
      }));
      return;
    }
    fill(windowsHost, table(
      ['群号', '来源', '剩余消息', '剩余时间', '状态'],
      windows.map((item) => {
        const source = item.llm_owned ? 'LLM 临时放行' : '@ 触发';
        const remainingMessages = item.remaining_messages == null
          ? '不限' : `${formatNumber(item.remaining_messages)} 条`;
        const remainingMinutes = item.remaining_minutes == null
          ? '不限' : `约 ${formatNumber(item.remaining_minutes)} 分钟`;
        return h('tr', {},
          h('td', { class: 'mono' }, String(item.group_id)),
          h('td', {}, source),
          h('td', {}, remainingMessages),
          h('td', {}, remainingMinutes),
          h('td', { class: item.near_limit ? 'badge warn' : 'field-help' },
            item.near_limit ? '即将结束' : '进行中'),
        );
      }),
    ));
  }

  function renderAll() {
    enabledInput.checked = !!data.enabled;
    renderRules();
    renderWindows();
    renderStatus();
  }

  function addRule() {
    if (!data) return;
    const groupId = asInt(groupInput.value, 0);
    if (groupId <= 0) {
      ctx.toast('群号必须是正整数', 'error');
      return;
    }
    if (data.groups.some((rule) => rule.group_id === groupId)) {
      ctx.toast('这个群已经在触发名单中', 'warn');
      return;
    }
    data.groups.push({
      group_id: groupId,
      max_messages: clamp(asInt(maxInput.value, 0), 0, 1000),
      window_minutes: clamp(asInt(minutesInput.value, 0), 0, 1440),
      cache_messages: clamp(asInt(cacheInput.value, 50), 0, 500),
    });
    groupInput.value = '';
    maxInput.value = 0;
    minutesInput.value = 0;
    cacheInput.value = 50;
    dirty = true;
    renderRules();
    renderStatus();
  }

  addBtn.onclick = addRule;
  groupInput.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    addRule();
  });
  enabledInput.onchange = () => {
    dirty = true;
    renderStatus();
  };

  async function load() {
    try {
      data = await endpoints.groupTriggers();
      renderAll();
    } catch (e) {
      fill(container, card('群聊触发', '', empty(`读取失败：${e.message}`)));
      return false;
    }
    return true;
  }

  async function save() {
    if (!data || busy) return;
    busy = true;
    saveBtn.disabled = true;
    try {
      const result = await endpoints.saveGroupTriggers({
        enabled: enabledInput.checked,
        groups: (data.groups || []).map((rule) => ({
          group_id: asInt(rule.group_id, 0),
          max_messages: clamp(asInt(rule.max_messages, 0), 0, 1000),
          window_minutes: clamp(asInt(rule.window_minutes, 0), 0, 1440),
          cache_messages: clamp(asInt(rule.cache_messages, 50), 0, 500),
        })),
      });
      data = { ...data, ...result };
      dirty = false;
      renderAll();
      ctx.toast(result.message || '群聊 @ 触发规则已保存', 'ok');
    } catch (e) {
      ctx.toast(e.message, 'error');
    } finally {
      busy = false;
      saveBtn.disabled = false;
    }
  }

  const loaded = await load();
  if (!loaded) return {};

  fill(container,
    h('div', { class: 'page-head' },
      h('div', {},
        h('h1', { class: 'page-title' }, '群聊触发'),
        h('p', { class: 'page-desc' },
          '指定哪些群只在被 @ 时响应，并设置 @ 后继续接收普通消息的条数或时长。'
          + '规则保存后立即生效；活动窗口是 Runtime 内存状态。'),
      ),
      h('div', { class: 'row' }, saveBtn),
    ),

    card('触发规则',
      '只有名单中的群受限制；未列出的群保持正常接收。',
      h('label', { class: 'switch' }, enabledInput, '启用按群 @ 触发'),
      h('div', { class: 'row row-wrap', style: { marginTop: '16px' } },
        field('群号', groupInput),
        field('连续消息数', maxInput, '0 = 不按条数关闭'),
        field('时间窗口', minutesInput, '0 = 不按时间关闭，单位分钟'),
        field('过滤缓存条数', cacheInput, '0 = 不缓存；超出后丢弃最旧消息'),
        h('div', { class: 'spacer' }),
        addBtn,
      ),
      h('p', { class: 'field-help' },
        '条数和时间窗口可以只填一个，也可以都填；都填时先满足哪个就关闭窗口。'
        + '两者都为 0 时只接收 @ 消息。每次被 @ 会重新开启/刷新窗口。'
        + '被过滤的普通消息会进入该群的近期缓存，超过缓存条数后丢弃最旧记录；'
        + '缓存只在 Runtime 内存中保留，重启后清空。'),
      rulesHost,
    ),

    card('当前窗口',
      '窗口关闭后普通消息会被丢弃，但原始 QQ 事件仍保留在事件库；'
      + 'LLM 可在关闭前调用 group_trigger_window extend 延长，或 close 提前关闭。',
      windowsHost,
      h('div', { class: 'row' }, statusLine),
    ),

    card('LLM 临时放行', '',
      h('ul', { style: { margin: 0, paddingLeft: '20px', color: 'var(--text-secondary)' } },
        h('li', {}, '模型可以调用 group_trigger_window open 临时放行群消息，最多同时覆盖 2 个群。'),
        h('li', {}, 'open/extend/status 可用 history_limit 让模型决定附带最近几条被过滤消息；条数不会超过该群缓存上限。'),
        h('li', {}, '窗口快结束时，任务上下文会提示剩余条数/时间；模型可调用 extend 并自行决定延长多久。'),
        h('li', {}, '模型也可以调用 close 提前关闭窗口；重启 Runtime 会清空所有临时窗口和过滤缓存。'),
        h('li', {}, '被过滤的普通消息只进入有限的内存缓存，不会进入模型历史；超出缓存条数后立即丢弃。'),
      ),
    ),
  );

  window.addEventListener('beforeunload', (event) => {
    if (dirty) event.preventDefault();
  });

  return {};
}
