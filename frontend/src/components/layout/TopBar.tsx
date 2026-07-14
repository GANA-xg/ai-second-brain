"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clsx } from "clsx";

export function TopBar({ title, showBack, rightAction }: { title: string; showBack?: boolean; rightAction?: React.ReactNode }) {
  const router = useRouter();
  return (
    <header className="mb-8">
      <div className="flex items-center gap-3">
        {showBack && <button onClick={()=>router.back()} className="flex items-center justify-center w-9 h-9 rounded-sm text-text-secondary hover:text-text-primary hover:bg-white/5 transition-all duration-150" aria-label="Go back"><svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" /></svg></button>}
        <h1 className="text-[34px] font-semibold text-text-primary tracking-tight flex-1">{title}</h1>
        {rightAction && <div>{rightAction}</div>}
      </div>
    </header>
  );
}

export function PageNav({ tabs }: { tabs: { href: string; label: string }[] }) {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1 mb-8 border-b border-surface-border">
      {tabs.map(tab => {
        const isActive = pathname === tab.href;
        return <Link key={tab.href} href={tab.href}
          className={clsx("px-4 py-[10px] text-[17px] font-medium border-b-2 -mb-px transition-all duration-150",
            isActive ? "border-apple-blue text-apple-blue-on-dark" : "border-transparent text-text-tertiary hover:text-text-secondary")}>{tab.label}</Link>;
      })}
    </nav>
  );
}
