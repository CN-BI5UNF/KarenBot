// 人格页 —— 对应 ui/dashboard/personas_page.py。
// 列出 personas/ 下的人格目录，支持切换、导入 zip、导出 zip、删除。

import { h, fill, card, empty, modal } from '../dom.js';
import { icon } from '../icons.js';
import { endpoints } from '../api.js';
import {
  openPersonaCreator,
  openPersonaDirectEditor,
  openPersonaDuplicate,
  openPersonaRefine,
} from '../persona_dialogs.js';
import { openPersonaCleanup } from '../destructive_admin.js';

function formatBytes(value) {
  const num = Math.max(0, Number(value) || 0);
  if (num >= 1024 ** 2) return `${(num / 1024 ** 2).toFixed(1)} MiB`;
  if (num >= 1024) return `${(num / 1024).toFixed(1)} KiB`;
  return `${num} B`;
}

function openAppearance(ctx, persona, { onDone } = {}) {
  let images = [];
  let cover = persona.appearance || null;
  let activeId = cover?.id || '';
  let selectedFiles = [];
  let busy = false;

  const previewHost = h('div', {
    style: {
      minHeight: '220px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      border: '1px solid var(--border)',
      borderRadius: '10px',
      padding: '12px',
      marginBottom: '12px',
      overflow: 'hidden',
    },
  });
  const galleryHost = h('div', { class: 'row row-wrap', style: { gap: '10px' } });
  const metaHost = h('p', { class: 'field-help' });
  const status = h('p', { class: 'field-help' });
  const selectedLabel = h('span', { class: 'field-help' }, '未选择新图片');
  const fileInput = h('input', {
    type: 'file',
    accept: 'image/png,image/jpeg,image/gif,image/webp',
    multiple: true,
    style: { display: 'none' },
  });
  const chooseBtn = h('button', { class: 'btn' }, '选择图片（可多选）');
  const uploadBtn = h('button', { class: 'btn btn-primary', disabled: true }, '上传图片');
  const deleteAllBtn = h('button', { class: 'btn btn-danger' }, '删除全部形象');

  const dialog = modal({
    title: `「${persona.name}」的角色形象`,
    subtitle: '可以上传多张图片，并选择其中一张作为列表预览图。'
      + '图片会作为只读资料提供给当前人格，LLM 可以查看，也可以直接发送。',
    wide: true,
    body: h('div', {},
      previewHost,
      metaHost,
      h('div', { class: 'stat-label', style: { margin: '10px 0 8px' } }, '形象图库'),
      galleryHost,
      h('p', { class: 'field-help' },
        '上传的图片会保存到人格目录，随人格导出；每张会缩放到最长边 2048，单张上限 8 MiB。'),
      h('div', { class: 'row row-wrap', style: { marginTop: '12px' } },
        fileInput,
        chooseBtn,
        selectedLabel,
        h('div', { class: 'spacer' }),
        uploadBtn,
      ),
      status,
    ),
    footer: [],
  });
  const foot = dialog.el.querySelector('.modal-foot');
  fill(foot,
    h('button', { class: 'btn', onclick: () => dialog.close() }, '关闭'),
    h('div', { class: 'spacer' }),
    deleteAllBtn,
  );
  document.body.append(dialog.el);

  function currentImage() {
    return images.find((item) => item.id === activeId) || cover || images[0] || null;
  }

  function setStatus(text, kind = '') {
    status.textContent = text;
    status.style.color = kind === 'error' ? 'var(--error)'
      : kind === 'ok' ? 'var(--success)' : '';
  }

  function render() {
    cover = images.find((item) => item.cover) || images[0] || null;
    if (!activeId || !images.some((item) => item.id === activeId)) {
      activeId = cover?.id || '';
    }
    uploadBtn.disabled = busy || !selectedFiles.length;
    chooseBtn.disabled = busy;
    deleteAllBtn.disabled = busy || !images.length;
    if (!images.length) {
      fill(previewHost, empty('还没有角色形象', {
        subtitle: '选择一张或多张图片上传后，LLM 才能在知识库中看到这只角色。',
        iconName: 'image',
      }));
      fill(galleryHost);
      metaHost.textContent = '';
      return;
    }
    const active = currentImage();
    if (!active) return;
    const meta = [];
    if (active.width && active.height) meta.push(`${active.width}×${active.height}`);
    meta.push(formatBytes(active.size));
    if (active.cover) meta.push('列表预览图');
    fill(previewHost,
      h('img', {
        src: endpoints.personaAppearanceUrl(persona.name, active.sha256, active.id),
        alt: `${persona.name} 的角色形象`,
        style: {
          maxWidth: '100%',
          maxHeight: '45vh',
          objectFit: 'contain',
          borderRadius: '8px',
        },
      }),
    );
    fill(galleryHost, ...images.map((item) => {
      const selected = item.id === active.id;
      const tile = h('button', {
        class: 'btn',
        title: item.cover ? '当前列表预览图' : '查看这张图片',
        style: {
          padding: '4px',
          borderColor: selected ? 'var(--accent)' : 'var(--border)',
          position: 'relative',
        },
        onclick: () => {
          activeId = item.id;
          render();
        },
      },
        h('img', {
          src: endpoints.personaAppearanceUrl(persona.name, item.sha256, item.id),
          alt: '',
          style: {
            width: '104px',
            height: '104px',
            objectFit: 'cover',
            borderRadius: '6px',
            display: 'block',
          },
        }),
        item.cover
          ? h('span', {
            class: 'badge ok',
            style: { position: 'absolute', top: '7px', left: '7px' },
          }, '预览')
          : null,
      );
      return h('div', {
        style: {
          display: 'flex',
          flexDirection: 'column',
          gap: '5px',
          alignItems: 'stretch',
        },
      },
        tile,
        h('div', { class: 'row', style: { gap: '4px' } },
          item.cover ? null : h('button', {
            class: 'btn btn-sm',
            onclick: async () => {
              if (busy) return;
              busy = true;
              render();
              try {
                await endpoints.setPersonaAppearanceCover(persona.name, item.id);
                await loadGallery();
                setStatus('已设为列表预览图。', 'ok');
                await onDone?.();
              } catch (e) {
                setStatus(`设置预览失败：${e.message}`, 'error');
              } finally {
                busy = false;
                render();
              }
            },
          }, '设为预览'),
          h('button', {
            class: 'btn btn-sm btn-danger',
            onclick: async () => {
              if (busy) return;
              if (!globalThis.confirm('删除这张角色形象？')) return;
              busy = true;
              render();
              try {
                await endpoints.deletePersonaAppearanceImage(persona.name, item.id);
                if (activeId === item.id) activeId = '';
                await loadGallery();
                setStatus('已删除该形象。', 'ok');
                await onDone?.();
              } catch (e) {
                setStatus(`删除失败：${e.message}`, 'error');
              } finally {
                busy = false;
                render();
              }
            },
          }, '删除'),
        ),
      );
    }));
    metaHost.textContent = `当前显示：${meta.join(' · ')}；共 ${images.length} 张，预览图会作为人格列表缩略图。`;
  }

  async function loadGallery() {
    try {
      const data = await endpoints.personaAppearance(persona.name);
      images = data.images || [];
      cover = data.appearance || null;
    } catch (e) {
      if (e.status === 404) {
        images = [];
        cover = null;
      } else {
        throw e;
      }
    }
    render();
  }

  async function uploadFiles(files) {
    if (busy || !files.length) return;
    busy = true;
    uploadBtn.disabled = true;
    chooseBtn.disabled = true;
    let uploaded = 0;
    try {
      for (let index = 0; index < files.length; index += 1) {
        const file = files[index];
        setStatus(`正在上传 ${index + 1}/${files.length}：${file.name}`);
        const form = new FormData();
        form.append('file', file);
        const result = await endpoints.uploadPersonaAppearance(persona.name, form);
        if (result.appearance?.id) activeId = result.appearance.id;
        uploaded += 1;
      }
      selectedFiles = [];
      fileInput.value = '';
      selectedLabel.textContent = '未选择新图片';
      await loadGallery();
      setStatus(`已上传 ${uploaded} 张角色形象。`, 'ok');
      ctx.toast(`已上传 ${uploaded} 张角色形象`, 'ok');
      await onDone?.();
    } catch (e) {
      setStatus(`上传失败：${e.message}`, 'error');
      if (uploaded) {
        await loadGallery().catch(() => {});
        await onDone?.();
      }
    } finally {
      busy = false;
      render();
    }
  }

  chooseBtn.onclick = () => fileInput.click();
  fileInput.onchange = () => {
    selectedFiles = Array.from(fileInput.files || []);
    uploadBtn.disabled = !selectedFiles.length;
    selectedLabel.textContent = selectedFiles.length
      ? `已选择 ${selectedFiles.length} 张`
      : '未选择新图片';
    setStatus('');
  };
  uploadBtn.onclick = () => uploadFiles(selectedFiles);
  deleteAllBtn.onclick = async () => {
    if (busy || !images.length) return;
    if (!globalThis.confirm(`删除「${persona.name}」的全部 ${images.length} 张角色形象？`)) return;
    busy = true;
    render();
    try {
      await endpoints.deletePersonaAppearance(persona.name);
      images = [];
      cover = null;
      activeId = '';
      render();
      setStatus('已删除全部角色形象。', 'ok');
      await onDone?.();
    } catch (e) {
      setStatus(`删除失败：${e.message}`, 'error');
    } finally {
      busy = false;
      render();
    }
  };

  render();
  loadGallery().catch((e) => setStatus(`读取形象失败：${e.message}`, 'error'));
}

