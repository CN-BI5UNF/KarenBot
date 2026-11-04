// 统一悬停提示。
//
// 浏览器原生 title 提示出现的时机和样式由浏览器决定，延迟长、样式不可控。
// 这里把 title 升级成 data-tooltip，用同一个浮层显示；如果脚本没有加载，
// 原生 title 仍然可用，属于渐进增强。
//
// 提示只负责解释控件，不接收鼠标事件；键盘聚焦同样会显示。

const SHOW_DELAY_MS = 320;
const FOCUS_DELAY_MS = 80;
const VIEWPORT_MARGIN = 8;
const TARGET_GAP = 8;

let initialized = false;
let tooltipEl = null;
let activeTarget = null;
let showTimer = null;
let observer = null;

function ensureTooltip() {
  if (tooltipEl) return tooltipEl;
  tooltipEl = document.createElement('div');
  tooltipEl.className = 'app-tooltip';
  tooltipEl.setAttribute('role', 'tooltip');
  tooltipEl.setAttribute('aria-hidden', 'true');
  document.body.append(tooltipEl);
  return tooltipEl;
}

function tooltipText(target) {
  return String(target.getAttribute('data-tooltip') || '').trim();
}

function hideTooltip() {
  if (showTimer) {
    clearTimeout(showTimer);
    showTimer = null;
  }
  activeTarget = null;
  if (tooltipEl) {
    tooltipEl.classList.remove('visible');
    tooltipEl.setAttribute('aria-hidden', 'true');
  }
}

function placeTooltip(target) {
  const tip = tooltipEl;
  if (!tip) return;
  const targetRect = target.getBoundingClientRect();
  const tipRect = tip.getBoundingClientRect();
  const viewportWidth = document.documentElement.clientWidth;
  const viewportHeight = document.documentElement.clientHeight;

  let left = targetRect.left + targetRect.width / 2 - tipRect.width / 2;
  left = Math.max(
    VIEWPORT_MARGIN,
    Math.min(left, viewportWidth - tipRect.width - VIEWPORT_MARGIN),
  );

  let top = targetRect.top - tipRect.height - TARGET_GAP;
  let placement = 'top';
  if (top < VIEWPORT_MARGIN) {
    top = targetRect.bottom + TARGET_GAP;
    placement = 'bottom';
  }
  if (top + tipRect.height > viewportHeight - VIEWPORT_MARGIN) {
    top = Math.max(VIEWPORT_MARGIN, viewportHeight - tipRect.height - VIEWPORT_MARGIN);
  }

  tip.style.left = `${Math.round(left)}px`;
  tip.style.top = `${Math.round(top)}px`;
  tip.dataset.placement = placement;
}

function showTooltip(target) {
  showTimer = null;
  if (!target || !target.isConnected) return;
  const text = tooltipText(target);
  if (!text) return;
  const tip = ensureTooltip();
  if (activeTarget === target && tip.classList.contains('visible')) return;
  activeTarget = target;
  tip.textContent = text;
  tip.classList.add('visible');
  tip.setAttribute('aria-hidden', 'false');
  placeTooltip(target);
}

function scheduleTooltip(target, delay) {
  if (!target) return;
  if (activeTarget === target && tooltipEl?.classList.contains('visible')) return;
  if (showTimer) clearTimeout(showTimer);
  showTimer = setTimeout(() => showTooltip(target), delay);
}

function targetFromEvent(event) {
  const node = event.target instanceof Element ? event.target : null;
  return node ? node.closest('[data-tooltip]') : null;
}

function upgradeElement(element) {
  if (!(element instanceof Element)) return;
  const title = element.getAttribute('title');
  if (title === null) return;
  const text = title.trim();
  if (!text) {
    element.removeAttribute('title');
    if (activeTarget === element) hideTooltip();
    return;
  }
  element.setAttribute('data-tooltip', text);
  if (!element.hasAttribute('aria-label')) {
    element.setAttribute('aria-label', text);
  }
  element.removeAttribute('title');
  if (activeTarget === element) {
    const tip = ensureTooltip();
    tip.textContent = text;
    placeTooltip(element);
  }
}

function upgradeTree(root) {
  if (!(root instanceof Element) && !(root instanceof DocumentFragment)) return;
  if (root instanceof Element) upgradeElement(root);
  for (const element of root.querySelectorAll('[title]')) {
    upgradeElement(element);
  }
}

function onPointerOver(event) {
  const target = targetFromEvent(event);
  if (!target) return;
  if (event.relatedTarget instanceof Node && target.contains(event.relatedTarget)) return;
  scheduleTooltip(target, SHOW_DELAY_MS);
}

function onPointerOut(event) {
  const target = targetFromEvent(event);
  if (!target) return;
  if (event.relatedTarget instanceof Node && target.contains(event.relatedTarget)) return;
  if (activeTarget === target || showTimer) hideTooltip();
}

function onFocusIn(event) {
  const target = targetFromEvent(event);
  if (!target) return;
  scheduleTooltip(target, FOCUS_DELAY_MS);
}

function onFocusOut(event) {
  const target = targetFromEvent(event);
  if (!target) return;
  if (event.relatedTarget instanceof Node && target.contains(event.relatedTarget)) return;
  if (activeTarget === target || showTimer) hideTooltip();
}

export function initTooltips() {
  if (initialized) return;
  initialized = true;
  upgradeTree(document.body);

  observer = new MutationObserver((records) => {
    if (activeTarget && !activeTarget.isConnected) hideTooltip();
    for (const record of records) {
      if (record.type === 'attributes') {
        const target = record.target;
        if (target instanceof Element && target.hasAttribute('title')) {
          upgradeElement(target);
        }
        continue;
      }
      for (const node of record.addedNodes) {
        if (node instanceof Element) upgradeTree(node);
        else if (node instanceof DocumentFragment) upgradeTree(node);
      }
    }
  });
  observer.observe(document.body, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ['title'],
  });

  document.addEventListener('pointerover', onPointerOver, true);
  document.addEventListener('pointerout', onPointerOut, true);
  document.addEventListener('focusin', onFocusIn, true);
  document.addEventListener('focusout', onFocusOut, true);
  document.addEventListener('click', hideTooltip, true);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') hideTooltip();
  });
  window.addEventListener('scroll', hideTooltip, true);
  window.addEventListener('resize', () => {
    if (activeTarget && tooltipEl?.classList.contains('visible')) {
      placeTooltip(activeTarget);
    }
  });
}
