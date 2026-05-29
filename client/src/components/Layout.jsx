import { useState } from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  BookOpen,
  TrendingUp,
  Ship,
  ClipboardCheck,
  Anchor,
  Download,
  Menu,
  X,
  RefreshCw,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import { api } from '../lib/api';

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/catalogue', label: 'Catalogue', icon: BookOpen },
  { path: '/curve-data', label: 'Curve Data', icon: TrendingUp },
  { path: '/flows', label: 'Flows', icon: Ship },
  { path: '/assessments', label: 'Assessments', icon: ClipboardCheck },
  { path: '/freight', label: 'Freight', icon: Anchor },
  { path: '/bulk-download', label: 'Bulk Download', icon: Download },
];

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const { data: authStatus, refetch: refreshAuth, isLoading: authLoading } = useQuery({
    queryKey: ['authStatus'],
    queryFn: api.getAuthStatus,
    refetchInterval: 300000,
  });

  return (
    <div className="min-h-screen flex bg-slate-50">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 text-white transform transition-transform duration-200 lg:translate-x-0 lg:static lg:z-auto ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between h-16 px-6 border-b border-slate-700">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center font-bold text-sm">
              S
            </div>
            <span className="font-semibold text-lg">Sparta Platform</span>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden text-slate-400 hover:text-white"
          >
            <X size={20} />
          </button>
        </div>

        <nav className="p-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`
              }
            >
              <item.icon size={18} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Auth status */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-slate-700">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              {authStatus?.authenticated ? (
                <CheckCircle2 size={14} className="text-green-400" />
              ) : (
                <XCircle size={14} className="text-red-400" />
              )}
              <span className="text-slate-400 truncate max-w-[140px]">
                {authStatus?.email || 'Not connected'}
              </span>
            </div>
            <button
              onClick={() => refreshAuth()}
              disabled={authLoading}
              className="text-slate-400 hover:text-white transition-colors"
              title="Refresh authentication"
            >
              <RefreshCw size={14} className={authLoading ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-16 bg-white border-b border-slate-200 flex items-center px-6 gap-4 shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden text-slate-600 hover:text-slate-900"
          >
            <Menu size={24} />
          </button>
          <h1 className="text-lg font-semibold text-slate-800">
            Sparta Commodities API Platform
          </h1>
        </header>

        {/* Page content */}
        <main className="flex-1 p-6 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
