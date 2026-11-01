// 危险数据操作：预览、确认、执行与轮询。
//
// 这里不使用 window.confirm：确认短语、勾选和影响清单都由后端预览生成；
// 服务端会再次校验 token、目标 generation、短语和幂等键。

import { h, fill, modal, table } from './dom.js';
import { endpoints } from './api.js';

function formatBytes(value) {
  const num = Math.max(0, Number(value) || 0);
  if (num >= 1024 ** 4) return `${(num / 1024 ** 4).toFixed(2)} TiB`;
  if (num >= 1024 ** 3) return `${(num / 1024 ** 3).toFixed(2)} GiB`;
  if (num >= 1024 ** 2) return `${(num / 1024 ** 2).toFixed(1)} MiB`;
  if (num >= 1024) return `${(num / 1024).toFixed(1)} KiB`;
  return `${num} B`;
}

function idempotencyKey() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  return `admin-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

const PHASE_LABELS = {
  queued: '排队中',
  preflight: '检查目标',
  backing_up: '创建备份',
  writing_cleanup_marker: '写入清理标记',
  updating_knowledge: '更新知识库',
  deleting_memory: '删除聊天与记忆',
  deleting_vector: '删除 RAG 向量库',
  creating_empty_database: '创建空数据库',
  completed: '完成',
  partial: '部分完成',
  failed: '失败',
  cancelled: '已取消',
  interrupted: '已中断',
};

const TERMINAL = new Set([
  'completed', 'partial', 'failed', 'cancelled', 'interrupted',
]);

function phaseLabel(job) {
  const phase = job?.phase || job?.state || '';
  return PHASE_LABELS[phase] || phase || '处理中';
}

function warningBox(...children) {
  return h('div', {
    style: {
      border: '1px solid var(--error, #b42318)',
      borderRadius: '8px',
      padding: '12px',
      marginBottom: '14px',
      background: 'color-mix(in srgb, var(--error, #b42318) 8%, transparent)',
    },
  }, ...children);
}

function impactTable(rows) {
  return table(['项目', '影响'], rows.map(([label, value]) =>
    h('tr', {}, h('td', {}, label), h('td', {}, value))));
}

function protectedList(items) {
  if (!Array.isArray(items) || !items.length) return null;
  return h('div', { class: 'row row-wrap', style: { gap: '6px' } },
    ...items.map((item) => h('span', { class: 'badge' },
      item.key || item.kind || item)));
}

function openProgressModal(ctx, title, subtitle, stageHost) {
  const status = h('p', { class: 'field-help' }, '正在提交…');
  const body = h('div', {},
    warningBox(h('p', {}, '请保持页面打开。任务已提交后即使页面断开，服务端仍会继续。')),
    stageHost,
    status,
  );
  const view = modal({
    title,
    subtitle,
    body,
    footer: h('div', { class: 'row' },
      h('div', { class: 'spacer' }),
      h('button', {
        class: 'btn',
        onclick: () => view.close(),
      }, '关闭'),
    ),
    wide: true,
  });
  document.body.append(view.el);
  return { view, status };
}

function pollJob(ctx, jobId, stageHost, status, { onDone, title, subtitle } = {}) {
  let attempts = 0;
  const tick = async () => {
    try {
      const job = await endpoints.adminJob(jobId);
      attempts = 0;
      if (!job) {
        status.textContent = '任务状态暂不可用，继续重试…';
        setTimeout(tick, 1200);
        return;
      }
      fill(stageHost,
        h('p', {}, `阶段：${phaseLabel(job)}`),
        h('p', { class: 'field-help' },
          `状态：${job.state || '未知'}`
          + (job.progress?.bytes_total
            ? ` · ${formatBytes(job.progress.bytes_done || 0)}`
              + ` / ${formatBytes(job.progress.bytes_total)}`
            : '')),
      );
      status.textContent = TERMINAL.has(job.state)
        ? (job.state === 'completed' ? '操作完成。' : '操作结束，请查看结果。')
        : '任务执行中…';
      if (!TERMINAL.has(job.state)) {
        setTimeout(tick, 700);
        return;
      }
      const result = job.result || {};
      if (job.state === 'completed') {
        ctx.toast('清理完成', 'ok');
      } else if (job.state === 'cancelled') {
        ctx.toast('任务已取消（可能已有部分内容被删除）', 'warn');
      } else {
        ctx.toast(
          `清理${job.state === 'partial' ? '部分完成' : '失败'}：`
          + (job.error_message || result.error || '请查看任务结果'),
          'error',
        );
      }
      fill(stageHost,
        h('p', {}, `阶段：${phaseLabel(job)}`),
        h('p', { class: 'field-help' },
          `释放：${formatBytes(result.bytes_freed || 0)}；`
          + `Runtime：${result.runtime?.restarted ? '已恢复' : '未运行/恢复失败'}`),
        result.backup?.path
          ? h('p', { class: 'field-help mono' }, `备份：${result.backup.path}`)
          : null,
      );
      if (onDone) await onDone();
    } catch (e) {
      attempts += 1;
      status.textContent = `读取任务状态失败：${e.message}；继续重试…`;
      if (attempts < 20) setTimeout(tick, 1200);
    }
  };
  setTimeout(tick, 300);
}

export async function openPersonaCleanup(ctx, persona, { onDone } = {}) {
  let preview;
  try {
    preview = await endpoints.adminPersonaCleanupPreview(persona);
  } catch (e) {
    ctx.toast(`读取清理预览失败：${e.message}`, 'error');
    return;
  }

  const backup = h('input', { type: 'checkbox' });
  const acknowledge = h('input', { type: 'checkbox' });
  const phrase = h('input', {
    placeholder: preview.confirmation_phrase,
    autocomplete: 'off',
  });
  const errorLine = h('p', { class: 'field-help' });
  const confirmBtn = h('button', { class: 'btn btn-danger', disabled: true }, '确认清理');
  const view = modal({
    title: `清理「${persona}」的运行数据`,
    subtitle: '人格定义会保留；运行数据删除后不可恢复。',
    wide: true,
    body: h('div', {},
      warningBox(
        h('p', {}, '此操作不可撤销。执行时会短暂停止 Runtime，删除完成后自动恢复。'),
        h('p', { class: 'field-help' },
          '不会删除：人格定义、其他人格、workspace、日志、表情包、全局配置/密钥、'
          + '备份库、群共享黑话、共享知识。'),
      ),
      impactTable([
        ['聊天/记忆数据库', `${formatBytes(preview.memory?.bytes || 0)} · `
          + `${preview.memory?.files || 0} 个文件`],
        ['RAG 向量库', `${formatBytes(preview.vector?.bytes || 0)} · `
          + `${preview.vector?.files || 0} 个文件`],
        ['私有知识条目', `${preview.knowledge?.private_entries || 0} 条`],
        ['共享知识 / 其他人格', '保留'],
        ['预计释放', formatBytes(preview.expected_bytes || 0)],
      ]),
      h('p', { class: 'field-help' },
        `当前人格：${preview.active ? '是' : '否'}；`
        + `执行方式：${preview.requires_runtime_restart ? '暂停并自动恢复 Runtime' : '离线执行'}。`),
      protectedList(preview.protected),
      h('label', { class: 'row', style: { marginTop: '14px', gap: '8px' } },
        backup,
        h('span', {}, '删除前创建该人格的完整备份（默认关闭；备份包含聊天与记忆）'),
      ),
      h('label', { class: 'row', style: { marginTop: '10px', gap: '8px' } },
        acknowledge,
        h('span', {}, '我明白此操作不可撤销，且未勾选备份时不会保留副本'),
      ),
      h('label', { class: 'field', style: { marginTop: '10px' } },
        h('span', { class: 'field-label' }, '输入确认短语'),
        phrase,
        h('div', { class: 'field-help' }, preview.confirmation_phrase),
      ),
      errorLine,
    ),
    footer: h('div', { class: 'row' },
      h('button', { class: 'btn', onclick: () => view.close() }, '取消'),
      h('div', { class: 'spacer' }),
      confirmBtn,
    ),
  });
  document.body.append(view.el);

  const sync = () => {
    confirmBtn.disabled = !(
      acknowledge.checked
      && phrase.value.trim() === preview.confirmation_phrase
    );
  };
  acknowledge.onchange = sync;
  phrase.oninput = sync;

  confirmBtn.onclick = async () => {
    if (confirmBtn.disabled) return;
    confirmBtn.disabled = true;
    errorLine.textContent = '';
    const payload = {
      preview_id: preview.preview_id,
      confirmation_token: preview.confirmation_token,
      expected_generation: preview.generation,
      idempotency_key: idempotencyKey(),
      typed_confirmation: phrase.value.trim(),
      acknowledge_destructive: true,
      create_backup: backup.checked,
    };
    let job;
    try {
      job = await endpoints.adminPersonaCleanupExecute(persona, payload);
    } catch (e) {
      errorLine.style.color = 'var(--error)';
      errorLine.textContent = `清理失败：${e.message}`;
      confirmBtn.disabled = false;
      return;
    }
    view.close();
    const stageHost = h('div', {});
    const progress = openProgressModal(
      ctx,
      `正在清理「${persona}」`,
      '服务端任务已提交；关闭页面不会中止已开始的删除。',
      stageHost,
    );
    pollJob(ctx, job.job_id, stageHost, progress.status, {
      onDone,
      title: '清理任务',
      subtitle: persona,
    });
  };
}

export async function openUninstall(ctx) {
  let preview;
  try {
    preview = await endpoints.adminUninstallPreview();
  } catch (e) {
    ctx.toast(`读取卸载预览失败：${e.message}`, 'error');
    return;
  }
  if (!preview.supported) {
    const view = modal({
      title: '当前环境不支持自动卸载',
      subtitle: preview.unsupported_reason || '请按文档手动卸载。',
      body: h('div', {},
        h('p', {}, '未执行任何删除。'),
        h('pre', { class: 'draft-raw' }, preview.manual_steps || ''),
      ),
      footer: h('div', { class: 'row' },
        h('div', { class: 'spacer' }),
        h('button', { class: 'btn', onclick: () => view.close() }, '关闭'),
      ),
      wide: true,
    });
    document.body.append(view.el);
    return;
  }

  const backup = h('input', {
    type: 'checkbox',
    disabled: !preview.optional_backup?.available,
  });
  const acknowledge = h('input', { type: 'checkbox' });
  const phrase = h('input', {
    placeholder: preview.confirmation_phrase,
    autocomplete: 'off',
  });
  const errorLine = h('p', { class: 'field-help' });
  const confirmBtn = h('button', { class: 'btn btn-danger', disabled: true }, '永久卸载');
  const rows = (preview.targets || []).map((target) => [
    target.kind,
    `${formatBytes(target.bytes || 0)} · ${target.files || 0} 个文件`,
  ]);
  const retained = (preview.retained || []).map((item) =>
    item.kind || item.path || String(item));
  const view = modal({
    title: '永久卸载 KarenBot',
    subtitle: '会停止服务并删除源码、数据目录和程序备份；GitHub 不会被修改。',
    wide: true,
    body: h('div', {},
      warningBox(
        h('p', {}, '点击确认后 WebUI 会立即关闭；删除完成后无法再从本页确认结果。'),
        h('p', { class: 'field-help' },
          '未勾选备份时，本机不会保留任何数据副本。'),
      ),
      impactTable(rows),
      h('p', { class: 'field-label' }, '删除目标'),
      h('div', { class: 'mono field-help', style: { whiteSpace: 'pre-wrap' } },
        (preview.targets || []).map((t) => t.path).join('\n')),
      retained.length
        ? h('p', { class: 'field-help' }, `保留：${retained.join('、')}`)
        : null,
      h('label', { class: 'row', style: { marginTop: '14px', gap: '8px' } },
        backup,
        h('span', {}, preview.optional_backup?.available
          ? '删除前创建完整备份（用户数据 + 源码归档，默认关闭）'
          : '当前 Runtime 未运行，无法创建可选备份'),
      ),
      h('label', { class: 'row', style: { marginTop: '10px', gap: '8px' } },
        acknowledge,
        h('span', {}, '我确认已理解并接受永久删除，且知道 GitHub 远端不会改变'),
      ),
      h('label', { class: 'field', style: { marginTop: '10px' } },
        h('span', { class: 'field-label' }, '输入确认短语'),
        phrase,
        h('div', { class: 'field-help' }, preview.confirmation_phrase),
      ),
      errorLine,
    ),
    footer: h('div', { class: 'row' },
      h('button', { class: 'btn', onclick: () => view.close() }, '取消'),
      h('div', { class: 'spacer' }),
      confirmBtn,
    ),
  });
  document.body.append(view.el);

  const sync = () => {
    confirmBtn.disabled = !(
      acknowledge.checked
      && phrase.value.trim() === preview.confirmation_phrase
      && (!backup.checked || preview.optional_backup?.available)
    );
  };
  acknowledge.onchange = sync;
  phrase.oninput = sync;
  backup.onchange = sync;

  confirmBtn.onclick = async () => {
    if (confirmBtn.disabled) return;
    confirmBtn.disabled = true;
    errorLine.textContent = '';
    const payload = {
      preview_id: preview.preview_id,
      confirmation_token: preview.confirmation_token,
      expected_generation: preview.generation,
      idempotency_key: idempotencyKey(),
      typed_confirmation: phrase.value.trim(),
      acknowledge_destructive: true,
      create_backup: backup.checked,
    };
    let job;
    try {
      job = await endpoints.adminUninstallExecute(payload);
    } catch (e) {
      errorLine.style.color = 'var(--error)';
      errorLine.textContent = `卸载未能启动：${e.message}`;
      confirmBtn.disabled = false;
      return;
    }
    view.close();
    const auditPath = job.audit_path || preview.audit_path || '';
    if (auditPath) {
      try {
        localStorage.setItem('karen-uninstall-audit', auditPath);
      } catch { /* ignore */ }
    }
    const card = h('div', { class: 'gate-card gate-card-wide' });
    const gate = h('div', { class: 'gate' }, card);
    document.body.replaceChildren(gate);

    const renderGate = (title, subtitle, detail, final = false) => {
      fill(card,
        h('div', { class: 'gate-brand' }, title),
        h('p', { class: 'gate-hint' }, subtitle),
        h('p', { class: 'field-help mono' }, `任务：${job.job_id}`),
        auditPath
          ? h('p', { class: 'field-help mono' }, `审计：${auditPath}`)
          : null,
        h('p', { class: 'field-help' }, detail),
        final ? h('button', {
          class: 'btn',
          style: { marginTop: '14px' },
          onclick: () => location.reload(),
        }, '刷新页面') : null,
      );
    };

    let attempts = 0;
    let stopped = false;
    const tick = async () => {
      if (stopped) return;
      try {
        const state = await endpoints.adminJob(job.job_id);
        attempts = 0;
        if (!state) throw new Error('任务状态为空');
        if (state.state === 'scheduled') {
          stopped = true;
          renderGate(
            '卸载已调度',
            '后端即将退出；独立助手会在退出后继续删除。',
            `阶段：${phaseLabel(state)}。此页面可以关闭，请保存审计路径。`,
            false,
          );
          return;
        }
        if (TERMINAL.has(state.state)) {
          stopped = true;
          renderGate(
            `卸载未完成：${state.state}`,
            state.error_message || state.result?.error || '后端仍在运行，可检查日志后重试。',
            '没有启动独立删除助手，或删除前已中止。',
            true,
          );
          return;
        }
        renderGate(
          '正在准备卸载',
          '可选备份可能需要几分钟；请保持页面打开。',
          `阶段：${phaseLabel(state)}`
          + (state.progress?.bytes_total
            ? ` · ${formatBytes(state.progress.bytes_done || 0)}`
              + ` / ${formatBytes(state.progress.bytes_total)}`
            : ''),
          false,
        );
        setTimeout(tick, 700);
      } catch (e) {
        attempts += 1;
        if (attempts < 8) {
          setTimeout(tick, 1200);
          return;
        }
        stopped = true;
        renderGate(
          '无法读取卸载任务状态',
          '服务可能已经退出，或网络连接已断开。',
          `请用审计文件确认结果：${auditPath || '（生成中）'}`,
          false,
        );
      }
    };
    renderGate(
      '正在准备卸载',
      '服务即将退出；删除助手会在后端退出后继续。',
      '正在读取任务状态…',
      false,
    );
    setTimeout(tick, 500);
  };
}
