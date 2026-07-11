/** Mobile sidebar drawer + layout resize hook for graph viewers. */

const MOBILE_MQ = '(max-width: 899px)';

function notifyLayoutChange(onLayoutChange) {
  window.dispatchEvent(new Event('resize'));
  onLayoutChange?.();
}

export function initViewerSidebar(options = {}) {
  const menuBtn = document.getElementById('menu-btn');
  const backdrop = document.getElementById('sidebar-backdrop');
  const aside = document.getElementById('viewer-sidebar');
  if (!menuBtn || !backdrop || !aside) return null;

  const mq = window.matchMedia(MOBILE_MQ);

  function isMobile() {
    return mq.matches;
  }

  function open() {
    if (!isMobile()) return;
    document.body.classList.add('sidebar-open');
    menuBtn.setAttribute('aria-expanded', 'true');
    backdrop.setAttribute('aria-hidden', 'false');
    notifyLayoutChange(options.onLayoutChange);
  }

  function close() {
    if (!document.body.classList.contains('sidebar-open')) return;
    document.body.classList.remove('sidebar-open');
    menuBtn.setAttribute('aria-expanded', 'false');
    backdrop.setAttribute('aria-hidden', 'true');
    notifyLayoutChange(options.onLayoutChange);
  }

  function toggle() {
    if (document.body.classList.contains('sidebar-open')) close();
    else open();
  }

  function closeIfMobile() {
    if (isMobile()) close();
  }

  menuBtn.addEventListener('click', toggle);
  backdrop.addEventListener('click', close);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') close();
  });

  mq.addEventListener('change', () => {
    if (!mq.matches) close();
    notifyLayoutChange(options.onLayoutChange);
  });

  return { open, close, toggle, closeIfMobile, isMobile };
}
