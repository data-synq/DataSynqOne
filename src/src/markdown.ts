import { Marked } from "marked";
import DOMPurify from "dompurify";

// Ohne Emoji: das Design kennt keine. Statt eines Akzentstrichs markiert ein
// schlankes Link-Icon nach dem Text die Belegstelle — dezenter als der
// frühere Button-Look, aber immer noch klar als eigenes Ziel erkennbar.
const DOC_LINK_ICON =
  '<svg class="doc-link__icon" viewBox="0 0 16 16" aria-hidden="true">' +
  '<path d="M6.5 9.5 9.5 6.5M7 4H4.5A1.5 1.5 0 0 0 3 5.5v6A1.5 1.5 0 0 0 4.5 13h6a1.5 1.5 0 0 0 1.5-1.5V9M9 3h4v4" ' +
  'fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>' +
  "</svg>";

const marked = new Marked({
  renderer: {
    link({ href, text }) {
      if (href?.startsWith("doc:")) {
        const id = href.slice("doc:".length);
        return `<button type="button" class="doc-link" data-doc-id="${id}">${text}${DOC_LINK_ICON}</button>`;
      }
      if (href?.startsWith("case:")) {
        const trackingId = href.slice("case:".length);
        return `<button type="button" class="doc-link" data-case-id="${trackingId}">${text}${DOC_LINK_ICON}</button>`;
      }
      return `<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`;
    },
  },
});

export function renderMarkdown(content: string): string {
  const html = marked.parse(content, { async: false }) as string;
  return DOMPurify.sanitize(html, { ADD_ATTR: ["data-doc-id", "data-case-id", "target"] });
}
