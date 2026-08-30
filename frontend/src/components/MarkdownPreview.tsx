import { ReactNode } from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Props {
  source: string;
  compact?: boolean;
}

export function MarkdownPreview({ source, compact = false }: Props) {
  const text = source.trim();
  if (!text) {
    return null;
  }
  return (
    <div className={`md-preview${compact ? ' is-compact' : ''}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={httpUrl} components={previewComponents(compact)}>
        {text}
      </ReactMarkdown>
    </div>
  );
}

function httpUrl(url: string): string {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return url;
    }
  } catch {
    /* relative or invalid */
  }
  return '';
}

function heading(level: 1 | 2 | 3) {
  const Tag = level === 1 ? 'h4' : level === 2 ? 'h5' : 'h6';
  return ({ children }: { children?: ReactNode }) => <Tag className={`md-h md-h${level}`}>{children}</Tag>;
}

function previewComponents(compact: boolean): Components {
  return {
    h1: heading(1),
    h2: heading(2),
    h3: heading(3),
    h4: heading(3),
    h5: heading(3),
    h6: heading(3),
    p: ({ children }) => <p className="md-p">{children}</p>,
    blockquote: ({ children }) => <blockquote className="md-quote">{children}</blockquote>,
    ul: ({ children }) => <ul className="md-list">{children}</ul>,
    ol: ({ children }) => <ol className="md-list">{children}</ol>,
    hr: () => <hr className="md-hr" />,
    table: ({ children }) => (
      <div className="md-table-wrap">
        <table className="md-table">{children}</table>
      </div>
    ),
    a: compact
      ? ({ children }) => <span className="md-link-text">{children}</span>
      : ({ href, children }) => (
          <a href={href} target="_blank" rel="noreferrer">
            {children}
          </a>
        ),
    pre: ({ children }) => <pre className="md-code">{children}</pre>,
    code: ({ className, children }) => {
      const lang = /language-([^\s]+)/.exec(className ?? '')?.[1];
      const block = Boolean(className) || String(children).includes('\n');
      if (!block) {
        return <code className="md-inline-code">{children}</code>;
      }
      return (
        <>
          {compact || !lang ? null : <span className="md-code-lang">{lang}</span>}
          <code>{children}</code>
        </>
      );
    },
    input: ({ type, checked }) => (type === 'checkbox' ? <input type="checkbox" checked={Boolean(checked)} disabled readOnly /> : null)
  };
}