export async function render(container, ctx) {
  let personas = [];
  let active = '';
  let disposed = false;

  const listBox = h('div', {});

  async function load() {
    try {
      const data = await endpoints.personas();
      personas = data.personas || [];
      active = data.active || '';
      renderList();
    } catch (e) {
      fill(listBox, empty(`读取人格失败：${e.message}`));
    }
  }

  function renderList() {
    if (!personas.length) {
      fill(listBox, empty('personas/ 目录下没有找到任何人设'));
      return;
    }
    fill(listBox, h('table', { class: 'table' },
      h('thead', {}, h('tr', {},
        h('th', {}, '人格'), h('th', {}, '说明'), h('th', {}, '状态'), h('th', {}, '操作'))),
      h('tbody', {}, ...personas.map((p) =>
        h('tr', {},
          h('td', {},
            h('div', { class: 'row', style: { gap: '9px' } },
              p.appearance
                ? h('img', {
                  class: 'persona-thumb',
                  src: endpoints.personaAppearanceUrl(
                    p.name, p.appearance.sha256, p.appearance.id,
                  ),
                  alt: '',
                  title: p.appearance_count > 1
                    ? `角色形象预览（共 ${p.appearance_count} 张）`
                    : '角色形象预览',
                  loading: 'lazy',
                })
                : h('span', { class: 'persona-thumb persona-thumb-empty' },
                  icon('personas', { size: 18 })),
              h('strong', {}, p.name),
              p.appearance_count > 1
                ? h('span', { class: 'badge' }, `${p.appearance_count} 张`)
                : null,
            ),
          ),
          h('td', { class: 'field-help' }, p.description || '—'),
          h('td', {},
            p.active
              ? h('span', { class: 'badge ok' }, '当前使用')
              : (p.builtin ? h('span', { class: 'badge' }, '内置') : '')),
          h('td', {},
            h('div', { class: 'row row-wrap' },
              p.active ? null : h('button', {
                class: 'btn btn-sm',
                onclick: async () => {
                  try {
                    const result = await endpoints.activatePersona(p.name);
                    ctx.toast(result.message, 'ok');
                    await load();
                  } catch (e) {
                    ctx.toast(e.message, 'error');
                  }
                },
              }, '设为当前'),
              h('a', {
                class: 'btn btn-sm',
                href: `/api/personas/${encodeURIComponent(p.name)}/export`,
                download: `${p.name}.zip`,
              }, '导出'),
              h('button', {
                class: 'btn btn-sm',
                onclick: () => openAppearance(ctx, p, { onDone: load }),
              }, icon('image', { size: 14 }), '角色形象'),
              h('button', {
                class: 'btn btn-sm',
                onclick: async () => {
                  try {
                    const data = await endpoints.personaPrompt(p.name);
                    showSource(p.name, data);
                  } catch (e) {
                    ctx.toast(e.message, 'error');
                  }
                },
              }, '查看人设'),
              h('button', {
                class: 'btn btn-sm',
                title: '贴一句反馈，让 AI 出一版修改稿',
                onclick: () => openPersonaRefine(ctx, p.name, { onDone: load }),
              }, icon('edit', { size: 14 }), '修改'),
              h('button', {
                class: 'btn btn-sm',
                title: '直接编辑 PERSONA_PROMPT，不经过 AI',
                onclick: () => openPersonaDirectEditor(ctx, p.name, { onDone: load }),
              }, '直接编辑'),
              h('button', {
                class: 'btn btn-sm',
                title: '以它为模板建一个新人格',
                onclick: () => openPersonaDuplicate(ctx, p.name, { onDone: load }),
              }, '复制'),
              h('button', {
                class: 'btn btn-sm btn-danger',
                title: '删除聊天、记忆、RAG 和私有知识；保留人格定义',
                onclick: () => openPersonaCleanup(ctx, p.name, { onDone: load }),
              }, '清理运行数据'),
              (p.builtin || p.active) ? null : h('button', {
                class: 'btn btn-sm btn-danger',
                title: '只删除 personas/<name>/ 人格定义；不清理运行数据',
                onclick: async () => {
                  if (!confirm(`删除人格 ${p.name}？该目录会被整体删除，无法撤销。`)) return;
                  try {
                    await endpoints.deletePersona(p.name);
                    ctx.toast('已删除', 'ok');
                    await load();
                  } catch (e) {
                    ctx.toast(e.message, 'error');
                  }
                },
              }, '删除人格定义'),
            )),
        ),
      )),
    ));
  }

  function showSource(name, data) {
    const dialog = h('div', { class: 'gate' },
      h('div', { class: 'gate-card gate-card-wide' },
        h('div', { class: 'gate-brand' }, `${name} · persona_prompt.py`),
        h('p', { class: 'gate-hint mono' }, data.path),
        h('pre', {
          style: { maxHeight: '55vh', overflow: 'auto', background: 'var(--bg-primary)',
                   padding: '12px', borderRadius: '8px', margin: '0 0 16px' },
        }, data.source),
        h('button', {
          class: 'btn btn-primary btn-block',
          onclick: () => dialog.remove(),
        }, '关闭'),
      ),
    );
    document.body.append(dialog);
  }

  const fileInput = h('input', {
    type: 'file',
    accept: '.zip',
    style: { display: 'none' },
    onchange: async (event) => {
      const file = event.target.files[0];
      if (!file) return;
      const form = new FormData();
      form.append('file', file);
      try {
        const result = await endpoints.importPersona(form);
        ctx.toast(result.message, 'ok');
        await load();
      } catch (e) {
        ctx.toast(e.message, 'error');
      } finally {
        event.target.value = '';
      }
    },
  });

  fill(container,
    h('div', { class: 'page-head' },
      h('div', {},
        h('h1', { class: 'page-title' }, '人格'),
        h('p', { class: 'page-desc' },
          '每套人设是 personas/<名字>/ 下的一个目录。切换后需要重启 Runtime 生效；'
          + '「角色形象」支持多张图片，并以只读知识条目提供给当前人格；LLM 可以查看和发送。'),
      ),
      h('div', { class: 'row' },
        fileInput,
        h('button', {
          class: 'btn btn-primary',
          onclick: () => openPersonaCreator(ctx, { onDone: load }),
        }, icon('add', { size: 16 }), '新建人格'),
        h('button', {
          class: 'btn',
          onclick: () => openPersonaDirectEditor(ctx, null, { onDone: load }),
        }, '直接写提示词'),
        h('button', {
          class: 'btn',
          onclick: () => fileInput.click(),
        }, '导入 zip'),
        h('button', { class: 'btn', onclick: load }, '刷新'),
      ),
    ),
    card('', '', listBox),
  );

  await load();
  return { destroy() { disposed = true; void disposed; } };
}
