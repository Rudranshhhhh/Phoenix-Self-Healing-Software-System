import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  Flame,
  LayoutDashboard,
  Boxes,
  AlertOctagon,
  LineChart,
  Terminal,
  BrainCircuit,
  Settings as SettingsIcon,
} from 'lucide-react';

export const Sidebar: React.FC = () => {
  const menuItems = [
    { name: 'Overview', path: '/', icon: LayoutDashboard },
    { name: 'Containers', path: '/containers', icon: Boxes },
    { name: 'Incidents', path: '/incidents', icon: AlertOctagon },
    { name: 'Metrics', path: '/metrics', icon: LineChart },
    { name: 'Logs', path: '/logs', icon: Terminal },
    { name: 'AI Advisor', path: '/ai-advisor', icon: BrainCircuit },
    { name: 'Settings', path: '/settings', icon: SettingsIcon },
  ];

  return (
    <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col h-full shrink-0">
      {/* Brand Header */}
      <div className="p-6 border-b border-slate-800 flex items-center gap-3">
        <div className="p-2 bg-gradient-to-tr from-orange-500 to-amber-400 rounded-lg shadow-lg animate-pulse-glow">
          <Flame className="w-6 h-6 text-white" />
        </div>
        <div>
          <h1 className="font-extrabold text-xl tracking-wider text-slate-100 uppercase">
            Phoenix
          </h1>
          <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest block">
            Self-Healing OS
          </span>
        </div>
      </div>

      {/* Nav Menu */}
      <nav className="flex-1 px-4 py-6 space-y-1">
        {menuItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3.5 px-4 py-3 rounded-xl font-medium transition-all duration-200 group ${
                  isActive
                    ? 'bg-gradient-to-r from-blue-600/20 to-indigo-600/10 text-blue-400 border border-blue-500/20 shadow-md'
                    : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                }`
              }
            >
              <Icon className="w-5 h-5 transition-transform duration-200 group-hover:scale-110" />
              <span>{item.name}</span>
            </NavLink>
          );
        })}
      </nav>

      {/* Sidebar Footer */}
      <div className="p-6 border-t border-slate-800 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-full">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping" />
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 absolute" />
          <span className="text-xs font-semibold text-emerald-400">Agent Online</span>
        </div>
      </div>
    </aside>
  );
};
export default Sidebar;
