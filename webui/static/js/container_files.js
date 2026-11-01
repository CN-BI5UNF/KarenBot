// 受控容器的文件管理器。
//
// 只浏览 /workspace；后端返回结构化目录项，文件内容只做有界文本预览。
// 符号链接不会跟随，二进制文件不会把字节送回浏览器。

import { h, fill, card, empty, table, modal, debounce } from './dom.js';
import { icon } from './icons.js';
import { endpoints } from './api.js';

const ROOT = '/workspace';

const TYPE_TEXT = {
  dir: '文件夹',
  file: '文件',
  symlink: '符号链接',
  other: '其他',
};

function formatBytes(value) {
  const num = Math.max(0, Number(value) || 0);
  if (num >= 1024 ** 3) return `${(num / 1024 ** 3).toFixed(2)} GiB`;
  if (num >= 1024 ** 2) return `${(num / 1024 ** 2).toFixed(1)} MiB`;
  if (num >= 1024) return `${(num / 1024).toFixed(1)} KiB`;
  return `${num} B`;
}

function formatMtime(value) {
  const seconds = Number(value) || 0;
  if (!seconds) return '—';
  const date = new Date(seconds * 1000);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('zh-CN', { hour12: false });
}

function typeIcon(type) {
  return icon(type === 'dir' ? 'folder' : 'file', { size: 16 });
}

