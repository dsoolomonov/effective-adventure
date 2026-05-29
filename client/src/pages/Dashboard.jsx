import { useQuery } from '@tanstack/react-query';
import { NavLink } from 'react-router-dom';
import {
  BookOpen,
  TrendingUp,
  Ship,
  ClipboardCheck,
  Anchor,
  Download,
  CheckCircle2,
  XCircle,
  Activity,
} from 'lucide-react';
import { api } from '../lib/api';
import LoadingSpinner from '../components/LoadingSpinner';

const endpoints = [
  {
    path: '/catalogue',
    label: 'Catalogue',
    icon: BookOpen,
    description: 'Browse all available curve quotations with filters for vertical, region, and quotation type.',
    color: 'bg-blue-500',
  },
  {
    path: '/curve-data',
    label: 'Curve Data',
    icon: TrendingUp,
    description: 'Retrieve historical and current pricing curve data by curve ID and date range.',
    color: 'bg-emerald-500',
  },
  {
    path: '/flows',
    label: 'Flows',
    icon: Ship,
    description: 'Access commodity trade flow data across global routes and regions.',
    color: 'bg-violet-500',
  },
  {
    path: '/assessments',
    label: 'Assessments',
    icon: ClipboardCheck,
    description: 'View price assessments for various commodity products and markets.',
    color: 'bg-amber-500',
  },
  {
    path: '/freight',
    label: 'Freight',
    icon: Anchor,
    description: 'Query freight rate data for different vessel types and routes.',
    color: 'bg-rose-500',
  },
  {
    path: '/bulk-download',
    label: 'Bulk Download',
    icon: Download,
    description: 'Submit and track bulk data export jobs for large historical datasets.',
    color: 'bg-cyan-500',
  },
];

export default function Dashboard() {
  const { data: authStatus, isLoading } = useQuery({
    queryKey: ['authStatus'],
    queryFn: api.getAuthStatus,
  });

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: api.getHealth,
  });

  if (isLoading) return <LoadingSpinner />;

  return (
    <div>
      {/* Status cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center gap-3">
            {authStatus?.authenticated ? (
              <CheckCircle2 size={24} className="text-green-500" />
            ) : (
              <XCircle size={24} className="text-red-500" />
            )}
            <div>
              <p className="text-sm font-medium text-slate-500">API Authentication</p>
              <p className="text-lg font-bold text-slate-800">
                {authStatus?.authenticated ? 'Connected' : 'Disconnected'}
              </p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center gap-3">
            <Activity size={24} className="text-blue-500" />
            <div>
              <p className="text-sm font-medium text-slate-500">Server Status</p>
              <p className="text-lg font-bold text-slate-800">
                {health?.status === 'ok' ? 'Online' : 'Offline'}
              </p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center gap-3">
            <BookOpen size={24} className="text-violet-500" />
            <div>
              <p className="text-sm font-medium text-slate-500">API Version</p>
              <p className="text-lg font-bold text-slate-800">v2.0</p>
            </div>
          </div>
        </div>
      </div>

      {/* Endpoint cards */}
      <h3 className="text-lg font-semibold text-slate-800 mb-4">API Endpoints</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {endpoints.map((ep) => (
          <NavLink
            key={ep.path}
            to={ep.path}
            className="bg-white rounded-xl border border-slate-200 p-5 hover:shadow-md hover:border-blue-200 transition-all group"
          >
            <div className="flex items-start gap-4">
              <div className={`${ep.color} p-2.5 rounded-lg text-white shrink-0`}>
                <ep.icon size={20} />
              </div>
              <div>
                <h4 className="font-semibold text-slate-800 group-hover:text-blue-600 transition-colors">
                  {ep.label}
                </h4>
                <p className="text-sm text-slate-500 mt-1">{ep.description}</p>
              </div>
            </div>
          </NavLink>
        ))}
      </div>

      {/* API Info */}
      <div className="mt-8 bg-slate-900 text-white rounded-xl p-6">
        <h3 className="text-lg font-semibold mb-3">API Base URL</h3>
        <code className="bg-slate-800 px-4 py-2 rounded-lg text-sm text-blue-300 block">
          https://api.sparta.app/v2
        </code>
        <p className="text-slate-400 text-sm mt-3">
          All requests are proxied through the backend server to keep credentials secure.
          The platform handles token management and automatic refresh.
        </p>
      </div>
    </div>
  );
}
