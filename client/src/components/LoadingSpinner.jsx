import { Loader2 } from 'lucide-react';

export default function LoadingSpinner({ message = 'Loading...' }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-slate-400">
      <Loader2 size={32} className="animate-spin mb-3" />
      <span className="text-sm">{message}</span>
    </div>
  );
}
