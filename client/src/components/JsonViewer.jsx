import { useState } from 'react';
import { ChevronDown, ChevronRight, Copy, Check } from 'lucide-react';

function JsonNode({ data, depth = 0 }) {
  const [expanded, setExpanded] = useState(depth < 2);

  if (data === null) return <span className="text-slate-400">null</span>;
  if (typeof data === 'boolean') return <span className="text-purple-600">{String(data)}</span>;
  if (typeof data === 'number') return <span className="text-blue-600">{data}</span>;
  if (typeof data === 'string') return <span className="text-green-700">"{data}"</span>;

  if (Array.isArray(data)) {
    if (data.length === 0) return <span className="text-slate-500">[]</span>;
    return (
      <span>
        <button
          onClick={() => setExpanded(!expanded)}
          className="inline-flex items-center text-slate-500 hover:text-slate-700"
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <span className="text-xs ml-1">Array({data.length})</span>
        </button>
        {expanded && (
          <div className="ml-4 border-l border-slate-200 pl-3">
            {data.map((item, i) => (
              <div key={i} className="my-0.5">
                <span className="text-slate-400 text-xs mr-2">{i}:</span>
                <JsonNode data={item} depth={depth + 1} />
              </div>
            ))}
          </div>
        )}
      </span>
    );
  }

  if (typeof data === 'object') {
    const keys = Object.keys(data);
    if (keys.length === 0) return <span className="text-slate-500">{'{}'}</span>;
    return (
      <span>
        <button
          onClick={() => setExpanded(!expanded)}
          className="inline-flex items-center text-slate-500 hover:text-slate-700"
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <span className="text-xs ml-1">Object({keys.length})</span>
        </button>
        {expanded && (
          <div className="ml-4 border-l border-slate-200 pl-3">
            {keys.map((key) => (
              <div key={key} className="my-0.5">
                <span className="text-amber-700 font-medium text-xs">{key}: </span>
                <JsonNode data={data[key]} depth={depth + 1} />
              </div>
            ))}
          </div>
        )}
      </span>
    );
  }

  return <span>{String(data)}</span>;
}

export default function JsonViewer({ data }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-slate-50 rounded-xl border border-slate-200 p-4 overflow-auto max-h-[600px]">
      <div className="flex justify-end mb-2">
        <button
          onClick={handleCopy}
          className="inline-flex items-center gap-1 px-2 py-1 text-xs text-slate-500 hover:text-slate-700 border border-slate-200 rounded-md hover:bg-white transition-colors"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy JSON'}
        </button>
      </div>
      <div className="font-mono text-xs leading-relaxed">
        <JsonNode data={data} />
      </div>
    </div>
  );
}