export function createContainerFileBrowser(ctx) {
  let currentPath = ROOT;
  let data = null;
  let error = '';
  let filter = '';
  let loading = false;
  let loaded = false;
  let running = false;
  let seq = 0;
  let destroyed = false;

  const pathInput = h('input', {
    value: ROOT,
    placeholder: '/workspace',
    autocomplete: 'off',
    style: { minWidth: '260px' },
  });
  const filterInput = h('input', {
    placeholder: '筛选当前目录',
    autocomplete: 'off',
    style: { minWidth: '180px' },
  });
  const upBtn = h('button', { class: 'btn btn-sm', title: '上一级' },
    icon('arrow-up', { size: 14 }), '上级');
  const openBtn = h('button', { class: 'btn btn-sm' }, '打开路径');
  const refreshBtn = h('button', { class: 'btn btn-sm' }, icon('refresh', { size: 14 }), '刷新');
  const breadcrumbHost = h('div', { class: 'row row-wrap', style: { gap: '4px' } });
  const statusHost = h('p', { class: 'field-help' });
  const listHost = h('div', {});

  const root = card(
    '文件管理',
    '浏览容器 /workspace；仅预览文本文件，不跟随符号链接。二进制文件只显示元数据。',
    h('div', { class: 'row row-wrap' },
      upBtn,
      h('div', { class: 'field' },
        h('span', { class: 'field-label' }, '路径'),
        pathInput),
      openBtn,
      refreshBtn,
      h('div', { class: 'spacer' }),
      h('div', { class: 'field' },
        h('span', { class: 'field-label' }, '筛选'),
        filterInput),
    ),
    breadcrumbHost,
    statusHost,
    listHost,
  );

  function renderBreadcrumb() {
    const rest = currentPath.startsWith(`${ROOT}/`)
      ? currentPath.slice(ROOT.length + 1)
      : '';
    const parts = rest.split('/').filter(Boolean);
    const nodes = [
      h('button', {
        class: 'btn btn-sm',
        onclick: () => load(ROOT),
      }, icon('container', { size: 14 }), 'workspace'),
    ];
    let accumulated = ROOT;
    for (const part of parts) {
      accumulated += `/${part}`;
      const target = accumulated;
      nodes.push(icon('chevron-right', { size: 12 }));
      nodes.push(h('button', {
        class: 'btn btn-sm',
        onclick: () => load(target),
      }, part));
    }
    fill(breadcrumbHost, ...nodes);
  }

  function renderStatus() {
    if (loading) {
      statusHost.textContent = `正在读取 ${currentPath}…`;
      return;
    }
    if (error) {
      statusHost.textContent = `读取失败：${error}`;
      return;
    }
    if (!loaded) {
      statusHost.textContent = running
        ? '正在等待目录列表…'
        : '容器未运行；点「刷新」会尝试启动容器并读取 /workspace。';
      return;
    }
    const shown = filteredEntries().length;
    const total = data?.count ?? 0;
    const suffix = filter ? `（筛选后 ${shown}/${total}）` : '';
    statusHost.textContent = `${total} 项${suffix}`
      + (data?.truncated ? `；目录超过 ${data.max_entries || 1000} 项，仅显示部分内容` : '');
  }

  function filteredEntries() {
    const entries = data?.entries || [];
    const needle = filter.trim().toLocaleLowerCase();
    if (!needle) return entries;
    return entries.filter((entry) =>
      String(entry.name || '').toLocaleLowerCase().includes(needle));
  }

  function renderList() {
    if (loading) {
      fill(listHost, empty('正在读取目录…'));
      return;
    }
    if (error) {
      fill(listHost, empty(`无法读取目录：${error}`, {
        subtitle: '确认容器已启动；也可以点「刷新」重试。',
        iconName: 'folder',
      }));
      return;
    }
    if (!loaded) {
      fill(listHost, empty('尚未加载文件列表', {
        subtitle: '容器运行后会自动加载；也可以点「刷新」。',
        iconName: 'folder',
      }));
      return;
    }
    const entries = filteredEntries();
    if (!entries.length) {
      fill(listHost, empty(filter ? '当前目录没有匹配项' : '目录为空', {
        iconName: 'folder',
      }));
      return;
    }
    fill(listHost, table(
      ['名称', '类型', '大小', '修改时间', '权限', '操作'],
      entries.map((entry) => {
        const isDir = entry.type === 'dir';
        const isFile = entry.type === 'file';
        const action = isDir
          ? h('button', {
            class: 'btn btn-sm',
            onclick: () => load(entry.path),
          }, '打开')
          : isFile
            ? h('button', {
              class: 'btn btn-sm',
              onclick: () => openFile(entry),
            }, '查看')
            : h('span', { class: 'field-help' },
              entry.type === 'symlink' ? '不跟随' : '—');
        return h('tr', {},
          h('td', {},
            h('div', { class: 'row', style: { gap: '8px' } },
              typeIcon(entry.type),
              h('strong', {}, entry.name),
              entry.type === 'symlink' && entry.target
                ? h('span', { class: 'field-help mono' }, `→ ${entry.target}`)
                : null,
            ),
          ),
          h('td', { class: 'field-help' }, entry.type === 'symlink'
            ? '符号链接' : (TYPE_TEXT[entry.type] || entry.type)),
          h('td', {}, isDir ? '—' : formatBytes(entry.size)),
          h('td', { class: 'field-help' }, formatMtime(entry.mtime)),
          h('td', { class: 'mono field-help' }, entry.mode || '—'),
          h('td', {}, action),
        );
      }),
    ));
  }

  function render() {
    if (destroyed) return;
    pathInput.value = currentPath;
    upBtn.disabled = !currentPath || currentPath === ROOT || loading;
    refreshBtn.disabled = loading;
    openBtn.disabled = loading;
    renderBreadcrumb();
    renderStatus();
    renderList();
  }

  async function load(path = currentPath) {
    const target = String(path || '').trim() || ROOT;
    const request = ++seq;
    currentPath = target;
    error = '';
    loading = true;
    render();
    try {
      const result = await endpoints.containerFiles(target);
      if (destroyed || request !== seq) return;
      data = result;
      currentPath = result.path || target;
      loaded = true;
    } catch (e) {
      if (destroyed || request !== seq) return;
      data = null;
      loaded = false;
      error = e.message;
    } finally {
      if (!destroyed && request === seq) {
        loading = false;
        render();
      }
    }
  }

  async function openFile(entry) {
    try {
      const result = await endpoints.containerFileContent(entry.path);
      const body = h('div', {},
        h('p', { class: 'field-help mono' }, result.path),
        h('p', { class: 'field-help' },
          `${formatBytes(result.size)} · ${formatMtime(result.mtime)}`
          + (result.mode ? ` · ${result.mode}` : '')),
        result.binary
          ? empty('这是二进制文件，无法以文本方式预览', {
            subtitle: '可以在容器页用「容器工具」执行命令处理。',
            iconName: 'file',
          })
          : h('pre', {
            class: 'draft-raw',
            style: { maxHeight: '55vh', overflow: 'auto' },
          }, result.content || '（空文件）'),
        result.truncated
          ? h('p', { class: 'field-help' },
            `文件较大，仅预览前 ${formatBytes(result.preview_bytes || 0)}。`)
          : null,
      );
      const view = modal({
        title: result.name || entry.name,
        subtitle: '容器文件预览',
        wide: true,
        body,
        footer: h('div', { class: 'row' },
          h('div', { class: 'spacer' }),
          h('button', { class: 'btn', onclick: () => view.close() }, '关闭'),
        ),
      });
      document.body.append(view.el);
    } catch (e) {
      ctx.toast(`读取文件失败：${e.message}`, 'error');
    }
  }

  upBtn.onclick = () => {
    if (!currentPath || currentPath === ROOT) return;
    const parent = data?.parent || ROOT;
    load(parent);
  };
  openBtn.onclick = () => load(pathInput.value);
  refreshBtn.onclick = () => load();
  pathInput.onkeydown = (event) => {
    if (event.key === 'Enter') load(pathInput.value);
  };
  filterInput.oninput = debounce(() => {
    filter = filterInput.value;
    renderStatus();
    renderList();
  }, 120);

  function setRunning(value) {
    running = Boolean(value);
    if (!running && !loading) {
      loaded = false;
      data = null;
      error = '';
    }
    renderStatus();
    renderList();
    if (running && !loaded && !loading) load();
  }

  function reset() {
    seq += 1;
    currentPath = ROOT;
    data = null;
    error = '';
    filter = '';
    filterInput.value = '';
    loaded = false;
    loading = false;
    render();
  }

  render();
  return {
    el: root,
    load,
    reset,
    setRunning,
    get loaded() { return loaded; },
    get path() { return currentPath; },
  };
}
