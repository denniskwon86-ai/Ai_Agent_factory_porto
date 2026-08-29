(() => {
  const PAGE_WIDTH_PX = 1440;
  const SIDE_GUTTER_PX = 24;

  function fitDocumentToViewport() {
    const available = Math.max(320, window.innerWidth - SIDE_GUTTER_PX);
    const scale = Math.min(1, available / PAGE_WIDTH_PX);
    document.documentElement.style.setProperty("--screen-scale", scale.toFixed(4));
  }

  fitDocumentToViewport();
  window.addEventListener("resize", fitDocumentToViewport, { passive: true });

  if (window.location.hash) {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const target = document.querySelector(window.location.hash);
        if (target) target.scrollIntoView({ block: "start" });
      });
    });
  }
})();
