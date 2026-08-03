(() => {
  "use strict";

  const state = { dirty: false, running: false, message: "" };
  let pendingHref = "";

  function ensureDialog() {
    let dialog = document.querySelector(".afs-state-dialog");
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.className = "afs-state-dialog";
    dialog.innerHTML = `
      <header><small>WORKSPACE PROTECTION</small><h2>현재 작업을 두고 이동할까요?</h2></header>
      <p data-dialog-message>저장하지 않은 변경이 있습니다. 이동하면 현재 화면의 편집 내용이 사라질 수 있습니다.</p>
      <footer><button type="button" data-stay>계속 작업</button><button type="button" data-leave>이동</button></footer>`;
    document.body.appendChild(dialog);
    dialog.querySelector("[data-stay]").addEventListener("click", () => dialog.close());
    dialog.querySelector("[data-leave]").addEventListener("click", () => {
      state.dirty = false;
      state.running = false;
      const href = pendingHref;
      pendingHref = "";
      dialog.close();
      if (href) location.href = href;
    });
    return dialog;
  }

  function guardNavigation(event) {
    const link = event.target.closest("a[href]");
    if (!link || (!state.dirty && !state.running)) return;
    const target = new URL(link.href, location.href);
    const current = new URL(location.href);
    if (target.href === current.href || target.hash && target.pathname === current.pathname && target.hash === current.hash) return;
    event.preventDefault();
    pendingHref = target.href;
    const dialog = ensureDialog();
    const message = state.message || (state.running
      ? "현재 Sprint 또는 시뮬레이션이 진행 중입니다. 백그라운드 실행·일시정지 정책을 확인한 뒤 이동하세요."
      : "저장하지 않은 변경이 있습니다. 이동하면 현재 화면의 편집 내용이 사라질 수 있습니다.");
    dialog.querySelector("[data-dialog-message]").textContent = message;
    dialog.showModal();
  }

  window.AFSProductShell = {
    markDirty(message = "") { state.dirty = true; state.message = message; },
    markSaved() { state.dirty = false; state.message = ""; },
    markRunning(message = "") { state.running = true; state.message = message; },
    markStopped() { state.running = false; state.message = ""; },
    getState() { return { ...state }; }
  };

  document.addEventListener("click", guardNavigation, true);
  window.addEventListener("beforeunload", event => {
    if (!state.dirty && !state.running) return;
    event.preventDefault();
    event.returnValue = "";
  });
})();
