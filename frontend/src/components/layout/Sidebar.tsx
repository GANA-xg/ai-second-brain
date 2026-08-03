"use client";
import React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";
import {
  FileText,
  MessageCircle,
  Layers,
  HelpCircle,
  Settings,
  LogOut,
  Brain,
} from "lucide-react";

const navItems = [
  { href: "/dashboard", label: "Documents", icon: FileText },
  { href: "/chat", label: "Chat", icon: MessageCircle },
  { href: "/flashcards", label: "Flashcards", icon: Layers },
  { href: "/quizzes", label: "Quizzes", icon: HelpCircle },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { logout } = useAuth();

  const handleLogout = async () => {
    await logout();
    router.push("/auth/login");
  };

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-[250px] bg-canvas border-r border-border flex flex-col z-40 transition-colors duration-200">
      {/* Logo */}
      <div className="px-6 py-5 flex items-center gap-3">
        <div className="w-8 h-8 rounded-md bg-rausch flex items-center justify-center">
          <Brain className="w-5 h-5 text-white" />
        </div>
        <span className="text-nav-link text-ink">Second Brain</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-2">
        {navItems.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href !== "/dashboard" && pathname.startsWith(item.href));
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-sm text-body-md transition-all duration-150 mb-0.5",
                isActive
                  ? "bg-canvas-soft text-ink font-semibold"
                  : "text-ink-muted hover:bg-canvas-soft hover:text-ink"
              )}
            >
              <Icon className="w-5 h-5 flex-shrink-0" strokeWidth={isActive ? 2.5 : 2} />
              <span>{item.label}</span>
              {isActive && (
                <div className="ml-auto w-1.5 h-1.5 rounded-full bg-rausch" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Logout */}
      <div className="px-3 py-4 border-t border-border">
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-3 py-2.5 rounded-sm text-body-md text-ink-muted hover:bg-canvas-soft hover:text-ink transition-all duration-150 w-full"
        >
          <LogOut className="w-5 h-5" strokeWidth={2} />
          <span>Sign Out</span>
        </button>
      </div>
    </aside>
  );
}
