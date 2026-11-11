// Minimal DOM helpers. Text is always assigned with textContent, never innerHTML.

export const $ = id => document.getElementById(id);

/** Create an element: el('td', {className: 'x', text: 'value'}, child1, child2). */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null) continue;
    if (key === 'text') node.textContent = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('on')) node.addEventListener(key.slice(2).toLowerCase(), value);
    else node[key] = value;
  }
  node.append(...children.filter(child => child !== null && child !== undefined));
  return node;
}

export const setText = (id, text) => { $(id).textContent = text; };
export const toggle = (id, className, on) => $(id).classList.toggle(className, Boolean(on));

/** Close a <dialog> when its backdrop (outside the box) is clicked, and wire [data-close] buttons. */
export function enhanceDialogs(root = document) {
  root.querySelectorAll('dialog').forEach(dialog => {
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const box = dialog.getBoundingClientRect();
      const outside = event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom;
      if (outside) dialog.close();
    });
  });
  root.querySelectorAll('[data-close]').forEach(button => {
    button.addEventListener('click', () => button.closest('dialog').close());
  });
}

/** One toast region per page. */
export function createToast(node, timeoutMs = 4500) {
  let timer = null;
  return message => {
    node.textContent = message;
    node.classList.add('show');
    clearTimeout(timer);
    timer = setTimeout(() => node.classList.remove('show'), timeoutMs);
  };
}

/** Trigger a browser download for a Blob. */
export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = el('a', { href: url, download: filename });
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
