/*
 * Small DOM helpers for game pages. Load before game.js.
 *
 *   const { $, el, svg, debounce, setInput, listNames } = AppDom;
 *
 *   $(id)                          document.getElementById(id)
 *   el(tag, props, ...children)    createElement + Object.assign(props) + append(children).
 *                                  Strings become text nodes, so player names are safe.
 *                                  e.g. el("li", { className: "me" }, name, el("b", {}, "Host"))
 *   svg(tag, attrs, ...children)   an SVG element (createElementNS): attrs are set as attributes
 *                                  (skipped if null/undefined/false); strings become text nodes.
 *                                  e.g. svg("circle", { cx: 10, cy: 10, r: 4, class: "dot" })
 *   debounce(fn, ms)               call fn only after `ms` without new calls
 *   setInput(input, value)         set input.value unless the user is typing in it
 *   listNames(["a", "b", "c"])     "a, b and c"
 */
(() => {
  const $ = (id) => document.getElementById(id);

  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    Object.assign(node, props);
    node.append(...children);
    return node;
  }

  const SVG_NS = "http://www.w3.org/2000/svg";

  function svg(tag, attrs = {}, ...children) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value !== null && value !== undefined && value !== false) node.setAttribute(key, value);
    }
    node.append(...children);
    return node;
  }

  function debounce(fn, ms) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), ms);
    };
  }

  function setInput(input, value) {
    if (document.activeElement !== input) input.value = value;
  }

  function listNames(names) {
    if (names.length <= 1) return names.join("");
    return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  }

  window.AppDom = { $, el, svg, debounce, setInput, listNames };
})();
