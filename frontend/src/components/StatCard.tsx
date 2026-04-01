import { type LucideIcon } from "lucide-react";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  color?: string;
}

export default function StatCard({ title, value, subtitle, icon: Icon, color = "text-blue-400" }: StatCardProps) {
  return (
    <div className="bg-[#141414] border border-[#262626] rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-zinc-500">{title}</span>
        <Icon className={`w-5 h-5 ${color}`} />
      </div>
      <div className="text-2xl font-bold">{value}</div>
      {subtitle && <div className="text-xs text-zinc-500 mt-1">{subtitle}</div>}
    </div>
  );
}
