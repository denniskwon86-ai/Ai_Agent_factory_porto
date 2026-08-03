(() => {
  document.querySelectorAll('[data-atlas-open]').forEach(button => button.addEventListener('click', () => document.querySelector('.atlas-drawer')?.classList.add('open')));
  document.querySelectorAll('[data-atlas-close]').forEach(button => button.addEventListener('click', () => document.querySelector('.atlas-drawer')?.classList.remove('open')));
  document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => {
    const group = button.closest('[data-tabs]');
    if (!group) return;
    group.querySelectorAll('[data-tab]').forEach(item => item.classList.remove('active'));
    button.classList.add('active');
    const target = button.dataset.tab;
    document.querySelectorAll(`[data-tab-panel]`).forEach(panel => panel.toggleAttribute('hidden', panel.getAttribute('data-tab-panel') !== target));
  }));
})();
