/*
 * Small DOM helpers for game pages. Load before game.js.
 *
 *   const { $, el, debounce, setInput, listNames } = AppDom;
 *
 *   $(id)                          document.getElementById(id)
 *   el(tag, props, ...children)    createElement + Object.assign(props) + append(children).
 *                                  Strings become text nodes, so player names are safe.
 *                                  e.g. el("li", { className: "me" }, name, el("b", {}, "Host"))
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

  window.AppDom = { $, el, debounce, setInput, listNames };
})();
