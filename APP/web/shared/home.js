/*
 * Home button component.
 *
 * Self-contained: adds a "GWF" button to the top left of the page that always links
 * to the home page. Styles live in a shadow root, so page CSS can't break it.
 * Pages should leave about 72px free at the top for it.
 */
(() => {
  const STYLE = `
    :host { all: initial; }
    a {
      position: fixed; top: 16px; left: 16px; z-index: 2147483000;
      display: inline-flex; align-items: center; justify-content: center;
      height: 40px; padding: 0 14px;
      background: #4a5cff; color: #fff;
      border-radius: 8px;
      font: 700 16px/1 system-ui, sans-serif; letter-spacing: 0.06em;
      text-decoration: none;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }
    a:hover { background: #3343d6; }
    a:focus-visible { outline: 3px solid #a9b3ff; outline-offset: 2px; }
  `;

  class AppHomeElement extends HTMLElement {
    connectedCallback() {
      if (this.shadowRoot) return;
      this.attachShadow({ mode: "open" }).innerHTML = `
        <style>${STYLE}</style>
        <a href="/" title="All games" aria-label="GWF home">GWF</a>`;
    }
  }

  customElements.define("app-home", AppHomeElement);
  if (!document.querySelector("app-home")) {
    document.body.append(document.createElement("app-home"));
  }
})();
