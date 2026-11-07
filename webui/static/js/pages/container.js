// 受控 Docker 容器状态页。配置在 设置 → 容器；本页做诊断、文件浏览与轻量测试。

import { h, fill, card, empty, table } from '../dom.js';
import { endpoints } from '../api.js';
import { promptStorageSetup } from '../container_setup.js';
import { createContainerFileBrowser } from '../container_files.js';

function formatBytes(value) {
  const num = Math.max(0, Number(value) || 0);
  if (num >= 1024 ** 3) return `${(num / 1024 ** 3).toFixed(2)} GiB`;
  if (num >= 1024 ** 2) return `${(num / 1024 ** 2).toFixed(1)} MiB`;
  if (num >= 1024) return `${(num / 1024).toFixed(1)} KiB`;
  return `${num} B`;
}

function badge(text, tone = '') {
  return h('span', { class: `badge ${tone}`.trim() }, text);
}

export async function render(container, ctx) {
  let status = null;
  let storageSetup = null;
  let agentStatus = null;
  let agentLoading = true;
  let agentBusy = false;
  let lastError = null;
  let destroyed = false;
  const fileBrowser = createContainerFileBrowser(ctx);

  const refreshButton = h('button', { class: 'btn', onclick: () => refresh() }, '刷新');
  const testButton = h('button', {
    class: 'btn btn-primary',
    onclick: () => runTest(),
  }, '一键准备 / 启动');
  const resetButton = h('button', {
    class: 'btn btn-danger',
    onclick: () => resetContainer(),
  }, '重建容器');
  const setupButton = h('button', {
    class: 'btn btn-primary',
    onclick: () => promptStorageSetup(ctx, { force: true, onDone: refresh }),
  }, '初始化 C 存储');
  setupButton.style.display = 'none';
  const configButton = h('button', {
    class: 'btn',
    onclick: () => ctx.navigate('settings', { section: 'container' }),
  }, '打开容器设置');
  const actionHost = h('div', { class: 'row' },
    refreshButton, testButton, setupButton, resetButton, configButton);
  const summaryHost = h('div', { class: 'grid grid-4' });
  const problemHost = h('div', {});
  const agentHost = h('div', {});
  const detailHost = h('div', {});
  const storageHost = h('div', {});
  const page = h('div', { class: 'page' },
    h('div', { class: 'page-head' },
      h('h1', { class: 'page-title' }, '受控容器'),
      h('p', { class: 'page-desc' },
        'Docker 容器只提供资源/文件隔离，不是对抗恶意代码的绝对安全边界。'
        + '默认无网络、无特权、非 root、只挂载专用 workspace。'
        + '首次使用直接点「一键准备 / 启动」；可在下方文件管理中只读浏览容器文件系统。这里的 /workspace 是容器存储，不是本机 AI 工作区；本机工作区请切到同一文件管理的「本机工作区」模式。')),
    actionHost, summaryHost, problemHost, agentHost, fileBrowser.el, detailHost, storageHost);
  fill(container, page);

  async function refresh() {
    refreshButton.disabled = true;
    agentLoading = true;
    // 三个接口都依赖 Docker 但互相独立，串行等待会让 Agent 卡片明显变慢。
    const agentsPromise = endpoints.containerAgents()
      .then((data) => { agentStatus = data; })
      .catch(() => { agentStatus = null; })
      .finally(() => {
        agentLoading = false;
        if (!destroyed) renderAgents();
      });
    try {
      const [statusResult, storageResult] = await Promise.allSettled([
        endpoints.containerStatus(),
        endpoints.containerStorage(),
      ]);
      if (statusResult.status !== 'fulfilled') {
        throw statusResult.reason;
      }
      status = statusResult.value;
      storageSetup = storageResult.status === 'fulfilled'
        ? storageResult.value
        : null;
      if (!destroyed) renderAll();
    } catch (e) {
      if (!destroyed) {
        fill(container, card('受控容器', '',
          empty(`读取容器状态失败：${e.message}`)));
      }
    } finally {
      await agentsPromise.catch(() => {});
      refreshButton.disabled = false;
    }
  }

  function storageMismatch() {
    const storage = status?.status?.storage || {};
    return storage.code === 'container_storage_size_mismatch' && storage.marker_size_mb;
  }

  function renderAll() {
    const info = status?.status || {};
    const docker = info.docker || {};
    const storage = info.storage || {};
    const box = info.container || {};
    const admin = storageSetup?.admin || {};
    const mismatch = storageMismatch();
    const needsMount = storage.code === 'container_storage_not_mounted';
    setupButton.textContent = needsMount ? '重新挂载 C 存储' : '初始化 C 存储';
    setupButton.style.display = (
      storage.mode === 'image_fixed'
      && !storage.ready
      && !mismatch
      && admin.available
    ) ? '' : 'none';
    fill(summaryHost,
      metric('功能', info.enabled ? '已启用' : '未启用',
        info.enabled ? 'ok' : ''),
      metric('就绪', info.ready ? '可用' : '未就绪',
        info.ready ? 'ok' : 'warn'),
      metric('Docker', docker.available ? '可用' : '不可用',
        docker.available ? 'ok' : 'bad'),
      metric('存储', storage.mode === 'image_fixed' ? 'C 固定大小' : 'B 软配额',
        storage.ready ? 'ok' : 'bad'));

    fill(problemHost, renderProblems(info, storage, docker, mismatch));
    const limits = info.limits || {};
    fill(detailHost, card('运行诊断', '',
      table(
        ['项目', '值'],
        [
          ['Docker Server', docker.server_version || docker.error || '—'],
          ['镜像', `${info.image || '—'} ${info.image_present ? '（已存在）' : '（缺失）'}`],
          ['容器名', info.container_name || '—'],
          ['容器状态', box.state || '—'],
          ['内存 / CPU', `${limits.memory_mb ?? '—'} MiB / ${limits.cpus ?? '—'}`],
          ['pids / 单文件', `${limits.pids_limit ?? '—'} / ${limits.file_size_mb ?? '—'} MiB`],
          ['网络', limits.network || '—'],
          ['exec 超时', `${limits.exec_timeout_seconds ?? '—'} 秒`],
          ['存储就绪', storage.ready ? '是' : (storage.error || '否')],
          ['存储大小', storage.mode === 'image_fixed'
            ? `${storage.size_mb ?? '—'} MiB`
            : `${storage.size_mb ?? '—'} MiB 软配额`],
          ['镜像实际大小', storage.marker_size_mb == null
            ? '—' : `${storage.marker_size_mb} MiB`],
          ['剩余空间', storage.free_bytes == null ? '—' : formatBytes(storage.free_bytes)],
        ].map(([label, value]) => h('tr', {},
          h('td', {}, label), h('td', {}, String(value)))),
      )));

    const rows = [];
    if (storage.mountpoint) rows.push(['挂载点', storage.mountpoint]);
    if (storage.image_path) rows.push(['镜像文件', storage.image_path]);
    if (admin.method) {
      rows.push([
        '初始化方式',
        admin.method === 'uac'
          ? 'Windows UAC 管理员确认'
          : (admin.method === 'sudo_password' ? 'sudo 密码（仅本次）' : '手动命令'),
      ]);
    }
    if (storageSetup?.setup?.command) {
      rows.push(['安装命令', storageSetup.setup.command]);
    }
    fill(storageHost, card('存储与安装',
      admin.note || storageSetup?.setup?.note
        || 'B 模式使用 Docker 命名卷；C 模式需要一次性管理员初始化。',
      rows.length
        ? table(['项目', '值'], rows.map(([label, value]) => h('tr', {},
          h('td', {}, label), h('td', {}, String(value)))))
        : empty('暂无存储路径信息')));

    renderAgents();
    fileBrowser.setRunning(box.state === 'running');
  }

  async function runAgentAction(action, label) {
    if (agentBusy) return;
    agentBusy = true;
    try {
      await action();
      ctx.toast(label, 'ok');
      await refresh();
    } catch (e) {
      ctx.toast(e.message, 'error');
    } finally {
      agentBusy = false;
    }
  }

  function renderAgents() {
    if (agentLoading) {
      fill(agentHost, card('Agent 模式', '',
        empty('正在读取 Agent 模式…')));
      return;
    }
    if (!agentStatus) {
      fill(agentHost, card('Agent 模式', '',
        empty('Agent 模式状态不可用；请先启动 Runtime 与容器。')));
      return;
    }
    const modes = agentStatus.agents || [];
    const rows = modes.map((item) => {
      const installed = !!item.installed;
      const active = !!item.active;
      const version = installed
        ? `已安装${item.version ? ` · ${item.version}` : ''}`
        : '未安装';
      const installButton = h('button', {
        class: 'btn btn-sm',
        disabled: agentBusy,
        onclick: () => runAgentAction(
          () => endpoints.installContainerAgent(item.id),
          `已安装 ${item.label}`,
        ),
      }, installed ? '重装' : '安装');
      const activateButton = h('button', {
        class: 'btn btn-sm btn-primary',
        disabled: agentBusy || !installed || active,
        onclick: () => runAgentAction(
          () => endpoints.activateContainerAgent(item.id),
          `已激活 ${item.label}`,
        ),
      }, active ? '当前使用' : '激活');
      const deactivateButton = h('button', {
        class: 'btn btn-sm',
        disabled: agentBusy || !active,
        onclick: () => runAgentAction(
          () => endpoints.deactivateContainerAgent(),
          '已停用容器 Agent',
        ),
      }, '停用');
      const deleteButton = h('button', {
        class: 'btn btn-sm btn-danger',
        disabled: agentBusy || !installed || active,
        onclick: () => {
          if (!globalThis.confirm(`卸载 ${item.label} 的容器运行时？不会删除 /workspace 文件。`)) return;
          runAgentAction(
            () => endpoints.deleteContainerAgent(item.id),
            `已卸载 ${item.label}`,
          );
        },
      }, '卸载');
      return h('tr', {},
        h('td', {},
          h('strong', {}, item.label),
          h('div', { class: 'field-help' }, item.description || ''),
        ),
        h('td', {}, badge(
          active ? '使用中' : (installed ? '已安装' : '未安装'),
          active ? 'ok' : (installed ? '' : 'warn'),
        )),
        h('td', {}, version),
        h('td', {}, item.dependencies?.length
          ? item.dependencies.join('、')
          : '内置回退'),
        h('td', {},
          h('div', { class: 'row row-wrap' },
            installButton, activateButton, deactivateButton, deleteButton)),
      );
    });

    const hostInfo = agentStatus.host || {};
    const executionSelect = h('select', {},
      h('option', { value: 'sandbox', selected: hostInfo.execution_mode !== 'host' },
        '沙箱联网（bubblewrap，推荐）'),
      h('option', { value: 'host', selected: hostInfo.execution_mode === 'host' },
        '直接控制整台电脑（高风险）'),
    );
    const networkInput = h('input', {
      type: 'checkbox',
      checked: hostInfo.sandbox_network !== false,
    });
    const saveHostButton = h('button', {
      class: 'btn btn-sm',
      disabled: agentBusy,
      onclick: () => runAgentAction(
        () => endpoints.saveContainerAgentHost({
          execution_mode: executionSelect.value,
          sandbox_network: !!networkInput.checked,
        }),
        '本机 Claude Code 执行方式已保存',
      ),
    }, '保存本机设置');

    fill(agentHost, card(
      'Agent 模式',
      '仅向 KarenBot 的 LLM 提供 Pi / DSH / Claude Code 的工具语义，不启动它们的 TUI/GUI/WebUI。'
        + '容器可安装多个模式，但同一时间只能激活一个；本机固定使用 Claude Code。',
      table(
        ['模式', '状态', '版本', '依赖', '操作'],
        rows,
      ),
      h('div', { class: 'field-help', style: { marginTop: '12px' } },
        '安装只写入 /workspace/.karen-agents，不会重建容器或删除 /workspace 文件。'
        + '原生工具不需要外部 CLI 或额外依赖。'
        + '建议在 设置 → 软件行为 → 工具 schema 档位 选择 agent，获得核心工具常加载 + '
        + 'ToolSearch 延迟加载。'),
      h('h3', { style: { marginTop: '18px' } }, '本机 Claude Code 执行方式'),
      h('div', { class: 'row row-wrap' },
        h('label', { class: 'field' },
          h('span', { class: 'field-label' }, '命令执行'),
          executionSelect,
        ),
        h('label', { class: 'field' },
          h('span', { class: 'field-label' }, '沙箱联网'),
          networkInput,
        ),
        h('div', { class: 'spacer' }),
        saveHostButton,
      ),
      h('p', { class: 'field-help' },
        '沙箱模式：只读系统目录 + workspace 可写，默认联网；host 模式：命令直接以当前用户控制整台电脑。'
        + 'host 模式风险很高，只在你明确需要时使用。'),
    ));
  }

  function renderProblems(info, storage, docker, mismatch) {
    const buttons = [];
    let message = '';
    if (mismatch) {
      message = storage.error
        || `存储镜像实际为 ${storage.marker_size_mb} MiB，与当前配置不一致。`;
      buttons.push(h('button', {
        class: 'btn btn-primary',
        onclick: () => adoptStorageSize(Number(storage.marker_size_mb)),
      }, `采用 ${storage.marker_size_mb} MiB`));
      buttons.push(h('button', {
        class: 'btn',
        onclick: () => ctx.navigate('settings', { section: 'container' }),
      }, '修改存储设置'));
      buttons.push(h('button', {
        class: 'btn',
        onclick: () => restartRuntime(),
      }, '重启 Runtime'));
    } else if (!docker.available) {
      message = docker.error || 'Docker 不可用；请先安装并启动 Docker Engine / Docker Desktop。';
    } else if (!info.image_present) {
      message = `镜像 ${info.image || ''} 缺失。点「一键准备 / 启动」会自动拉取；`
        + '如果 Docker Hub 不通，可在设置→容器填写「Docker 镜像加速前缀」。';
      buttons.push(h('button', {
        class: 'btn',
        onclick: () => ctx.navigate('settings', { section: 'container' }),
      }, '打开容器设置'));
    } else if (storage.mode === 'image_fixed' && !storage.ready) {
      message = storage.error || 'C 固定大小存储尚未初始化。';
      if (!mismatch) {
        buttons.push(h('button', {
          class: 'btn btn-primary',
          onclick: () => promptStorageSetup(ctx, { force: true, onDone: refresh }),
        }, storage.code === 'container_storage_not_mounted'
          ? '重新挂载 C 存储'
          : '初始化 C 存储'));
      }
    } else if (lastError) {
      const detail = lastError?.detail?.details || {};
      message = lastError.message || '容器准备失败';
      if (detail.output_tail) message += `\n${detail.output_tail}`;
      if (!info.image_present) {
        buttons.push(h('button', {
          class: 'btn',
          onclick: () => ctx.navigate('settings', { section: 'container' }),
        }, '配置镜像加速'));
      }
    } else if (info.config_warning) {
      message = info.config_warning.message
        || '容器创建后的设置发生变化；当前继续使用现有容器。';
      buttons.push(h('button', {
        class: 'btn',
        onclick: () => ctx.navigate('settings', { section: 'container' }),
      }, '查看容器设置'));
    }
    if (!message) return null;
    const warningOnly = !lastError && !!info.config_warning;
    const body = [
      h('p', { style: { whiteSpace: 'pre-wrap' } }, message),
      buttons.length ? h('div', { class: 'row row-wrap' }, ...buttons) : null,
    ];
    return card(
      warningOnly ? '配置提示' : '需要处理',
      warningOnly
        ? '当前容器可以继续使用；下面的设置只影响显式重建。'
        : '先修复下面这一项，再点「一键准备 / 启动」。',
      ...body,
    );
  }

  async function restartRuntime() {
    if (!globalThis.confirm('重启 Runtime？正在运行的请求会被中断，通常需要几秒到一分钟。')) {
      return;
    }
    try {
      await endpoints.restart();
      ctx.toast('已请求重启 Runtime，请稍候刷新', 'ok');
      setTimeout(() => refresh(), 5000);
    } catch (e) {
      ctx.toast(`重启失败：${e.message}`, 'error');
    }
  }

  async function adoptStorageSize(size) {
    if (!Number.isFinite(size) || size <= 0) return;
    if (!globalThis.confirm(
      `把存储大小改为 ${size} MiB？\n\n` +
      '这是已有镜像的实际大小；修改后需要重启 Runtime 才能生效。'
    )) return;
    try {
      await endpoints.patchSetting('features.container.workspace_size_mb', size);
      lastError = null;
      ctx.toast(`已采用 ${size} MiB；请重启 Runtime 生效`, 'ok');
      await refresh();
    } catch (e) {
      ctx.toast(`修改存储大小失败：${e.message}`, 'error');
    }
  }

  async function runTest() {
    testButton.disabled = true;
    testButton.textContent = '准备中…';
    lastError = null;
    ctx.toast('正在准备容器；首次可能需要下载镜像，请稍候', '');
    try {
      const result = await endpoints.containerTest();
      if (!result.ok) {
        lastError = { message: result.result?.error || '容器测试未通过', detail: {} };
      }
      ctx.toast(result.ok ? '容器已启动并通过测试' : '容器测试未通过', result.ok ? 'ok' : 'error');
      await refresh();
    } catch (e) {
      lastError = e;
      await refresh();
      ctx.toast(`容器准备失败：${e.message}`, 'error');
    } finally {
      testButton.disabled = false;
      testButton.textContent = '一键准备 / 启动';
    }
  }

  async function resetContainer() {
    if (!globalThis.confirm('只重建容器，不删除持久 workspace。确定继续？')) return;
    resetButton.disabled = true;
    try {
      await endpoints.containerReset();
      fileBrowser.reset();
      ctx.toast('容器已重建', 'ok');
      await refresh();
    } catch (e) {
      ctx.toast(`重建失败：${e.message}`, 'error');
    } finally {
      resetButton.disabled = false;
    }
  }

  await refresh();
  return { destroy: () => { destroyed = true; } };
}

function metric(label, value, tone) {
  return h('div', { class: 'card' },
    h('div', { class: 'field-label' }, label),
    h('div', { class: 'stat-value' }, badge(value, tone)));
}
