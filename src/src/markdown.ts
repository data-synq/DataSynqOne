import { Marked } from "marked";
import DOMPurify from "dompurify";

const marked = new Marked({
  renderer: {
    link({ href, text }) {
      if (href?.startsWith("doc:")) {
        const id = href.slice("doc:".length);
        // Ohne Emoji: das Design kennt keine, und der Akzentstrich am
        // .doc-link markiert die Belegstelle bereits.
        return `<button type="button" class="doc-link" data-doc-id="${id}">${text}</button>`;
      }
      return `<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`;
    },
  },
});

export function renderMarkdown(content: string): string {
  const html = marked.parse(content, { async: false }) as string;
  return DOMPurify.sanitize(html, { ADD_ATTR: ["data-doc-id", "target"] });
}
