import ReactMarkdown, { type Components, type ExtraProps } from "react-markdown";
import remarkGfm from "remark-gfm";

// react-markdown passe aussi le nœud de l'arbre (`node`) : à ne pas transmettre au DOM
function withoutNode<P extends ExtraProps>(props: P): Omit<P, "node"> {
  const domProps = { ...props };
  delete domProps.node;
  return domProps;
}

// Styles appliqués élément par élément (pas de plugin typography)
const components: Components = {
  p: (props) => <p className="my-2 first:mt-0 last:mb-0" {...withoutNode(props)} />,
  ul: (props) => <ul className="my-2 list-disc space-y-1 pl-5" {...withoutNode(props)} />,
  ol: (props) => <ol className="my-2 list-decimal space-y-1 pl-5" {...withoutNode(props)} />,
  h1: (props) => <p className="mt-3 mb-1 text-base font-semibold" {...withoutNode(props)} />,
  h2: (props) => <p className="mt-3 mb-1 font-semibold" {...withoutNode(props)} />,
  h3: (props) => <p className="mt-3 mb-1 font-semibold" {...withoutNode(props)} />,
  strong: (props) => <strong className="font-semibold" {...withoutNode(props)} />,
  a: (props) => (
    <a className="font-medium text-violet-800 underline underline-offset-2" target="_blank" rel="noopener noreferrer" {...withoutNode(props)} />
  ),
  code: (props) => <code className="rounded bg-zinc-200 px-1 py-0.5 text-[0.9em]" {...withoutNode(props)} />,
  pre: (props) => <pre className="my-2 overflow-x-auto rounded-md bg-zinc-200 p-3" {...withoutNode(props)} />,
  table: (props) => (
    <div className="my-2 overflow-x-auto">
      <table className="border-collapse text-left" {...withoutNode(props)} />
    </div>
  ),
  th: (props) => <th className="border border-zinc-300 px-2 py-1 font-semibold" {...withoutNode(props)} />,
  td: (props) => <td className="border border-zinc-300 px-2 py-1" {...withoutNode(props)} />,
};

/**
 * Markdown des réponses de l'assistant. Le HTML brut éventuellement présent est ignoré
 * (skipHtml) et react-markdown neutralise les URL dangereuses (javascript:...) des liens.
 * Les titres deviennent du texte en gras : ils ne doivent pas casser la hiérarchie de la page.
 */
export function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={components}>
      {children}
    </ReactMarkdown>
  );
}
