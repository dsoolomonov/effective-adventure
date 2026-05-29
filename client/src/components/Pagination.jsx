import { ChevronLeft, ChevronRight } from 'lucide-react';

export default function Pagination({ page, onPageChange, hasNext, hasPrev }) {
  return (
    <div className="flex items-center justify-between mt-4">
      <span className="text-sm text-slate-500">Page {page}</span>
      <div className="flex gap-2">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={!hasPrev}
          className="inline-flex items-center gap-1 px-3 py-1.5 text-sm border border-slate-200 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors"
        >
          <ChevronLeft size={16} />
          Previous
        </button>
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={!hasNext}
          className="inline-flex items-center gap-1 px-3 py-1.5 text-sm border border-slate-200 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors"
        >
          Next
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}
