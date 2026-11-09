/*
 * Base page styles shared by the home page and every game page.
 *
 * Load it first and without `defer` (it's tiny), so the page never shows unstyled:
 *   <script src="/shared/theme.js"></script>
 *
 * The styles go at the start of <head> and every selector is wrapped in :where(), so they
 * have zero specificity: any rule in the page's own <style> wins. To restyle a game, set
 * the variables in the page, e.g.  :root { --gwf-bg: #efe8da; --gwf-accent: #5d6873; }
 *
 * Provides: box-sizing, [hidden], body, main (72px top padding for the fixed GWF and
 * settings buttons; set --gwf-main-width), h1, h2, h3, .muted, .small, .card/.panel, .row,
 * .spacer, buttons (default accent; .green, .red, .plain, .small) and number/text inputs
 * and selects (colored from --gwf-surface/--gwf-text, disabled ones from --gwf-bg/--gwf-muted, so
 * they stay readable on dark themes).
 */
(() => {
  const STYLE = `
    :root {
      --gwf-bg: #f4f4f8;
      --gwf-surface: #fff;
      --gwf-line: #e4e4ec;
      --gwf-text: #222;
      --gwf-muted: #666;
      --gwf-accent: #4a5cff;
      --gwf-accent-hover: #3343d6;
      --gwf-soft: #eef0ff;
      --gwf-soft-hover: #dfe3ff;
      --gwf-green: #1a8a4a;
      --gwf-green-hover: #146e3b;
      --gwf-red: #e5484d;
      --gwf-red-hover: #c93a3f;
      --gwf-input-line: #c8c8d4;
      --gwf-radius: 10px;
      --gwf-main-width: 900px;
    }
    :where(*) { box-sizing: border-box; }
    :where([hidden]) { display: none !important; }
    :where(body) { margin: 0; font-family: system-ui, sans-serif; background: var(--gwf-bg); color: var(--gwf-text); }
    :where(main) { max-width: var(--gwf-main-width); margin: 0 auto; padding: 72px 16px 80px; }
    :where(h1) { margin: 16px 0 4px; }
    :where(h2) { font-size: 1.05rem; margin: 0 0 10px; }
    :where(h3) { font-size: 0.95rem; margin: 0 0 8px; }
    :where(.muted) { color: var(--gwf-muted); }
    :where(.small) { font-size: 0.85rem; }
    :where(.card, .panel) {
      background: var(--gwf-surface); border: 1px solid var(--gwf-line);
      border-radius: var(--gwf-radius); padding: 16px; margin-bottom: 16px;
    }
    :where(.row) { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    :where(.spacer) { flex: 1; }

    :where(button) {
      font: inherit; padding: 8px 16px; border: none; border-radius: 6px;
      cursor: pointer; color: #fff; background: var(--gwf-accent);
    }
    :where(button:hover:not(:disabled)) { background: var(--gwf-accent-hover); }
    :where(button:disabled) { opacity: 0.45; cursor: default; }
    :where(button.green) { background: var(--gwf-green); }
    :where(button.green:hover:not(:disabled)) { background: var(--gwf-green-hover); }
    :where(button.red) { background: var(--gwf-red); }
    :where(button.red:hover:not(:disabled)) { background: var(--gwf-red-hover); }
    :where(button.plain) { background: var(--gwf-soft); color: var(--gwf-accent); }
    :where(button.plain:hover:not(:disabled)) { background: var(--gwf-soft-hover); }
    :where(button.small) { padding: 4px 10px; font-size: 0.8rem; }

    :where(input[type="number"], input[type="text"], select) {
      font: inherit; padding: 6px 8px; border: 1px solid var(--gwf-input-line);
      border-radius: 6px; background: var(--gwf-surface); color: var(--gwf-text);
    }
    :where(input[type="number"]) { width: 72px; }
    :where(input:disabled, select:disabled) { background: var(--gwf-bg); color: var(--gwf-muted); }
  `;

  const style = document.createElement("style");
  style.dataset.gwf = "theme";
  style.textContent = STYLE;
  document.head.prepend(style);
})();
