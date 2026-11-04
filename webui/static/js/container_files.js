// 受控容器页的统一只读文件管理器。
//
// 「本机工作区」读取 AppPaths.WORKSPACE_DIR；「容器工作区」只读取容器
// /workspace（数据目录下的 container/workspace）。两个目录互相独立。
// 目录列表短期缓存以加快来回切换；图片直接走 raw 接口，文本走有界预览。

import { h, fill, card, empty, table, modal, debounce } from './dom.js';
import { icon } from './icons.js';
import { endpoints } from './api.js';

const MODES = {
  host: {
    root: '/',
    rootLabel: '本机工作区',
    pathPlaceholder: '/',
    description: '本机 AI 工作区',
  },
  container: {
    root: '/workspace',
    rootLabel: '容器工作区',
    pathPlaceholder: '/workspace',
    description: '容器 /workspace',
  },
};

const TYPE_TEXT = {
  dir: '文件夹',
  file: '文件',
  symlink: '符号链接',
  other: '其他',
};

const IMAGE_EXT = /\.(png|jpe?g|gif|webp|bmp)$/i;
const CACHE_TTL_MS = 15000;

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

function isImageEntry(entry) {
  return entry.type === 'file' && IMAGE_EXT.test(String(entry.name || ''));
}

export function createContainerFileBrowser(ctx) {
  let mode = 'host';
  let loading = false;
  let containerRunning = null;
  let seq = 0;
  let destroyed = false;
  const filters = { host: '', container: '' };
  const states = {
    host: { currentPath: MODES.host.root, data: null, error: '', loaded: false },
    container: {
      currentPath: MODES.container.root,
      data: null,
      error: '',
      loaded: false,
    },
  };
  const cache = new Map();

  const hostModeBtn = h('button', {
    class: 'btn btn-sm',
    title: '本机 AI 工作区（模型文件工具使用的目录）',
  }, icon('folder', { size: 14 }), '本机工作区');
  const containerModeBtn = h('button', {
    class: 'btn btn-sm',
    title: '容器 /workspace（Docker 持久工作区）',
  }, icon('container', { size: 14 }), '容器工作区');
  const pathInput = h('input', {
    value: states.host.currentPath,
    placeholder: MODES.host.pathPlaceholder,
    title: '输入路径后按 Enter 或点「打开路径」',
    autocomplete: 'off',
    style: { minWidth: '260px' },
  });
  const filterInput = h('input', {
    placeholder: '筛选当前目录',
    title: '只筛选当前目录中已加载的条目',
    autocomplete: 'off',
    style: { minWidth: '180px' },
  });
  const upBtn = h('button', { class: 'btn btn-sm', title: '回到上一级目录' },
    icon('arrow-up', { size: 14 }), '上级');
  const openBtn = h('button', { class: 'btn btn-sm', title: '打开输入框中的路径' }, '打开路径');
  const refreshBtn = h('button', {
    class: 'btn btn-sm',
    title: '刷新当前目录（绕过 15 秒缓存）',
  }, icon('refresh', { size: 14 }), '刷新');
  const breadcrumbHost = h('div', { class: 'row row-wrap', style: { gap: '4px' } });
  const statusHost = h('p', { class: 'field-help' });
  const listHost = h('div', {});

  const root = card(
    '文件管理',
    '只读浏览两个互相独立的工作区：本机 AI 工作区（AppPaths.WORKSPACE_DIR）和容器 /workspace（container/workspace）。支持目录导航、文本预览和常见图片打开；符号链接不跟随。',
    h('div', { class: 'row row-wrap', style: { marginBottom: '10px' } },
      hostModeBtn,
      containerModeBtn,
      h('span', { class: 'field-help' }, '本机工作区是模型文件工具使用的目录；容器工作区是 Docker 挂载存储。'),
    ),
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

  function state() {
    return states[mode];
  }

  function rootForMode() {
    return MODES[mode].root;
  }

  function normalizeInput(path) {
    let text = String(path || '').trim();
    if (!text) return rootForMode();
    if (mode === 'host') {
      if (!text.startsWith('/')) text = `/${text}`;
      return text;
    }
    if (!text.startsWith('/')) text = `/workspace/${text}`;
    return text;
  }

  function filteredEntries() {
    const entries = state().data?.entries || [];
    const needle = filters[mode].trim().toLocaleLowerCase();
    if (!needle) return entries;
    return entries.filter((entry) =>
      String(entry.name || '').toLocaleLowerCase().includes(needle));
  }

  function renderModeButtons() {
    const host = mode === 'host';
    hostModeBtn.classList.toggle('btn-primary', host);
    containerModeBtn.classList.toggle('btn-primary', !host);
  }

  function renderBreadcrumb() {
    const rootPath = rootForMode();
    const currentPath = state().currentPath;
    let parts = [];
    if (mode === 'host') {
      parts = currentPath.replace(/^\/+|\/+$/g, '').split('/').filter(Boolean);
    } else if (currentPath.startsWith('/workspace/')) {
      parts = currentPath.slice('/workspace/'.length).split('/').filter(Boolean);
    }
    const nodes = [
      h('button', {
        class: 'btn btn-sm',
        title: mode === 'host'
          ? '回到本机工作区根目录'
          : '回到容器 /workspace 根目录',
        onclick: () => load(rootPath, { force: true }),
      }, mode === 'host' ? icon('folder', { size: 14 }) : icon('container', { size: 14 }),
      MODES[mode].rootLabel),
    ];
    let accumulated = rootPath;
    for (const part of parts) {
      accumulated += `/${part}`;
      const target = accumulated;
      nodes.push(icon('chevron-right', { size: 12 }));
      nodes.push(h('button', {
        class: 'btn btn-sm',
        title: `打开 ${target}`,
        onclick: () => load(target),
      }, part));
    }
    fill(breadcrumbHost, ...nodes);
  }

  function renderStatus() {
    const current = state();
    if (loading) {
      statusHost.textContent = `正在读取 ${current.currentPath}…`;
      return;
    }
    if (current.error) {
      statusHost.textContent = `读取失败：${current.error}`;
      return;
    }
    if (!current.loaded) {
      statusHost.textContent = mode === 'container' && containerRunning === false
        ? '容器未运行；点「刷新」会尝试启动容器并读取 /workspace。'
        : '正在等待目录列表…';
      return;
    }
    const shown = filteredEntries().length;
    const total = current.data?.count ?? 0;
    const suffix = filters[mode]
      ? `（筛选后 ${shown}/${total}）`
      : '';
    const rootText = mode === 'host'
      ? (current.data?.root ? `根目录：${current.data.root} · ` : '')
      : '容器 /workspace · ';
    statusHost.textContent = `${rootText}${total} 项${suffix}`
      + (current.data?.truncated
        ? `；目录超过 ${current.data.max_entries || 1000} 项，仅显示部分内容`
        : '');
  }

  function renderList() {
    const current = state();
    if (loading) {
      fill(listHost, empty('正在读取目录…'));
      return;
    }
    if (current.error) {
      fill(listHost, empty(`无法读取目录：${current.error}`, {
        subtitle: mode === 'container'
          ? '确认 Docker 容器和 C 存储已启动；也可以点「刷新」重试。'
          : '确认本机工作区目录存在；也可以点「刷新」重试。',
        iconName: 'folder',
      }));
      return;
    }
    if (!current.loaded) {
      fill(listHost, empty('尚未加载文件列表', { iconName: 'folder' }));
      return;
    }
    const entries = filteredEntries();
    if (!entries.length) {
      fill(listHost, empty(filters[mode] ? '当前目录没有匹配项' : '目录为空', {
        subtitle: filters[mode]
          ? '换一个筛选词试试。'
          : (mode === 'host'
            ? '本机 AI 工作区当前没有文件。'
            : '容器工作区是持久目录；本机文件请切到「本机工作区」。'),
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
            }, isImageEntry(entry) ? '查看图片' : '查看')
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
    const current = state();
    pathInput.value = current.currentPath;
    pathInput.placeholder = MODES[mode].pathPlaceholder;
    upBtn.disabled = !current.currentPath
      || current.currentPath === rootForMode()
      || loading;
    refreshBtn.disabled = loading;
    openBtn.disabled = loading;
    renderModeButtons();
    renderBreadcrumb();
    renderStatus();
    renderList();
  }

  function cacheKey(path) {
    return `${mode}:${path}`;
  }

  async function load(path = state().currentPath, { force = false } = {}) {
    const target = normalizeInput(path);
    const request = ++seq;
    const current = state();
    current.currentPath = target;
    current.error = '';
    const hit = cache.get(cacheKey(target));
    if (hit && !force && Date.now() - hit.at < CACHE_TTL_MS) {
      current.data = hit.data;
      current.loaded = true;
      loading = false;
      render();
      return;
    }
    loading = true;
    render();
    try {
      const result = mode === 'host'
        ? await endpoints.workspaceFiles(target)
        : await endpoints.containerFiles(target);
      if (destroyed || request !== seq) return;
      current.data = result;
      current.currentPath = result.path || target;
      current.loaded = true;
      cache.set(cacheKey(current.currentPath), { at: Date.now(), data: result });
      if (mode === 'container') containerRunning = true;
    } catch (e) {
      if (destroyed || request !== seq) return;
      current.data = null;
      current.loaded = false;
      current.error = e.message;
      if (mode === 'container') containerRunning = false;
    } finally {
      if (!destroyed && request === seq) {
        loading = false;
        render();
      }
    }
  }

  function openImage(entry) {
    const imageUrl = mode === 'host'
      ? endpoints.workspaceFileRawUrl(entry.path)
      : endpoints.containerFileRawUrl(entry.path);
    const img = h('img', {
      src: imageUrl,
      alt: entry.name,
      style: {
        display: 'block',
        maxWidth: '100%',
        maxHeight: '65vh',
        margin: '0 auto',
        objectFit: 'contain',
      },
    });
    const failed = h('p', {
      class: 'field-help',
      style: { display: 'none' },
    }, '图片无法显示；文件可能不是受支持的 PNG/JPEG/GIF/WebP/BMP，或容器尚未就绪。');
    img.onerror = () => {
      img.style.display = 'none';
      failed.style.display = '';
    };
    const body = h('div', {},
      h('p', { class: 'field-help mono' }, entry.path),
      h('p', { class: 'field-help' },
        `${formatBytes(entry.size)} · ${formatMtime(entry.mtime)}`
        + (entry.mode ? ` · ${entry.mode}` : '')),
      img,
      failed,
    );
    const view = modal({
      title: entry.name,
      subtitle: mode === 'host' ? '本机工作区图片预览' : '容器工作区图片预览',
      wide: true,
      body,
      footer: h('div', { class: 'row' },
        h('div', { class: 'spacer' }),
        h('button', { class: 'btn', onclick: () => view.close() }, '关闭'),
      ),
    });
    document.body.append(view.el);
  }

  async function openFile(entry) {
    if (isImageEntry(entry)) {
      openImage(entry);
      return;
    }
    try {
      const result = mode === 'host'
        ? await endpoints.workspaceFileContent(entry.path)
        : await endpoints.containerFileContent(entry.path);
      const body = h('div', {},
        h('p', { class: 'field-help mono' }, result.path),
        h('p', { class: 'field-help' },
          `${formatBytes(result.size)} · ${formatMtime(result.mtime)}`
          + (result.mode ? ` · ${result.mode}` : '')),
        result.binary
          ? empty('这是二进制文件，无法以文本方式预览', {
            subtitle: '图片文件会自动按图片打开。',
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
        subtitle: mode === 'host' ? '本机工作区文件预览' : '容器工作区文件预览',
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

  function switchMode(next) {
    if (mode === next) return;
    filters[mode] = filterInput.value;
    mode = next;
    filterInput.value = filters[mode];
    render();
    load(state().currentPath);
  }

  hostModeBtn.onclick = () => switchMode('host');
  containerModeBtn.onclick = () => switchMode('container');
  upBtn.onclick = () => {
    const current = state();
    if (!current.currentPath || current.currentPath === rootForMode()) return;
    load(current.data?.parent || rootForMode());
  };
  openBtn.onclick = () => load(pathInput.value);
  refreshBtn.onclick = () => load(state().currentPath, { force: true });
  pathInput.onkeydown = (event) => {
    if (event.key === 'Enter') load(pathInput.value);
  };
  filterInput.oninput = debounce(() => {
    filters[mode] = filterInput.value;
    renderStatus();
    renderList();
  }, 120);

  function setRunning(value) {
    containerRunning = Boolean(value);
    if (mode === 'container') renderStatus();
  }

  function reset() {
    seq += 1;
    cache.clear();
    for (const key of Object.keys(states)) {
      states[key] = {
        currentPath: MODES[key].root,
        data: null,
        error: '',
        loaded: false,
      };
      filters[key] = '';
    }
    filterInput.value = '';
    loading = false;
    render();
    load(state().currentPath, { force: true });
  }

  render();
  load(states.host.currentPath);
  return {
    el: root,
    load,
    reset,
    setRunning,
    get loaded() { return state().loaded; },
    get path() { return state().currentPath; },
    destroy() {
      destroyed = true;
      seq += 1;
    },
  };
}
