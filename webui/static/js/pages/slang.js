// 群聊黑话 / 网络热梗管理页。
//
// 学习是自动的（可在设置→功能里关闭），但候选必须在这里补释义并确认，
// 只有 confirmed + meaning 的词条能被模型按需查询（lookup_slang）。

import { h, fill, card, empty, field, table, modal, debounce } from '../dom.js';
import { icon } from '../icons.js';
import { endpoints } from '../api.js';

const STATUS_TEXT = {
  candidate: '待确认',
  confirmed: '已确认',
  rejected: '已拒绝',
};

function statusBadge(status) {
  const kind = status === 'confirmed' ? 'ok' : (status === 'rejected' ? 'bad' : 'warn');
  return h('span', { class: `badge ${kind}` }, STATUS_TEXT[status] || status);
}

function sourceText(entry) {
  return entry.source === 'manual' ? '手动' : 'AI 候选';
}

export async function render(container, ctx) {
  let data = null;
  let selectedConversation = '';
  let selectedStatus = '';
  let selectedQuery = '';
  let busy = false;
  let loadSeq = 0;

  const statusLine = h('p', { class: 'field-help' });
  const statsHost = h('div', { class: 'row row-wrap' });
  const listHost = h('div', {});
  const conversationInput = h('input', {
    placeholder: 'group:123456',
    style: { minWidth: '220px' },
  });
  const conversationList = h('datalist', { id: 'slang-conversations' });
  conversationInput.setAttribute('list', 'slang-conversations');
  const searchInput = h('input', {
    placeholder: '搜索词条、释义、用法、示例',
    style: { minWidth: '220px' },
    autocomplete: 'off',
  });
  const statusSelect = h('select', {},
    h('option', { value: '' }, '全部状态'),
    h('option', { value: 'candidate' }, '待确认'),
    h('option', { value: 'confirmed' }, '已确认'),
    h('option', { value: 'rejected' }, '已拒绝'),
  );

  const refreshBtn = h('button', { class: 'btn btn-sm' }, '刷新');
  const learnBtn = h('button', { class: 'btn btn-sm' },
    '从当前缓存学习');

  const newContent = h('input', { placeholder: '例如：难绷' });
  const newMeaning = h('input', { placeholder: '含义（确认词条必填）' });
  const newUsage = h('input', { placeholder: '使用场景（可选）' });
  const newExample = h('input', { placeholder: '示例短句（可选）' });
  const newRisk = h('input', { placeholder: '慎用/敏感提示（可选）' });
  const addBtn = h('button', { class: 'btn btn-primary' }, '手动添加');

  async function load() {
    const seq = ++loadSeq;
    try {
      const result = await endpoints.slangList({
        conversation_id: selectedConversation,
        status: selectedStatus,
        q: selectedQuery,
      });
      if (seq !== loadSeq) return;
      data = result;
      renderAll();
    } catch (e) {
      if (seq === loadSeq) {
        data = null;
        fill(listHost, empty(`读取黑话库失败：${e.message}`));
      }
    }
  }

  function renderStats() {
    const stats = data?.stats || {};
    const counts = stats.counts || {};
    const buffers = data?.buffers || {};
    const buffered = selectedConversation ? (buffers[selectedConversation] || 0) : 0;
    fill(statsHost,
      h('span', { class: 'badge' }, `共 ${stats.total || 0} 条`),
      selectedQuery || selectedStatus
        ? h('span', { class: 'badge' }, `匹配 ${data?.matched || 0} 条`)
        : null,
      h('span', { class: 'badge ok' }, '同群人格共享'),
      h('span', { class: 'badge warn' }, `待确认 ${counts.candidate || 0}`),
      h('span', { class: 'badge ok' }, `已确认 ${counts.confirmed || 0}`),
      h('span', { class: 'badge bad' }, `已拒绝 ${counts.rejected || 0}`),
      h('span', { class: 'field-help' },
        selectedConversation
          ? `当前群缓存 ${buffered} 条消息；自动提取阈值 ${data?.settings?.extract_min_messages ?? '—'} 条。`
          : '选择或输入 group:<群号> 查看该群的黑话；也可以直接搜索全部群。'),
      data?.writable === false
        ? h('span', { class: 'badge bad' }, '黑话库只读：上次读取失败')
        : null,
    );
    fill(conversationList,
      ...(data?.conversations || []).map((item) =>
        h('option', { value: item }, item)));
  }

  function openEdit(entry) {
    const meaning = h('textarea', { rows: 3, value: entry.meaning || '' });
    const usage = h('input', { value: entry.usage || '' });
    const example = h('input', { value: entry.example || '' });
    const risk = h('input', { value: entry.risk || '' });
    const content = h('input', { value: entry.content || '' });
    const editStatus = h('p', { class: 'field-help' });
    const dialog = modal({
      title: `编辑「${entry.content}」`,
      subtitle: `${entry.conversation_id} · 来源 ${entry.persona_id || '未知人格'} · `
        + `${sourceText(entry)} · 出现 ${entry.count || 0} 次`,
      body: h('div', {},
        h('p', { class: 'field-help' },
          '此词条属于当前群，同群所有人格共享；在这里修改会立即影响所有人格。'),
        entry.rejection_reason
          ? h('p', {
            class: 'field-help',
            style: { color: 'var(--error)', margin: '6px 0 12px' },
          }, `自动拒绝记录：${entry.rejection_reason}`)
          : null,
        field('词条', content, '2–8 个字符最合适；同群不能重复'),
        field('含义', meaning, '确认前必须填写；模型只看到这里的释义'),
        field('使用场景', usage),
        field('示例', example),
        field('风险提示', risk, '敏感、容易引战或需要慎用的词写在这里'),
        editStatus,
        h('details', {},
          h('summary', { class: 'field-help' }, `查看依据（${(entry.evidence || []).length} 条）`),
          h('pre', { class: 'draft-raw' },
            (entry.evidence || []).map((item) =>
              `${item.time || ''} ${item.sender || ''}: ${item.text || ''}`).join('\n')
            || '没有保存依据。'),
        ),
      ),
      footer: [],
      wide: true,
    });
    const saveBtn = h('button', { class: 'btn btn-primary' }, '保存');
    const confirmBtn = h('button', { class: 'btn' }, '保存并确认');
    const rejectBtn = h('button', { class: 'btn btn-danger' }, '拒绝');
    const deleteBtn = h('button', { class: 'btn btn-danger' }, '删除');
    const duplicateRejected = (
      entry.status === 'rejected'
      && entry.rejection_code === 'duplicate_term'
      && (data?.entries || []).some((item) =>
        item.id !== entry.id
        && item.conversation_id === entry.conversation_id
        && item.content === entry.content
        && item.status !== 'rejected')
    );
    if (duplicateRejected) {
      confirmBtn.disabled = true;
      confirmBtn.title = '同群已有同名词条；如需启用请先处理原词条或修改本词条';
    }
    content.oninput = () => {
      confirmBtn.disabled = (
        duplicateRejected && content.value.trim() === entry.content
      );
    };
    fill(dialog.el.querySelector('.modal-foot'),
      h('button', { class: 'btn', onclick: () => dialog.close() }, '取消'),
      deleteBtn,
      rejectBtn,
      confirmBtn,
      saveBtn,
    );
    const payload = (status) => ({
      content: content.value.trim(),
      meaning: meaning.value.trim(),
      usage: usage.value.trim(),
      example: example.value.trim(),
      risk: risk.value.trim(),
      ...(status ? { status } : {}),
    });
    const run = async (status, label) => {
      if (busy) return;
      if (status === 'confirmed' && !meaning.value.trim()) {
        editStatus.textContent = '确认前需要填写释义。';
        editStatus.style.color = 'var(--error)';
        meaning.focus();
        return;
      }
      busy = true;
      saveBtn.disabled = true;
      confirmBtn.disabled = true;
      rejectBtn.disabled = true;
      try {
        await endpoints.slangUpdate(entry.id, payload(status));
        ctx.toast(label, 'ok');
        dialog.close();
        await load();
      } catch (e) {
        editStatus.textContent = e.message;
        editStatus.style.color = 'var(--error)';
        saveBtn.disabled = false;
        confirmBtn.disabled = (
          duplicateRejected && content.value.trim() === entry.content
        );
        rejectBtn.disabled = false;
      } finally {
        busy = false;
      }
    };
    saveBtn.onclick = () => run('', '词条已保存');
    confirmBtn.onclick = () => run('confirmed', '词条已确认，可由 lookup_slang 查询');
    rejectBtn.onclick = () => run('rejected', '词条已拒绝');
    deleteBtn.onclick = async () => {
      if (!confirm(`删除「${entry.content}」？不会影响聊天记录。`)) return;
      try {
        await endpoints.slangDelete(entry.id);
        ctx.toast('词条已删除', 'ok');
        dialog.close();
        await load();
      } catch (e) {
        editStatus.textContent = e.message;
        editStatus.style.color = 'var(--error)';
      }
    };
    document.body.append(dialog.el);
  }

  function renderList() {
    const entries = data?.entries || [];
    if (!entries.length) {
      fill(listHost, empty(
        selectedConversation
          ? '这个群还没有词条。聊够消息后点「从当前缓存学习」，或手动添加。'
          : '还没有黑话记录。选择群聊后等自动学习，或手动添加。'
      ));
      return;
    }
    fill(listHost, table(
      ['词条', '含义', '群聊', '来源人格', '次数', '状态', '方式', '操作'],
      entries.map((entry) => h('tr', {},
        h('td', {}, h('strong', {}, entry.content)),
        h('td', { class: 'field-help' }, entry.meaning || '（未填写）'),
        h('td', { class: 'mono field-help' }, entry.conversation_id || '—'),
        h('td', { class: 'field-help' }, entry.persona_id || '—'),
        h('td', {}, String(entry.count || 0)),
        h('td', {},
          statusBadge(entry.status),
          entry.rejection_reason
            ? h('div', {
              class: 'field-help',
              style: { marginTop: '4px', maxWidth: '180px' },
            }, entry.rejection_reason)
            : null),
        h('td', { class: 'field-help' }, sourceText(entry)),
        h('td', {}, h('button', {
          class: 'btn btn-sm',
          onclick: () => openEdit(entry),
        }, icon('edit', { size: 14 }), '编辑')),
      )),
    ));
  }

  function renderAll() {
    renderStats();
    renderList();
  }

  async function learn() {
    if (!selectedConversation) {
      statusLine.textContent = '先选择或输入 group:<群号>。';
      return;
    }
    busy = true;
    learnBtn.disabled = true;
    statusLine.textContent = '正在提取候选，可能需要十几秒…';
    try {
      const result = await endpoints.slangLearn({
        conversation_id: selectedConversation,
      });
      statusLine.textContent = result.ok
        ? result.message
        : `没有学习：${result.error || '未知原因'}`;
      if (result.ok) {
        if (result.auto_rejected) ctx.toast(
          `有 ${result.auto_rejected} 条重复申请已自动拒绝，仍保留在列表中`,
          'warn',
        );
        await load();
      }
    } catch (e) {
      statusLine.textContent = `学习失败：${e.message}`;
    } finally {
      busy = false;
      learnBtn.disabled = false;
    }
  }

  async function addManual() {
    if (!selectedConversation) {
      statusLine.textContent = '先选择或输入 group:<群号>。';
      return;
    }
    if (!newContent.value.trim() || !newMeaning.value.trim()) {
      statusLine.textContent = '手动添加需要词条和释义。';
      return;
    }
    addBtn.disabled = true;
    try {
      await endpoints.slangCreate({
        conversation_id: selectedConversation,
        content: newContent.value.trim(),
        meaning: newMeaning.value.trim(),
        usage: newUsage.value.trim(),
        example: newExample.value.trim(),
        risk: newRisk.value.trim(),
        status: 'confirmed',
      });
      ctx.toast('词条已添加', 'ok');
      for (const input of [newContent, newMeaning, newUsage, newExample, newRisk]) {
        input.value = '';
      }
      statusLine.textContent = '';
      await load();
    } catch (e) {
      statusLine.textContent = e.message;
    } finally {
      addBtn.disabled = false;
    }
  }

  refreshBtn.onclick = () => load();
  learnBtn.onclick = learn;
  addBtn.onclick = addManual;
  searchInput.oninput = debounce(() => {
    selectedQuery = searchInput.value.trim();
    load();
  }, 250);
  conversationInput.onchange = () => {
    selectedConversation = conversationInput.value.trim();
    load();
  };
  statusSelect.onchange = () => {
    selectedStatus = statusSelect.value;
    load();
  };

  fill(container,
    h('div', { class: 'page-head' },
      h('div', {},
        h('h1', { class: 'page-title' }, '群聊黑话'),
        h('p', { class: 'page-desc' },
          '群聊黑话知识库：按群隔离，同群所有人格共享。候选必须人工补释义并确认，'
          + '只有已确认词条能被模型按需查询（lookup_slang），不会每轮注入上下文。'),
      ),
      h('div', { class: 'row' },
        h('button', {
          class: 'btn',
          onclick: () => ctx.navigate('settings', { section: 'features' }),
        }, '学习设置'),
        refreshBtn,
      ),
    ),
    card('', '',
      h('div', { class: 'row row-wrap' },
        field('群聊会话', conversationInput, '格式 group:<群号>；也可以从已有记录中选择'),
        field('搜索', searchInput, '搜索词条、释义、用法、示例或风险提示'),
        field('状态', statusSelect, ''),
        h('div', { class: 'spacer' }),
        learnBtn,
      ),
      statsHost,
      statusLine,
      conversationList,
    ),
    card('手动添加', '手动词条默认已确认，保存后同群所有人格共享；适合你已经在群里验证过的梗。',
      h('div', { class: 'grid grid-2' },
        field('词条', newContent),
        field('含义', newMeaning),
        field('使用场景', newUsage),
        field('示例', newExample),
        field('风险提示', newRisk),
      ),
      h('div', { class: 'row' },
        h('div', { class: 'spacer' }),
        addBtn),
    ),
    card('词条列表',
      '同群所有人格共享这些词条；已确认 + 有释义的词条按出现次数排序，'
      + '模型查询时最多返回 inject_max 条。',

      listHost),
  );

  await load();
  return {};
}
